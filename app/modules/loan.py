"""
Module 4 - Loan Management (Application, Bank Review, Disbursal, EMI Repayment)
SRS reference: Sections 4.4, 4.5, 4.6

Progressive lending tiers follow the restructured PM SVANidhi scheme (Aug 2025):
    Tier 1: up to Rs 15,000 repaid in 12 months
    Tier 2: up to Rs 25,000 repaid in 18 months  (after Tier 1 is fully repaid)
    Tier 3: up to Rs 50,000 repaid in 36 months  (after Tier 2 is fully repaid)

Loan life cycle (see the State Transition Diagram in the SRS):
    PENDING -> APPROVED -> DISBURSED -> CLOSED
    PENDING -> REJECTED | WITHDRAWN
    DISBURSED -> DEFAULTED (an EMI unpaid for more than 90 days) -> CLOSED (all dues cleared)
"""
import calendar
from datetime import date, timedelta

from database import ValidationError
from modules.auth import get_user
from modules.credit_score import MIN_SCORE_FOR_LOAN, get_trust_score

TIERS = {1: (15000, 12), 2: (25000, 18), 3: (50000, 36)}   # tier -> (max amount, tenure in months)
ANNUAL_INTEREST_RATE = 12.0                                 # % p.a., assumed lender rate (SRS 2.7)
DEFAULT_AFTER_DAYS = 90
ACTIVE_STATUSES = ("PENDING", "APPROVED", "DISBURSED", "DEFAULTED")


# ---------------------------------------------------------------- helpers
def add_months(start, months):
    """Same day-of-month `months` later, clamped to the month's last day (31 Jan + 1 -> 28/29 Feb)."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_emi_schedule(principal, annual_rate, months, start_date):
    """Reducing-balance EMI schedule: EMI = P*r*(1+r)^n / ((1+r)^n - 1)."""
    if principal <= 0 or months <= 0:
        raise ValidationError("Principal and tenure must be positive")
    r = annual_rate / 12 / 100
    emi = principal / months if r == 0 else principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    emi = round(emi, 2)

    schedule, balance = [], principal
    for n in range(1, months + 1):
        interest = round(balance * r, 2)
        principal_part = round(emi - interest, 2)
        amount = emi
        if n == months:                      # last EMI clears any rounding difference
            principal_part = round(balance, 2)
            amount = round(principal_part + interest, 2)
        balance = round(balance - principal_part, 2)
        schedule.append({
            "installment_no": n,
            "due_date": add_months(start_date, n).isoformat(),
            "emi_amount": amount,
            "principal_part": principal_part,
            "interest_part": interest,
        })
    return schedule


def eligible_tier(conn, vendor_id):
    """Tier = number of fully repaid (CLOSED) loans + 1, capped at 3 (FR-LN-3)."""
    closed = conn.execute(
        "SELECT COUNT(*) FROM loans WHERE vendor_id = ? AND status = 'CLOSED'", (vendor_id,)
    ).fetchone()[0]
    return min(closed + 1, 3)


def get_loan(conn, loan_id):
    loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
    if loan is None:
        raise ValidationError("Loan not found")
    return loan


# ---------------------------------------------------------------- vendor side
def apply_loan(conn, vendor_id, amount, today=None):
    """Vendor submits a loan application; returns the new loan_id (FR-LN-1 to FR-LN-6)."""
    today = today or date.today()
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError("Loan amount must be a number")

    active = conn.execute(
        f"SELECT 1 FROM loans WHERE vendor_id = ? AND status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
        (vendor_id, *ACTIVE_STATUSES),
    ).fetchone()
    if active:
        raise ValidationError("You already have an active loan")

    trust = get_trust_score(conn, vendor_id, today)
    if trust["score"] < MIN_SCORE_FOR_LOAN:
        raise ValidationError(f"Trust score {trust['score']} is below {MIN_SCORE_FOR_LOAN}. Not eligible")

    tier = eligible_tier(conn, vendor_id)
    limit, tenure = TIERS[tier]
    if amount <= 0:
        raise ValidationError("Loan amount must be greater than 0")
    if amount > limit:
        raise ValidationError(f"Amount exceeds Tier {tier} limit of Rs {limit:,}")

    cur = conn.execute(
        """INSERT INTO loans (vendor_id, tier, amount, tenure_months, interest_rate, trust_score, applied_on)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (vendor_id, tier, amount, tenure, ANNUAL_INTEREST_RATE, trust["score"], today.isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def withdraw_loan(conn, loan_id, vendor_id):
    loan = get_loan(conn, loan_id)
    if loan["vendor_id"] != vendor_id or loan["status"] != "PENDING":
        raise ValidationError("Only your own PENDING application can be withdrawn")
    conn.execute("UPDATE loans SET status = 'WITHDRAWN' WHERE loan_id = ?", (loan_id,))
    conn.commit()


def pay_emi(conn, loan_id, installment_no, amount, paid_date=None):
    """Record payment of one EMI (FR-EMI-1 to FR-EMI-6). Returns {'on_time', 'loan_closed'}."""
    paid_date = paid_date or date.today()
    loan = get_loan(conn, loan_id)
    if loan["status"] not in ("DISBURSED", "DEFAULTED"):
        raise ValidationError("Loan is not active for repayment")

    emi = conn.execute(
        "SELECT * FROM emi_installments WHERE loan_id = ? AND installment_no = ?", (loan_id, installment_no)
    ).fetchone()
    if emi is None:
        raise ValidationError("Installment not found")
    if emi["status"] == "PAID":
        raise ValidationError("Installment already paid")

    earlier = conn.execute(
        """SELECT MIN(installment_no) FROM emi_installments
           WHERE loan_id = ? AND status = 'DUE' AND installment_no < ?""",
        (loan_id, installment_no),
    ).fetchone()[0]
    if earlier:
        raise ValidationError(f"Pay earlier installment #{earlier} first")

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError("Payment amount must be a number")
    if amount + 0.001 < emi["emi_amount"]:
        raise ValidationError(f"Amount is less than EMI due of Rs {emi['emi_amount']:.2f}")

    on_time = paid_date.isoformat() <= emi["due_date"]
    conn.execute(
        "UPDATE emi_installments SET status = 'PAID', paid_on = ?, paid_on_time = ? WHERE emi_id = ?",
        (paid_date.isoformat(), int(on_time), emi["emi_id"]),
    )
    remaining = conn.execute(
        "SELECT COUNT(*) FROM emi_installments WHERE loan_id = ? AND status = 'DUE'", (loan_id,)
    ).fetchone()[0]
    if remaining == 0:
        conn.execute("UPDATE loans SET status = 'CLOSED' WHERE loan_id = ?", (loan_id,))
    conn.commit()
    return {"on_time": on_time, "loan_closed": remaining == 0}


# ---------------------------------------------------------------- bank officer side
def _require_officer(conn, officer_id):
    officer = get_user(conn, officer_id)
    if officer is None or officer["role"] != "BANK_OFFICER":
        raise ValidationError("Only bank officers can perform this action")


def review_loan(conn, loan_id, officer_id, decision, remarks=""):
    """Approve or reject a PENDING application (FR-BNK-1 to FR-BNK-4)."""
    _require_officer(conn, officer_id)
    loan = get_loan(conn, loan_id)
    if loan["status"] != "PENDING":
        raise ValidationError("Only PENDING applications can be reviewed")
    if decision not in ("APPROVE", "REJECT"):
        raise ValidationError("Decision must be APPROVE or REJECT")
    if decision == "REJECT" and not (remarks or "").strip():
        raise ValidationError("Remarks are required when rejecting")

    status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    conn.execute(
        "UPDATE loans SET status = ?, officer_id = ?, remarks = ? WHERE loan_id = ?",
        (status, officer_id, (remarks or "").strip(), loan_id),
    )
    conn.commit()
    return status


def disburse_loan(conn, loan_id, officer_id, today=None):
    """Disburse an APPROVED loan and create its EMI schedule (FR-BNK-5, FR-BNK-6)."""
    today = today or date.today()
    _require_officer(conn, officer_id)
    loan = get_loan(conn, loan_id)
    if loan["status"] != "APPROVED":
        raise ValidationError("Only APPROVED loans can be disbursed")

    schedule = generate_emi_schedule(loan["amount"], loan["interest_rate"], loan["tenure_months"], today)
    conn.executemany(
        """INSERT INTO emi_installments (loan_id, installment_no, due_date, emi_amount, principal_part, interest_part)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(loan_id, s["installment_no"], s["due_date"], s["emi_amount"], s["principal_part"], s["interest_part"])
         for s in schedule],
    )
    conn.execute(
        "UPDATE loans SET status = 'DISBURSED', disbursed_on = ? WHERE loan_id = ?", (today.isoformat(), loan_id)
    )
    conn.commit()
    return schedule


def mark_defaults(conn, today=None):
    """FR-BNK-7: a DISBURSED loan with an EMI unpaid for more than 90 days becomes DEFAULTED."""
    cutoff = ((today or date.today()) - timedelta(days=DEFAULT_AFTER_DAYS)).isoformat()
    cur = conn.execute(
        """UPDATE loans SET status = 'DEFAULTED'
           WHERE status = 'DISBURSED' AND loan_id IN (
               SELECT loan_id FROM emi_installments WHERE status = 'DUE' AND due_date < ?)""",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- queries
def get_loans(conn, vendor_id):
    return conn.execute("SELECT * FROM loans WHERE vendor_id = ? ORDER BY loan_id DESC", (vendor_id,)).fetchall()


def get_installments(conn, loan_id):
    return conn.execute(
        "SELECT * FROM emi_installments WHERE loan_id = ? ORDER BY installment_no", (loan_id,)
    ).fetchall()


def all_loans_for_officer(conn):
    return conn.execute(
        """SELECT l.*, u.name AS vendor_name, u.phone AS vendor_phone
           FROM loans l JOIN users u ON u.user_id = l.vendor_id
           ORDER BY CASE l.status WHEN 'PENDING' THEN 0 WHEN 'APPROVED' THEN 1 ELSE 2 END, l.loan_id DESC"""
    ).fetchall()
