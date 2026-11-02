"""
Module 1 - User Registration & Authentication
SRS reference: Section 4.1 (FR-AUTH-1 to FR-AUTH-7)
"""
import re

from werkzeug.security import check_password_hash, generate_password_hash

from database import ValidationError

ROLES = ("VENDOR", "BANK_OFFICER", "MUNICIPAL_OFFICER", "CUSTOMER")
MAX_FAILED_ATTEMPTS = 5

PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")       # Indian 10-digit mobile number


def validate_password(password):
    """FR-AUTH-3: at least 6 characters with at least one letter and one digit."""
    if len(password) < 6 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("Password must be at least 6 characters with letters and digits")


def register_user(conn, name, phone, password, role):
    """Create a new account and return its user_id."""
    name = (name or "").strip()
    phone = (phone or "").strip()

    if not name:
        raise ValidationError("Name is required")
    if not PHONE_PATTERN.match(phone):
        raise ValidationError("Enter a valid 10-digit mobile number")
    validate_password(password or "")
    if role not in ROLES:
        raise ValidationError("Invalid role selected")

    if conn.execute("SELECT 1 FROM users WHERE phone = ?", (phone,)).fetchone():
        raise ValidationError("Mobile number already registered")

    cur = conn.execute(
        "INSERT INTO users (name, phone, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, phone, generate_password_hash(password), role),
    )
    conn.commit()
    return cur.lastrowid


def login_user(conn, phone, password):
    """
    Check credentials and return the user row.
    After MAX_FAILED_ATTEMPTS wrong passwords the account is locked (FR-AUTH-6).
    """
    user = conn.execute("SELECT * FROM users WHERE phone = ?", ((phone or "").strip(),)).fetchone()
    if user is None:
        raise ValidationError("Invalid mobile number or password")
    if user["is_locked"]:
        raise ValidationError("Account locked after 5 failed attempts. Contact support")

    if not check_password_hash(user["password_hash"], password or ""):
        attempts = user["failed_attempts"] + 1
        locked = 1 if attempts >= MAX_FAILED_ATTEMPTS else 0
        conn.execute(
            "UPDATE users SET failed_attempts = ?, is_locked = ? WHERE user_id = ?",
            (attempts, locked, user["user_id"]),
        )
        conn.commit()
        if locked:
            raise ValidationError("Account locked after 5 failed attempts. Contact support")
        raise ValidationError("Invalid mobile number or password")

    conn.execute("UPDATE users SET failed_attempts = 0 WHERE user_id = ?", (user["user_id"],))
    conn.commit()
    return user


def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
