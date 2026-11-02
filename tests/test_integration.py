"""
Integration test: drives the Flask app end-to-end through its HTTP routes
(register -> login -> profile -> sales -> apply -> officer approve/disburse -> pay EMI).

    python -m pytest tests -v
"""
import re
from datetime import date, timedelta

import pytest

import test_cases  # noqa: F401  (puts app/ on sys.path)
import app as app_module
from database import get_connection
from modules import auth, vendor


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "it.db")
    monkeypatch.setattr(app_module, "get_connection", lambda: get_connection(db_file))
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        c.db_file = db_file
        yield c


def flashes(resp):
    return re.findall(r'class="flash \w+">([^<]+)<', resp.get_data(as_text=True))


def login(c, phone, pw):
    c.get("/logout")
    return c.post("/login", data={"phone": phone, "password": pw}, follow_redirects=True)


def test_end_to_end_loan_flow(client):
    c = client
    r = c.post("/register", data={"name": "Ramesh Kumar", "phone": "9876543210", "password": "ramesh123",
                                  "confirm_password": "ramesh123", "role": "VENDOR"}, follow_redirects=True)
    assert flashes(r) == ["Registration successful. Please log in."]
    r = c.post("/register", data={"name": "Anil Sharma", "phone": "9123456780", "password": "bank123",
                                  "confirm_password": "bank123", "role": "BANK_OFFICER"}, follow_redirects=True)
    assert flashes(r) == ["Registration successful. Please log in."]

    assert flashes(login(c, "9876543210", "ramesh123")) == ["Welcome, Ramesh Kumar!"]
    r = c.post("/vendor/profile", data={"business_type": "Fruits", "vending_zone": "Sector 14",
                                        "years_vending": "5", "upi_id": "r@upi"}, follow_redirects=True)
    assert flashes(r) == ["Profile saved."]

    r = c.post("/vendor/sales", data={"sale_date": date.today().isoformat(), "amount": "1500",
                                      "payment_mode": "UPI"}, follow_redirects=True)
    assert flashes(r) == ["Sale logged. Your trust score has been updated."]
    # back-fill 29 more days directly so the vendor reaches the eligible score
    conn = get_connection(c.db_file)
    vid = auth.login_user(conn, "9876543210", "ramesh123")["user_id"]
    for i in range(1, 30):
        vendor.log_daily_sale(conn, vid, (date.today() - timedelta(days=i)).isoformat(), 1500, "CASH")
    conn.close()

    r = c.post("/vendor/loan/apply", data={"amount": "15000"}, follow_redirects=True)
    assert flashes(r) == ["Loan application #1 submitted. Status: PENDING."]

    login(c, "9123456780", "bank123")
    r = c.post("/officer/loan/1/review", data={"decision": "APPROVE", "remarks": ""}, follow_redirects=True)
    assert flashes(r) == ["Loan #1 APPROVED."]
    r = c.post("/officer/loan/1/disburse", follow_redirects=True)
    assert flashes(r) == ["Loan #1 disbursed. 12 EMIs of Rs 1332.73 scheduled."]

    login(c, "9876543210", "ramesh123")
    r = c.post("/vendor/loan/1/pay/1", data={"amount": "1332.73"}, follow_redirects=True)
    assert flashes(r) == ["EMI #1 paid on time."]


def test_role_based_access(client):
    c = client
    c.post("/register", data={"name": "Priya", "phone": "9988776655", "password": "priya123",
                              "confirm_password": "priya123", "role": "CUSTOMER"})
    login(c, "9988776655", "priya123")
    r = c.get("/officer", follow_redirects=True)
    assert flashes(r) == ["You are not allowed to open that page."]
    c.get("/logout")
    r = c.get("/dashboard", follow_redirects=True)
    assert flashes(r)[-1] == "Please log in first."
