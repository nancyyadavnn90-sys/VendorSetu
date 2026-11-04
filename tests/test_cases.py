"""
test_cases.py - The documented test cases of VendorSetu in the course format (Test Case Template, Doc T_01).

6 test cases for each of the 5 tested modules (30 in total). Like the template, every test case has a header,
pre-conditions, numbered steps (Action -> Expected System Response) and post-conditions; a step called
"Check post-condition n" looks inside the database. Each test case covers the happy path and its failure
conditions (invalid classes, boundary values, several errors at once, forged requests).

Level "System": the steps drive the running web application exactly as a user would (fill a form, click a
button) through Flask's test client, and the Actual Output is the message / value shown on the page.
Level "Unit": the steps call the Trust Score formula directly.

Every Expected Output was written from the SRS (and hand calculation) before running the code.
run_test_cases.py executes each test case on a fresh, empty database and records the Actual Output of every
step; test_vendorsetu.py runs the same cases under pytest.
"""
import calendar
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, List, Optional

# VENDORSETU_APP_DIR lets run_test_cases.py --before-fix run the same cases against the first version of the
# code (git commit 0ce1911), to show which steps failed before the defects were fixed.
APP_DIR = os.environ.get("VENDORSETU_APP_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, APP_DIR)

import app as app_module  # noqa: E402
from database import ValidationError, get_connection, init_db  # noqa: E402
from modules import auth, credit_score, loan, vendor  # noqa: E402

TODAY = date.today()
_real_get_connection = get_connection


def dmy(d):
    return d.strftime("%d-%m-%Y")


def months_later(d, n):
    """Same day n months later, clamped to the month's last day (independent of the code under test)."""
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# ====================================================================== test case structure (Doc T_01)
@dataclass
class Step:
    action: str                 # what the tester does
    data: str                   # input / test data
    expected: str               # expected system response
    fn: Callable                # performs the step, returns the actual output
    note: str = ""              # Comment column: test design technique
    defect: str = ""            # defect this step found in the first version of the code (see DEFECTS)


@dataclass
class TestCase:
    __test__ = False            # a data structure, not a pytest test class
    id: str
    module: str
    name: str
    description: str
    pre: List[str]
    steps: List[Step]
    post: List[str]
    reqs: List[str]
    setup: Optional[Callable] = None        # creates the data listed in the pre-conditions
    level: str = "System"

    def run(self):
        """Run every step on one fresh database; return the actual output of each step."""
        actuals = []
        with App() as a:
            if self.setup:
                self.setup(a)
            for s in self.steps:
                try:
                    actuals.append(s.fn(a))
                except Exception as e:          # a crash is a failed step, not a test-runner error
                    actuals.append(f"ERROR: {type(e).__name__}: {e}")
        return actuals


MODULES = {
    "AUTH": {"name": "User Registration & Login",
             "subsystem": "Authentication (Module 1 - modules/auth.py)"},
    "SALE": {"name": "Vendor Profile & Daily Sales",
             "subsystem": "Vendor Profile & Sales (Module 2 - modules/vendor.py)"},
    "TS": {"name": "Trust Score Calculation",
           "subsystem": "Alt-Credit Scoring Engine (Module 3 - modules/credit_score.py)"},
    "LOAN": {"name": "Loan Application & Bank Review",
             "subsystem": "Loan Management (Module 4 - modules/loan.py)"},
    "EMI": {"name": "EMI Schedule & Repayment",
            "subsystem": "Loan Management - Repayment (Module 4 - modules/loan.py)"},
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
        self.page = ""
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

    # ---- pre-condition data (created directly in the database, as listed in each case's Pre-conditions)
    def vendor(self, name="Ramesh Kumar", phone="9876543210", password="ramesh123", years=5, sale_days=30,
               profile=True):
        uid = auth.register_user(self.conn, name, phone, password, "VENDOR")
        if profile:
            vendor.save_profile(self.conn, uid, "Fruits & vegetables", "Sector 14 Market, Gurugram", years, "")
        for i in range(sale_days):
            vendor.log_daily_sale(self.conn, uid, (TODAY - timedelta(days=i)).isoformat(), 1500, "UPI")
        return uid

    def user(self, name, phone, password, role):
        return auth.register_user(self.conn, name, phone, password, role)

    def officer(self):
        return self.user("Anil Sharma", "9123456780", "bank123", "BANK_OFFICER")

    def disbursed_loan(self, on=TODAY):
        vid, oid = self.vendor(), self.officer()
        lid = loan.apply_loan(self.conn, vid, 15000)
        loan.review_loan(self.conn, lid, oid, "APPROVE", "Regular sales record")
        loan.disburse_loan(self.conn, lid, oid, on)
        return vid, lid


def find(pattern, page, default="(not shown)"):
    m = re.search(pattern, page)
    return m.group(1) if m else default


def count(a, table):
    return a.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ====================================================================== step builders
def screen(a):
    """Which page is on screen, from its main heading."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", a.page, re.S)
    if not m:
        return "(no page shown)"
    text = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())
    loan_page = re.match(r"Loan #(\d+)", text)
    if loan_page:
        return f"Loan #{loan_page.group(1)} page is shown"
    return {"Log in": "Log in page is shown", "Create account": "Register page is shown",
            "Loan applications": "Bank officer dashboard is shown"}.get(
        text, "Vendor dashboard is shown" if text.startswith("Namaste") else f"'{text}' page is shown")


def _shown(a, msg, show):
    if msg.startswith("HTTP 5") or not (show or not msg):
        return msg
    return f"{msg} -> {screen(a)}" if msg else screen(a)


def post(url, show=False, **data):
    return lambda a: _shown(a, a.post(url, **data), show)


def get(url, show=False):
    return lambda a: _shown(a, a.get(url), show)


def login(phone, password, show=True):
    return lambda a: _shown(a, a.login(phone, password), show)


def as_user(phone, password, then):
    """Log in as another user first, then perform the step."""
    def fn(a):
        a.login(phone, password)
        return then(a)
    return fn


def register(name="Ramesh Kumar", phone="9876543210", password="ramesh123", confirm=None, role="VENDOR",
             show=False):
    return post("/register", show, name=name, phone=phone, password=password,
                confirm_password=password if confirm is None else confirm, role=role)


def sale(day, amount, mode="UPI"):
    return post("/vendor/sales", sale_date=day if isinstance(day, str) else day.isoformat(), amount=amount,
                payment_mode=mode)


PROFILE = dict(business_type="Fruits & vegetables", vending_zone="Sector 14 Market, Gurugram", years_vending="5",
               upi_id="")


def profile(**override):
    return post("/vendor/profile", **{**PROFILE, **override})


def apply(amount):
    return post("/vendor/loan/apply", amount=amount)


def review(decision, remarks="", loan_no=1):
    return post(f"/officer/loan/{loan_no}/review", decision=decision, remarks=remarks)


def pay(n, amount, loan_no=1):
    return post(f"/vendor/loan/{loan_no}/pay/{n}", amount=amount)


def then(*fns):
    """Several actions in one step; the output of the last one is reported."""
    def fn(a):
        out = ""
        for f in fns:
            out = f(a)
        return out
    return fn


# ---- reading values shown on the dashboard / loan page
def trust_card(a):
    a.get("/dashboard")
    score = find(r"<strong>(\d+)</strong><span>out of 100</span>", a.page)
    band = find(r'<span class="score-badge [\w-]+">([A-Z ]+)</span>', a.page)
    return f"Trust Score {score}/100, {band}"


def components(a):
    a.get("/dashboard")
    rows = re.findall(r'<div class="row"><span>([^<]+)</span><span>([\d.]+) / (\d+)</span></div>', a.page)
    return ", ".join(f"{n} {float(p):g}/{m}" for n, p, m in rows) or "(not shown)"


def limit_card(a):
    a.get("/dashboard")
    m = re.search(r'<div class="value">₹([\d,]+)</div><div class="label">Eligible limit · Tier (\d)', a.page)
    return f"Eligible limit Rs {m.group(1)} (Tier {m.group(2)})" if m else "(eligible limit not shown)"


def summary_cards(a):
    a.get("/dashboard")
    total = find(r'<div class="value">₹([\d,]+)</div><div class="label">Sales, last 30 days', a.page)
    days = find(r'<div class="value">(\d+)<span class="muted"[^>]*>/30</span></div><div class="label">Active', a.page)
    avg = find(r"avg ₹([\d,]+) per active day", a.page)
    return f"30-day sales Rs {total}; active days {days}/30; average Rs {avg} per active day"


def next_emi_card(a):
    a.get("/dashboard")
    m = re.search(r'<div class="value">₹([\d,.]+)</div><div class="label">Next EMI · due ([\d-]+)', a.page)
    return f"Next EMI Rs {m.group(1)} due {m.group(2)}" if m else "(next EMI not shown)"


SCHEDULE_ROW = (r'<td><strong>(\d+)</strong></td>\s*<td>([\d-]+)</td>\s*<td class="num">₹([\d,.]+)</td>\s*'
                r'<td class="num">₹([\d,.]+)</td>\s*<td class="num">₹([\d,.]+)</td>')


def schedule(a):
    a.get("/loan/1")
    rows = re.findall(SCHEDULE_ROW, a.page)
    if not rows:
        return "(schedule not shown)"
    return f"{len(rows)} installments; EMI #1 Rs {rows[0][2]} due {rows[0][1]}; EMI #{rows[-1][0]} due {rows[-1][1]}"


def emi_split(n):
    def fn(a):
        a.get("/loan/1")
        row = next((r for r in re.findall(SCHEDULE_ROW, a.page) if r[0] == str(n)), None)
        return f"EMI #{n} = Principal Rs {row[3]} + Interest Rs {row[4]}" if row else "(not shown)"
    return fn


def loan_cards(a):
    a.get("/loan/1")
    amount = find(r'₹([\d,]+)</div><div class="label">Principal · Tier', a.page)
    tier = find(r'</div><div class="label">Principal · Tier (\d)', a.page)
    tenure = find(r'(\d+) mo</div>', a.page)
    rate = find(r'<div class="label">@ ([\d.]+)% p.a.', a.page)
    paid = find(r'(\d+/\d+)</div><div class="label">EMIs paid', a.page)
    return f"Rs {amount}, Tier {tier}; {tenure} months @ {rate}% p.a.; EMIs paid {paid}"


def loan_page_with_remarks(a):
    a.get("/loan/1")
    return f"{screen(a)}; Officer remarks: {find(r'<strong>Officer remarks:</strong> ([^<]+)</span>', a.page)}"


# ---- post-condition checks (database)
def _short(name):
    return f"'{name[0]}' x {len(name)}" if len(name) > 20 and len(set(name)) == 1 else name


def users_stored(a):
    rows = a.conn.execute("SELECT name, role FROM users ORDER BY user_id").fetchall()
    if not rows:
        return "0 users stored"
    s = "" if len(rows) == 1 else "s"
    return f"{len(rows)} user{s} stored: " + ", ".join(f"{_short(n)} ({r})" for n, r in rows)


def password_hashed(a):
    rows = a.conn.execute("SELECT password_hash FROM users").fetchall()
    h = rows[0][0] if rows else ""
    hashed = h != "ramesh123" and h.startswith(("scrypt:", "pbkdf2:"))
    return f"{len(rows)} user stored; password saved as " + ("a hash, not as 'ramesh123'" if hashed else repr(h))


def lock_state(a):
    r = a.conn.execute("SELECT is_locked, failed_attempts FROM users WHERE phone = '9876543210'").fetchone()
    return f"is_locked = {r[0]}, failed_attempts = {r[1]}"


def sales_stored(a):
    rows = a.conn.execute("SELECT sale_date, amount, payment_mode FROM sales ORDER BY sale_date DESC").fetchall()
    if not rows:
        return "0 sales stored"
    s = "" if len(rows) == 1 else "s"
    return f"{len(rows)} sale{s} stored: " + ", ".join(
        f"{dmy(date.fromisoformat(d))} Rs {amt:g} {mode}" for d, amt, mode in rows)


def profile_stored(a):
    r = a.conn.execute("SELECT business_type, vending_zone, years_vending FROM vendor_profiles").fetchone()
    return f"Profile stored: {r[0]}, {r[1]}, {r[2]} years" if r else "No profile stored"


def loans_stored(a):
    rows = a.conn.execute("SELECT loan_id, amount, tier, tenure_months, interest_rate, trust_score, status "
                          "FROM loans ORDER BY loan_id").fetchall()
    if not rows:
        return "0 loans stored"
    s = "" if len(rows) == 1 else "s"
    return f"{len(rows)} loan{s} stored: " + ", ".join(
        f"#{i} Rs {amt:g}, Tier {t}, {n} months, {r:g}% p.a., Trust Score {ts}, {st}" for i, amt, t, n, r, ts, st in rows)


def loan_status(a):
    rows = a.conn.execute("SELECT loan_id, status, remarks, disbursed_on FROM loans ORDER BY loan_id").fetchall()
    parts = []
    for i, st, remarks, on in rows:
        extra = f" (remarks: {remarks})" if remarks and st == "REJECTED" else ""
        extra += f" on {dmy(date.fromisoformat(on))}" if on and st == "DISBURSED" else ""
        parts.append(f"Loan #{i} {st}{extra}")
    emis = count(a, "emi_installments")
    return "; ".join(parts) + (f"; {emis} EMIs created" if emis and len(rows) == 1 and rows[0][1] == "DISBURSED"
                               else "")


def emis_paid(a):
    rows = a.conn.execute("SELECT installment_no, paid_on_time FROM emi_installments WHERE status = 'PAID' "
                          "ORDER BY installment_no").fetchall()
    due = a.conn.execute("SELECT COUNT(*) FROM emi_installments WHERE status = 'DUE'").fetchone()[0]
    if not rows:
        return f"0 installments PAID; {due} DUE"
    if len(rows) > 2:
        return f"{len(rows)} of {len(rows) + due} EMIs PAID"
    return ", ".join(f"EMI #{n} PAID {'on time' if t else 'late'}" for n, t in rows) + f"; {due} DUE"


# ---- unit steps (Trust Score formula)
def ts(**kw):
    def fn(_a):
        try:
            r = credit_score.compute_trust_score(**kw)
        except ValidationError as e:
            return str(e)
        parts = " + ".join(f"{v:g}" for v in r["components"].values())
        return f"{parts} = {r['score']} -> {r['band']}, {'eligible' if r['eligible'] else 'not eligible'}"
    return fn


def formula(active, window=30, on_time=0, due=0, vouches=0, years=0):
    return ts(active_days=active, window_days=window, on_time_emis=on_time, emis_due=due, vouches=vouches,
              years_vending=years)


# ====================================================================== pre-condition setups
def ramesh_logged_in(profile_saved=True, sale_days=0):
    def setup(a):
        a.vendor(profile=profile_saved, sale_days=sale_days)
        a.login("9876543210", "ramesh123")
    return setup


def ramesh_eligible(a):
    a.vendor()
    a.login("9876543210", "ramesh123")


def pending_loan_officer_logged_in(a):
    vid = a.vendor()
    a.officer()
    loan.apply_loan(a.conn, vid, 15000)
    a.login("9123456780", "bank123")


def disbursed_ramesh_logged_in(on=TODAY):
    def setup(a):
        a.disbursed_loan(on)
        a.login("9876543210", "ramesh123")
    return setup


SUNITA = dict(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)


# ====================================================================== the documented test cases
WEAK = "Password must be at least 6 characters with letters and digits"
BAD_MOBILE = "Enter a valid 10-digit mobile number"
INVALID_LOGIN = "Invalid mobile number or password"
LOCKED = "Account locked after 5 failed attempts. Contact support"
REG_OK = "Registration successful. Please log in."
LOGGED = "Sale logged. Your trust score has been updated."
CREATE = "Fill the Register form and click 'Create account'"
LOG_SALE = "In 'Daily sales' enter the values and click 'Log sale'"
APPLY = "In 'Micro-credit' enter the amount and click 'Apply for loan'"
PAY = "On loan #1 enter the amount and click 'Pay' on the installment"
CALL = "Call compute_trust_score() with the input"
CHECK = "Check post-condition"
T, Y, TM = TODAY, TODAY - timedelta(days=1), TODAY + timedelta(days=1)
D90, D91 = TODAY - timedelta(days=90), TODAY - timedelta(days=91)
EMPTY_DB = "The application is running with an empty database"
RAMESH_PRE = "Vendor Ramesh Kumar (9876543210 / ramesh123) is registered and logged in"
ELIGIBLE_PRE = [RAMESH_PRE, "His profile shows 5 years of vending and he logged a sale on each of the last 30 days, "
                "so his Trust Score is 40 + 20 + 0 + 10 = 70 (LOW RISK)", "He has no loan"]
DISBURSED_PRE = [RAMESH_PRE, f"His Tier-1 loan #1 of Rs 15,000 at 12% p.a. for 12 months was approved and disbursed "
                 f"today ({dmy(TODAY)}) by bank officer Anil Sharma",
                 "Hand calculation: r = 12% / 12 = 0.01; EMI = 15000 x 0.01 x 1.01^12 / (1.01^12 - 1) = Rs 1,332.73"]

CASES = [
    # ================================================================ Module 1: Registration & Login
    TestCase("TC-AUTH-01", "AUTH", "Register a new account",
             "Test that a new user can register, that the password is stored as a hash and that a mobile number "
             "can be registered only once.",
             [EMPTY_DB, "The user is on the Register page"],
             [Step(CREATE, "Name = Ramesh Kumar, Mobile = 9876543210, Role = Street Vendor, Password = ramesh123, "
                   "Confirm = ramesh123", f"{REG_OK} -> Log in page is shown", register(show=True),
                   "Positive (happy path)"),
              Step(f"{CHECK} 1", "-", "1 user stored; password saved as a hash, not as 'ramesh123'", password_hashed),
              Step("Register again with the same mobile number", "Name = Suresh Kumar, Mobile = 9876543210, "
                   "Password = suresh123", "Mobile number already registered",
                   register(name="Suresh Kumar", password="suresh123"), "Negative - duplicate mobile"),
              Step("Register a bank officer with a new mobile number", "Name = Anil Sharma, Mobile = 9123456780, "
                   "Role = Bank / NBFC Officer, Password = bank123", f"{REG_OK} -> Log in page is shown",
                   register("Anil Sharma", "9123456780", "bank123", role="BANK_OFFICER", show=True),
                   "Positive - another role"),
              Step(f"{CHECK} 2", "-", "2 users stored: Ramesh Kumar (VENDOR), Anil Sharma (BANK_OFFICER)",
                   users_stored)],
             ["Ramesh's password is stored only as a salted hash",
              "Only the two valid registrations are stored; the duplicate mobile number is rejected"],
             ["FR-AUTH-1", "FR-AUTH-2", "FR-AUTH-4", "NFR-SEC-1"]),

    TestCase("TC-AUTH-02", "AUTH", "Registration - name validation",
             "Test the name rules: required, only letters, spaces and dots, at most 50 characters.",
             [EMPTY_DB, "The user is on the Register page; Role = Street Vendor and Password = ramesh123 in every "
              "step, and a new mobile number in every step"],
             [Step(CREATE, "Name = (empty), Mobile = 9876543210", "Name is required", register("", "9876543210"),
                   "Negative (EP) - empty"),
              Step(CREATE, "Name = 12345, Mobile = 9876543211", "Name can contain only letters, spaces and dots",
                   register("12345", "9876543211"), "Negative (EP) - digits", "DEF-04"),
              Step(CREATE, "Name = 'A' x 51 characters, Mobile = 9876543212", "Name must be at most 50 characters",
                   register("A" * 51, "9876543212"), "BVA - just above the limit", "DEF-04"),
              Step(CREATE, "Name = 'A' x 50 characters, Mobile = 9876543213", REG_OK, register("A" * 50, "9876543213"),
                   "BVA - on the limit"),
              Step(CREATE, "Name = Mohd. Salim, Mobile = 9876543214", REG_OK, register("Mohd. Salim", "9876543214"),
                   "Positive - name with a dot"),
              Step(f"{CHECK} 1", "-", "2 users stored: 'A' x 50 (VENDOR), Mohd. Salim (VENDOR)", users_stored)],
             ["Only the two valid names are stored; every rejected name stores nothing"],
             ["FR-AUTH-1"]),

    TestCase("TC-AUTH-03", "AUTH", "Registration - mobile number and role validation",
             "Test that only a 10-digit Indian mobile number starting with 6-9 and one of the four roles are "
             "accepted.",
             [EMPTY_DB, "The user is on the Register page; Name = Ramesh Kumar and Password = ramesh123 in every step"],
             [Step(CREATE, "Mobile = 987654321 (9 digits)", BAD_MOBILE, register(phone="987654321"), "BVA - 9 digits"),
              Step(CREATE, "Mobile = 98765432101 (11 digits)", BAD_MOBILE, register(phone="98765432101"),
                   "BVA - 11 digits"),
              Step(CREATE, "Mobile = 5876543210 (starts with 5)", BAD_MOBILE, register(phone="5876543210"),
                   "Negative (EP) - must start with 6-9"),
              Step(CREATE, "Mobile = 98765abcde", BAD_MOBILE, register(phone="98765abcde"),
                   "Negative (EP) - letters"),
              Step(CREATE, "Mobile = 9876543210, Role = (not selected)", "Invalid role selected", register(role=""),
                   "Negative - no role"),
              Step("Send the form with a role that is not offered", "Mobile = 9876543210, Role = ADMIN",
                   "Invalid role selected", register(role="ADMIN"), "Security - forged request"),
              Step(f"{CHECK} 1", "-", "0 users stored", users_stored)],
             ["No account is created by any of these inputs"],
             ["FR-AUTH-1", "FR-AUTH-2"]),

    TestCase("TC-AUTH-04", "AUTH", "Registration - password validation",
             "Test the password rules (at least 6 characters with a letter and a digit, confirmation must match) "
             "and the message shown when every field is wrong.",
             [EMPTY_DB, "The user is on the Register page; Name = Ramesh Kumar, Mobile = 9876543210, Role = Street "
              "Vendor unless the step says otherwise"],
             [Step(CREATE, "Password = Confirm = ab123 (5 characters)", WEAK, register(password="ab123"),
                   "BVA - 5 characters"),
              Step(CREATE, "Password = Confirm = abcdefgh", WEAK, register(password="abcdefgh"),
                   "Negative (EP) - no digit"),
              Step(CREATE, "Password = Confirm = 12345678", WEAK, register(password="12345678"),
                   "Negative (EP) - no letter"),
              Step(CREATE, "Password = ramesh123, Confirm = ramesh124", "Passwords do not match",
                   register(confirm="ramesh124"), "Negative - confirmation differs"),
              Step("Leave every field empty and click 'Create account'", "All fields empty", "Name is required",
                   register("", "", "", role=""), "Combination - first broken rule is reported"),
              Step(CREATE, "Password = Confirm = ab1234 (6 characters)", REG_OK, register(password="ab1234"),
                   "BVA - 6 characters"),
              Step(f"{CHECK} 1", "-", "1 user stored: Ramesh Kumar (VENDOR)", users_stored)],
             ["Only the registration with a valid password (step 6) is stored"],
             ["FR-AUTH-1", "FR-AUTH-3"]),

    TestCase("TC-AUTH-05", "AUTH", "Login and logout",
             "Test login with correct and wrong credentials, logout, and that pages need a logged-in user.",
             ["Vendor Ramesh Kumar (9876543210 / ramesh123) is registered", "The user is on the Log in page"],
             [Step("Enter mobile number and password; click 'Log in'", "9876543210 / ramesh123",
                   "Welcome, Ramesh Kumar! -> Vendor dashboard is shown", login("9876543210", "ramesh123"),
                   "Positive (happy path)"),
              Step("Click 'Logout'", "-", "Logged out. -> Log in page is shown", get("/logout", show=True),
                   "Positive"),
              Step("Log in with a wrong password", "9876543210 / ramesh124", f"{INVALID_LOGIN} -> Log in page is shown",
                   login("9876543210", "ramesh124"), "Negative - wrong password"),
              Step("Log in with a mobile number that is not registered", "9000000001 / ramesh123",
                   f"{INVALID_LOGIN} -> Log in page is shown", login("9000000001", "ramesh123"),
                   "Negative - unknown user (same message, so no hint is given)"),
              Step("Type an SQL-injection string in both fields", "' OR '1'='1 / ' OR '1'='1",
                   f"{INVALID_LOGIN} -> Log in page is shown", login("' OR '1'='1", "' OR '1'='1"),
                   "Security - SQL injection"),
              Step("Type the dashboard address in the browser without logging in", "URL = /dashboard",
                   "Please log in first. -> Log in page is shown", get("/dashboard", show=True),
                   "Security - page needs login")],
             ["A session exists only after step 1; after a failed login the user stays on the Log in page"],
             ["FR-AUTH-5", "FR-AUTH-7", "NFR-SEC-4"], setup=lambda a: a.vendor()),

    TestCase("TC-AUTH-06", "AUTH", "Account lock after 5 failed attempts",
             "Test that 5 consecutive wrong passwords lock the account and that a successful login resets the "
             "counter.",
             ["Vendor Ramesh Kumar (9876543210 / ramesh123) is registered and not locked",
              "The user is on the Log in page"],
             [Step("Log in with a wrong password 4 times", "9876543210 / wrong1 (x4)",
                   f"{INVALID_LOGIN} (each time)",
                   lambda a: " / ".join(sorted({a.login("9876543210", "wrong1") for _ in range(4)})) + " (each time)",
                   "Negative"),
              Step("Log in with the correct password", "9876543210 / ramesh123",
                   "Welcome, Ramesh Kumar! -> Vendor dashboard is shown", login("9876543210", "ramesh123"),
                   "Successful login resets the counter"),
              Step("Log in with a wrong password 4 more times", "9876543210 / wrong1 (x4)",
                   f"{INVALID_LOGIN} (each time)",
                   lambda a: " / ".join(sorted({a.login("9876543210", "wrong1") for _ in range(4)})) + " (each time)",
                   "Not locked: the counter was reset"),
              Step("Log in with a wrong password a 5th time", "9876543210 / wrong1", LOCKED,
                   login("9876543210", "wrong1", show=False), "BVA - 5th attempt locks"),
              Step("Log in with the correct password", "9876543210 / ramesh123", LOCKED,
                   login("9876543210", "ramesh123", show=False), "Locked even with the correct password"),
              Step(f"{CHECK} 1", "-", "is_locked = 1, failed_attempts = 5", lock_state)],
             ["Ramesh's account is locked (is_locked = 1) after 5 consecutive failed attempts"],
             ["FR-AUTH-6", "NFR-SEC-2"], setup=lambda a: a.vendor()),

    # ================================================================ Module 2: Vendor Profile & Daily Sales
    TestCase("TC-SALE-01", "SALE", "Save the profile and log a daily sale",
             "Test that sales can be logged only after the profile is saved, and only once per day.",
             [RAMESH_PRE, "He has NOT saved his business profile yet and has no sales"],
             [Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 1500, Mode = UPI", "Complete your vendor profile first",
                   sale(T, 1500), "Negative - profile missing"),
              Step("In 'Business profile' enter the values and click 'Save profile'",
                   "Business = Fruits & vegetables, Zone = Sector 14 Market, Gurugram, Years = 5, UPI = ramesh@upi",
                   "Profile saved.", profile(upi_id="ramesh@upi"), "Positive"),
              Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 1500, Mode = UPI", LOGGED, sale(T, 1500),
                   "Positive (happy path)"),
              Step(LOG_SALE, f"Date = {dmy(T)} (same day), Amount = 900, Mode = Cash",
                   "Sales already logged for this date", sale(T, 900, "CASH"), "Negative - one entry per day"),
              Step(f"{CHECK} 1", "-", f"1 sale stored: {dmy(T)} Rs 1500 UPI", sales_stored)],
             ["The profile is saved and exactly one sale is stored for today; the duplicate entry is rejected"],
             ["FR-VEN-1", "FR-VEN-3", "FR-VEN-5", "FR-VEN-6"], setup=ramesh_logged_in(profile_saved=False)),

    TestCase("TC-SALE-02", "SALE", "Business profile validation",
             "Test that business type and vending zone are required and years of vending must be 0-60.",
             [RAMESH_PRE, "He has NOT saved his business profile; in every step the other fields are valid "
              "(Business = Fruits & vegetables, Zone = Sector 14 Market, Gurugram, Years = 5)"],
             [Step("Save the profile", "Business type = (empty)", "Business type and vending zone are required",
                   profile(business_type=""), "Negative - required field"),
              Step("Save the profile", "Vending zone = (empty)", "Business type and vending zone are required",
                   profile(vending_zone=""), "Negative - required field"),
              Step("Save the profile", "Years = abc", "Years of vending must be a number",
                   profile(years_vending="abc"), "Negative (EP) - not a number"),
              Step("Save the profile", "Years = 61", "Years of vending must be between 0 and 60",
                   profile(years_vending="61"), "BVA - just above 60"),
              Step("Save the profile", "Years = -1", "Years of vending must be between 0 and 60",
                   profile(years_vending="-1"), "BVA - just below 0"),
              Step("Save the profile", "Years = 60", "Profile saved.", profile(years_vending="60"),
                   "BVA - on the limit"),
              Step(f"{CHECK} 1", "-", "Profile stored: Fruits & vegetables, Sector 14 Market, Gurugram, 60 years",
                   profile_stored)],
             ["Only the valid profile (step 6) is stored"],
             ["FR-VEN-1", "FR-VEN-2"], setup=ramesh_logged_in(profile_saved=False)),

    TestCase("TC-SALE-03", "SALE", "Sale amount - invalid values",
             "Test that zero, negative, non-numeric and special values (nan, inf) are rejected as the amount.",
             [RAMESH_PRE, "His profile is saved and he has no sales; Date = today and Mode = UPI in every step"],
             [Step(LOG_SALE, "Amount = 0", "Sale amount must be greater than 0", sale(T, "0"), "BVA - zero"),
              Step(LOG_SALE, "Amount = -500", "Sale amount must be greater than 0", sale(T, "-500"),
                   "Negative (EP) - negative"),
              Step(LOG_SALE, "Amount = abc", "Sale amount must be a number", sale(T, "abc"),
                   "Negative (EP) - text"),
              Step(LOG_SALE, "Amount = (empty)", "Sale amount must be a number", sale(T, ""),
                   "Negative (EP) - empty"),
              Step(LOG_SALE, "Amount = nan", "Sale amount must be a number", sale(T, "nan"),
                   "Negative (EP) - special value", "DEF-01"),
              Step(LOG_SALE, "Amount = inf", "Sale amount must be a number", sale(T, "inf"),
                   "Negative (EP) - special value", "DEF-01"),
              Step(f"{CHECK} 1", "-", "0 sales stored", sales_stored)],
             ["No sale is stored for any invalid amount"],
             ["FR-VEN-4"], setup=ramesh_logged_in()),

    TestCase("TC-SALE-04", "SALE", "Sale amount - boundary values",
             "Test the amounts on both sides of the limits: greater than 0 and at most Rs 1,00,000 per day.",
             [RAMESH_PRE, "His profile is saved and he has no sales; Mode = UPI in every step"],
             [Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 100000.01", "Sale amount cannot exceed Rs 1,00,000 per day",
                   sale(T, "100000.01"), "BVA - just above the upper limit"),
              Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 100000", LOGGED, sale(T, "100000"),
                   "BVA - on the upper limit"),
              Step(LOG_SALE, f"Date = {dmy(Y)}, Amount = 1", LOGGED, sale(Y, "1"), "BVA - smallest whole amount"),
              Step(LOG_SALE, f"Date = {dmy(T - timedelta(days=2))}, Amount = -0.01",
                   "Sale amount must be greater than 0", sale(T - timedelta(days=2), "-0.01"),
                   "BVA - just below the lower limit"),
              Step(f"{CHECK} 1", "-", f"2 sales stored: {dmy(T)} Rs 100000 UPI, {dmy(Y)} Rs 1 UPI", sales_stored)],
             ["Only the two amounts inside the limits are stored"],
             ["FR-VEN-4"], setup=ramesh_logged_in()),

    TestCase("TC-SALE-05", "SALE", "Sale date and payment mode validation",
             "Test the date rules (not in the future, not more than 90 days old, a real date), the payment mode "
             "and an entry with several wrong fields.",
             [RAMESH_PRE, "His profile is saved and he has no sales; Amount = 1500 and Mode = UPI unless the step "
              "says otherwise"],
             [Step(LOG_SALE, f"Date = {dmy(TM)} (tomorrow)", "Sale date cannot be in the future", sale(TM, "1500"),
                   "BVA - tomorrow"),
              Step(LOG_SALE, "Date = 2026-02-30 (no such day)", "Enter a valid date (YYYY-MM-DD)",
                   sale("2026-02-30", "1500"), "Negative (EP) - invalid date"),
              Step(LOG_SALE, f"Date = {dmy(D91)} (91 days ago)", "Sale date cannot be more than 90 days old",
                   sale(D91, "1500"), "BVA - just outside 90 days", "DEF-02"),
              Step(LOG_SALE, f"Date = {dmy(D90)} (90 days ago)", LOGGED, sale(D90, "1500"),
                   "BVA - on the 90-day limit"),
              Step("Send the sales form with a payment mode that is not offered", f"Date = {dmy(T)}, Mode = CARD",
                   "Payment mode must be CASH or UPI", sale(T, "1500", "CARD"), "Security - forged value"),
              Step(LOG_SALE, f"Amount = 0, Date = {dmy(TM)}, Mode = CARD (three fields wrong)",
                   "Sale amount must be greater than 0", sale(TM, "0", "CARD"),
                   "Combination - first broken rule is reported"),
              Step(f"{CHECK} 1", "-", f"1 sale stored: {dmy(D90)} Rs 1500 UPI", sales_stored)],
             ["Only the entry dated 90 days ago (step 4) is stored"],
             ["FR-VEN-3", "FR-VEN-4", "FR-VEN-5"], setup=ramesh_logged_in()),

    TestCase("TC-SALE-06", "SALE", "30-day sales summary on the dashboard",
             "Test that the dashboard shows the correct 30-day total, active days, daily average and the updated "
             "Trust Score.",
             [RAMESH_PRE, "His profile is saved (5 years of vending) and he has no sales"],
             [Step(LOG_SALE, f"Date = {dmy(T - timedelta(days=2))}, Amount = 1000, Mode = Cash", LOGGED,
                   sale(T - timedelta(days=2), "1000", "CASH"), "Positive"),
              Step(LOG_SALE, f"Date = {dmy(Y)}, Amount = 2000, Mode = Cash", LOGGED, sale(Y, "2000", "CASH"),
                   "Positive"),
              Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 3000, Mode = Cash", LOGGED, sale(T, "3000", "CASH"),
                   "Positive"),
              Step("Read the summary cards on the dashboard", "-",
                   "30-day sales Rs 6,000; active days 3/30; average Rs 2,000 per active day", summary_cards,
                   "Hand calculation: 6000 / 3 = 2000"),
              Step("Read the Trust Score card", "-", "Trust Score 34/100, HIGH RISK", trust_card,
                   "Hand calculation: 3/30 x 40 + 20 + 0 + 10 = 34")],
             ["Three sales are stored and the summary and Trust Score reflect them"],
             ["FR-VEN-7", "FR-TS-1"], setup=ramesh_logged_in()),

    # ================================================================ Module 3: Trust Score
    TestCase("TC-TS-01", "TS", "Trust Score of a new vendor on the dashboard",
             "Test the score, risk band and component points shown to a new vendor, and that the score is updated "
             "and used for loan eligibility.",
             ["Vendor Sunita Devi (9812345670 / sunita123) is registered; her profile shows 0 years of vending; "
              "she has no sales, vouches or loans"],
             [Step("Log in as Sunita and read the Trust Score card", "9812345670 / sunita123",
                   "Trust Score 20/100, HIGH RISK", as_user("9812345670", "sunita123", trust_card),
                   "Hand calculation: 0 + 20 (no EMI due) + 0 + 0"),
              Step("Read the four component bars", "-",
                   "Sales consistency 0/40, Repayment history 20/40, Peer vouching 0/10, Vending tenure 0/10",
                   components, "Explainable score"),
              Step(LOG_SALE, f"Date = {dmy(T)}, Amount = 800, Mode = Cash", LOGGED, sale(T, "800", "CASH"),
                   "Positive"),
              Step("Read the Trust Score card again", "-", "Trust Score 21/100, HIGH RISK", trust_card,
                   "1/30 x 40 = 1.3; 1.3 + 20 = 21"),
              Step(APPLY, "Amount = 10000", "Trust score 21 is below 40. Not eligible", apply("10000"),
                   "Negative - score below 40")],
             ["One sale is stored; no loan is created"],
             ["FR-TS-1", "FR-TS-3", "FR-TS-4", "FR-TS-5", "FR-TS-6"], setup=lambda a: a.vendor(**SUNITA)),

    TestCase("TC-TS-02", "TS", "Formula - loan eligibility boundary (39 / 40)",
             "Test the score on both sides of the eligibility cut-off of 40.",
             ["compute_trust_score() is called directly (unit test)",
              "Window = 30 days; no EMI due yet (repayment = 20); Vouches = 0; Years = 0"],
             [Step(CALL, "Active days = 14", "18.7 + 20 + 0 + 0 = 39 -> HIGH RISK, not eligible", formula(14),
                   "BVA - just below 40"),
              Step(CALL, "Active days = 15", "20 + 20 + 0 + 0 = 40 -> MEDIUM RISK, eligible", formula(15),
                   "BVA - on 40"),
              Step(CALL, "Active days = 16", "21.3 + 20 + 0 + 0 = 41 -> MEDIUM RISK, eligible", formula(16),
                   "BVA - just above 40")],
             ["Score, band and eligibility are returned; no stored data changes"],
             ["FR-TS-2", "FR-TS-4", "FR-TS-5"], level="Unit"),

    TestCase("TC-TS-03", "TS", "Formula - risk band boundary (69 / 70)",
             "Test the score on both sides of the MEDIUM / LOW RISK boundary.",
             ["compute_trust_score() is called directly (unit test)",
              "Window = 30 days; no EMI due yet (repayment = 20); Years = 5"],
             [Step(CALL, "Active days = 29, Vouches = 0", "38.7 + 20 + 0 + 10 = 69 -> MEDIUM RISK, eligible",
                   formula(29, years=5), "BVA - just below 70"),
              Step(CALL, "Active days = 30, Vouches = 0", "40 + 20 + 0 + 10 = 70 -> LOW RISK, eligible",
                   formula(30, years=5), "BVA - on 70"),
              Step(CALL, "Active days = 28, Vouches = 1", "37.3 + 20 + 3.3 + 10 = 71 -> LOW RISK, eligible",
                   formula(28, vouches=1, years=5), "BVA - just above 70")],
             ["Score, band and eligibility are returned; no stored data changes"],
             ["FR-TS-2", "FR-TS-4"], level="Unit"),

    TestCase("TC-TS-04", "TS", "Formula - minimum, maximum and repayment history",
             "Test the lowest and highest possible scores and the effect of the repayment record.",
             ["compute_trust_score() is called directly (unit test)", "Window = 30 days"],
             [Step(CALL, "Active days = 0, EMIs due = 0, Vouches = 0, Years = 0",
                   "0 + 20 + 0 + 0 = 20 -> HIGH RISK, not eligible", formula(0), "BVA - minimum"),
              Step(CALL, "Active days = 30, On-time EMIs = 12 of 12, Vouches = 3, Years = 5",
                   "40 + 40 + 10 + 10 = 100 -> LOW RISK, eligible", formula(30, on_time=12, due=12, vouches=3, years=5),
                   "BVA - maximum"),
              Step(CALL, "Active days = 30, On-time EMIs = 0 of 6, Vouches = 0, Years = 5",
                   "40 + 0 + 0 + 10 = 50 -> MEDIUM RISK, eligible", formula(30, due=6, years=5),
                   "No EMI paid on time"),
              Step(CALL, "Active days = 24, On-time EMIs = 6 of 12, Vouches = 1, Years = 2",
                   "32 + 20 + 3.3 + 4 = 59 -> MEDIUM RISK, eligible", formula(24, on_time=6, due=12, vouches=1, years=2),
                   "Positive - partial record")],
             ["Score, band and eligibility are returned; no stored data changes"],
             ["FR-TS-2", "FR-TS-3", "FR-TS-4"], level="Unit"),

    TestCase("TC-TS-05", "TS", "Formula - caps on vouches and tenure",
             "Test that only 3 vouches and 5 years of vending count toward the score.",
             ["compute_trust_score() is called directly (unit test)",
              "Active days = 30 of 30; no EMI due yet (repayment = 20)"],
             [Step(CALL, "Vouches = 3, Years = 5", "40 + 20 + 10 + 10 = 80 -> LOW RISK, eligible",
                   formula(30, vouches=3, years=5), "BVA - on the caps"),
              Step(CALL, "Vouches = 7, Years = 20", "40 + 20 + 10 + 10 = 80 -> LOW RISK, eligible",
                   formula(30, vouches=7, years=20), "BVA - above the caps (same score)"),
              Step(CALL, "Vouches = 2, Years = 4", "40 + 20 + 6.7 + 8 = 75 -> LOW RISK, eligible",
                   formula(30, vouches=2, years=4), "BVA - below the caps")],
             ["Score, band and eligibility are returned; no stored data changes"],
             ["FR-TS-2", "BR-8"], level="Unit"),

    TestCase("TC-TS-06", "TS", "Formula - invalid inputs",
             "Test that impossible input values are rejected with a clear message.",
             ["compute_trust_score() is called directly (unit test)"],
             [Step(CALL, "Active days = 35, Window = 30", "Active days cannot exceed the observation window",
                   formula(35), "Negative - more days than the window"),
              Step(CALL, "Active days = 30, Vouches = -1, Years = 5", "Score inputs cannot be negative",
                   formula(30, vouches=-1, years=5), "Negative - negative value"),
              Step(CALL, "Active days = 30, On-time EMIs = 5, EMIs due = 3", "On-time EMIs cannot exceed EMIs due",
                   formula(30, on_time=5, due=3), "Negative - inconsistent values")],
             ["No score is returned for invalid input"],
             ["FR-TS-1"], level="Unit"),

    # ================================================================ Module 4: Loan Application & Bank Review
    TestCase("TC-LOAN-01", "LOAN", "Eligible vendor applies for a Tier-1 loan",
             "Test a loan application at and above the Tier-1 limit and the one-active-loan rule.",
             ELIGIBLE_PRE,
             [Step("Read the Trust Score and the eligible-limit card on the dashboard", "-",
                   "Trust Score 70/100, LOW RISK; Eligible limit Rs 15,000 (Tier 1)",
                   lambda a: f"{trust_card(a)}; {limit_card(a)}", "Positive"),
              Step(APPLY, "Amount = 15000.01", "Amount exceeds Tier 1 limit of Rs 15,000", apply("15000.01"),
                   "BVA - just above the tier limit"),
              Step(APPLY, "Amount = 15000", "Loan application #1 submitted. Status: PENDING.", apply("15000"),
                   "BVA - on the tier limit"),
              Step(APPLY, "Amount = 5000", "You already have an active loan", apply("5000"),
                   "Negative - one active loan only"),
              Step(f"{CHECK} 1", "-", "1 loan stored: #1 Rs 15000, Tier 1, 12 months, 12% p.a., Trust Score 70, "
                   "PENDING", loans_stored)],
             ["Application #1 is stored as PENDING with its tier, tenure, interest rate and Trust Score"],
             ["FR-LN-1", "FR-LN-2", "FR-LN-4", "FR-LN-5", "FR-LN-6"], setup=ramesh_eligible),

    TestCase("TC-LOAN-02", "LOAN", "Loan amount - invalid values",
             "Test that zero, negative, non-numeric and special values are rejected as the loan amount.",
             ELIGIBLE_PRE,
             [Step(APPLY, "Amount = 0", "Loan amount must be greater than 0", apply("0"), "BVA - zero"),
              Step(APPLY, "Amount = -5000", "Loan amount must be greater than 0", apply("-5000"),
                   "Negative (EP) - negative"),
              Step(APPLY, "Amount = abc", "Loan amount must be a number", apply("abc"), "Negative (EP) - text"),
              Step(APPLY, "Amount = (empty)", "Loan amount must be a number", apply(""), "Negative (EP) - empty"),
              Step(APPLY, "Amount = nan", "Loan amount must be a number", apply("nan"),
                   "Negative (EP) - special value", "DEF-01"),
              Step(APPLY, "Amount = inf", "Loan amount must be a number", apply("inf"),
                   "Negative (EP) - special value", "DEF-01"),
              Step(f"{CHECK} 1", "-", "0 loans stored", loans_stored)],
             ["No loan application is stored"],
             ["FR-LN-4"], setup=ramesh_eligible),

    TestCase("TC-LOAN-03", "LOAN", "Vendor who is not eligible applies",
             "Test that a vendor with a Trust Score below 40, or without a profile, cannot apply.",
             ["Vendor Sunita Devi (9812345670 / sunita123): profile with 0 years of vending, no sales, Trust Score 20",
              "Vendor Mohan Lal (9898989898 / mohan123) is registered but has NOT saved a profile"],
             [Step(f"Log in as Sunita. {APPLY}", "Amount = 10000", "Trust score 20 is below 40. Not eligible",
                   as_user("9812345670", "sunita123", apply("10000")), "Negative - score below 40"),
              Step(APPLY, "Amount = 20000 (also above the Tier-1 limit)", "Trust score 20 is below 40. Not eligible",
                   apply("20000"), "Combination - eligibility is checked first"),
              Step(f"Log in as Mohan. {APPLY}", "Amount = 10000", "Complete your vendor profile first",
                   as_user("9898989898", "mohan123", apply("10000")), "Negative - no profile"),
              Step(f"{CHECK} 1", "-", "0 loans stored", loans_stored)],
             ["No loan application is stored"],
             ["FR-TS-5", "FR-VEN-6", "BR-4"],
             setup=lambda a: (a.vendor(**SUNITA), a.vendor("Mohan Lal", "9898989898", "mohan123", profile=False,
                                                            sale_days=0))),

    TestCase("TC-LOAN-04", "LOAN", "Bank officer approves and disburses a loan",
             "Test approval and disbursal, and that the loan cannot skip or repeat a state.",
             ["Ramesh's application #1 for Rs 15,000 (Tier 1) is PENDING",
              "Bank officer Anil Sharma (9123456780 / bank123) is logged in"],
             [Step("Send a Disburse request for #1 (the button appears only after approval)", "Loan #1",
                   "Only APPROVED loans can be disbursed", post("/officer/loan/1/disburse"),
                   "Negative - invalid state change"),
              Step("Click 'Approve' on application #1", "Decision = Approve, Remarks = (empty)", "Loan #1 APPROVED.",
                   review("APPROVE"), "Positive"),
              Step("Send an Approve request for #1 again", "Decision = Approve", "Only PENDING applications can be "
                   "reviewed", review("APPROVE"), "Negative - invalid state change"),
              Step("Click 'Disburse' on loan #1", "Loan #1", "Loan #1 disbursed. 12 EMIs of Rs 1332.73 scheduled.",
                   post("/officer/loan/1/disburse"), "Positive - EMI from hand calculation"),
              Step(f"{CHECK} 1", "-", f"Loan #1 DISBURSED on {dmy(T)}; 12 EMIs created", loan_status)],
             ["Loan #1 is DISBURSED with today's date and 12 EMIs are created"],
             ["FR-BNK-2", "FR-BNK-5", "FR-BNK-6"], setup=pending_loan_officer_logged_in),

    TestCase("TC-LOAN-05", "LOAN", "Officer rejects; vendor re-applies and withdraws",
             "Test rejection rules (remarks required, valid decision, existing loan), that the vendor sees the "
             "remarks, and withdrawal.",
             ["Ramesh's application #1 for Rs 15,000 is PENDING; Ramesh's Trust Score is 70",
              "Bank officer Anil Sharma (9123456780 / bank123) is logged in"],
             [Step("Leave Remarks empty and click 'Reject' on #1", "Decision = Reject, Remarks = (empty)",
                   "Remarks are required when rejecting", review("REJECT"), "Negative - remarks required"),
              Step("Send the review form with a decision that is not offered", "Decision = DELETE, Remarks = x",
                   "Decision must be APPROVE or REJECT", review("DELETE", "x"), "Security - forged value"),
              Step("Send an Approve request for application #99", "Loan #99 (does not exist)", "Loan not found",
                   review("APPROVE", loan_no=99), "Negative - unknown loan"),
              Step("Enter remarks and click 'Reject' on #1", "Decision = Reject, Remarks = Sales record too short",
                   "Loan #1 REJECTED.", review("REJECT", "Sales record too short"), "Positive"),
              Step("Log in as Ramesh and open loan #1", "9876543210 / ramesh123",
                   "Loan #1 page is shown; Officer remarks: Sales record too short",
                   as_user("9876543210", "ramesh123", loan_page_with_remarks), "Remarks shown to the vendor"),
              Step(APPLY, "Amount = 12000", "Loan application #2 submitted. Status: PENDING.", apply("12000"),
                   "Positive - may re-apply after rejection"),
              Step("Click 'Withdraw' on application #2", "Loan #2", "Application #2 withdrawn.",
                   post("/vendor/loan/2/withdraw"), "Positive"),
              Step(f"{CHECK} 1", "-", "Loan #1 REJECTED (remarks: Sales record too short); Loan #2 WITHDRAWN",
                   loan_status)],
             ["Application #1 is REJECTED with the officer's remarks and application #2 is WITHDRAWN"],
             ["FR-BNK-2", "FR-BNK-3", "FR-LN-5", "FR-LN-6", "BR-5"], setup=pending_loan_officer_logged_in),

    TestCase("TC-LOAN-06", "LOAN", "Access control on officer and loan pages",
             "Test that each role can open only the pages allowed to it.",
             ["Ramesh's application #1 exists", "Registered: Sunita Devi (vendor, 9812345670 / sunita123), Priya "
              "Mehta (customer, 9988776655 / priya123), R K Verma (municipal officer, 9090909090 / muni123), "
              "Anil Sharma (bank officer, 9123456780 / bank123)"],
             [Step("Log in as Ramesh; type /officer in the browser", "URL = /officer",
                   "You are not allowed to open that page.", as_user("9876543210", "ramesh123", get("/officer")),
                   "Security - vendor on officer page"),
              Step("Log in as Priya (customer); type /loan/1", "URL = /loan/1",
                   "You are not allowed to open that page.", as_user("9988776655", "priya123", get("/loan/1")),
                   "Security - customer", "DEF-05"),
              Step("Log in as R K Verma (municipal officer); type /loan/1", "URL = /loan/1",
                   "You are not allowed to open that page.", as_user("9090909090", "muni123", get("/loan/1")),
                   "Security - municipal officer", "DEF-05"),
              Step("Log in as Sunita (another vendor); type /loan/1", "URL = /loan/1",
                   "You can only view your own loans.", as_user("9812345670", "sunita123", get("/loan/1")),
                   "Security - other vendor"),
              Step("Log in as Anil (bank officer); open /loan/1", "URL = /loan/1", "Loan #1 page is shown",
                   as_user("9123456780", "bank123", get("/loan/1")), "Positive - bank officer"),
              Step("Log in as Ramesh; open /loan/1", "URL = /loan/1", "Loan #1 page is shown",
                   as_user("9876543210", "ramesh123", get("/loan/1")), "Positive - owner")],
             ["Loan data is visible only to its vendor and to bank officers; nothing is changed"],
             ["FR-AUTH-7", "FR-BNK-4", "NFR-SEC-7", "BR-1"],
             setup=lambda a: (loan.apply_loan(a.conn, a.vendor(), 15000), a.vendor(**SUNITA),
                              a.user("Priya Mehta", "9988776655", "priya123", "CUSTOMER"),
                              a.user("R K Verma", "9090909090", "muni123", "MUNICIPAL_OFFICER"), a.officer())),

    # ================================================================ Module 5: EMI Schedule & Repayment
    TestCase("TC-EMI-01", "EMI", "View the EMI schedule",
             "Test the generated reducing-balance EMI schedule against a hand calculation.",
             DISBURSED_PRE,
             [Step("Read the 'Next EMI' card on the dashboard", "-",
                   f"Next EMI Rs 1,332.73 due {months_later(T, 1).isoformat()}", next_emi_card, "Positive"),
              Step("Click 'View' on loan #1 and read the EMI schedule", "Loan #1",
                   f"12 installments; EMI #1 Rs 1,332.73 due {months_later(T, 1).isoformat()}; EMI #12 due "
                   f"{months_later(T, 12).isoformat()}", schedule, "Monthly due dates"),
              Step("Read the principal / interest split of EMI #1", "-",
                   "EMI #1 = Principal Rs 1,182.73 + Interest Rs 150.00", emi_split(1),
                   "Interest = 15000 x 0.01 = 150"),
              Step("Read the split of EMI #2", "-", "EMI #2 = Principal Rs 1,194.56 + Interest Rs 138.17", emi_split(2),
                   "Interest = 13817.27 x 0.01 (reducing balance)"),
              Step("Read the summary cards on the loan page", "-", "Rs 15,000, Tier 1; 12 months @ 12.0% p.a.; EMIs "
                   "paid 0/12", loan_cards, "Positive")],
             ["The schedule is displayed; nothing is changed"],
             ["FR-BNK-6", "FR-EMI-1"], setup=disbursed_ramesh_logged_in()),

    TestCase("TC-EMI-02", "EMI", "Pay EMIs in order",
             "Test paying EMIs, and that an installment cannot be paid twice or out of order.",
             DISBURSED_PRE + ["No EMI has been paid"],
             [Step(PAY, "Installment #1, Amount = 1332.73", "EMI #1 paid on time.", pay(1, "1332.73"),
                   "Positive (happy path)"),
              Step("Send a payment request for #1 again", "Installment #1, Amount = 1332.73", "Installment already paid",
                   pay(1, "1332.73"), "Security - forged request"),
              Step("Send a payment request for #3 (the page offers only #2)", "Installment #3, Amount = 1332.73",
                   "Pay earlier installment #2 first", pay(3, "1332.73"), "Security - out of order"),
              Step(PAY, "Installment #2, Amount = 1332.73", "EMI #2 paid on time.", pay(2, "1332.73"), "Positive"),
              Step(f"{CHECK} 1", "-", "EMI #1 PAID on time, EMI #2 PAID on time; 10 DUE", emis_paid)],
             ["EMIs #1 and #2 are PAID (on time); the other 10 are still DUE"],
             ["FR-EMI-2", "FR-EMI-4", "FR-EMI-5"], setup=disbursed_ramesh_logged_in()),

    TestCase("TC-EMI-03", "EMI", "Payment amount - invalid values",
             "Test that a payment less than the EMI, or one that is not a number, is rejected.",
             DISBURSED_PRE + ["No EMI has been paid; every step pays installment #1"],
             [Step(PAY, "Amount = 1332.72 (1 paisa less)", "Amount is less than EMI due of Rs 1332.73",
                   pay(1, "1332.72"), "BVA - just below the EMI"),
              Step(PAY, "Amount = 0", "Amount is less than EMI due of Rs 1332.73", pay(1, "0"), "BVA - zero"),
              Step(PAY, "Amount = abc", "Payment amount must be a number", pay(1, "abc"), "Negative (EP) - text"),
              Step(PAY, "Amount = (empty)", "Payment amount must be a number", pay(1, ""), "Negative (EP) - empty"),
              Step(PAY, "Amount = nan", "Payment amount must be a number", pay(1, "nan"),
                   "Negative (EP) - special value", "DEF-03"),
              Step(PAY, "Amount = inf", "Payment amount must be a number", pay(1, "inf"),
                   "Negative (EP) - special value", "DEF-03"),
              Step(f"{CHECK} 1", "-", "0 installments PAID; 12 DUE", emis_paid)],
             ["No installment is marked PAID"],
             ["FR-EMI-3"], setup=disbursed_ramesh_logged_in()),

    TestCase("TC-EMI-04", "EMI", "Full repayment raises the score and unlocks Tier 2",
             "Test that on-time payments raise the Trust Score and that paying the last EMI closes the loan and "
             "unlocks the next tier (progressive lending).",
             DISBURSED_PRE + ["No EMI has been paid; Ramesh's Trust Score is 70"],
             [Step("Read the Trust Score card", "-", "Trust Score 70/100, LOW RISK", trust_card,
                   "No EMI due yet: repayment = 20"),
              Step(f"{PAY}; then read the Trust Score", "Installment #1, Amount = 1332.73",
                   "EMI #1 paid on time. -> Trust Score 90/100, LOW RISK",
                   lambda a: f"{pay(1, '1332.73')(a)} -> {trust_card(a)}", "1 of 1 on time: repayment = 40"),
              Step("Pay installments #2 to #12 in order, each with the amount shown", "11 payments",
                   "EMI #12 paid on time. Loan fully repaid - you are now eligible for the next tier!",
                   lambda a: [pay(r[0], r[1])(a) for r in a.conn.execute(
                       "SELECT installment_no, emi_amount FROM emi_installments WHERE installment_no > 1 "
                       "ORDER BY installment_no").fetchall()][-1], "Positive"),
              Step("Open the dashboard and read the eligible-limit card", "-", "Eligible limit Rs 25,000 (Tier 2)",
                   limit_card, "Next tier unlocked"),
              Step(f"{CHECK} 1", "-", "Loan #1 CLOSED; 12 of 12 EMIs PAID",
                   lambda a: f"{loan_status(a)}; {emis_paid(a)}")],
             ["Loan #1 is CLOSED, all 12 EMIs are PAID and Ramesh can now borrow up to Rs 25,000"],
             ["FR-EMI-5", "FR-EMI-6", "FR-LN-3", "FR-TS-2"], setup=disbursed_ramesh_logged_in()),

    TestCase("TC-EMI-05", "EMI", "Invalid payment requests",
             "Test forged payment requests: unknown installment or loan, someone else's loan, a loan not disbursed.",
             DISBURSED_PRE + ["Sunita Devi (9812345670 / sunita123) is a registered vendor",
                              "Mohd. Salim (9811122233 / salim123) has loan #2 APPROVED but not yet disbursed"],
             [Step("Send a payment request for installment #13", "Loan #1, Installment #13, Amount = 1332.73",
                   "Installment not found", pay(13, "1332.73"), "Security - no such installment"),
              Step("Send a payment request for installment #0", "Loan #1, Installment #0, Amount = 1332.73",
                   "Installment not found", pay(0, "1332.73"), "BVA - below #1"),
              Step("Send a payment request for loan #99", "Loan #99, Installment #1, Amount = 1332.73",
                   "Loan not found", pay(1, "1332.73", loan_no=99), "Negative - unknown loan", "DEF-06"),
              Step("Log in as Sunita; send a payment for Ramesh's loan #1", "Loan #1, Installment #1",
                   "You can only pay your own loans", as_user("9812345670", "sunita123", pay(1, "1332.73")),
                   "Security - someone else's loan", "DEF-06"),
              Step("Log in as Salim; send a payment for his loan #2", "Loan #2, Installment #1",
                   "Loan is not active for repayment", as_user("9811122233", "salim123", pay(1, "1332.73", loan_no=2)),
                   "Negative - loan not disbursed"),
              Step(f"{CHECK} 1", "-", "0 installments PAID; 12 DUE", emis_paid)],
             ["No installment is marked PAID"],
             ["FR-EMI-1", "FR-BNK-5", "NFR-SEC-7"],
             setup=lambda a: (disbursed_ramesh_logged_in()(a), a.vendor(**SUNITA),
                              loan.review_loan(a.conn, loan.apply_loan(
                                  a.conn, a.vendor("Mohd. Salim", "9811122233", "salim123", years=4), 10000),
                                  2, "APPROVE", ""),
                              a.login("9876543210", "ramesh123"))),

    TestCase("TC-EMI-06", "EMI", "Late payment and default check (90 / 91 days overdue)",
             "Test that a loan becomes DEFAULTED only when an EMI is MORE than 90 days overdue, that it can still be "
             "repaid, and that a late payment lowers the Trust Score.",
             [RAMESH_PRE.replace(" and logged in", ""), "His loan #1 (Rs 15,000) is DISBURSED and no EMI is paid",
              f"EMI #1's due date is {dmy(D90)} (exactly 90 days ago)",
              "Bank officer Anil Sharma (9123456780 / bank123) is logged in"],
             [Step("Click 'Run default check (90+ days overdue)'", f"EMI #1 due {dmy(D90)} (90 days overdue)",
                   "Default check complete: 0 loan(s) marked DEFAULTED.", post("/officer/mark-defaults"),
                   "BVA - exactly 90 days: not defaulted"),
              Step("One day later, click 'Run default check' again", f"EMI #1 due {dmy(D91)} (91 days overdue)",
                   "Default check complete: 1 loan(s) marked DEFAULTED.",
                   lambda a: (a.conn.execute("UPDATE emi_installments SET due_date = ? WHERE installment_no = 1",
                                             (D91.isoformat(),)), a.conn.commit(),
                              post("/officer/mark-defaults")(a))[-1], "BVA - 91 days: defaulted"),
              Step(f"{CHECK} 1", "-", "Loan #1 DEFAULTED", loan_status),
              Step(f"Log in as Ramesh. {PAY}", "Installment #1, Amount = 1332.73", "EMI #1 paid late.",
                   as_user("9876543210", "ramesh123", pay(1, "1332.73")), "A defaulted loan can still be repaid"),
              Step("Read the Trust Score card", "-", "Trust Score 50/100, MEDIUM RISK", trust_card,
                   "0 of 1 on time: repayment = 0; 40 + 0 + 0 + 10")],
             ["Loan #1 is DEFAULTED; EMI #1 is PAID (late)"],
             ["FR-BNK-7", "BR-6", "FR-EMI-5", "FR-TS-2"],
             setup=lambda a: (a.disbursed_loan(),
                              a.conn.execute("UPDATE emi_installments SET due_date = ? WHERE installment_no = 1",
                                             (D90.isoformat(),)), a.conn.commit(),
                              a.login("9123456780", "bank123"))),
]

# Defects found by these test cases in the first version of the code (git commit 0ce1911) and fixed afterwards.
DEFECTS = [
    {"id": "DEF-01", "severity": "High",
     "found": "Typing 'nan' as a sale or loan amount crashed the app (HTTP 500 Internal Server Error); 'inf' gave a "
              "misleading message.",
     "cause": "Python's float() accepts 'nan' and 'inf'. NaN passed every comparison and SQLite stored it as NULL "
              "in a NOT NULL column.",
     "fix": "New helper parse_number() in database.py rejects values that are not finite numbers."},
    {"id": "DEF-02", "severity": "Medium",
     "found": "A sale dated 91 days ago (or 01-01-1900) was accepted.",
     "cause": "Only future dates were checked.",
     "fix": "vendor.log_daily_sale() rejects entries more than 90 days old (MAX_BACKDATE_DAYS); FR-VEN-5 updated."},
    {"id": "DEF-03", "severity": "High",
     "found": "Paying an EMI with amount 'nan' marked the installment PAID.",
     "cause": "Same as DEF-01: the 'less than EMI' check is False for NaN.",
     "fix": "loan.pay_emi() uses parse_number()."},
    {"id": "DEF-04", "severity": "Low",
     "found": "Names such as '12345' or a 51-character string were accepted at registration.",
     "cause": "The name was only checked for being non-empty.",
     "fix": "auth.validate_name(): letters, spaces, dots and apostrophes only, at most 50 characters; FR-AUTH-1 "
            "updated."},
    {"id": "DEF-05", "severity": "High",
     "found": "A customer or municipal officer could open any vendor's loan page and see the amount and EMIs.",
     "cause": "The /loan/<id> page only required a logged-in user and checked ownership for vendors only.",
     "fix": "Only the owning vendor and bank officers may open a loan page (LOAN_VIEW_ROLES in app.py)."},
    {"id": "DEF-06", "severity": "Low",
     "found": "Paying an EMI of a loan that does not exist, or of another vendor's loan, showed two error messages "
              "('Loan not found | Loan not found').",
     "cause": "The error page redirected to the loan page, which reported a second error.",
     "fix": "The pay_emi route redirects to the dashboard when the loan is missing or not the vendor's own."},
]
for d in DEFECTS:      # which test cases / steps found each defect
    d["cases"] = [f"{c.id} step {i}" for c in CASES for i, s in enumerate(c.steps, 1) if s.defect == d["id"]]
