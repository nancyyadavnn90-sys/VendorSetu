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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

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


MODULES = {
    "AUTH": {
        "name": "User Registration & Login",
        "subsystem": "Authentication (Module 1 - modules/auth.py)",
        "description": "Verify account creation rules, login, and account lock-out after 5 wrong passwords.",
        "pre": ["Application is running with an empty database.",
                "User is on the Register or Log in page of VendorSetu."],
        "post": ["A valid registration stores exactly one user with a hashed password; rejected input stores nothing.",
                 "After 5 consecutive wrong passwords the account stays locked even for the correct password."],
    },
    "SALE": {
        "name": "Daily Sales Logging",
        "subsystem": "Vendor Profile & Sales (Module 2 - modules/vendor.py)",
        "description": "Verify that a vendor can log one valid sales entry per day and that invalid entries are rejected.",
        "pre": ["Vendor 'Ramesh Kumar' (9876543210 / ramesh123) is registered and logged in.",
                "His business profile is saved (unless the case says otherwise)."],
        "post": ["A valid entry is saved and counted in the 30-day summary; a rejected entry changes nothing."],
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
                 "the EMI schedule; rejected requests change nothing."],
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
        path = os.path.join(self.dir, "test.db")
        app_module.get_connection = lambda: _real_get_connection(path)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.conn = _real_get_connection(path)
        init_db(self.conn)
        return self

    def __exit__(self, *exc):
        self.conn.close()
        app_module.get_connection = _real_get_connection
        shutil.rmtree(self.dir, ignore_errors=True)

    def post(self, url, **data):
        self.page = self.client.post(url, data=data, follow_redirects=True).get_data(as_text=True)
        return self.message()

    def get(self, url):
        self.page = self.client.get(url, follow_redirects=True).get_data(as_text=True)
        return self.message()

    def message(self):
        """The flash message(s) shown at the top of the current page."""
        return " | ".join(re.findall(r'class="flash \w+">([^<]+)<', self.page))

    def login(self, phone, password):
        self.client.get("/logout", follow_redirects=True)     # consume the "Logged out." message
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
            msg = a.post("/vendor/sales", sale_date=sale_date.isoformat(), amount=amount, payment_mode=mode)
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
         "Registration successful. Please log in. -> Log in page is shown", auth_register_valid, ["FR-AUTH-1"]),
    Case("TC-AUTH-02", "AUTH", "System", "Register with an already registered mobile number",
         "An account already exists for 9876543210",
         ["Open the Register page", "Enter the same mobile number with other details", "Click 'Create account'"],
         "Name = Ramesh Kumar, Mobile = 9876543210 (already registered), Password = ramesh123",
         "Mobile number already registered", auth_register(_existing=True), ["FR-AUTH-2"]),
    Case("TC-AUTH-03", "AUTH", "System", "Register with an invalid mobile number", "-",
         ["Open the Register page", "Enter a 5-digit mobile number", "Click 'Create account'"],
         "Mobile = 98765 (5 digits), other fields valid",
         "Enter a valid 10-digit mobile number", auth_register(phone="98765"), ["FR-AUTH-2"]),
    Case("TC-AUTH-04", "AUTH", "System", "Register with a weak password", "-",
         ["Open the Register page", "Enter a 3-letter password in both password fields", "Click 'Create account'"],
         "Password = abc, Confirm = abc, other fields valid",
         "Password must be at least 6 characters with letters and digits",
         auth_register(password="abc", confirm_password="abc"), ["FR-AUTH-3"]),
    Case("TC-AUTH-05", "AUTH", "System", "Register with non-matching passwords", "-",
         ["Open the Register page", "Enter different values in Password and Confirm password",
          "Click 'Create account'"],
         "Password = ramesh123, Confirm = ramesh124", "Passwords do not match",
         auth_register(confirm_password="ramesh124"), ["FR-AUTH-1"]),
    Case("TC-AUTH-06", "AUTH", "System", "Log in with correct credentials", "Ramesh is registered as a vendor",
         ["Open the Log in page", "Enter mobile number and password", "Click 'Log in'"],
         "Mobile = 9876543210, Password = ramesh123",
         "Welcome, Ramesh Kumar! -> Vendor dashboard is shown", auth_login_valid, ["FR-AUTH-5"]),
    Case("TC-AUTH-07", "AUTH", "System", "Account lock after 5 wrong passwords", "Ramesh is registered as a vendor",
         ["Log in with a wrong password 5 times", "Then log in with the correct password"],
         "Mobile = 9876543210; Password = wrong1 (x5), then ramesh123",
         "Attempts 1-4: Invalid mobile number or password | Attempt 5: Account locked after 5 failed attempts. "
         "Contact support | Attempt 6 (correct password): Account locked after 5 failed attempts. Contact support",
         auth_lockout, ["FR-AUTH-6", "NFR-SEC-2"]),

    # ---------------------------------------------------------------- Module 2
    Case("TC-SALE-01", "SALE", "System", "Log a valid daily sale", "No sale logged today", SALE_STEPS,
         f"Date = {dmy(TODAY)} (today), Amount = 1500, Mode = UPI",
         "Sale logged. Your trust score has been updated.", sale(TODAY, 1500), ["FR-VEN-3"]),
    Case("TC-SALE-02", "SALE", "System", "Log a sale with zero amount", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 0, Mode = Cash",
         "Sale amount must be greater than 0", sale(TODAY, 0, "CASH"), ["FR-VEN-4"]),
    Case("TC-SALE-03", "SALE", "System", "Log a sale for a future date", "-", SALE_STEPS,
         f"Date = {dmy(TODAY + timedelta(days=2))} (2 days ahead), Amount = 1200, Mode = Cash",
         "Sale date cannot be in the future", sale(TODAY + timedelta(days=2), 1200, "CASH"), ["FR-VEN-5"]),
    Case("TC-SALE-04", "SALE", "System", "Log a second sale for the same date",
         f"A sale for {dmy(TODAY - timedelta(days=1))} is already logged", SALE_STEPS,
         f"Date = {dmy(TODAY - timedelta(days=1))}, Amount = 900, Mode = Cash",
         "Sales already logged for this date",
         sale(TODAY - timedelta(days=1), 900, "CASH", existing=TODAY - timedelta(days=1)), ["FR-VEN-5"]),
    Case("TC-SALE-05", "SALE", "System", "Log a sale above the daily limit", "-", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 150000, Mode = UPI",
         "Sale amount cannot exceed Rs 1,00,000 per day", sale(TODAY, 150000), ["FR-VEN-4"]),
    Case("TC-SALE-06", "SALE", "System", "Log a sale before saving the business profile",
         "Ramesh has NOT saved his business profile", SALE_STEPS,
         f"Date = {dmy(TODAY)}, Amount = 1500, Mode = UPI",
         "Complete your vendor profile first", sale(TODAY, 1500, profile=False), ["FR-VEN-6"]),
    Case("TC-SALE-07", "SALE", "System", "30-day summary on the dashboard", "No sales logged yet",
         ["Log three sales (one per day)", "Open the dashboard and read the summary cards"],
         f"{dmy(TODAY - timedelta(days=2))}: 1000, {dmy(TODAY - timedelta(days=1))}: 2000, {dmy(TODAY)}: 3000",
         "30-day sales Rs 6,000; active days 3/30; average Rs 2,000 per active day", sale_summary, ["FR-VEN-7"]),

    # ---------------------------------------------------------------- Module 3
    Case("TC-TS-01", "TS", "Unit", "Ideal vendor - maximum observable score", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 30/30, EMIs due = 0, Vouches = 3, Years = 5",
         "40 + 20 + 10 + 10 = 80 -> LOW RISK, eligible",
         ts_unit(active_days=30, window_days=30, on_time_emis=0, emis_due=0, vouches=3, years_vending=5),
         ["FR-TS-2", "FR-TS-3", "FR-TS-4"]),
    Case("TC-TS-02", "TS", "Unit", "Boundary value - score exactly 40", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 15/30, EMIs due = 0, Vouches = 0, Years = 0",
         "20 + 20 + 0 + 0 = 40 -> MEDIUM RISK, eligible",
         ts_unit(active_days=15, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-2", "FR-TS-4", "FR-TS-5"]),
    Case("TC-TS-03", "TS", "Unit", "Boundary value - score just below 40", "No EMI due yet",
         ["Call compute_trust_score() with the input values"],
         "Active days = 14/30, EMIs due = 0, Vouches = 0, Years = 0",
         "18.7 + 20 + 0 + 0 = 39 -> HIGH RISK, not eligible",
         ts_unit(active_days=14, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-2", "FR-TS-4", "FR-TS-5"]),
    Case("TC-TS-04", "TS", "Unit", "Vendor with a partial repayment record", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 24/30, On-time EMIs = 6 of 12 due, Vouches = 1, Years = 2",
         "32 + 20 + 3.3 + 4 = 59 -> MEDIUM RISK, eligible",
         ts_unit(active_days=24, window_days=30, on_time_emis=6, emis_due=12, vouches=1, years_vending=2),
         ["FR-TS-2", "FR-TS-4"]),
    Case("TC-TS-05", "TS", "Unit", "Invalid input - active days exceed the window", "-",
         ["Call compute_trust_score() with the input values"],
         "Active days = 35, Window = 30", "Active days cannot exceed the observation window",
         ts_unit(active_days=35, window_days=30, on_time_emis=0, emis_due=0, vouches=0, years_vending=0),
         ["FR-TS-1"]),
    Case("TC-TS-06", "TS", "System", "New vendor sees the score on the dashboard", NEW_SUNITA,
         ["Log in as Sunita", "Read the Trust Score card"],
         "Mobile = 9812345670, Password = sunita123",
         "Dashboard shows Trust Score 20/100, HIGH RISK", ts_dashboard, ["FR-TS-3", "FR-TS-4", "FR-TS-6"]),

    # ---------------------------------------------------------------- Module 4
    Case("TC-LOAN-01", "LOAN", "System", "Eligible vendor applies for a Tier-1 loan", "Ramesh has no loan",
         [LOGIN_RAMESH, "In 'Micro-credit', enter the amount", "Click 'Apply for loan'"],
         "Amount = 15000 (Trust Score 70, Tier 1 limit 15,000)",
         "Loan application #1 submitted. Status: PENDING.", loan_apply(15000), ["FR-LN-1", "FR-LN-6"]),
    Case("TC-LOAN-02", "LOAN", "System", "Amount above the tier limit", "Ramesh has no loan",
         [LOGIN_RAMESH, "Enter an amount above Rs 15,000", "Click 'Apply for loan'"],
         "Amount = 20000", "Amount exceeds Tier 1 limit of Rs 15,000", loan_apply(20000), ["FR-LN-2", "FR-LN-4"]),
    Case("TC-LOAN-03", "LOAN", "System", "Vendor with a low Trust Score applies", NEW_SUNITA + " (score 20)",
         ["Log in as Sunita", "Enter the amount", "Click 'Apply for loan'"],
         "Amount = 10000", "Trust score 20 is below 40. Not eligible", loan_apply(10000, low_score=True),
         ["FR-TS-5", "BR-4"]),
    Case("TC-LOAN-04", "LOAN", "System", "Second application while one is pending",
         "Ramesh's application #1 for Rs 15,000 is PENDING",
         [LOGIN_RAMESH, "Enter the amount", "Click 'Apply for loan'"],
         "Amount = 5000", "You already have an active loan", loan_apply(5000, twice=True), ["FR-LN-5", "BR-2"]),
    Case("TC-LOAN-05", "LOAN", "System", "Officer rejects without remarks", "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Leave the Remarks box empty", "Click 'Reject' on application #1"],
         "Remarks = (empty), Decision = Reject", "Remarks are required when rejecting", loan_reject_without_remarks,
         ["FR-BNK-3", "BR-5"]),
    Case("TC-LOAN-06", "LOAN", "System", "Vendor tries to open the bank officer page", "-",
         [LOGIN_RAMESH, "Type the officer page address in the browser"],
         "URL = /officer", "You are not allowed to open that page.", loan_vendor_opens_officer_page,
         ["FR-AUTH-7", "FR-BNK-4", "BR-1"]),
    Case("TC-LOAN-07", "LOAN", "System", "Officer approves and disburses", "Ramesh's application #1 is PENDING",
         [LOGIN_OFFICER, "Click 'Approve' on application #1", "Click 'Disburse' on application #1"],
         "Decision = Approve, then Disburse",
         "Loan #1 APPROVED. | Loan #1 disbursed. 12 EMIs of Rs 1332.73 scheduled.", loan_approve_disburse,
         ["FR-BNK-2", "FR-BNK-5", "FR-BNK-6"]),

    # ---------------------------------------------------------------- Module 5
    Case("TC-EMI-01", "EMI", "System", "View the EMI schedule", "-",
         [LOGIN_RAMESH, "Click 'View' on loan #1", "Read the EMI schedule table"],
         f"Loan #1: P = 15000, r = 12% p.a., n = 12, disbursed {dmy(TODAY)}",
         f"12 installments; EMI #1 Rs 1,332.73 due {next_month(TODAY).isoformat()}; "
         f"EMI #12 due {date(TODAY.year + 1, TODAY.month, min(TODAY.day, calendar.monthrange(TODAY.year + 1, TODAY.month)[1])).isoformat()}",
         emi_schedule, ["FR-BNK-6", "FR-EMI-1"]),
    Case("TC-EMI-02", "EMI", "System", "Pay EMI #1 before its due date", "No EMI paid yet",
         [LOGIN_RAMESH, "Open loan #1", "Click 'Pay' on installment #1 (amount pre-filled)"],
         f"Installment = 1, Amount = 1332.73, paid on {dmy(TODAY)}", "EMI #1 paid on time.",
         emi_pay([(1, 1332.73)]), ["FR-EMI-5"]),
    Case("TC-EMI-03", "EMI", "System", "Pay less than the EMI amount", "No EMI paid yet",
         [LOGIN_RAMESH, "Open loan #1", "Change the amount to 1000", "Click 'Pay' on installment #1"],
         "Installment = 1, Amount = 1000", "Amount is less than EMI due of Rs 1332.73",
         emi_pay([(1, 1000)]), ["FR-EMI-3"]),
    Case("TC-EMI-04", "EMI", "System", "Skip an installment (forged request)", "EMI #1 is paid; #2 is due",
         [LOGIN_RAMESH, "Pay EMI #1", "Send a payment request for installment #3 directly (the page only offers #2)"],
         "POST /vendor/loan/1/pay/3, Amount = 1332.73", "Pay earlier installment #2 first",
         emi_pay([(1, 1332.73), (3, 1332.73)]), ["FR-EMI-2"]),
    Case("TC-EMI-05", "EMI", "System", "Pay the same installment twice (forged request)", "EMI #1 is already paid",
         [LOGIN_RAMESH, "Pay EMI #1", "Send a payment request for installment #1 again"],
         "POST /vendor/loan/1/pay/1, Amount = 1332.73", "Installment already paid",
         emi_pay([(1, 1332.73), (1, 1332.73)]), ["FR-EMI-4"]),
    Case("TC-EMI-06", "EMI", "System", "Repay all 12 EMIs (progressive lending)", "No EMI paid yet",
         [LOGIN_RAMESH, "Pay installments 1 to 12 in order", "Open the dashboard"],
         "12 payments, each equal to the EMI shown",
         "EMI #12 paid on time. Loan fully repaid - you are now eligible for the next tier! -> Dashboard shows "
         "eligible limit Rs 25,000 (Tier 2)", emi_full_repayment, ["FR-EMI-6", "FR-LN-3"]),
    Case("TC-EMI-07", "EMI", "System", "Default check marks a 90+ days overdue loan",
         f"Loan #1 was disbursed on {dmy(TODAY - timedelta(days=150))} (150 days ago) and no EMI has been paid",
         [LOGIN_OFFICER, "Click 'Run default check (90+ days overdue)'"],
         "(button click, no data)", "Default check complete: 1 loan(s) marked DEFAULTED.", emi_default_check,
         ["FR-BNK-7", "BR-6"]),
]
