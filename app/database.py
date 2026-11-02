"""
database.py - SQLite connection helper and schema for VendorSetu.

All modules receive a sqlite3 connection object, so the business logic can be
tested against an in-memory database without starting the web server.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendorsetu.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    phone            TEXT    NOT NULL UNIQUE,
    password_hash    TEXT    NOT NULL,
    role             TEXT    NOT NULL,          -- VENDOR / BANK_OFFICER / MUNICIPAL_OFFICER / CUSTOMER
    failed_attempts  INTEGER NOT NULL DEFAULT 0,
    is_locked        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vendor_profiles (
    vendor_id        INTEGER PRIMARY KEY REFERENCES users(user_id),
    business_type    TEXT    NOT NULL,
    vending_zone     TEXT    NOT NULL,
    years_vending    INTEGER NOT NULL DEFAULT 0,
    upi_id           TEXT,
    updated_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id        INTEGER NOT NULL REFERENCES users(user_id),
    sale_date        TEXT    NOT NULL,          -- ISO date YYYY-MM-DD
    amount           REAL    NOT NULL,
    payment_mode     TEXT    NOT NULL,          -- CASH / UPI
    UNIQUE (vendor_id, sale_date)
);

CREATE TABLE IF NOT EXISTS vouches (
    vouch_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id       INTEGER NOT NULL REFERENCES users(user_id),
    vendor_id        INTEGER NOT NULL REFERENCES users(user_id),
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (voucher_id, vendor_id)
);

CREATE TABLE IF NOT EXISTS loans (
    loan_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id        INTEGER NOT NULL REFERENCES users(user_id),
    tier             INTEGER NOT NULL,
    amount           REAL    NOT NULL,
    tenure_months    INTEGER NOT NULL,
    interest_rate    REAL    NOT NULL,
    trust_score      INTEGER NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'PENDING',
    officer_id       INTEGER REFERENCES users(user_id),
    remarks          TEXT,
    applied_on       TEXT    NOT NULL,
    disbursed_on     TEXT
);

CREATE TABLE IF NOT EXISTS emi_installments (
    emi_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id          INTEGER NOT NULL REFERENCES loans(loan_id),
    installment_no   INTEGER NOT NULL,
    due_date         TEXT    NOT NULL,
    emi_amount       REAL    NOT NULL,
    principal_part   REAL    NOT NULL,
    interest_part    REAL    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'DUE',   -- DUE / PAID
    paid_on          TEXT,
    paid_on_time     INTEGER,
    UNIQUE (loan_id, installment_no)
);
"""


def get_connection(path=DB_PATH):
    """Open a connection that returns rows as dict-like objects."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    """Create all tables if they do not exist yet."""
    conn.executescript(SCHEMA)
    conn.commit()


class ValidationError(Exception):
    """Raised by any module when user input breaks a business rule."""
