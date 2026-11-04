"""
Module 2 - Vendor Profile & Daily Sales Logging
SRS reference: Section 4.2 (FR-VEN-1 to FR-VEN-7)
"""
from datetime import date, timedelta

from database import ValidationError, parse_number

PAYMENT_MODES = ("CASH", "UPI")
MAX_DAILY_SALE = 100000          # FR-VEN-4: a street vendor's single-day sale above this is treated as a typo
MAX_BACKDATE_DAYS = 90           # FR-VEN-5: older entries (e.g. 1900-01-01) cannot be verified (defect DEF-02)


def save_profile(conn, vendor_id, business_type, vending_zone, years_vending, upi_id=""):
    """Create or update the vendor's business profile (FR-VEN-1, FR-VEN-2)."""
    business_type = (business_type or "").strip()
    vending_zone = (vending_zone or "").strip()
    if not business_type or not vending_zone:
        raise ValidationError("Business type and vending zone are required")
    try:
        years_vending = int(years_vending)
    except (TypeError, ValueError):
        raise ValidationError("Years of vending must be a number")
    if years_vending < 0 or years_vending > 60:
        raise ValidationError("Years of vending must be between 0 and 60")

    conn.execute(
        """INSERT INTO vendor_profiles (vendor_id, business_type, vending_zone, years_vending, upi_id)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(vendor_id) DO UPDATE SET
               business_type = excluded.business_type,
               vending_zone  = excluded.vending_zone,
               years_vending = excluded.years_vending,
               upi_id        = excluded.upi_id,
               updated_at    = CURRENT_TIMESTAMP""",
        (vendor_id, business_type, vending_zone, years_vending, (upi_id or "").strip()),
    )
    conn.commit()


def get_profile(conn, vendor_id):
    return conn.execute("SELECT * FROM vendor_profiles WHERE vendor_id = ?", (vendor_id,)).fetchone()


def log_daily_sale(conn, vendor_id, sale_date, amount, payment_mode, today=None):
    """Record one day's total sales (FR-VEN-3 to FR-VEN-6). Returns the sale_id."""
    today = today or date.today()
    try:
        sale_day = date.fromisoformat(str(sale_date))
    except ValueError:
        raise ValidationError("Enter a valid date (YYYY-MM-DD)")
    amount = parse_number(amount, "Sale amount must be a number")

    if amount <= 0:
        raise ValidationError("Sale amount must be greater than 0")
    if amount > MAX_DAILY_SALE:
        raise ValidationError("Sale amount cannot exceed Rs 1,00,000 per day")
    if sale_day > today:
        raise ValidationError("Sale date cannot be in the future")
    if (today - sale_day).days > MAX_BACKDATE_DAYS:
        raise ValidationError(f"Sale date cannot be more than {MAX_BACKDATE_DAYS} days old")
    if payment_mode not in PAYMENT_MODES:
        raise ValidationError("Payment mode must be CASH or UPI")
    if get_profile(conn, vendor_id) is None:
        raise ValidationError("Complete your vendor profile first")

    exists = conn.execute(
        "SELECT 1 FROM sales WHERE vendor_id = ? AND sale_date = ?", (vendor_id, sale_day.isoformat())
    ).fetchone()
    if exists:
        raise ValidationError("Sales already logged for this date")

    cur = conn.execute(
        "INSERT INTO sales (vendor_id, sale_date, amount, payment_mode) VALUES (?, ?, ?, ?)",
        (vendor_id, sale_day.isoformat(), amount, payment_mode),
    )
    conn.commit()
    return cur.lastrowid


def get_sales(conn, vendor_id, limit=30):
    return conn.execute(
        "SELECT * FROM sales WHERE vendor_id = ? ORDER BY sale_date DESC LIMIT ?", (vendor_id, limit)
    ).fetchall()


def sales_summary(conn, vendor_id, days=30, today=None):
    """Totals over the last `days` days, used by the dashboard and the trust score (FR-VEN-7)."""
    today = today or date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    row = conn.execute(
        """SELECT COUNT(*) AS active_days, COALESCE(SUM(amount), 0) AS total
           FROM sales WHERE vendor_id = ? AND sale_date BETWEEN ? AND ?""",
        (vendor_id, start, today.isoformat()),
    ).fetchone()
    active_days = row["active_days"]
    total = round(row["total"], 2)
    average = round(total / active_days, 2) if active_days else 0
    return {"active_days": active_days, "window_days": days, "total": total, "average": average}


def list_vendors(conn, zone=None):
    """Public vendor directory used by the customer page."""
    sql = """SELECT u.user_id, u.name, p.business_type, p.vending_zone, p.upi_id
             FROM users u JOIN vendor_profiles p ON p.vendor_id = u.user_id"""
    if zone:
        return conn.execute(sql + " WHERE p.vending_zone LIKE ? ORDER BY u.name", (f"%{zone}%",)).fetchall()
    return conn.execute(sql + " ORDER BY u.name").fetchall()
