"""
test_cases.py - The documented test cases for VendorSetu (SRS Appendix E and docs/Test_Cases_VendorSetu.docx).

Level "System": the case drives the running web application exactly as a user would (fill a form, click a
button) through Flask's test client, and the Actual Output is the message / value shown on the page.
Anyone can repeat these by hand in the demo app.
Level "Unit": the case calls a module function directly (used for the Trust Score formula).

Every Expected Output was written from the SRS before running the code. `run_test_cases.py` executes each
case on a fresh, empty database and records the Actual Output; `test_vendorsetu.py` runs the same cases
under pytest.
"""
import calendar
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, List

# VENDORSETU_APP_DIR lets run_test_cases.py --before-fix run the same cases against the first version of the
# code (git commit 0ce1911), to show which cases failed before the defects were fixed.
APP_DIR = os.environ.get("VENDORSETU_APP_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, APP_DIR)

import app as app_module  # noqa: E402
from database import ValidationError, get_connection, init_db  # noqa: E402
from modules import auth, credit_score, loan, vendor  # noqa: E402

TODAY = date.today()
_real_get_connection = get_connection


def dmy(d):
    return d.strftime("%d-%m-%Y")


def next_month(d):
    """Same day next month (independent of the code under test)."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


@dataclass
class Case:
    id: str
    module: str
    level: str
    scenario: str
    pre: str
    steps: List[str]
    input: str
    expected: str
    run: Callable
    reqs: List[str] = field(default_factory=list)
    technique: str = "Positive"       # Positive / Negative (EP) / BVA / Combination / Security
    defect: str = ""                  # defect this case found in the first version (see DEFECTS)


MODULES = {
    "AUTH": {
        "name": "User Registration & Login",
        "subsystem": "Authentication (Module 1 - modules/auth.py)",
        "description": "Verify account creation rules (valid / invalid classes, boundaries, several errors at once), "
                       "login, lock-out after 5 wrong passwords and protection of pages that need a login.",
        "pre": ["Application is running with an empty database.",
                "User is on the Register or Log in page of VendorSetu."],
        "post": ["A valid registration stores exactly one user with a hashed password; rejected input stores nothing.",
                 "After 5 consecutive wrong passwords the account stays locked even for the correct password."],
    },
    "SALE": {
        "name": "Vendor Profile & Daily Sales Logging",
        "subsystem": "Vendor Profile & Sales (Module 2 - modules/vendor.py)",
        "description": "Verify the business profile rules and that a vendor can log one valid sales entry per day, "
                       "while invalid amounts, dates and payment modes are rejected without saving anything.",
        "pre": ["Vendor 'Ramesh Kumar' (9876543210 / ramesh123) is registered and logged in.",
                "His business profile is saved (unless the case says otherwise)."],
        "post": ["A valid entry is saved and counted in the 30-day summary; a rejected entry changes nothing.",
                 "A rejected profile is not saved."],
    },
    "TS": {
        "name": "Trust Score Calculation",
        "subsystem": "Alt-Credit Scoring Engine (Module 3 - modules/credit_score.py)",
        "description": "Verify the 0-100 Trust Score formula, the risk band and the loan-eligibility cut-off of 40.",
        "pre": ["Formula: Sales (active days / 30 x 40) + Repayment (on-time / due x 40, or 20 if no EMI is due yet) "
                "+ Peer vouching (min(vouches, 3) / 3 x 10) + Tenure (min(years, 5) / 5 x 10), rounded.",
                "Bands: 70-100 LOW RISK, 40-69 MEDIUM RISK, 0-39 HIGH RISK."],
        "post": ["Score, band and eligibility are returned / displayed; no stored data is modified."],
    },
    "LOAN": {
        "name": "Loan Application & Bank Review",
        "subsystem": "Loan Management (Module 4 - modules/loan.py)",
        "description": "Verify progressive-tier loan application rules and the bank officer's approve / reject / "
                       "disburse actions.",
        "pre": ["Vendor 'Ramesh Kumar' (9876543210 / ramesh123): profile with 5 years of vending and a sale logged on "
                "each of the last 30 days, so his Trust Score is 40 + 20 + 0 + 10 = 70.",
                "Bank officer 'Anil Sharma' (9123456780 / bank123) is registered."],
        "post": ["An accepted application is stored as PENDING; approval and disbursal change its status and create "
                 "the EMI schedule; rejected requests change nothing.",
                 "Only the owning vendor and bank officers can open a loan's page."],
    },
    "EMI": {
        "name": "EMI Schedule & Repayment",
        "subsystem": "Loan Management - Repayment (Module 4 - modules/loan.py)",
        "description": "Verify the EMI schedule, the repayment rules, loan closure (next tier unlocked) and the "
                       "default check.",
        "pre": ["Ramesh's Tier-1 loan #1 of Rs 15,000 at 12% p.a. for 12 months has been approved and disbursed "
                "today by the bank officer (unless the case says otherwise).",
                "Hand calculation: r = 12% / 12 = 0.01, EMI = 15000 x 0.01 x 1.01^12 / (1.01^12 - 1) = Rs 1,332.73."],
        "post": ["Paid installments are marked PAID (on time / late); when all 12 are paid the loan is CLOSED and "
                 "Tier 2 (Rs 25,000) is unlocked."],
    },
}


# ====================================================================== system-test harness
class App:
    """A fresh copy of the web app backed by its own empty database file."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="vendorsetu_test_")
        self.path = os.path.join(self.dir, "test.db")
        self._activate()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.conn = _real_get_connection(self.path)
        init_db(self.conn)
        return self

    def __exit__(self, *exc):
        self.conn.close()
        app_module.get_connection = _real_get_connection
        shutil.rmtree(self.dir, ignore_errors=True)

    def _activate(self):
        """Point the web app at this test's database (several App objects may be open at once)."""
        app_module.get_connection = lambda: _real_get_connection(self.path)

    def _request(self, method, url, data=None):
        self._activate()
        try:
            resp = getattr(self.client, method)(url, data=data, follow_redirects=True)
        except Exception as e:          # the app crashed: a real user would see "Internal Server Error"
            self.page = ""
            return f"HTTP 500 Internal Server Error ({type(e).__name__}: {e})"
        self.page = resp.get_data(as_text=True)
        if resp.status_code >= 500:
            return f"HTTP {resp.status_code} Internal Server Error"
        return self.message()

    def post(self, url, **data):
        return self._request("post", url, data)

    def get(self, url):
        return self._request("get", url)

    def message(self):
        """The flash message(s) shown at the top of the current page."""
        return " | ".join(re.findall(r'class="flash \w+">([^<]+)<', self.page))

    def login(self, phone, password):
        self._request("get", "/logout")                       # consume the "Logged out." message
        return self.post("/login", phone=phone, password=password)

    # ---- preconditions (created directly in the database, as described in each case's Pre-condition)
    def vendor(self, name="Ramesh Kumar", phone="9876543210", password="ramesh123", years=5, sale_days=30,
               profile=True):
        uid = auth.register_user(self.conn, name, phone, password, "VENDOR")
        if profile:
            vendor.save_profile(self.conn, uid, "Fruits & vegetables", "Sector 14 Market, Gurugram", years, "")
        for i in range(sale_days):
            vendor.log_daily_sale(self.conn, uid, (TODAY - timedelta(days=i)).isoformat(), 1500, "UPI")
        return uid

    def officer(self):
        return auth.register_user(self.conn, "Anil Sharma", "9123456780", "bank123", "BANK_OFFICER")

    def disbursed_loan(self, on=TODAY):
        vid, oid = self.vendor(), self.officer()
        lid = loan.apply_loan(self.conn, vid, 15000)
        loan.review_loan(self.conn, lid, oid, "APPROVE", "Regular sales record")
        loan.disburse_loan(self.conn, lid, oid, on)
        return vid, lid


def find(pattern, page, default="(not shown)"):
    m = re.search(pattern, page)
    return m.group(1) if m else default


REGISTER = dict(name="Ramesh Kumar", phone="9876543210", role="VENDOR", password="ramesh123",
                confirm_password="ramesh123")


# ====================================================================== Module 1 - Authentication
def count(a, table):
    return a.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def check_unchanged(a, table, before, msg, success_text):
    """Post-condition: a rejected request must not add a row; an accepted one adds exactly one."""
    expected_rows = before + (1 if success_text in msg else 0)
    return "" if count(a, table) == expected_rows else f" [POST-CONDITION FAILED: {table} rows = {count(a, table)}]"


def auth_register_valid():
    with App() as a:
        msg = a.post("/register", **REGISTER)
        out = msg + (" -> Log in page is shown" if "<h1>Log in</h1>" in a.page else "")
        rows = a.conn.execute("SELECT password_hash FROM users").fetchall()
        if len(rows) != 1 or rows[0][0] == REGISTER["password"]:       # one user, password not stored as plain text
            out += " [POST-CONDITION FAILED: user not stored with a hashed password]"
        return out


def auth_register(_existing=False, **override):
    def run():
        with App() as a:
            if _existing:
                a.post("/register", **REGISTER)
            before = count(a, "users")
            msg = a.post("/register", **{**REGISTER, **override})
            return msg + check_unchanged(a, "users", before, msg, "Registration successful")
    return run


def auth_login_valid():
    with App() as a:
        a.vendor()
        msg = a.login("9876543210", "ramesh123")
        return msg + (" -> Vendor dashboard is shown" if "Namaste, Ramesh" in a.page else "")


def auth_lockout():
    with App() as a:
        a.vendor()
        first4 = {a.login("9876543210", "wrong1") for _ in range(4)}
        fifth = a.login("9876543210", "wrong1")
        sixth = a.login("9876543210", "ramesh123")
        return f"Attempts 1-4: {' / '.join(first4)} | Attempt 5: {fifth} | Attempt 6 (correct password): {sixth}"


# ====================================================================== Module 2 - Sales
def sale(sale_date, amount, mode="UPI", profile=True, existing=None):
    def run():
        with App() as a:
            vid = a.vendor(sale_days=0, profile=profile)
            if existing:
                vendor.log_daily_sale(a.conn, vid, existing.isoformat(), 1500, "UPI")
            a.login("9876543210", "ramesh123")
            before = count(a, "sales")
            day = sale_date if isinstance(sale_date, str) else sale_date.isoformat()
            msg = a.post("/vendor/sales", sale_date=day, amount=amount, payment_mode=mode)
            return msg + check_unchanged(a, "sales", before, msg, "Sale logged")
    return run


def sale_summary():
    with App() as a:
        a.vendor(sale_days=0)
        a.login("9876543210", "ramesh123")
        for days_ago, amount in ((2, 1000), (1, 2000), (0, 3000)):
            a.post("/vendor/sales", sale_date=(TODAY - timedelta(days=days_ago)).isoformat(), amount=amount,
                   payment_mode="CASH")
        a.get("/dashboard")
        total = find(r'<div class="value">₹([\d,]+)</div><div class="label">Sales, last 30 days', a.page)
        days = find(r'<div class="value">(\d+)<span class="muted"[^>]*>/30</span></div><div class="label">Active', a.page)
        avg = find(r"avg ₹([\d,]+) per active day", a.page)
        return f"30-day sales Rs {total}; active days {days}/30; average Rs {avg} per active day"


# ====================================================================== Module 3 - Trust score
def ts_unit(**kw):
    def run():
        try:
            r = credit_score.compute_trust_score(**kw)
        except ValidationError as e:
            return str(e)
        parts = " + ".join(f"{v:g}" for v in r["components"].values())
        return f"{parts} = {r['score']} -> {r['band']}, {'eligible' if r['eligible'] else 'not eligible'}"
    return run


def ts_dashboard():
    with App() as a:
        a.vendor(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)
        a.login("9812345670", "sunita123")
        score = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        band = find(r'<span class="score-badge [\w-]+">([A-Z ]+)</span>', a.page)
        return f"Dashboard shows Trust Score {score}/100, {band}"


# ====================================================================== Module 4 - Loans
def loan_apply(amount, low_score=False, twice=False):
    def run():
        with App() as a:
            if low_score:
                a.vendor(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)
                a.login("9812345670", "sunita123")
            else:
                a.vendor()
                a.login("9876543210", "ramesh123")
            if twice:
                a.post("/vendor/loan/apply", amount=15000)
            before = count(a, "loans")
            msg = a.post("/vendor/loan/apply", amount=amount)
            return msg + check_unchanged(a, "loans", before, msg, "submitted")
    return run


def loan_reject_without_remarks():
    with App() as a:
        vid = a.vendor()
        a.officer()
        loan.apply_loan(a.conn, vid, 15000)
        a.login("9123456780", "bank123")
        return a.post("/officer/loan/1/review", decision="REJECT", remarks="")


def loan_vendor_opens_officer_page():
    with App() as a:
        a.vendor()
        a.login("9876543210", "ramesh123")
        return a.get("/officer")


def loan_approve_disburse():
    with App() as a:
        vid = a.vendor()
        a.officer()
        loan.apply_loan(a.conn, vid, 15000)
        a.login("9123456780", "bank123")
        first = a.post("/officer/loan/1/review", decision="APPROVE", remarks="")
        second = a.post("/officer/loan/1/disburse")
        return f"{first} | {second}"


# ====================================================================== Module 5 - EMI
def emi_schedule():
    with App() as a:
        a.disbursed_loan()
        a.login("9876543210", "ramesh123")
        a.get("/loan/1")
        rows = re.findall(r"<td><strong>(\d+)</strong></td>\s*<td>(\d{4}-\d{2}-\d{2})</td>\s*"
                          r'<td class="num">₹([\d,.]+)</td>', a.page)
        if not rows:
            return "(schedule not shown)"
        return f"{len(rows)} installments; EMI #1 Rs {rows[0][2]} due {rows[0][1]}; EMI #12 due {rows[-1][1]}"


def emi_pay(steps):
    """steps: list of (installment_no, amount); returns the message after the last payment."""
    def run():
        with App() as a:
            a.disbursed_loan()
            a.login("9876543210", "ramesh123")
            msg = ""
            for n, amount in steps:
                msg = a.post(f"/vendor/loan/1/pay/{n}", amount=amount)
            return msg
    return run


def emi_full_repayment():
    with App() as a:
        _, lid = a.disbursed_loan()
        a.login("9876543210", "ramesh123")
        msg = ""
        for inst in loan.get_installments(a.conn, lid):
            msg = a.post(f"/vendor/loan/1/pay/{inst['installment_no']}", amount=inst["emi_amount"])
        a.get("/dashboard")
        limit = find(r'<div class="value">₹([\d,]+)</div><div class="label">Eligible limit · Tier (\d)', a.page)
        tier = find(r'<div class="label">Eligible limit · Tier (\d)', a.page)
        return f"{msg} -> Dashboard shows eligible limit Rs {limit} (Tier {tier})"


def emi_default_check():
    with App() as a:
        a.disbursed_loan(on=TODAY - timedelta(days=150))
        a.login("9123456780", "bank123")
        return a.post("/officer/mark-defaults")


# ====================================================================== helpers for the extended cases
def each(*labelled_runs):
    """Boundary pairs / several inputs in one case: 'label: actual | label: actual'."""
    def run():
        return " | ".join(f"{label}: {fn()}" for label, fn in labelled_runs)
    return run


def auth_login_case(phone, password):
    def run():
        with App() as a:
            a.vendor()
            msg = a.login(phone, password)
            return msg + (" [POST-CONDITION FAILED: user is logged in]" if "Namaste," in a.page else "")
    return run


def auth_counter_reset():
    with App() as a:
        a.vendor()
        for _ in range(4):
            a.login("9876543210", "wrong1")
        first = a.login("9876543210", "ramesh123")
        for _ in range(4):
            last_wrong = a.login("9876543210", "wrong1")
        again = a.login("9876543210", "ramesh123")
        return f"4 wrong + correct: {first} | 4 more wrong: {last_wrong} | Correct again: {again}"


def auth_dashboard_without_login():
    with App() as a:
        msg = a.get("/dashboard")
        return msg + (" -> Log in page is shown" if "<h1>Log in</h1>" in a.page else "")


def profile_case(**form):
    def run():
        with App() as a:
            a.vendor(profile=False, sale_days=0)
            a.login("9876543210", "ramesh123")
            data = {"business_type": "Fruits & vegetables", "vending_zone": "Sector 14 Market, Gurugram",
                    "years_vending": "5", "upi_id": "", **form}
            before = count(a, "vendor_profiles")
            msg = a.post("/vendor/profile", **data)
            return msg + check_unchanged(a, "vendor_profiles", before, msg, "Profile saved")
    return run


def ts_after_sale():
    with App() as a:
        a.vendor(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)
        a.login("9812345670", "sunita123")
        before = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        a.post("/vendor/sales", sale_date=TODAY.isoformat(), amount=800, payment_mode="CASH")
        after = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        band = find(r'<span class="score-badge [\w-]+">([A-Z ]+)</span>', a.page)
        return f"Before: {before}/100 | After logging 1 sale: {after}/100, {band}"


def loan_no_profile():
    with App() as a:
        a.vendor(profile=False, sale_days=0)
        a.login("9876543210", "ramesh123")
        return a.post("/vendor/loan/apply", amount=10000)


def loan_officer_action(setup, url, **form):
    """setup: 'pending' or 'approved'; then the officer sends one request. A refused request must not change
    the loan's status."""
    def run():
        with App() as a:
            vid = a.vendor()
            oid = a.officer()
            lid = loan.apply_loan(a.conn, vid, 15000)
            if setup == "approved":
                loan.review_loan(a.conn, lid, oid, "APPROVE", "")
            a.login("9123456780", "bank123")
            before = a.conn.execute("SELECT status FROM loans WHERE loan_id = 1").fetchone()[0]
            msg = a.post(url, **form)
            after = a.conn.execute("SELECT status FROM loans WHERE loan_id = 1").fetchone()[0]
            if before != after:
                msg += f" [POST-CONDITION FAILED: status changed to {after}]"
            return msg
    return run


def loan_withdraw_and_reapply():
    with App() as a:
        vid = a.vendor()
        loan.apply_loan(a.conn, vid, 15000)
        a.login("9876543210", "ramesh123")
        first = a.post("/vendor/loan/1/withdraw")
        second = a.post("/vendor/loan/apply", amount=12000)
        return f"{first} | {second}"


def loan_reject_with_remarks():
    with App() as a:
        vid = a.vendor()
        a.officer()
        loan.apply_loan(a.conn, vid, 15000)
        a.login("9123456780", "bank123")
        first = a.post("/officer/loan/1/review", decision="REJECT", remarks="Sales record too short")
        a.login("9876543210", "ramesh123")
        a.get("/loan/1")
        remarks = find(r"<strong>Officer remarks:</strong> ([^<]+)</span>", a.page)
        third = a.post("/vendor/loan/apply", amount=15000)
        return f"{first} | Vendor's loan page shows remarks: {remarks} | {third}"


OTHER_USERS = {"CUSTOMER": ("Priya Mehta", "9988776655", "priya123"),
               "MUNICIPAL_OFFICER": ("R K Verma", "9090909090", "muni123"),
               "VENDOR": ("Sunita Devi", "9812345670", "sunita123")}


def loan_page_as(role):
    """Another user tries to open Ramesh's loan #1 page."""
    def run():
        with App() as a:
            vid = a.vendor()
            loan.apply_loan(a.conn, vid, 15000)
            name, phone, pw = OTHER_USERS[role]
            auth.register_user(a.conn, name, phone, pw, role)
            a.login(phone, pw)
            msg = a.get("/loan/1")
            if re.search(r"<h1[^>]*>Loan #1 ", a.page):
                return (msg or "(no message)") + " [POST-CONDITION FAILED: Ramesh's loan #1 page is shown]"
            return msg
    return run


def emi_case(steps, as_other_vendor=False, loan_no=1):
    """Ramesh's loan #1 is disbursed today; send the payments in `steps`; a refused payment must not mark
    any installment PAID."""
    def run():
        with App() as a:
            a.disbursed_loan()
            if as_other_vendor:
                a.vendor(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)
                a.login("9812345670", "sunita123")
            else:
                a.login("9876543210", "ramesh123")
            msg = ""
            for n, amount in steps:
                msg = a.post(f"/vendor/loan/{loan_no}/pay/{n}", amount=amount)
            paid = a.conn.execute("SELECT COUNT(*) FROM emi_installments WHERE status = 'PAID'").fetchone()[0]
            if " paid " not in msg and paid:
                msg += f" [POST-CONDITION FAILED: {paid} installment(s) marked PAID]"
            return msg
    return run


def emi_late_payment():
    with App() as a:
        a.disbursed_loan(on=TODAY - timedelta(days=40))
        a.login("9876543210", "ramesh123")
        msg = a.post("/vendor/loan/1/pay/1", amount=1332.73)
        a.get("/dashboard")
        score = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        return f"{msg} -> Trust Score {score}/100"


def emi_score_after_on_time():
    with App() as a:
        a.disbursed_loan()
        a.login("9876543210", "ramesh123")
        before = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        a.post("/vendor/loan/1/pay/1", amount=1332.73)
        a.get("/dashboard")
        after = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
        return f"Before: {before}/100 | After paying EMI #1 on time: {after}/100"


def emi_not_disbursed():
    with App() as a:
        vid, oid = a.vendor(), a.officer()
        lid = loan.apply_loan(a.conn, vid, 15000)
        loan.review_loan(a.conn, lid, oid, "APPROVE", "")
        a.login("9876543210", "ramesh123")
        return a.post("/vendor/loan/1/pay/1", amount=1332.73)


def emi_default_boundary(days_overdue):
    def run():
        with App() as a:
            a.disbursed_loan()
            a.conn.execute("UPDATE emi_installments SET due_date = ? WHERE installment_no = 1",
                           ((TODAY - timedelta(days=days_overdue)).isoformat(),))
            a.conn.commit()
            a.login("9123456780", "bank123")
            return a.post("/officer/mark-defaults")
    return run


# ====================================================================== the documented cases
LOGIN_RAMESH = "Log in as Ramesh (9876543210 / ramesh123)"
LOGIN_OFFICER = "Log in as bank officer (9123456780 / bank123)"
SALE_STEPS = [LOGIN_RAMESH, "In 'Daily sales', enter the date, amount and payment mode", "Click 'Log sale'"]
NEW_SUNITA = "Vendor 'Sunita Devi' (9812345670 / sunita123) has a profile with 0 years of vending and no sales"

CASES = [
    # ---------------------------------------------------------------- Module 1
    Case("TC-AUTH-01", "AUTH", "System", "Register with valid details", "No account exists for 9876543210",
         ["Open the Register page", "Enter name, mobile, role, password and confirm password",
          "Click 'Create account'"],
         "Name = Ramesh Kumar, Mobile = 9876543210, Role = Street Vendor, Password = ramesh123, "
         "Confirm = ramesh123",
         "Registration successful. Please log in. -> Log in page is shown", auth_register_valid, ["FR-AUTH-1"], technique="Positive"),
    Case("TC-AUTH-02", "AUTH", "System", "Register with an already registered mobile number",
         "An account already exists for 9876543210",
         ["Open the Register page", "Enter the same mobile number with other details", "Click 'Create account'"],
         "Name = Ramesh Kumar, Mobile = 9876543210 (already registered), Password = ramesh123",
         "Mobile number already registered", auth_register(_existing=True), ["FR-AUTH-2"], technique="Negative"),
    Case("TC-AUTH-03", "AUTH", "System", "Register with an invalid mobile number", "-",
         ["Open the Register page", "Enter a 5-digit mobile number", "Click 'Create account'"],
         "Mobile = 98765 (5 digits), other fields valid",
         "Enter a valid 10-digit mobile number", auth_register(phone="98765"), ["FR-AUTH-2"], technique="Negative (EP)"),
    Case("TC-AUTH-04", "AUTH", "System", "Register with a weak password", "-",
         ["Open the Register page", "Enter a 3-letter password in both password fields", "Click 'Create account'"],
         "Password = abc, Confirm = abc, other fields valid",
         "Password must be at least 6 characters with letters and digits",
         auth_register(password="abc", confirm_password="abc"), ["FR-AUTH-3"], technique="Negative (EP)"),
    Case("TC-AUTH-05", "AUTH", "System", "Register with non-matching passwords", "-",
         ["Open the Register page", "Enter different values in Password and Confirm password",
          "Click 'Create account'"],
         "Password = ramesh123, Confirm = ramesh124", "Passwords do not match",
         auth_register(confirm_password="ramesh124"), ["FR-AUTH-1"], technique="Negative"),
    Case("TC-AUTH-06", "AUTH", "System", "Log in with correct credentials", "Ramesh is registered as a vendor",
         ["Open the Log in page", "Enter mobile number and password", "Click 'Log in'"],
         "Mobile = 9876543210, Password = ramesh123",
         "Welcome, Ramesh Kumar! -> Vendor dashboard is shown", auth_login_valid, ["FR-AUTH-5"], technique="Positive"),
    Case("TC-AUTH-07", "AUTH", "System", "Account lock after 5 wrong passwords", "Ramesh is registered as a vendor",
         ["Log in with a wrong password 5 times", "Then log in with the correct password"],
         "Mobile = 9876543210; Password = wrong1 (x5), then ramesh123",
         "Attempts 1-4: Invalid mobile number or password | Attempt 5: Account locked after 5 failed attempts. "
         "Contact support | Attempt 6 (correct password): Account locked after 5 failed attempts. Contact support",
         auth_lockout, ["FR-AUTH-6", "NFR-SEC-2"], technique="BVA"),

    # ---------------------------------------------------------------- Module 2
    Case("TC-SALE-01", "SALE", "System", "Log a valid daily sale", "No sale logged today", SALE_STEPS,
         f"Date = {dmy(TODAY)} (today), Amount = 1500, Mode = UPI",
         "Sale logged. Your trust score has been updated.", sale(TODAY, 1500), ["FR-VEN-3"], technique="Positive"),
    Case("TC-SALE-02", "SALE", "System", "Log a sale with zero amount", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 0, Mode = Cash",
         "Sale amount must be greater than 0", sale(TODAY, 0, "CASH"), ["FR-VEN-4"], technique="BVA"),
    Case("TC-SALE-03", "SALE", "System", "Log a sale for a future date", "-", SALE_STEPS,
         f"Date = {dmy(TODAY + timedelta(days=2))} (2 days ahead), Amount = 1200, Mode = Cash",
         "Sale date cannot be in the future", sale(TODAY + timedelta(days=2), 1200, "CASH"), ["FR-VEN-5"], technique="Negative (EP)"),
    Case("TC-SALE-04", "SALE", "System", "Log a second sale for the same date",
         f"A sale for {dmy(TODAY - timedelta(days=1))} is already logged", SALE_STEPS,
         f"Date = {dmy(TODAY - timedelta(days=1))}, Amount = 900, Mode = Cash",
         "Sales already logged for this date",
         sale(TODAY - timedelta(days=1), 900, "CASH", existing=TODAY - timedelta(days=1)), ["FR-VEN-5"], technique="Negative"),
    Case("TC-SALE-05", "SALE", "System", "Log a sale above the daily limit", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 150000, Mode = UPI",
         "Sale amount cannot exceed Rs 1,00,000 per day", sale(TODAY, 150000), ["FR-VEN-4"], technique="Negative (EP)"),
    Case("TC-SALE-06", "SALE", "System", "Log a sale before saving the business profile",
         "Ramesh has NOT saved his business profile", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 1500, Mode = UPI",
         "Complete your vendor profile first", sale(TODAY, 1500, profile=False), ["FR-VEN-6"], technique="Negative"),
    Case("TC-SALE-07", "SALE", "System", "30-day summary on the dashboard", "No sales logged yet",
         ["Log three sales (one per day)", "Open the dashboard and read the summary cards"],
         f"{dmy(TODAY - timedelta(days=2))}: 1000, {dmy(TODAY - timedelta(days=1))}: 2000, {dmy(TODAY)}: 3000",
         "30-day sales Rs 6,000; active days 3/30; average Rs 2,000 per active day", sale_summary, ["FR-VEN-7"], technique="Positive"),

    # ---------------------------------------------------------------- Module 3
    Case("TC-TS-01", "TS", "Unit", "Ideal vendor - maximum observable score", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, EMIs due = 0, Vouches = 3, Years = 5",
         "40 + 20 + 10 + 10 = 80 -> LOW RISK, eligible",
         ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=0, vouches=3, years_vending=5),
         ["FR-TS-2", "FR-TS-3", "FR-TS-4"], technique="Positive"),
    Case("TC-TS-02", "TS", "Unit", "Boundary value - score exactly 40", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 15/30, EMIs due = 0, Vouches = 0, Years = 0",
         "20 + 20 + 0 + 0 = 40 -> MEDIUM RISK, eligible",
         ts_unit(active_days=15, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-2", "FR-TS-4", "FR-TS-5"], technique="BVA"),
    Case("TC-TS-03", "TS", "Unit", "Boundary value - score just below 40", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 14/30, EMIs due = 0, Vouches = 0, Years = 0",
         "18.7 + 20 + 0 + 0 = 39 -> HIGH RISK, not eligible",
         ts_unit(active_days=14, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-2", "FR-TS-4", "FR-TS-5"], technique="BVA"),
    Case("TC-TS-04", "TS", "Unit", "Vendor with a partial repayment record", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 24/30, On-time EMIs = 6 of 12 due, Vouches = 1, Years = 2",
         "32 + 20 + 3.3 + 4 = 59 -> MEDIUM RISK, eligible",
         ts_unit(active_days=24, window_days=30, on_time_emis=6, emis_due=12, vouches=1, years_vending=2),
         ["FR-TS-2", "FR-TS-4"], technique="Positive"),
    Case("TC-TS-05", "TS", "Unit", "Invalid input - active days exceed the window", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 35, Window = 30", "Active days cannot exceed the observation window",
         ts_unit(active_days=35, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-1"], technique="Negative"),
    Case("TC-TS-06", "TS", "System", "New vendor sees the score on the dashboard", NEW_SUNITA,
         ["Log in as Sunita", "Read the Trust Score card"],
         "Mobile = 9812345670, Password = sunita123",
         "Dashboard shows Trust Score 20/100, HIGH RISK", ts_dashboard, ["FR-TS-3", "FR-TS-4", "FR-TS-6"], technique="Positive"),

    # ---------------------------------------------------------------- Module 4
    Case("TC-LOAN-01", "LOAN", "System", "Eligible vendor applies for a Tier-1 loan", "Ramesh has no loan",
         [LOGIN_RAMESH, "In 'Micro-credit', enter the amount", "Click 'Apply for loan'"],
         "Amount = 15000 (Trust Score 70, Tier 1 limit 15,000)",
         "Loan application #1 submitted. Status: PENDING.", loan_apply(15000), ["FR-LN-1", "FR-LN-6"], technique="BVA"),
    Case("TC-LOAN-02", "LOAN", "System", "Amount above the tier limit", "Ramesh has no loan",
         [LOGIN_RAMESH, "Enter an amount above Rs 15,000", "Click 'Apply for loan'"],
         "Amount = 20000", "Amount exceeds Tier 1 limit of Rs 15,000", loan_apply(20000), ["FR-LN-2", "FR-LN-4"], technique="Negative (EP)"),
    Case("TC-LOAN-03", "LOAN", "System", "Vendor with a low Trust Score applies", NEW_SUNITA + " (score 20)",
         ["Log in as Sunita", "Enter the amount", "Click 'Apply for loan'"],
         "Amount = 10000", "Trust score 20 is below 40. Not eligible", loan_apply(10000, low_score=True),
         ["FR-TS-5", "BR-4"], technique="Negative"),
    Case("TC-LOAN-04", "LOAN", "System", "Second application while one is pending",
         "Ramesh's application #1 for Rs 15,000 is PENDING",
         [LOGIN_RAMESH, "Enter the amount", "Click 'Apply for loan'"],
         "Amount = 5000", "You already have an active loan", loan_apply(5000, twice=True), ["FR-LN-5", "BR-2"], technique="Negative"),
    Case("TC-LOAN-05", "LOAN", "System", "Officer rejects without remarks", "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Leave the Remarks box empty", "Click 'Reject' on application #1"],
         "Remarks = (empty), Decision = Reject", "Remarks are required when rejecting", loan_reject_without_remarks,
         ["FR-BNK-3", "BR-5"], technique="Negative"),
    Case("TC-LOAN-06", "LOAN", "System", "Vendor tries to open the bank officer page", "-",
         [LOGIN_RAMESH, "Type the officer page address in the browser"],
         "URL = /officer", "You are not allowed to open that page.", loan_vendor_opens_officer_page,
         ["FR-AUTH-7", "FR-BNK-4", "BR-1"], technique="Security"),
    Case("TC-LOAN-07", "LOAN", "System", "Officer approves and disburses", "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Click 'Approve' on application #1", "Click 'Disburse' on application #1"],
         "Decision = Approve, then Disburse",
         "Loan #1 APPROVED. | Loan #1 disbursed. 12 EMIs of Rs 1332.73 scheduled.", loan_approve_disburse,
         ["FR-BNK-2", "FR-BNK-5", "FR-BNK-6"], technique="Positive"),

    # ---------------------------------------------------------------- Module 5
    Case("TC-EMI-01", "EMI", "System", "View the EMI schedule", "-",
         [LOGIN_RAMESH, "Click 'View' on loan #1", "Read the EMI schedule table"],
         f"Loan #1: P = 15000, r = 12% p.a., n = 12, disbursed {dmy(TODAY)}",
         f"12 installments; EMI #1 Rs 1,332.73 due {next_month(TODAY).isoformat()}; "
         f"EMI #12 due {date(TODAY.year + 1, TODAY.month, min(TODAY.day, calendar.monthrange(TODAY.year + 1, TODAY.month)[1])).isoformat()}",
         emi_schedule, ["FR-BNK-6", "FR-EMI-1"], technique="Positive"),
    Case("TC-EMI-02", "EMI", "System", "Pay EMI #1 before its due date", "No EMI paid yet",
         [LOGIN_RAMESH, "Open loan #1", "Click 'Pay' on installment #1 (amount pre-filled)"],
         f"Installment = 1, Amount = 1332.73, paid on {dmy(TODAY)}", "EMI #1 paid on time.",
         emi_pay([(1, 1332.73)]), ["FR-EMI-5"], technique="Positive"),
    Case("TC-EMI-03", "EMI", "System", "Pay less than the EMI amount", "No EMI paid yet",
         [LOGIN_RAMESH, "Open loan #1", "Change the amount to 1000", "Click 'Pay' on installment #1"],
         "Installment = 1, Amount = 1000", "Amount is less than EMI due of Rs 1332.73",
         emi_pay([(1, 1000)]), ["FR-EMI-3"], technique="Negative"),
    Case("TC-EMI-04", "EMI", "System", "Skip an installment (forged request)", "EMI #1 is paid; #2 is due",
         [LOGIN_RAMESH, "Pay EMI #1", "Send a payment request for installment #3 directly (the page only offers #2)"],
         "POST /vendor/loan/1/pay/3, Amount = 1332.73", "Pay earlier installment #2 first",
         emi_pay([(1, 1332.73), (3, 1332.73)]), ["FR-EMI-2"], technique="Security"),
    Case("TC-EMI-05", "EMI", "System", "Pay the same installment twice (forged request)", "EMI #1 is already paid",
         [LOGIN_RAMESH, "Pay EMI #1", "Send a payment request for installment #1 again"],
         "POST /vendor/loan/1/pay/1, Amount = 1332.73", "Installment already paid",
         emi_pay([(1, 1332.73), (1, 1332.73)]), ["FR-EMI-4"], technique="Security"),
    Case("TC-EMI-06", "EMI", "System", "Repay all 12 EMIs (progressive lending)", "No EMI paid yet",
         [LOGIN_RAMESH, "Pay installments 1 to 12 in order", "Open the dashboard"],
         "12 payments, each equal to the EMI shown",
         "EMI #12 paid on time. Loan fully repaid - you are now eligible for the next tier! -> Dashboard shows "
         "eligible limit Rs 25,000 (Tier 2)", emi_full_repayment, ["FR-EMI-6", "FR-LN-3"], technique="Positive"),
    Case("TC-EMI-07", "EMI", "System", "Default check marks a 90+ days overdue loan",
         f"Loan #1 was disbursed on {dmy(TODAY - timedelta(days=150))} (150 days ago) and no EMI has been paid",
         [LOGIN_OFFICER, "Click 'Run default check (90+ days overdue)'"],
         "(button click, no data)", "Default check complete: 1 loan(s) marked DEFAULTED.", emi_default_check,
         ["FR-BNK-7", "BR-6"], technique="Positive"),
]

# ====================================================================== extended cases (negative, BVA, combinations)
WEAK = "Password must be at least 6 characters with letters and digits"
BAD_MOBILE = "Enter a valid 10-digit mobile number"
INVALID_LOGIN = "Invalid mobile number or password"
LOGGED = "Sale logged. Your trust score has been updated."
REGISTER_STEPS = ["Open the Register page", "Fill the form with the input values", "Click 'Create account'"]
LOGIN_STEPS = ["Open the Log in page", "Enter the mobile number and password", "Click 'Log in'"]
PROFILE_STEPS = [LOGIN_RAMESH, "In 'Business profile', enter the values", "Click 'Save profile'"]
LOAN_STEPS = [LOGIN_RAMESH, "In 'Micro-credit', enter the amount", "Click 'Apply for loan'"]
PAY_STEPS = [LOGIN_RAMESH, "Open loan #1", "Enter the amount for the installment", "Click 'Pay'"]
NO_PROFILE = "Ramesh is registered but has NOT saved his business profile"
A50, A51 = "A" * 50, "A" * 51
D90, D91 = TODAY - timedelta(days=90), TODAY - timedelta(days=91)

CASES += [
    # ---------------------------------------------------------------- Module 1 (extended)
    Case("TC-AUTH-08", "AUTH", "System", "Register with the name left empty", "-", REGISTER_STEPS,
         "Name = (empty), other fields valid", "Name is required", auth_register(name=""), ["FR-AUTH-1"],
         technique="Negative (EP)"),
    Case("TC-AUTH-09", "AUTH", "System", "Register with digits as the name", "-", REGISTER_STEPS,
         "Name = 12345, other fields valid", "Name can contain only letters, spaces and dots",
         auth_register(name="12345"), ["FR-AUTH-1"], technique="Negative (EP)", defect="DEF-04"),
    Case("TC-AUTH-10", "AUTH", "System", "Boundary value - name length 50 / 51", "No account exists for 9876543210",
         REGISTER_STEPS, "Name = 'A' x 50 characters; then Name = 'A' x 51 characters (fresh database each time)",
         "50 characters: Registration successful. Please log in. | 51 characters: Name must be at most 50 characters",
         each(("50 characters", auth_register(name=A50)), ("51 characters", auth_register(name=A51))),
         ["FR-AUTH-1"], technique="BVA", defect="DEF-04"),
    Case("TC-AUTH-11", "AUTH", "System", "Mobile number - invalid equivalence classes", "-", REGISTER_STEPS,
         "Mobile = 987654321 (9 digits) / 98765432101 (11 digits) / 5876543210 (starts with 5) / 98765abcde",
         f"9 digits: {BAD_MOBILE} | 11 digits: {BAD_MOBILE} | Starts with 5: {BAD_MOBILE} | Letters: {BAD_MOBILE}",
         each(("9 digits", auth_register(phone="987654321")), ("11 digits", auth_register(phone="98765432101")),
              ("Starts with 5", auth_register(phone="5876543210")), ("Letters", auth_register(phone="98765abcde"))),
         ["FR-AUTH-2"], technique="Negative (EP)"),
    Case("TC-AUTH-12", "AUTH", "System", "Boundary value - password length 5 / 6", "No account exists for 9876543210",
         REGISTER_STEPS, "Password = ab123 (5 characters); then Password = ab1234 (6 characters)",
         f"5 characters: {WEAK} | 6 characters: Registration successful. Please log in.",
         each(("5 characters", auth_register(password="ab123", confirm_password="ab123")),
              ("6 characters", auth_register(password="ab1234", confirm_password="ab1234"))),
         ["FR-AUTH-3"], technique="BVA"),
    Case("TC-AUTH-13", "AUTH", "System", "Password with only letters / only digits", "-", REGISTER_STEPS,
         "Password = abcdefgh (no digit); then Password = 12345678 (no letter)",
         f"Only letters: {WEAK} | Only digits: {WEAK}",
         each(("Only letters", auth_register(password="abcdefgh", confirm_password="abcdefgh")),
              ("Only digits", auth_register(password="12345678", confirm_password="12345678"))),
         ["FR-AUTH-3"], technique="Negative (EP)"),
    Case("TC-AUTH-14", "AUTH", "System", "No role / forged role", "-",
         ["Open the Register page", "Do not select a role (or send role=ADMIN in the request)",
          "Click 'Create account'"],
         "Role = (not selected); then Role = ADMIN (not in the list)",
         "Not selected: Invalid role selected | ADMIN: Invalid role selected",
         each(("Not selected", auth_register(role="")), ("ADMIN", auth_register(role="ADMIN"))),
         ["FR-AUTH-1"], technique="Security"),
    Case("TC-AUTH-15", "AUTH", "System", "Several invalid fields at once (combination)", "-", REGISTER_STEPS,
         "(a) all fields empty; (b) Mobile = 98765 and Password = abc together",
         f"All empty: Name is required | Mobile + password invalid: {BAD_MOBILE}",
         each(("All empty", auth_register(name="", phone="", password="", confirm_password="", role="")),
              ("Mobile + password invalid", auth_register(phone="98765", password="abc", confirm_password="abc"))),
         ["FR-AUTH-1", "FR-AUTH-2", "FR-AUTH-3"], technique="Combination"),
    Case("TC-AUTH-16", "AUTH", "System", "Log in with a wrong password", "Ramesh is registered as a vendor",
         LOGIN_STEPS, "Mobile = 9876543210, Password = ramesh124", INVALID_LOGIN,
         auth_login_case("9876543210", "ramesh124"), ["FR-AUTH-5"], technique="Negative"),
    Case("TC-AUTH-17", "AUTH", "System", "Log in with an unregistered mobile number", "Ramesh is registered as a vendor",
         LOGIN_STEPS, "Mobile = 9000000001 (not registered), Password = ramesh123", INVALID_LOGIN,
         auth_login_case("9000000001", "ramesh123"), ["FR-AUTH-5"], technique="Negative"),
    Case("TC-AUTH-18", "AUTH", "System", "SQL injection in the login form", "Ramesh is registered as a vendor",
         LOGIN_STEPS, "Mobile = ' OR '1'='1, Password = ' OR '1'='1", INVALID_LOGIN,
         auth_login_case("' OR '1'='1", "' OR '1'='1"), ["FR-AUTH-5", "NFR-SEC-4"], technique="Security"),
    Case("TC-AUTH-19", "AUTH", "System", "Failed-attempt counter resets after a successful login",
         "Ramesh is registered as a vendor",
         ["Log in with a wrong password 4 times, then the correct one",
          "Log in with a wrong password 4 more times, then the correct one"],
         "Mobile = 9876543210; wrong1 (x4), ramesh123, wrong1 (x4), ramesh123",
         "4 wrong + correct: Welcome, Ramesh Kumar! | 4 more wrong: Invalid mobile number or password | "
         "Correct again: Welcome, Ramesh Kumar!", auth_counter_reset, ["FR-AUTH-6"], technique="BVA"),
    Case("TC-AUTH-20", "AUTH", "System", "Open the dashboard without logging in", "Nobody is logged in",
         ["Type the dashboard address in the browser"], "URL = /dashboard",
         "Please log in first. -> Log in page is shown", auth_dashboard_without_login, ["FR-AUTH-7"],
         technique="Security"),

    # ---------------------------------------------------------------- Module 2 (extended)
    Case("TC-SALE-08", "SALE", "System", "Log a sale with a negative amount", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = -500, Mode = Cash", "Sale amount must be greater than 0",
         sale(TODAY, -500, "CASH"), ["FR-VEN-4"], technique="Negative (EP)"),
    Case("TC-SALE-09", "SALE", "System", "Non-numeric / empty amount", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = abc; then Amount = (empty)",
         "abc: Sale amount must be a number | Empty: Sale amount must be a number",
         each(("abc", sale(TODAY, "abc")), ("Empty", sale(TODAY, ""))), ["FR-VEN-4"], technique="Negative (EP)"),
    Case("TC-SALE-10", "SALE", "System", "Special float values as the amount", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = nan; then Amount = inf",
         "nan: Sale amount must be a number | inf: Sale amount must be a number",
         each(("nan", sale(TODAY, "nan")), ("inf", sale(TODAY, "inf"))), ["FR-VEN-4"], technique="Negative (EP)",
         defect="DEF-01"),
    Case("TC-SALE-11", "SALE", "System", "Boundary value - upper limit Rs 1,00,000", "No sale logged today",
         SALE_STEPS, f"Date = {dmy(TODAY)}, Amount = 100000; then Amount = 100000.01",
         f"100000: {LOGGED} | 100000.01: Sale amount cannot exceed Rs 1,00,000 per day",
         each(("100000", sale(TODAY, 100000)), ("100000.01", sale(TODAY, 100000.01))), ["FR-VEN-4"],
         technique="BVA"),
    Case("TC-SALE-12", "SALE", "System", "Boundary value - lower limit", "No sale logged today", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 1; then Amount = -0.01",
         f"1: {LOGGED} | -0.01: Sale amount must be greater than 0",
         each(("1", sale(TODAY, 1)), ("-0.01", sale(TODAY, -0.01))), ["FR-VEN-4"], technique="BVA"),
    Case("TC-SALE-13", "SALE", "System", "Payment mode other than Cash / UPI (forged request)", "-",
         [LOGIN_RAMESH, "Send the sales form with a payment mode that is not in the list"],
         f"Date = {dmy(TODAY)}, Amount = 1500, Mode = CARD; then Mode = (empty)",
         "CARD: Payment mode must be CASH or UPI | Empty: Payment mode must be CASH or UPI",
         each(("CARD", sale(TODAY, 1500, "CARD")), ("Empty", sale(TODAY, 1500, ""))), ["FR-VEN-3"],
         technique="Security"),
    Case("TC-SALE-14", "SALE", "System", "Invalid / empty date", "-", SALE_STEPS,
         "Date = 2026-02-30 (no such day); then Date = (empty); Amount = 1500, Mode = UPI",
         "2026-02-30: Enter a valid date (YYYY-MM-DD) | Empty: Enter a valid date (YYYY-MM-DD)",
         each(("2026-02-30", sale("2026-02-30", 1500)), ("Empty", sale("", 1500))), ["FR-VEN-3"],
         technique="Negative (EP)"),
    Case("TC-SALE-15", "SALE", "System", "Boundary value - back-dated entry 90 / 91 days old", "No sales logged",
         SALE_STEPS, f"Date = {dmy(D90)} (90 days ago); then Date = {dmy(D91)} (91 days ago); Amount = 1500",
         f"90 days old: {LOGGED} | 91 days old: Sale date cannot be more than 90 days old",
         each(("90 days old", sale(D90, 1500)), ("91 days old", sale(D91, 1500))), ["FR-VEN-5"], technique="BVA",
         defect="DEF-02"),
    Case("TC-SALE-16", "SALE", "System", "Boundary value - today / tomorrow", "No sale logged today", SALE_STEPS,
         f"Date = {dmy(TODAY)} (today); then Date = {dmy(TODAY + timedelta(days=1))} (tomorrow); Amount = 1500",
         f"Today: {LOGGED} | Tomorrow: Sale date cannot be in the future",
         each(("Today", sale(TODAY, 1500)), ("Tomorrow", sale(TODAY + timedelta(days=1), 1500))), ["FR-VEN-5"],
         technique="BVA"),
    Case("TC-SALE-17", "SALE", "System", "Several invalid fields at once (combination)", "-", SALE_STEPS,
         f"(a) Amount = 0, Date = tomorrow, Mode = CARD; (b) Amount = 1500, Date = tomorrow, Mode = CARD",
         "Amount + date + mode invalid: Sale amount must be greater than 0 | "
         "Date + mode invalid: Sale date cannot be in the future",
         each(("Amount + date + mode invalid", sale(TODAY + timedelta(days=1), 0, "CARD")),
              ("Date + mode invalid", sale(TODAY + timedelta(days=1), 1500, "CARD"))),
         ["FR-VEN-4", "FR-VEN-5"], technique="Combination"),
    Case("TC-SALE-18", "SALE", "System", "Boundary value - years of vending 60 / 61 / -1", NO_PROFILE, PROFILE_STEPS,
         "Business = Fruits & vegetables, Zone = Sector 14 Market, Years = 60; then 61; then -1",
         "60: Profile saved. | 61: Years of vending must be between 0 and 60 | "
         "-1: Years of vending must be between 0 and 60",
         each(("60", profile_case(years_vending="60")), ("61", profile_case(years_vending="61")),
              ("-1", profile_case(years_vending="-1"))), ["FR-VEN-2"], technique="BVA"),
    Case("TC-SALE-19", "SALE", "System", "Profile with a mandatory field missing", NO_PROFILE, PROFILE_STEPS,
         "Business type = (empty); then Vending zone = (empty); then Years = abc",
         "No business type: Business type and vending zone are required | No zone: Business type and vending zone "
         "are required | Years = abc: Years of vending must be a number",
         each(("No business type", profile_case(business_type="")), ("No zone", profile_case(vending_zone="")),
              ("Years = abc", profile_case(years_vending="abc"))), ["FR-VEN-2"], technique="Negative (EP)"),

    # ---------------------------------------------------------------- Module 3 (extended)
    Case("TC-TS-07", "TS", "Unit", "Minimum score - brand-new vendor", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 0/30, EMIs due = 0, Vouches = 0, Years = 0",
         "0 + 20 + 0 + 0 = 20 -> HIGH RISK, not eligible",
         ts_unit(active_days=0, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-2", "FR-TS-3"], technique="BVA"),
    Case("TC-TS-08", "TS", "Unit", "Maximum score - perfect record", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, On-time EMIs = 12 of 12 due, Vouches = 3, Years = 5",
         "40 + 40 + 10 + 10 = 100 -> LOW RISK, eligible",
         ts_unit(active_days=30, window_days=30, on_time_emis=12, emis_due=12, vouches=3, years_vending=5),
         ["FR-TS-2", "FR-TS-4"], technique="BVA"),
    Case("TC-TS-09", "TS", "Unit", "Vouches and years above their caps", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, EMIs due = 0, Vouches = 7 (cap 3), Years = 20 (cap 5)",
         "40 + 20 + 10 + 10 = 80 -> LOW RISK, eligible",
         ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=0, vouches=7, years_vending=20),
         ["FR-TS-2"], technique="BVA"),
    Case("TC-TS-10", "TS", "Unit", "Good sales but no EMI paid on time", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, On-time EMIs = 0 of 6 due, Vouches = 0, Years = 5",
         "40 + 0 + 0 + 10 = 50 -> MEDIUM RISK, eligible",
         ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=6, vouches=0, years_vending=5),
         ["FR-TS-2", "FR-TS-4"], technique="Positive"),
    Case("TC-TS-11", "TS", "Unit", "Boundary value - score 69 / 70 (MEDIUM / LOW RISK)", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 29/30, then 30/30; EMIs due = 0, Vouches = 0, Years = 5",
         "29 days: 38.7 + 20 + 0 + 10 = 69 -> MEDIUM RISK, eligible | 30 days: 40 + 20 + 0 + 10 = 70 -> LOW RISK, "
         "eligible",
         each(("29 days", ts_unit(active_days=29, window_days=30, on_time_emis=0, emis_due=0, vouches=0,
                                  years_vending=5)),
              ("30 days", ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=0, vouches=0,
                                  years_vending=5))),
         ["FR-TS-4"], technique="BVA"),
    Case("TC-TS-12", "TS", "Unit", "Invalid input - negative vouches", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, EMIs due = 0, Vouches = -1, Years = 5", "Score inputs cannot be negative",
         ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=0, vouches=-1, years_vending=5),
         ["FR-TS-1"], technique="Negative"),
    Case("TC-TS-13", "TS", "Unit", "Invalid input - on-time EMIs exceed EMIs due", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, On-time EMIs = 5, EMIs due = 3, Vouches = 0, Years = 5",
         "On-time EMIs cannot exceed EMIs due",
         ts_unit(active_days=30, window_days=30, on_time_emis=5, emis_due=3, vouches=0, years_vending=5),
         ["FR-TS-1"], technique="Negative"),
    Case("TC-TS-14", "TS", "System", "Score goes up after a sale is logged", NEW_SUNITA,
         ["Log in as Sunita and read the score", "Log today's sale", "Read the score again"],
         f"Date = {dmy(TODAY)}, Amount = 800, Mode = Cash",
         "Before: 20/100 | After logging 1 sale: 21/100, HIGH RISK", ts_after_sale, ["FR-TS-1", "FR-VEN-3"],
         technique="Positive"),

    # ---------------------------------------------------------------- Module 4 (extended)
    Case("TC-LOAN-08", "LOAN", "System", "Zero / negative loan amount", "Ramesh has no loan", LOAN_STEPS,
         "Amount = 0; then Amount = -5000",
         "0: Loan amount must be greater than 0 | -5000: Loan amount must be greater than 0",
         each(("0", loan_apply(0)), ("-5000", loan_apply(-5000))), ["FR-LN-4"], technique="BVA"),
    Case("TC-LOAN-09", "LOAN", "System", "Non-numeric / empty loan amount", "Ramesh has no loan", LOAN_STEPS,
         "Amount = abc; then Amount = (empty)",
         "abc: Loan amount must be a number | Empty: Loan amount must be a number",
         each(("abc", loan_apply("abc")), ("Empty", loan_apply(""))), ["FR-LN-4"], technique="Negative (EP)"),
    Case("TC-LOAN-10", "LOAN", "System", "Special float values as the loan amount", "Ramesh has no loan", LOAN_STEPS,
         "Amount = nan; then Amount = inf",
         "nan: Loan amount must be a number | inf: Loan amount must be a number",
         each(("nan", loan_apply("nan")), ("inf", loan_apply("inf"))), ["FR-LN-4"], technique="Negative (EP)",
         defect="DEF-01"),
    Case("TC-LOAN-11", "LOAN", "System", "Boundary value - Tier-1 limit 15,000 / 15,000.01", "Ramesh has no loan",
         LOAN_STEPS, "Amount = 15000; then Amount = 15000.01 (fresh database each time)",
         "15000: Loan application #1 submitted. Status: PENDING. | 15000.01: Amount exceeds Tier 1 limit of "
         "Rs 15,000", each(("15000", loan_apply(15000)), ("15000.01", loan_apply(15000.01))), ["FR-LN-2", "FR-LN-4"],
         technique="BVA"),
    Case("TC-LOAN-12", "LOAN", "System", "Apply before saving the business profile", NO_PROFILE, LOAN_STEPS,
         "Amount = 10000", "Complete your vendor profile first", loan_no_profile, ["FR-TS-1", "FR-VEN-6"],
         technique="Negative"),
    Case("TC-LOAN-13", "LOAN", "System", "Two rules broken at once (combination)", "-", LOAN_STEPS,
         "(a) Sunita, score 20, Amount = 20000 (low score + above limit); (b) Ramesh with application #1 PENDING, "
         "Amount = 20000 (active loan + above limit)",
         "Low score + above limit: Trust score 20 is below 40. Not eligible | Active loan + above limit: You already "
         "have an active loan",
         each(("Low score + above limit", loan_apply(20000, low_score=True)),
              ("Active loan + above limit", loan_apply(20000, twice=True))),
         ["FR-LN-4", "FR-LN-5", "FR-TS-5"], technique="Combination"),
    Case("TC-LOAN-14", "LOAN", "System", "Review an application that is already approved",
         "Ramesh's application #1 is APPROVED", [LOGIN_OFFICER, "Send a Reject request for application #1"],
         "Decision = Reject, Remarks = Changed my mind", "Only PENDING applications can be reviewed",
         loan_officer_action("approved", "/officer/loan/1/review", decision="REJECT", remarks="Changed my mind"),
         ["FR-BNK-2"], technique="Negative"),
    Case("TC-LOAN-15", "LOAN", "System", "Disburse an application that is still pending",
         "Ramesh's application #1 is PENDING", [LOGIN_OFFICER, "Send a Disburse request for application #1"],
         "POST /officer/loan/1/disburse", "Only APPROVED loans can be disbursed",
         loan_officer_action("pending", "/officer/loan/1/disburse"), ["FR-BNK-5"], technique="Negative"),
    Case("TC-LOAN-16", "LOAN", "System", "Forged decision value", "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Send the review form with a decision that is not offered"],
         "Decision = DELETE, Remarks = x", "Decision must be APPROVE or REJECT",
         loan_officer_action("pending", "/officer/loan/1/review", decision="DELETE", remarks="x"), ["FR-BNK-2"],
         technique="Security"),
    Case("TC-LOAN-17", "LOAN", "System", "Review a loan that does not exist", "Only application #1 exists",
         [LOGIN_OFFICER, "Send an Approve request for application #99"], "POST /officer/loan/99/review, Approve",
         "Loan not found",
         loan_officer_action("pending", "/officer/loan/99/review", decision="APPROVE", remarks=""), ["FR-BNK-2"],
         technique="Negative"),
    Case("TC-LOAN-18", "LOAN", "System", "Withdraw a pending application, then apply again",
         "Ramesh's application #1 for Rs 15,000 is PENDING",
         [LOGIN_RAMESH, "Click 'Withdraw' on application #1", "Apply for Rs 12,000"],
         "Withdraw #1; then Amount = 12000",
         "Application #1 withdrawn. | Loan application #2 submitted. Status: PENDING.", loan_withdraw_and_reapply,
         ["FR-LN-5", "FR-LN-6"], technique="Positive"),
    Case("TC-LOAN-19", "LOAN", "System", "Reject with remarks; vendor sees them and can re-apply",
         "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Enter remarks and click 'Reject' on #1", LOGIN_RAMESH, "Open loan #1",
          "Apply for Rs 15,000 again"],
         "Remarks = Sales record too short; then Amount = 15000",
         "Loan #1 REJECTED. | Vendor's loan page shows remarks: Sales record too short | Loan application #2 "
         "submitted. Status: PENDING.", loan_reject_with_remarks, ["FR-BNK-3", "BR-5"], technique="Positive"),
    Case("TC-LOAN-20", "LOAN", "System", "Customer / municipal officer opens a vendor's loan page",
         "Ramesh's application #1 exists",
         ["Log in as customer Priya (9988776655 / priya123) or municipal officer (9090909090 / muni123)",
          "Type /loan/1 in the browser"], "URL = /loan/1",
         "Customer: You are not allowed to open that page. | Municipal officer: You are not allowed to open that "
         "page.", each(("Customer", loan_page_as("CUSTOMER")), ("Municipal officer", loan_page_as("MUNICIPAL_OFFICER"))),
         ["FR-AUTH-7", "NFR-SEC-7"], technique="Security", defect="DEF-05"),
    Case("TC-LOAN-21", "LOAN", "System", "Vendor opens another vendor's loan page", "Ramesh's application #1 exists",
         ["Log in as Sunita (9812345670 / sunita123)", "Type /loan/1 in the browser"], "URL = /loan/1",
         "You can only view your own loans.", loan_page_as("VENDOR"), ["FR-AUTH-7", "NFR-SEC-7"],
         technique="Security"),

    # ---------------------------------------------------------------- Module 5 (extended)
    Case("TC-EMI-08", "EMI", "System", "Special float values as the payment", "No EMI paid yet", PAY_STEPS,
         "Installment = 1, Amount = nan; then Amount = inf",
         "nan: Payment amount must be a number | inf: Payment amount must be a number",
         each(("nan", emi_case([(1, "nan")])), ("inf", emi_case([(1, "inf")]))), ["FR-EMI-3"],
         technique="Negative (EP)", defect="DEF-03"),
    Case("TC-EMI-09", "EMI", "System", "Non-numeric / empty payment", "No EMI paid yet", PAY_STEPS,
         "Installment = 1, Amount = abc; then Amount = (empty)",
         "abc: Payment amount must be a number | Empty: Payment amount must be a number",
         each(("abc", emi_case([(1, "abc")])), ("Empty", emi_case([(1, "")]))), ["FR-EMI-3"],
         technique="Negative (EP)"),
    Case("TC-EMI-10", "EMI", "System", "Boundary value - 1 paisa less than the EMI / exact EMI", "No EMI paid yet",
         PAY_STEPS, "Installment = 1, Amount = 1332.72; then Amount = 1332.73 (fresh database each time)",
         "1332.72: Amount is less than EMI due of Rs 1332.73 | 1332.73: EMI #1 paid on time.",
         each(("1332.72", emi_case([(1, 1332.72)])), ("1332.73", emi_case([(1, 1332.73)]))), ["FR-EMI-3"],
         technique="BVA"),
    Case("TC-EMI-11", "EMI", "System", "Zero / negative payment", "No EMI paid yet", PAY_STEPS,
         "Installment = 1, Amount = 0; then Amount = -1332.73",
         "0: Amount is less than EMI due of Rs 1332.73 | -1332.73: Amount is less than EMI due of Rs 1332.73",
         each(("0", emi_case([(1, 0)])), ("-1332.73", emi_case([(1, -1332.73)]))), ["FR-EMI-3"],
         technique="Negative (EP)"),
    Case("TC-EMI-12", "EMI", "System", "Pay an EMI after its due date",
         f"Loan #1 was disbursed on {dmy(TODAY - timedelta(days=40))} (40 days ago), so EMI #1 is overdue",
         PAY_STEPS + ["Open the dashboard"], f"Installment = 1, Amount = 1332.73, paid on {dmy(TODAY)}",
         "EMI #1 paid late. -> Trust Score 50/100", emi_late_payment, ["FR-EMI-5", "FR-TS-2"],
         technique="Positive"),
    Case("TC-EMI-13", "EMI", "System", "Paying on time raises the Trust Score", "No EMI paid yet; Trust Score 70",
         PAY_STEPS + ["Open the dashboard"], "Installment = 1, Amount = 1332.73",
         "Before: 70/100 | After paying EMI #1 on time: 90/100", emi_score_after_on_time, ["FR-EMI-5", "FR-TS-2"],
         technique="Positive"),
    Case("TC-EMI-14", "EMI", "System", "Installment number that does not exist (forged request)", "No EMI paid yet",
         [LOGIN_RAMESH, "Send a payment request for installment #13, then #0"],
         "POST /vendor/loan/1/pay/13 and /pay/0, Amount = 1332.73",
         "#13: Installment not found | #0: Installment not found",
         each(("#13", emi_case([(13, 1332.73)])), ("#0", emi_case([(0, 1332.73)]))), ["FR-EMI-1"],
         technique="Security"),
    Case("TC-EMI-15", "EMI", "System", "Vendor pays another vendor's EMI (forged request)", NEW_SUNITA,
         ["Log in as Sunita (9812345670 / sunita123)", "Send a payment request for Ramesh's loan #1"],
         "POST /vendor/loan/1/pay/1, Amount = 1332.73", "You can only pay your own loans",
         emi_case([(1, 1332.73)], as_other_vendor=True), ["FR-AUTH-7", "NFR-SEC-7"], technique="Security",
         defect="DEF-06"),
    Case("TC-EMI-16", "EMI", "System", "Pay an EMI of a loan that does not exist", "Only loan #1 exists",
         [LOGIN_RAMESH, "Send a payment request for loan #99"], "POST /vendor/loan/99/pay/1, Amount = 1332.73",
         "Loan not found", emi_case([(1, 1332.73)], loan_no=99), ["FR-EMI-1"], technique="Negative",
         defect="DEF-06"),
    Case("TC-EMI-17", "EMI", "System", "Pay an EMI of an approved but not disbursed loan",
         "Ramesh's loan #1 is APPROVED (not disbursed)", [LOGIN_RAMESH, "Send a payment request for loan #1"],
         "POST /vendor/loan/1/pay/1, Amount = 1332.73", "Loan is not active for repayment", emi_not_disbursed,
         ["FR-EMI-1", "FR-BNK-5"], technique="Negative"),
    Case("TC-EMI-18", "EMI", "System", "Boundary value - EMI overdue 90 / 91 days", "Loan #1 is DISBURSED, no EMI paid",
         [LOGIN_OFFICER, "Click 'Run default check (90+ days overdue)'"],
         "EMI #1 due date set to 90 days ago; then to 91 days ago (fresh database each time)",
         "90 days: Default check complete: 0 loan(s) marked DEFAULTED. | 91 days: Default check complete: 1 loan(s) "
         "marked DEFAULTED.", each(("90 days", emi_default_boundary(90)), ("91 days", emi_default_boundary(91))),
         ["FR-BNK-7", "BR-6"], technique="BVA"),
]

# Order the list module by module (AUTH, SALE, TS, LOAN, EMI) so documents read naturally.
_ORDER = list(MODULES)
CASES.sort(key=lambda c: (_ORDER.index(c.module), int(c.id.rsplit("-", 1)[1])))

# Defects found by these test cases in the first version of the code (git commit 0ce1911) and fixed afterwards.
DEFECTS = [
    {"id": "DEF-01", "severity": "High", "cases": ["TC-SALE-10", "TC-LOAN-10"],
     "found": "Typing 'nan' as a sale or loan amount crashed the app (HTTP 500 Internal Server Error); 'inf' as a "
              "loan amount gave a misleading message.",
     "cause": "Python's float() accepts 'nan' and 'inf'. NaN passed every comparison and SQLite stored it as NULL "
              "in a NOT NULL column.",
     "fix": "New helper parse_number() in database.py rejects values that are not finite numbers."},
    {"id": "DEF-02", "severity": "Medium", "cases": ["TC-SALE-15"],
     "found": "A sale dated 1900-01-01 (or any old date) was accepted.",
     "cause": "Only future dates were checked.",
     "fix": "vendor.log_daily_sale() rejects entries more than 90 days old (MAX_BACKDATE_DAYS); FR-VEN-5 updated."},
    {"id": "DEF-03", "severity": "High", "cases": ["TC-EMI-08"],
     "found": "Paying an EMI with amount 'nan' or 'inf' marked the installment PAID.",
     "cause": "Same as DEF-01: the 'less than EMI' check is False for NaN.",
     "fix": "loan.pay_emi() uses parse_number()."},
    {"id": "DEF-04", "severity": "Low", "cases": ["TC-AUTH-09", "TC-AUTH-10"],
     "found": "Names such as '12345' or a 300-character string were accepted at registration.",
     "cause": "The name was only checked for being non-empty.",
     "fix": "auth.validate_name(): letters, spaces, dots and apostrophes only, at most 50 characters; FR-AUTH-1 "
            "updated."},
    {"id": "DEF-05", "severity": "High", "cases": ["TC-LOAN-20"],
     "found": "A customer or municipal officer could open any vendor's loan page and see the amount and EMIs.",
     "cause": "The /loan/<id> page only required a logged-in user and checked ownership for vendors only.",
     "fix": "Only the owning vendor and bank officers may open a loan page (LOAN_VIEW_ROLES in app.py)."},
    {"id": "DEF-06", "severity": "Low", "cases": ["TC-EMI-15", "TC-EMI-16"],
     "found": "Paying an EMI of a loan that does not exist, or of another vendor's loan, showed two error messages "
              "('Loan not found | Loan not found', 'You can only pay your own loans | You can only view your own "
              "loans.').",
     "cause": "The error page redirected to the loan page, which reported the same error again.",
     "fix": "The pay_emi route redirects to the dashboard when the loan is missing or not the vendor's own."},
]
