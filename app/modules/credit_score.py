"""
Module 3 - Alternative Credit (Trust) Scoring Engine
SRS reference: Section 4.3 (FR-TS-1 to FR-TS-6)

Street vendors usually have no CIBIL history, so the platform builds a
"Trust Score" (0-100) from data it can actually observe:

    Component              Max   Formula
    Sales consistency       40   active_days / window_days * 40
    Repayment history       40   on_time_emis / emis_due * 40   (no history -> neutral 20)
    Peer vouching           10   min(vouches, 3) / 3 * 10
    Vending tenure          10   min(years_vending, 5) / 5 * 10
"""
from datetime import date

from database import ValidationError
from modules.vendor import get_profile, sales_summary

MIN_SCORE_FOR_LOAN = 40
NEUTRAL_REPAYMENT_POINTS = 20
COMPONENT_MAX = {"Sales consistency": 40, "Repayment history": 40, "Peer vouching": 10, "Vending tenure": 10}


def compute_trust_score(active_days, window_days, on_time_emis, emis_due, vouches, years_vending):
    """Pure calculation - returns a dict with the total score, risk band and each component."""
    values = (active_days, window_days, on_time_emis, emis_due, vouches, years_vending)
    if any(v is None or v < 0 for v in values):
        raise ValidationError("Score inputs cannot be negative")
    if window_days == 0 or active_days > window_days:
        raise ValidationError("Active days cannot exceed the observation window")
    if on_time_emis > emis_due:
        raise ValidationError("On-time EMIs cannot exceed EMIs due")

    consistency = active_days / window_days * 40
    repayment = on_time_emis / emis_due * 40 if emis_due else NEUTRAL_REPAYMENT_POINTS
    peer = min(vouches, 3) / 3 * 10
    tenure = min(years_vending, 5) / 5 * 10

    score = round(consistency + repayment + peer + tenure)
    return {
        "score": score,
        "band": risk_band(score),
        "eligible": score >= MIN_SCORE_FOR_LOAN,
        "components": {
            "Sales consistency": round(consistency, 1),
            "Repayment history": round(repayment, 1),
            "Peer vouching": round(peer, 1),
            "Vending tenure": round(tenure, 1),
        },
    }


def risk_band(score):
    if score >= 70:
        return "LOW RISK"
    if score >= MIN_SCORE_FOR_LOAN:
        return "MEDIUM RISK"
    return "HIGH RISK"


def repayment_counts(conn, vendor_id, today=None):
    """EMIs that were due by today: paid ones plus overdue unpaid ones count as 'due'."""
    today = (today or date.today()).isoformat()
    row = conn.execute(
        """SELECT
               SUM(CASE WHEN e.status = 'PAID' AND e.paid_on_time = 1 THEN 1 ELSE 0 END) AS on_time,
               SUM(CASE WHEN e.status = 'PAID' OR e.due_date < ? THEN 1 ELSE 0 END)      AS due
           FROM emi_installments e JOIN loans l ON l.loan_id = e.loan_id
           WHERE l.vendor_id = ?""",
        (today, vendor_id),
    ).fetchone()
    return (row["on_time"] or 0), (row["due"] or 0)


def vouch_count(conn, vendor_id):
    return conn.execute("SELECT COUNT(*) FROM vouches WHERE vendor_id = ?", (vendor_id,)).fetchone()[0]


def get_trust_score(conn, vendor_id, today=None):
    """Collect the vendor's data from the database and score it (FR-TS-1)."""
    profile = get_profile(conn, vendor_id)
    if profile is None:
        raise ValidationError("Complete your vendor profile first")
    summary = sales_summary(conn, vendor_id, days=30, today=today)
    on_time, due = repayment_counts(conn, vendor_id, today)
    return compute_trust_score(
        active_days=summary["active_days"],
        window_days=summary["window_days"],
        on_time_emis=on_time,
        emis_due=due,
        vouches=vouch_count(conn, vendor_id),
        years_vending=profile["years_vending"],
    )
