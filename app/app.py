"""
app.py - Flask web interface for VendorSetu.

Run:  python app.py      then open http://127.0.0.1:5000
Demo accounts are created by:  python seed_demo.py
"""
import os
from collections import Counter
from datetime import date, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from database import ValidationError, get_connection, init_db
from modules import auth, credit_score, loan, vendor

app = Flask(__name__)
app.secret_key = os.environ.get("VENDORSETU_SECRET", "dev-only-secret-change-in-production")

ROLE_LABELS = {
    "VENDOR": "Street Vendor",
    "BANK_OFFICER": "Bank / NBFC Officer",
    "MUNICIPAL_OFFICER": "Municipal Officer",
    "CUSTOMER": "Customer",
}


# ---------------------------------------------------------------- request helpers
def db():
    if "db" not in g:
        g.db = get_connection()
        init_db(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.context_processor
def inject_globals():
    return {"current_user": g.get("user"), "ROLE_LABELS": ROLE_LABELS}


@app.template_filter("initials")
def initials(name):
    """'Ramesh Kumar' -> 'RK' for avatar circles."""
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            g.user = auth.get_user(db(), user_id) if user_id else None
            if g.user is None:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))
            if role and g.user["role"] != role:
                flash("You are not allowed to open that page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------- Module 1: authentication
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        try:
            if f.get("password") != f.get("confirm_password"):
                raise ValidationError("Passwords do not match")
            auth.register_user(db(), f.get("name"), f.get("phone"), f.get("password"), f.get("role"))
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except ValidationError as e:
            flash(str(e), "error")
    return render_template("register.html", roles=auth.ROLES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            user = auth.login_user(db(), request.form.get("phone"), request.form.get("password"))
            session.clear()
            session["user_id"] = user["user_id"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        except ValidationError as e:
            flash(str(e), "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = g.user["role"]
    if role == "VENDOR":
        return vendor_dashboard()
    if role == "BANK_OFFICER":
        return redirect(url_for("officer_dashboard"))
    if role == "MUNICIPAL_OFFICER":
        vendors = vendor.list_vendors(db())
        return render_template("municipal_dashboard.html", vendors=vendors,
                               zones={v["vending_zone"] for v in vendors})
    zone = request.args.get("zone", "").strip()
    return render_template("customer_dashboard.html", vendors=vendor.list_vendors(db(), zone or None), zone=zone)


# ---------------------------------------------------------------- Modules 2 & 3: vendor profile, sales, trust score
def vendor_dashboard():
    conn, vid = db(), g.user["user_id"]
    today = date.today()
    profile = vendor.get_profile(conn, vid)
    trust = credit_score.get_trust_score(conn, vid) if profile else None
    loans = loan.get_loans(conn, vid)
    tier = loan.eligible_tier(conn, vid)

    # last 14 days of sales for the bar chart (0 on days with no entry)
    sales = vendor.get_sales(conn, vid)
    by_day = {s["sale_date"]: s["amount"] for s in sales}
    chart = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        chart.append({"label": day.strftime("%d %b"), "amount": by_day.get(day.isoformat(), 0)})

    next_emi = None
    for l in loans:
        if l["status"] in ("DISBURSED", "DEFAULTED"):
            next_emi = next((e for e in loan.get_installments(conn, l["loan_id"]) if e["status"] == "DUE"), None)
            break

    return render_template(
        "vendor_dashboard.html",
        profile=profile,
        sales=sales,
        summary=vendor.sales_summary(conn, vid),
        trust=trust,
        component_max=credit_score.COMPONENT_MAX,
        chart=chart,
        chart_max=max([d["amount"] for d in chart] + [1]),
        loans=loans,
        next_emi=next_emi,
        tier=tier,
        tiers=loan.TIERS,
        tier_limit=loan.TIERS[tier],
        today=today.isoformat(),
    )


@app.route("/vendor/profile", methods=["POST"])
@login_required("VENDOR")
def save_profile():
    f = request.form
    try:
        vendor.save_profile(db(), g.user["user_id"], f.get("business_type"), f.get("vending_zone"),
                            f.get("years_vending"), f.get("upi_id"))
        flash("Profile saved.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))


@app.route("/vendor/sales", methods=["POST"])
@login_required("VENDOR")
def log_sale():
    f = request.form
    try:
        vendor.log_daily_sale(db(), g.user["user_id"], f.get("sale_date"), f.get("amount"), f.get("payment_mode"))
        flash("Sale logged. Your trust score has been updated.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- Module 4: loans and EMI
@app.route("/vendor/loan/apply", methods=["POST"])
@login_required("VENDOR")
def apply_loan():
    try:
        loan_id = loan.apply_loan(db(), g.user["user_id"], request.form.get("amount"))
        flash(f"Loan application #{loan_id} submitted. Status: PENDING.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))


@app.route("/vendor/loan/<int:loan_id>/withdraw", methods=["POST"])
@login_required("VENDOR")
def withdraw_loan(loan_id):
    try:
        loan.withdraw_loan(db(), loan_id, g.user["user_id"])
        flash(f"Application #{loan_id} withdrawn.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))


@app.route("/loan/<int:loan_id>")
@login_required()
def loan_detail(loan_id):
    try:
        record = loan.get_loan(db(), loan_id)
    except ValidationError as e:
        flash(str(e), "error")
        return redirect(url_for("dashboard"))
    if g.user["role"] == "VENDOR" and record["vendor_id"] != g.user["user_id"]:
        flash("You can only view your own loans.", "error")
        return redirect(url_for("dashboard"))
    installments = loan.get_installments(db(), loan_id)
    paid = [e for e in installments if e["status"] == "PAID"]
    return render_template("loan_detail.html", loan=record, installments=installments,
                           borrower=auth.get_user(db(), record["vendor_id"]),
                           paid=len(paid),
                           paid_amount=sum(e["emi_amount"] for e in paid),
                           outstanding=sum(e["emi_amount"] for e in installments if e["status"] == "DUE"))


@app.route("/vendor/loan/<int:loan_id>/pay/<int:installment_no>", methods=["POST"])
@login_required("VENDOR")
def pay_emi(loan_id, installment_no):
    try:
        if loan.get_loan(db(), loan_id)["vendor_id"] != g.user["user_id"]:
            raise ValidationError("You can only pay your own loans")
        result = loan.pay_emi(db(), loan_id, installment_no, request.form.get("amount"))
        msg = f"EMI #{installment_no} paid {'on time' if result['on_time'] else 'late'}."
        if result["loan_closed"]:
            msg += " Loan fully repaid - you are now eligible for the next tier!"
        flash(msg, "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("loan_detail", loan_id=loan_id))


@app.route("/officer")
@login_required("BANK_OFFICER")
def officer_dashboard():
    loans = loan.all_loans_for_officer(db())
    return render_template("officer_dashboard.html", loans=loans, counts=Counter(l["status"] for l in loans))


@app.route("/officer/loan/<int:loan_id>/review", methods=["POST"])
@login_required("BANK_OFFICER")
def review_loan(loan_id):
    try:
        status = loan.review_loan(db(), loan_id, g.user["user_id"], request.form.get("decision"),
                                  request.form.get("remarks"))
        flash(f"Loan #{loan_id} {status}.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("officer_dashboard"))


@app.route("/officer/loan/<int:loan_id>/disburse", methods=["POST"])
@login_required("BANK_OFFICER")
def disburse_loan(loan_id):
    try:
        schedule = loan.disburse_loan(db(), loan_id, g.user["user_id"])
        flash(f"Loan #{loan_id} disbursed. {len(schedule)} EMIs of Rs {schedule[0]['emi_amount']:.2f} scheduled.",
              "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("officer_dashboard"))


@app.route("/officer/mark-defaults", methods=["POST"])
@login_required("BANK_OFFICER")
def mark_defaults():
    count = loan.mark_defaults(db())
    flash(f"Default check complete: {count} loan(s) marked DEFAULTED.", "success")
    return redirect(url_for("officer_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
