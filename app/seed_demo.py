"""
seed_demo.py - Resets the database and fills it with demo data for the evaluation.

    python seed_demo.py
"""
import os
from datetime import date, timedelta

from database import DB_PATH, get_connection, init_db
from modules import auth, loan, vendor

DEMO_USERS = [
    # name, phone, password, role, profile (business, zone, years, upi), days with sales in last 30
    ("Ramesh Kumar", "9876543210", "ramesh123", "VENDOR",
     ("Fruits & vegetables", "Sector 14 Market, Gurugram", 6, "ramesh@upi"), 26),
    ("Sunita Devi", "9812345670", "sunita123", "VENDOR",
     ("Tea & snacks stall", "Sector 14 Market, Gurugram", 2, "sunita@upi"), 10),
    ("Mohd. Salim", "9811122233", "salim123", "VENDOR",
     ("Chaat corner", "Sohna Road, Gurugram", 4, ""), 20),
    ("Anil Sharma", "9123456780", "bank123", "BANK_OFFICER", None, 0),
    ("Priya Mehta", "9988776655", "priya123", "CUSTOMER", None, 0),
    ("R. K. Verma", "9090909090", "muni123", "MUNICIPAL_OFFICER", None, 0),
]


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_connection()
    init_db(conn)
    today = date.today()
    ids = {}

    for name, phone, password, role, profile, sale_days in DEMO_USERS:
        uid = auth.register_user(conn, name, phone, password, role)
        ids[phone] = uid
        if profile:
            vendor.save_profile(conn, uid, *profile)
            # 90 days of history, `sale_days` active days in every 30-day window
            for i in (i for i in range(90) if i % 30 < sale_days):
                day = today - timedelta(days=i)
                amount = 1200 + (uid * 137 + i * 53) % 900          # deterministic, varied amounts
                vendor.log_daily_sale(conn, uid, day.isoformat(), amount, "UPI" if i % 3 else "CASH", today)

    # Peer vouching (Peer-Guarantor module data)
    for voucher, vendee in [("9812345670", "9876543210"), ("9811122233", "9876543210"), ("9876543210", "9812345670")]:
        conn.execute("INSERT INTO vouches (voucher_id, vendor_id) VALUES (?, ?)", (ids[voucher], ids[vendee]))
    conn.commit()

    # Sunita has a pending application so the bank officer has something to review
    loan.apply_loan(conn, ids["9812345670"], 10000, today)

    # Salim already has a disbursed loan with two EMIs paid, to show the EMI schedule
    officer = ids["9123456780"]
    start = today - timedelta(days=65)
    lid = loan.apply_loan(conn, ids["9811122233"], 15000, start)
    loan.review_loan(conn, lid, officer, "APPROVE", "Regular sales record")
    loan.disburse_loan(conn, lid, officer, start)
    for n, inst in enumerate(loan.get_installments(conn, lid)[:2], start=1):
        loan.pay_emi(conn, lid, n, inst["emi_amount"], date.fromisoformat(inst["due_date"]) - timedelta(days=2))

    conn.close()
    print("Demo database created at", DB_PATH)
    for name, phone, password, role, *_ in DEMO_USERS:
        print(f"  {role:<18} {phone}  /  {password:<10} ({name})")


if __name__ == "__main__":
    main()
