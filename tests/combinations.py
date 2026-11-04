"""
combinations.py - Combination (decision-table) testing of every form in VendorSetu.

For each form we choose several valid and invalid values for EVERY field and submit ALL combinations
(the cartesian product) through the web app. For every combination an independent "oracle" written from
the SRS rules says what the screen must show; the test passes only if every combination matches, the app
never crashes (HTTP 500) and rejected input never changes the database.

    python tests/run_test_cases.py      (prints the summary and stores it for the test document)
    python -m pytest tests -v           (test_combinations.py runs the same suites)
"""
import itertools
import math
from datetime import date, datetime, timedelta

from test_cases import App, TODAY, count
from modules import auth, loan, vendor

# --------------------------------------------------------------------------- the oracle (SRS rules)
WEAK = "Password must be at least 6 characters with letters and digits"
ALLOWED_NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .'")


def is_number(text):
    try:
        return math.isfinite(float(text))
    except (TypeError, ValueError):
        return False


def is_date(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def expect_register(name, phone, password, confirm, role):
    """SRS FR-AUTH-1..3, checked in the order of the form: passwords, name, mobile, password, role."""
    name, phone = name.strip(), phone.strip()
    if password != confirm:
        return "Passwords do not match"
    if not name:
        return "Name is required"
    if len(name) > 50:
        return "Name must be at most 50 characters"
    if not name[0].isalpha() or not set(name) <= ALLOWED_NAME_CHARS:
        return "Name can contain only letters, spaces and dots"
    if not (len(phone) == 10 and phone.isdigit() and phone[0] in "6789"):
        return "Enter a valid 10-digit mobile number"
    if len(password) < 6 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return WEAK
    if role not in ("VENDOR", "BANK_OFFICER", "MUNICIPAL_OFFICER", "CUSTOMER"):
        return "Invalid role selected"
    return "Registration successful. Please log in."


def expect_sale(sale_date, amount, mode):
    """SRS FR-VEN-3..5."""
    if not is_date(sale_date):
        return "Enter a valid date (YYYY-MM-DD)"
    if not is_number(amount):
        return "Sale amount must be a number"
    value, day = float(amount), date.fromisoformat(sale_date)
    if value <= 0:
        return "Sale amount must be greater than 0"
    if value > 100000:
        return "Sale amount cannot exceed Rs 1,00,000 per day"
    if day > TODAY:
        return "Sale date cannot be in the future"
    if (TODAY - day).days > 90:
        return "Sale date cannot be more than 90 days old"
    if mode not in ("CASH", "UPI"):
        return "Payment mode must be CASH or UPI"
    return "Sale logged. Your trust score has been updated."


def expect_profile(business, zone, years):
    """SRS FR-VEN-1, FR-VEN-2."""
    if not business.strip() or not zone.strip():
        return "Business type and vending zone are required"
    if not years.strip().lstrip("-").isdigit():
        return "Years of vending must be a number"
    if not 0 <= int(years) <= 60:
        return "Years of vending must be between 0 and 60"
    return "Profile saved."


def expect_loan(state, amount):
    """SRS FR-LN-1..5, FR-TS-5."""
    if not is_number(amount):
        return "Loan amount must be a number"
    if state == "has a pending loan":
        return "You already have an active loan"
    if state == "no profile":
        return "Complete your vendor profile first"
    if state == "score 20":
        return "Trust score 20 is below 40. Not eligible"
    if float(amount) <= 0:
        return "Loan amount must be greater than 0"
    if float(amount) > 15000:
        return "Amount exceeds Tier 1 limit of Rs 15,000"
    return "Loan application #1 submitted. Status: PENDING."


def expect_emi(installment, amount):
    """SRS FR-EMI-1..4; nothing is paid yet, EMI = Rs 1332.73."""
    if not 1 <= installment <= 12:
        return "Installment not found"
    if installment > 1:
        return "Pay earlier installment #1 first"
    if not is_number(amount):
        return "Payment amount must be a number"
    if float(amount) < 1332.73:
        return "Amount is less than EMI due of Rs 1332.73"
    return "EMI #1 paid on time."


# --------------------------------------------------------------------------- running a suite
class AppPool:
    """One fresh app per key (vendor state / role), created on first use and reused for its combinations."""

    def __init__(self, setup):
        self.setup, self.apps = setup, {}

    def __enter__(self):
        return self

    def get(self, key):
        if key not in self.apps:
            self.apps[key] = App().__enter__()
            self.setup(self.apps[key], key)
        return self.apps[key]

    def __exit__(self, *exc):
        for a in self.apps.values():
            a.__exit__(None, None, None)



def _suite(name, values, combos, attempt):
    """values: {field: [values tried]}; attempt(combo) -> (actual, expected, database_ok)."""
    total = matched = crashes = 0
    mismatches = []
    for combo in combos:
        actual, expected, db_ok = attempt(combo)
        total += 1
        crashes += actual.startswith("HTTP 5")
        if actual == expected and db_ok:
            matched += 1
        elif len(mismatches) < 4:
            mismatches.append({"input": ", ".join(_show(v) for v in combo), "expected": expected,
                               "actual": actual + ("" if db_ok else " [database changed]")})
    return {"form": name, "fields": _fields(**values),
            "values": {k: [_show(x) for x in vs] for k, vs in values.items()},
            "combinations": total, "matched": matched, "crashes": crashes,
            "mismatches": mismatches}


def _show(x):
    """How a tried value is printed: 'abc', '' (empty), 'A' x 51 for long repeated strings."""
    if isinstance(x, str) and len(x) > 20 and len(set(x)) == 1:
        return f"'{x[0]}' x {len(x)}"
    return repr(x) if isinstance(x, str) else str(x)


def _fields(**values):
    return " x ".join(f"{k} ({len(v)})" for k, v in values.items())


def register_suite():
    v = dict(Name=["Ramesh Kumar", "Mohd. Salim", "", "12345", "A" * 51],
             Mobile=["9876543210", "987654321", "98765432101", "5876543210", "98765abcde", ""],
             Password=["ramesh123", "ab123", "abcdefgh", "12345678", ""],
             Confirm=["same", "different"],
             Role=["VENDOR", "BANK_OFFICER", "", "ADMIN"])
    with App() as a:
        def attempt(c):
            name, phone, pw, confirm, role = c
            confirm = pw if confirm == "same" else pw + "x"
            a.conn.execute("DELETE FROM users")
            a.conn.commit()
            actual = a.post("/register", name=name, phone=phone, password=pw, confirm_password=confirm, role=role)
            expected = expect_register(name, phone, pw, confirm, role)
            stored = count(a, "users")
            return actual, expected, stored == (1 if expected.startswith("Registration successful") else 0)
        return _suite("Register", v, itertools.product(*v.values()), attempt)


def login_suite():
    v = dict(Mobile=["9876543210", " 9876543210 ", "9000000001", "", "' OR '1'='1"],
             Password=["ramesh123", "RAMESH123", "ramesh124", "", "' OR '1'='1"])
    with App() as a:
        a.vendor(sale_days=0)

        def attempt(c):
            phone, pw = c
            a.conn.execute("UPDATE users SET failed_attempts = 0, is_locked = 0")
            a.conn.commit()
            actual = a.login(phone, pw)
            ok = phone.strip() == "9876543210" and pw == "ramesh123"
            expected = "Welcome, Ramesh Kumar!" if ok else "Invalid mobile number or password"
            return actual, expected, ("Namaste," in a.page) == ok
        return _suite("Log in", v, itertools.product(*v.values()), attempt)


def sale_suite():
    v = dict(Date=[TODAY.isoformat(), (TODAY - timedelta(days=1)).isoformat(), (TODAY - timedelta(days=90)).isoformat(),
                   (TODAY - timedelta(days=91)).isoformat(), (TODAY + timedelta(days=1)).isoformat(), "2026-02-30",
                   "", "abc"],
             Amount=["1500", "1", " 250 ", "1e3", "100000", "100000.01", "0", "-5", "abc", "", "nan", "inf"],
             Mode=["UPI", "CASH", "upi", "CARD", ""])
    with App() as a:
        a.vendor(sale_days=0)
        a.login("9876543210", "ramesh123")

        def attempt(c):
            d, amount, mode = c
            a.conn.execute("DELETE FROM sales")
            a.conn.commit()
            actual = a.post("/vendor/sales", sale_date=d, amount=amount, payment_mode=mode)
            expected = expect_sale(d, amount, mode)
            return actual, expected, count(a, "sales") == (1 if expected.startswith("Sale logged") else 0)
        return _suite("Daily sales", v, itertools.product(*v.values()), attempt)


def profile_suite():
    v = dict(Business=["Fruits", "", "   "], Zone=["Sector 14", ""],
             Years=["0", "5", "60", "61", "-1", "abc", "", "2.5"])
    with App() as a:
        a.vendor(profile=False, sale_days=0)
        a.login("9876543210", "ramesh123")

        def attempt(c):
            business, zone, years = c
            a.conn.execute("DELETE FROM vendor_profiles")
            a.conn.commit()
            actual = a.post("/vendor/profile", business_type=business, vending_zone=zone, years_vending=years,
                            upi_id="")
            expected = expect_profile(business, zone, years)
            return actual, expected, count(a, "vendor_profiles") == (1 if expected == "Profile saved." else 0)
        return _suite("Business profile", v, itertools.product(*v.values()), attempt)


def loan_suite():
    v = dict(Vendor=["eligible (score 70)", "score 20", "no profile", "has a pending loan"],
             Amount=["15000", "1", "15000.01", "0", "-1", "abc", "", "nan", "inf"])

    def setup(a, state):
        if state == "score 20":
            a.vendor(years=0, sale_days=0)
        elif state == "no profile":
            a.vendor(profile=False, sale_days=0)
        else:
            a.vendor()
        a.login("9876543210", "ramesh123")

    with AppPool(setup) as pool:
        def attempt(c):
            state, amount = c
            a = pool.get(state)
            a.conn.execute("DELETE FROM loans")
            a.conn.execute("DELETE FROM sqlite_sequence WHERE name = 'loans'")      # next loan is #1 again
            a.conn.commit()
            if state == "has a pending loan":
                loan.apply_loan(a.conn, 1, 15000)
            before = count(a, "loans")
            actual = a.post("/vendor/loan/apply", amount=amount)
            expected = expect_loan(state, amount)
            return actual, expected, count(a, "loans") == before + (1 if "submitted" in expected else 0)
        return _suite("Loan application", v, itertools.product(*v.values()), attempt)


def emi_suite():
    v = dict(Installment=[1, 2, 12, 13, 0],
             Amount=["1332.73", "1332.72", "5000", "0", "-1", "abc", "", "nan", "inf"])
    with App() as a:
        a.disbursed_loan()
        a.login("9876543210", "ramesh123")

        def attempt(c):
            n, amount = c
            a.conn.execute("UPDATE emi_installments SET status = 'DUE', paid_on = NULL, paid_on_time = NULL")
            a.conn.execute("UPDATE loans SET status = 'DISBURSED'")
            a.conn.commit()
            actual = a.post(f"/vendor/loan/1/pay/{n}", amount=amount)
            expected = expect_emi(n, amount)
            paid = a.conn.execute("SELECT COUNT(*) FROM emi_installments WHERE status = 'PAID'").fetchone()[0]
            return actual, expected, paid == (1 if "paid on time" in expected else 0)
        return _suite("EMI payment", v, itertools.product(*v.values()), attempt)


# role x page access matrix ------------------------------------------------------------------
ROLES = {"Guest (not logged in)": None, "Owner vendor (Ramesh)": ("9876543210", "ramesh123"),
         "Other vendor (Sunita)": ("9812345670", "sunita123"), "Bank officer": ("9123456780", "bank123"),
         "Customer": ("9988776655", "priya123"), "Municipal officer": ("9090909090", "muni123")}
REQUESTS = [("GET", "/dashboard"), ("GET", "/officer"), ("GET", "/loan/1"), ("POST", "/vendor/sales"),
            ("POST", "/vendor/profile"), ("POST", "/vendor/loan/apply"), ("POST", "/vendor/loan/1/pay/1"),
            ("POST", "/officer/loan/1/review"), ("POST", "/officer/loan/1/disburse"),
            ("POST", "/officer/mark-defaults")]
DENIED, LOGIN = "You are not allowed to open that page.", "Please log in first."
OWN = ("You can only view your own loans.", "You can only pay your own loans")


def expect_access(role, url):
    """SRS FR-AUTH-7, FR-BNK-4, NFR-SEC-7: who may open what (loan #1 belongs to Ramesh)."""
    if role.startswith("Guest"):
        return "login required"
    if url == "/dashboard":
        return "allowed"
    if url.startswith("/officer"):
        return "allowed" if role == "Bank officer" else "denied"
    if url == "/loan/1":
        return {"Owner vendor (Ramesh)": "allowed", "Bank officer": "allowed",
                "Other vendor (Sunita)": "own data only"}.get(role, "denied")
    if url == "/vendor/loan/1/pay/1":
        return {"Owner vendor (Ramesh)": "allowed", "Other vendor (Sunita)": "own data only"}.get(role, "denied")
    return "allowed" if "vendor" in role else "denied"          # the vendor's own forms


def classify(msg):
    if LOGIN in msg:
        return "login required"
    if DENIED in msg:
        return "denied"
    if any(o in msg for o in OWN):
        return "own data only"
    if msg.startswith("HTTP 5"):
        return msg
    return "allowed"


def _snapshot(a):
    """Everything a request could change; a refused request must leave it identical."""
    return [a.conn.execute(f"SELECT * FROM {t}").fetchall()
            for t in ("vendor_profiles", "sales", "loans", "emi_installments")]


def access_suite():
    def setup(a, role):
        vid = a.vendor()
        a.vendor(name="Sunita Devi", phone="9812345670", password="sunita123", years=0, sale_days=0)
        oid = a.officer()
        auth.register_user(a.conn, "Priya Mehta", "9988776655", "priya123", "CUSTOMER")
        auth.register_user(a.conn, "R K Verma", "9090909090", "muni123", "MUNICIPAL_OFFICER")
        lid = loan.apply_loan(a.conn, vid, 15000)
        loan.review_loan(a.conn, lid, oid, "APPROVE", "")
        loan.disburse_loan(a.conn, lid, oid)
        if ROLES[role]:
            a.login(*ROLES[role])

    with AppPool(setup) as pool:
        def attempt(c):
            role, (method, url) = c
            a = pool.get(role)
            before = _snapshot(a)
            if method == "GET":
                msg = a.get(url)
            else:
                msg = a.post(url, sale_date=TODAY.isoformat(), amount="1332.73", payment_mode="UPI",
                             business_type="Fruits", vending_zone="Sector 14", years_vending="5", decision="APPROVE")
            expected = expect_access(role, url)
            return classify(msg), expected, expected == "allowed" or _snapshot(a) == before
        return _suite("Role x page access", {"Role": list(ROLES), "Request": [f"{m} {u}" for m, u in REQUESTS]},
                      itertools.product(ROLES, REQUESTS), attempt)


SUITES = [register_suite, login_suite, profile_suite, sale_suite, loan_suite, emi_suite, access_suite]


def run_all(verbose=True):
    results = []
    for suite in SUITES:
        r = suite()
        results.append(r)
        if verbose:
            status = "PASS" if r["matched"] == r["combinations"] else "FAIL"
            print(f"  {r['form']:<20} {r['combinations']:>5} combinations  {r['matched']:>5} matched  "
                  f"{r['crashes']:>3} crashes  {status}")
            for m in r["mismatches"]:
                print(f"      input {m['input']}\n        expected: {m['expected']}\n        actual:   {m['actual']}")
    return results


if __name__ == "__main__":
    run_all()
