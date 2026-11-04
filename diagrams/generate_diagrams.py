"""
generate_diagrams.py - Draws every analysis/design diagram used in the SRS.

    python diagrams/generate_diagrams.py

Output PNGs are written next to this script.
"""
import os

from uml import (INK, actor, arrow, canvas, datastore, diamond, entity, ellipse_edge, final, flow,
                 initial, polyline, process, save, state, text, uc_edge, uml_class, usecase)
from matplotlib.patches import Rectangle

OUT = os.path.dirname(os.path.abspath(__file__))


def out(name):
    return os.path.join(OUT, name)


# ====================================================================== USE CASE
def use_case_diagram():
    W, H = 22.5, 17.5
    fig, ax = canvas(W, H, "Use Case Diagram - VendorSetu")
    bx0, bx1, by0, by1 = 4.3, 17.7, 0.4, 16.4
    ax.add_patch(Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fill=False, ec=INK, lw=1.8))
    text(ax, (bx0 + bx1) / 2, by1 - 0.4, "VendorSetu: Street Vendor Formalization & Micro-Credit Platform",
         fontweight="bold")

    vendor_a = actor(ax, 2.0, 9.0, "Street Vendor")
    peer = actor(ax, 2.0, 2.4, "Peer Guarantor")
    bank = actor(ax, 20.3, 11.0, "Bank / NBFC\nOfficer")
    muni = actor(ax, 20.3, 6.0, "Municipal\nOfficer")
    cust = actor(ax, 20.3, 1.6, "Customer")

    login = usecase(ax, 11.0, 15.0, "Register / Login")

    L, M, R = 7.1, 11.0, 14.9
    vendor_ucs = [
        usecase(ax, L, 13.4, "Manage Profile"),
        usecase(ax, L, 12.1, "Log Daily Sales"),
        usecase(ax, L, 10.8, "View Trust Score"),
        usecase(ax, L, 9.5, "Apply for Loan"),
        usecase(ax, L, 8.2, "Repay EMI"),
        usecase(ax, L, 6.9, "Apply / Renew\nVending Licence"),
        usecase(ax, L, 5.6, "View Vending\nZone Map"),
    ]
    view_ts, apply_loan = vendor_ucs[2], vendor_ucs[3]
    vouch = usecase(ax, L, 2.4, "Vouch for Peer\nVendor")

    calc_ts = usecase(ax, M, 10.15, "Calculate\nTrust Score")
    gen_emi = usecase(ax, M, 12.9, "Generate EMI\nSchedule")
    rate = usecase(ax, M, 1.3, "Rate Hygiene\n& Service")

    review = usecase(ax, R, 13.0, "Review Loan\nApplication")
    disburse = usecase(ax, R, 11.7, "Disburse Loan")
    track = usecase(ax, R, 10.4, "Track Repayments\n& Defaults")
    approve_lic = usecase(ax, R, 7.6, "Approve / Renew\nLicence")
    dispute = usecase(ax, R, 6.3, "Log Dispute /\nEviction Case")
    locate = usecase(ax, R, 3.9, "Locate Nearby\nVendors")
    pay = usecase(ax, R, 2.6, "Pay Vendor\nDigitally")

    def assoc(act, uc):
        # end on the ellipse's near side so fan-out lines never cut through neighbouring use cases
        side = -1 if act["x"] < uc["c"][0] else 1
        arrow(ax, act["mid"], (uc["c"][0] + side * uc["a"], uc["c"][1]), head="none")

    for uc in vendor_ucs:
        assoc(vendor_a, uc)
    assoc(peer, vouch)
    for uc in (review, disburse, track):
        assoc(bank, uc)
    for uc in (approve_lic, dispute):
        assoc(muni, uc)
    for uc in (locate, pay, rate):
        assoc(cust, uc)

    # Peer guarantor is a specialised vendor (actor generalisation)
    arrow(ax, peer["top"], (2.0, vendor_a["y"] - 1.0), head="hollow")

    # Every primary actor uses Register / Login (routed around the use cases)
    def to_login(start, via_x, y):
        end = ellipse_edge(*login["c"], login["a"], login["b"], via_x, y)
        end = (end[0], y)
        polyline(ax, [start, (via_x, start[1]), (via_x, y), end], head="none")

    tx = 11.0
    polyline(ax, [vendor_a["top"], (2.0, 15.0), uc_edge(login, (2.0, 15.0))], head="none")
    for act, vx, y in ((bank, 21.4, 15.25), (muni, 21.8, 15.0), (cust, 22.2, 14.75)):
        start = (act["x"] + 0.4, act["y"] + 0.8)
        dy = y - login["c"][1]
        half = login["a"] * (1 - (dy / login["b"]) ** 2) ** 0.5
        polyline(ax, [start, (vx, start[1]), (vx, y), (tx + half, y)], head="none")

    # «include» / «extend»
    def dep(a, b, label):
        p, q = uc_edge(a, b["c"]), uc_edge(b, a["c"])
        arrow(ax, p, q, head="open", dashed=True)
        text(ax, (p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 0.22, label, size=9, bg=True, style="italic")

    dep(view_ts, calc_ts, "«include»")
    dep(apply_loan, calc_ts, "«include»")
    dep(disburse, gen_emi, "«include»")
    dep(rate, pay, "«extend»")

    save(fig, out("01_use_case_diagram.png"))


# ====================================================================== CLASS
def class_diagram():
    W, H = 26.6, 26.2
    fig, ax = canvas(W, H, "Class Diagram - VendorSetu", u=0.48)   # tighter scale = larger text in the SRS
    d = 2.2      # vertical offset applied to every row

    user = uml_class(ax, 10.4, 22.6 + d, 5.4, "User",
                     ["- userId : int", "- name : String", "- phone : String", "- passwordHash : String",
                      "- role : Role", "- failedAttempts : int", "- isLocked : bool"],
                     ["+ register() : int", "+ login(phone, pwd) : User", "+ logout() : void"], stereo="abstract")

    cust = uml_class(ax, 0.4, 16.0 + d, 4.6, "Customer", ["- location : GeoPoint"],
                     ["+ locateVendors(zone)", "+ payVendor(v, amt)", "+ rateVendor(v)"])
    ven = uml_class(ax, 6.0, 16.0 + d, 5.6, "Vendor",
                    ["- businessType : String", "- vendingZone : String", "- yearsVending : int", "- upiId : String"],
                    ["+ saveProfile()", "+ logSale(date, amt, mode)", "+ getTrustScore() : int",
                     "+ applyLoan(amount) : Loan", "+ payEMI(loan, n)"])
    bank = uml_class(ax, 13.6, 16.0 + d, 5.0, "BankOfficer", ["- bankName : String", "- branchCode : String"],
                     ["+ reviewLoan(loan, dec)", "+ disburseLoan(loan)", "+ markDefaults()"])
    muni = uml_class(ax, 20.4, 16.0 + d, 5.2, "MunicipalOfficer", ["- wardNo : String"],
                     ["+ approveLicence(app)", "+ logCase(vendor, type)"])

    rating = uml_class(ax, 0.4, 10.2 + d, 4.6, "Rating",
                       ["- ratingId : int", "- hygieneStars : int", "- serviceStars : int", "- comment : String"],
                       ["+ submit()"])
    sale = uml_class(ax, 5.6, 10.2 + d, 4.6, "SaleRecord",
                     ["- saleId : int", "- saleDate : Date", "- amount : float", "- paymentMode : Mode"],
                     ["+ validate() : bool"])
    vouch = uml_class(ax, 10.7, 10.2 + d, 3.5, "Vouch",
                      ["- vouchId : int", "- voucherId : int", "- date : Date"], [])
    loan = uml_class(ax, 14.6, 10.2 + d, 5.4, "Loan",
                     ["- loanId : int", "- tier : int", "- amount : float", "- tenureMonths : int",
                      "- interestRate : float", "- trustScore : int", "- status : LoanStatus", "- appliedOn : Date"],
                     ["+ submit()", "+ approve(officer)", "+ reject(remarks)", "+ disburse() : EMI[]", "+ close()"])
    lic = uml_class(ax, 20.8, 10.2 + d, 4.8, "VendingLicence",
                    ["- licenceNo : String", "- zone : String", "- issueDate : Date", "- expiryDate : Date",
                     "- status : String"], ["+ renew()", "+ cancel()"])

    engine = uml_class(ax, 5.6, 6.0 + d, 5.6, "TrustScoreEngine", ["- MIN_SCORE : int = 40", "- WEIGHTS : dict"],
                       ["+ compute(..) : TrustScore", "+ riskBand(score) : String", "+ isEligible(s) : bool"])
    tscore = uml_class(ax, 0.4, 6.0 + d, 4.0, "TrustScore",
                       ["- score : int", "- band : String", "- eligible : bool", "- components : dict"], [],
                       stereo="value object")
    emi = uml_class(ax, 14.6, 3.4 + d, 5.4, "EMIInstallment",
                    ["- installmentNo : int", "- dueDate : Date", "- emiAmount : float", "- principalPart : float",
                     "- interestPart : float", "- status : String", "- paidOn : Date", "- paidOnTime : bool"],
                    ["+ pay(amount)", "+ isOverdue(today) : bool"])
    case = uml_class(ax, 20.8, 5.6 + d, 4.8, "DisputeCase",
                     ["- caseId : int", "- vendorId : int", "- caseType : String", "- description : String", "- status : String",
                      "- loggedOn : Date"], ["+ resolve()"])

    def mult(x, y, s, ha="left"):
        text(ax, x, y, s, size=9.5, ha=ha, color="#333")

    def assoc(p, q, m1, m2, label, lpos=(0.0, 0.0), m_off=0.12):
        arrow(ax, p, q, head="none")
        mult(p[0] + m_off, p[1] - 0.3 if p[1] > q[1] else p[1] + 0.3, m1)
        mult(q[0] + m_off, q[1] + 0.3 if p[1] > q[1] else q[1] - 0.3, m2)
        text(ax, (p[0] + q[0]) / 2 + lpos[0], (p[1] + q[1]) / 2 + lpos[1], label, size=9.5, bg=True, style="italic")

    # generalisation tree
    bus = 16.9 + d
    for c in (cust, ven, bank, muni):
        arrow(ax, (c["cx"], c["y1"]), (c["cx"], bus), head="none")
    arrow(ax, (cust["cx"], bus), (muni["cx"], bus), head="none")
    arrow(ax, (user["cx"], bus), (user["cx"], user["y0"]), head="hollow")

    # associations
    assoc((cust["cx"], cust["y0"]), (cust["cx"], rating["y1"]), "1", "0..*", "gives")
    assoc((ven["x0"] + 0.6, ven["y0"]), (rating["x1"] - 0.6, rating["y1"]), "1", "0..*", "receives", (-0.3, 0))
    assoc((7.9, ven["y0"]), (7.9, sale["y1"]), "1", "0..*", "logs")
    assoc((11.2, ven["y0"]), (11.2, vouch["y1"]), "1", "0..*", "vouched by")
    assoc((ven["x1"], ven["y0"] + 0.4), (15.6, loan["y1"]), "1", "0..*", "applies for", (0.2, 0.25))
    assoc((17.6, bank["y0"]), (17.6, loan["y1"]), "0..1", "0..*", "reviews", (0.0, 0.6))
    assoc((24.4, muni["y0"]), (24.4, lic["y1"]), "1", "0..*", "issues")

    # Vendor holds a licence (routed under the officer classes)
    y_route = 12.2 + d
    polyline(ax, [(ven["x1"], y_route), (22.0, y_route), (22.0, lic["y1"])], head="none")
    mult(ven["x1"] + 0.15, y_route + 0.3, "1")
    mult(22.15, lic["y1"] + 0.3, "0..1")
    text(ax, 13.0, y_route, "holds", size=9.5, bg=True, style="italic")

    # Municipal officer logs dispute cases (routed down the right margin)
    x_route = 26.1
    yc = (case["y0"] + case["y1"]) / 2
    polyline(ax, [(muni["x1"], muni["y1"] - 0.8), (x_route, muni["y1"] - 0.8), (x_route, yc), (case["x1"], yc)],
             head="none")
    mult(case["x1"] + 0.05, yc + 0.3, "0..*")
    mult(muni["x1"] + 0.05, muni["y1"] - 0.5, "1")
    text(ax, x_route, (yc + muni["y1"]) / 2, "logs", size=9.5, bg=True, style="italic", rotation=90)

    # composition Loan <>-- EMIInstallment
    tip = diamond(ax, (17.3, loan["y0"]), (17.3, emi["y1"]))
    arrow(ax, tip, (17.3, emi["y1"]), head="none")
    mult(17.1, loan["y0"] - 0.35, "1", ha="right")
    mult(17.1, emi["y1"] + 0.25, "1..*", ha="right")
    text(ax, 18.6, (loan["y0"] + emi["y1"]) / 2, "has schedule", size=9.5, style="italic")

    # dependencies
    def depend(p, q, label, lpos=(0, 0.28)):
        arrow(ax, p, q, head="open", dashed=True)
        text(ax, (p[0] + q[0]) / 2 + lpos[0], (p[1] + q[1]) / 2 + lpos[1], label, size=9, bg=True, style="italic")

    depend((loan["x0"], 5.6 + d), (engine["x1"], 5.2 + d), "«use» eligibility", (0, 0.3))
    depend((7.6, engine["y1"]), (7.6, sale["y0"]), "«read»", (0.6, 0))
    depend((engine["x0"], 4.6 + d), (tscore["x1"], 4.6 + d), "«create»", (0, 0.3))
    depend((engine["x1"], 3.8 + d), (emi["x0"], 2.4 + d), "«read»")

    save(fig, out("02_class_diagram.png"))


# ====================================================================== SEQUENCE
def sequence_diagram(filename, title, participants, steps, activations, gap=3.6, dy=0.62):
    """
    participants: [(key, label, 'actor'|'object')]
    steps: ('call'|'ret', a, b, text) | ('self', a, text) | ('alt', guard) | ('else', guard) | ('end',)
    activations: [(key, first_step, last_step)] - bars drawn from step to step (fractions allowed)
    """
    n = len(participants)
    W = gap * (n - 1) + 4.4
    head_y = 1.0
    H = 2.6 + head_y + 1.6 + dy * (len(steps) + 1)
    fig, ax = canvas(W, H, title)
    xs = {k: 2.2 + i * gap for i, (k, _, _) in enumerate(participants)}
    top = H - 1.3
    life_top = top - 1.75
    y = lambda i: life_top - 0.7 - i * dy  # noqa: E731
    bottom = y(len(steps)) - 0.2

    for k, label, kind in participants:
        x = xs[k]
        if kind == "actor":
            actor(ax, x, top - 1.6 + 0.1, "", size=10)
            text(ax, x, top - 1.65, label, fontweight="bold", va="top", size=10)
        else:
            ax.add_patch(Rectangle((x - 1.55, top - 1.3), 3.1, 0.95, fc="#e4efe8", ec=INK, lw=1.4, zorder=4))
            text(ax, x, top - 0.82, label, fontweight="bold", size=10)
        start = life_top - (0.35 if kind == "actor" else 0)
        arrow(ax, (x, start), (x, bottom), head="none", dashed=True, lw=1.0, color="#555")

    for k, s, e in activations:
        y1, y2 = y(s) + 0.15, y(e) - 0.15
        ax.add_patch(Rectangle((xs[k] - 0.13, y2), 0.26, y1 - y2, fc="white", ec=INK, lw=1.2, zorder=3))

    num, frames = 0, []
    for i, st in enumerate(steps):
        yy = y(i)
        kind = st[0]
        if kind in ("call", "ret"):
            num += 1
            a, b, label = xs[st[1]], xs[st[2]], st[3]
            sgn = 1 if b > a else -1
            p, q = (a + 0.13 * sgn, yy), (b - 0.13 * sgn, yy)
            arrow(ax, p, q, head="filled" if kind == "call" else "open", dashed=kind == "ret", lw=1.2)
            text(ax, (a + b) / 2, yy + 0.07, f"{num}: {label}", size=9.5, va="bottom")
        elif kind == "self":
            num += 1
            x = xs[st[1]] + 0.13
            polyline(ax, [(x, yy + 0.1), (x + 0.8, yy + 0.1), (x + 0.8, yy - 0.3), (x, yy - 0.3)], lw=1.2)
            text(ax, x + 0.95, yy - 0.1, f"{num}: {st[2]}", size=9.5, ha="left")
        elif kind == "alt":
            frames.append({"top": yy + 0.35, "guard": st[1], "else": []})
        elif kind == "else":
            frames[-1]["else"].append((yy + 0.1, st[1]))
        elif kind == "end":
            f = frames[-1]
            x0, x1 = 0.6, W - 0.6
            ax.add_patch(Rectangle((x0, yy + 0.2), x1 - x0, f["top"] - yy - 0.2, fill=False, ec="#444", lw=1.2,
                                   zorder=2))
            ax.add_patch(Rectangle((x0, f["top"] - 0.42), 0.9, 0.42, fc="#e4efe8", ec="#444", lw=1.2, zorder=2))
            text(ax, x0 + 0.45, f["top"] - 0.21, "alt", size=9.5, fontweight="bold")
            text(ax, x0 + 1.05, f["top"] - 0.21, f["guard"], size=9.5, ha="left", style="italic")
            for ey, guard in f["else"]:
                arrow(ax, (x0, ey), (x1, ey), head="none", dashed=True, lw=1.0, color="#444")
                text(ax, x0 + 0.15, ey - 0.22, guard, size=9.5, ha="left", style="italic")
    save(fig, out(filename))


def login_sequence():
    sequence_diagram(
        "03_sequence_login.png", "Sequence Diagram - User Login",
        [("V", "Vendor / User", "actor"), ("LP", ":LoginPage", "object"),
         ("AC", ":AuthController", "object"), ("DB", ":Database", "object")],
        [
            ("call", "V", "LP", "submit login form (phone, password)"),
            ("call", "LP", "AC", "login_user(phone, password)"),
            ("call", "AC", "DB", "SELECT user WHERE phone = ?"),
            ("ret", "DB", "AC", "user row / none"),
            ("alt", "[user found AND password correct AND not locked]"),
            ("call", "AC", "DB", "UPDATE failed_attempts = 0"),
            ("ret", "AC", "LP", "user row (session created)"),
            ("ret", "LP", "V", "redirect to role dashboard"),
            ("else", "[else: user not found / wrong password / account locked]"),
            ("call", "AC", "DB", "UPDATE failed_attempts + 1 (lock at 5)"),
            ("ret", "AC", "LP", "ValidationError(message)"),
            ("ret", "LP", "V", "show error message"),
            ("end",),
        ],
        [("LP", 0, 11), ("AC", 1, 10), ("DB", 2, 3), ("DB", 5, 5.5), ("DB", 9, 9.5)],
        gap=5.4,
    )


def loan_sequence():
    sequence_diagram(
        "04_sequence_loan.png", "Sequence Diagram - Loan Application, Approval & Disbursal",
        [("V", "Street Vendor", "actor"), ("VD", ":VendorDashboard", "object"), ("LS", ":LoanService", "object"),
         ("TS", ":TrustScoreEngine", "object"), ("DB", ":Database", "object"),
         ("OD", ":OfficerDashboard", "object"), ("BO", "Bank Officer", "actor")],
        [
            ("call", "V", "VD", "click Apply (amount)"),
            ("call", "VD", "LS", "apply_loan(vendorId, amount)"),
            ("call", "LS", "DB", "SELECT active loan of vendor"),
            ("ret", "DB", "LS", "none"),
            ("call", "LS", "TS", "get_trust_score(vendorId)"),
            ("call", "TS", "DB", "SELECT profile, sales, EMIs, vouches"),
            ("ret", "DB", "TS", "vendor data"),
            ("self", "TS", "compute_trust_score()"),
            ("ret", "TS", "LS", "score, risk band"),
            ("alt", "[score >= 40 AND amount <= tier limit]"),
            ("call", "LS", "DB", "INSERT loan (status PENDING)"),
            ("ret", "LS", "VD", "loanId"),
            ("ret", "VD", "V", "\"Application #id submitted\""),
            ("else", "[else: score < 40 OR amount > tier limit]"),
            ("ret", "LS", "VD", "ValidationError(reason)"),
            ("ret", "VD", "V", "show reason"),
            ("end",),
            ("call", "BO", "OD", "click Approve"),
            ("call", "OD", "LS", "review_loan(loanId, APPROVE)"),
            ("call", "LS", "DB", "UPDATE status = APPROVED"),
            ("ret", "LS", "OD", "APPROVED"),
            ("call", "BO", "OD", "click Disburse"),
            ("call", "OD", "LS", "disburse_loan(loanId)"),
            ("self", "LS", "generate_emi_schedule(P, r, n)"),
            ("call", "LS", "DB", "INSERT EMIs; status = DISBURSED"),
            ("ret", "LS", "OD", "EMI schedule"),
            ("ret", "OD", "BO", "\"Loan disbursed\""),
        ],
        [("VD", 0, 15), ("LS", 1, 14), ("DB", 2, 3), ("TS", 4, 8), ("DB", 5, 6), ("DB", 10, 10.5),
         ("OD", 17, 20), ("LS", 18, 20), ("DB", 19, 19.5), ("OD", 21, 26), ("LS", 22, 25), ("DB", 24, 24.5)],
        gap=3.7,
    )


# ====================================================================== STATE
def loan_state_diagram():
    W, H = 21.0, 13.0
    fig, ax = canvas(W, H, "State Transition Diagram - Loan Application Life Cycle")
    y1, y2 = 8.6, 3.8
    start = initial(ax, 0.8, y1)
    pending = state(ax, 4.9, y1, "PENDING")
    approved = state(ax, 10.3, y1, "APPROVED")
    disbursed = state(ax, 16.4, y1, "DISBURSED\n(Repaying)", w=3.4, h=1.4)
    rejected = state(ax, 2.6, y2, "REJECTED")
    withdrawn = state(ax, 7.0, y2, "WITHDRAWN")
    defaulted = state(ax, 12.6, y2, "DEFAULTED")
    closed = state(ax, 18.4, y2, "CLOSED")
    ends = [final(ax, s["c"][0], 1.3) for s in (rejected, withdrawn, closed)]

    flow(ax, start, pending, "submitApplication()\n[score >= 40]", size=9.5, loff=0.75)
    flow(ax, pending, approved, "approve()\nby Bank Officer", size=9.5, loff=0.65)
    flow(ax, approved, disbursed, "disburse() /\ncreate EMI schedule", size=9.5, loff=0.75)
    flow(ax, pending, rejected, "reject(remarks)", size=9.5, loff=-0.9)
    flow(ax, pending, withdrawn, "withdraw()\nby vendor", size=9.5, loff=0.95)
    flow(ax, disbursed, defaulted, "[an EMI overdue\n> 90 days]", size=9.5, loff=-1.0)
    flow(ax, disbursed, closed, "payEMI()\n[last EMI paid] /\nunlock next tier", size=9.5, loff=1.2)
    flow(ax, defaulted, closed, "all dues cleared", size=9.5, loff=0.35)
    for s, e in zip((rejected, withdrawn, closed), ends):
        flow(ax, s, e)

    # self-transition while EMIs remain
    x0, x1, top = disbursed["x0"] + 0.6, disbursed["x1"] - 0.6, disbursed["y1"] + 1.1
    polyline(ax, [(x0, disbursed["y1"]), (x0, top), (x1, top), (x1, disbursed["y1"])])
    text(ax, (x0 + x1) / 2, top + 0.35, "payEMI() [EMIs remaining]", size=9.5)

    save(fig, out("05_state_transition_loan.png"))


# ====================================================================== DFD
def dfd_level0():
    W, H = 25.0, 17.0
    fig, ax = canvas(W, H, "DFD Level 0 (Context Diagram) - VendorSetu")
    sys_ = process(ax, 12.5, 8.2, "0", "VendorSetu\nPlatform", r=2.3, size=12)
    vendor_e = entity(ax, 3.0, 12.6, "Street Vendor")
    peer = entity(ax, 3.0, 3.6, "Peer Guarantor")
    bank = entity(ax, 22.0, 12.6, "Bank / NBFC\nOfficer")
    muni = entity(ax, 22.0, 3.6, "Municipal\nOfficer")
    cust = entity(ax, 12.5, 1.0, "Customer")
    pg = entity(ax, 12.5, 15.2, "UPI / Payment\nGateway")

    # Two-way flows: each arrow is shifted to its own side (offset) and its label sits further out (loff)
    o = 0.35
    flow(ax, vendor_e, sys_, "registration, profile, daily sales,\nloan application, EMI payment,\nlicence application",
         offset=o, loff=1.4)
    flow(ax, sys_, vendor_e, "login status, sales summary, trust score,\nloan status, EMI schedule, licence status", offset=o, loff=1.15)
    flow(ax, bank, sys_, "approve / reject decision,\ndisbursal confirmation", offset=o, loff=1.15)
    flow(ax, sys_, bank, "loan applications + trust score,\ndefault report", offset=o, loff=1.15)
    flow(ax, muni, sys_, "licence decision,\ndispute / eviction case", offset=o, loff=1.15)
    flow(ax, sys_, muni, "licence applications,\ncase updates", offset=o, loff=1.15)
    flow(ax, peer, sys_, "vouch / guarantee", offset=o, loff=0.8)
    flow(ax, sys_, peer, "vouch confirmation", offset=o, loff=0.8)
    flow(ax, cust, sys_, "vendor search,\npayment, rating", offset=o, loff=1.6)
    flow(ax, sys_, cust, "nearby vendors,\npayment receipt", offset=o, loff=1.6)
    flow(ax, sys_, pg, "payment request", offset=o, loff=1.6, lpos=0.78)
    flow(ax, pg, sys_, "payment confirmation", offset=o, loff=1.9, lpos=0.22)

    save(fig, out("06_dfd_level0_context.png"))


def dfd_level1():
    W, H = 28.5, 22.5
    fig, ax = canvas(W, H, "DFD Level 1 - VendorSetu")
    oy = 0.8
    r = 1.4

    vendor_e = entity(ax, 2.2, 17.0 + oy, "Street\nVendor", w=3.0)
    peer = entity(ax, 2.2, 12.0 + oy, "Peer\nGuarantor", w=3.0)
    vendor2 = entity(ax, 2.2, 6.5 + oy, "Street\nVendor *", w=3.0)
    cust = entity(ax, 2.2, 2.6 + oy, "Customer", w=3.0)
    bank = entity(ax, 26.4, 16.5 + oy, "Bank / NBFC\nOfficer", w=3.4)
    pg = entity(ax, 26.4, 6.5 + oy, "Payment\nGateway", w=3.4)
    muni = entity(ax, 26.4, 2.5 + oy, "Municipal\nOfficer", w=3.4)

    p1 = process(ax, 8.0, 19.2 + oy, "1.0", "Manage User\nAccounts", r=r)
    p2 = process(ax, 8.0, 12.0 + oy, "2.0", "Manage Profile,\nSales & Vouches", r=r)
    p3 = process(ax, 19.5, 12.0 + oy, "3.0", "Compute\nTrust Score", r=r)
    p4 = process(ax, 19.5, 16.5 + oy, "4.0", "Process Loan\nApplications", r=r)
    p5 = process(ax, 19.5, 6.5 + oy, "5.0", "Manage EMI\nRepayment", r=r)
    p6 = process(ax, 19.5, 2.5 + oy, "6.0", "Manage Licences\n& Cases", r=r)
    p7 = process(ax, 8.0, 2.6 + oy, "7.0", "Customer\nServices", r=r)

    d1 = datastore(ax, 13.6, 19.2 + oy, "D1", "Users")
    d2 = datastore(ax, 13.6, 14.3 + oy, "D2", "Vendor Profiles")
    d3 = datastore(ax, 13.6, 12.0 + oy, "D3", "Sales")
    d6 = datastore(ax, 13.6, 9.7 + oy, "D6", "Vouches")
    d4 = datastore(ax, 19.5, 20.4 + oy, "D4", "Loans")
    d5 = datastore(ax, 25.0, 10.8 + oy, "D5", "EMI Installments", w=3.8)
    d2b = datastore(ax, 13.0, 0.9 + oy, "D2", "Vendor Profiles *")
    d7 = datastore(ax, 19.5, 0.2 + oy, "D7", "Licences & Cases", w=3.8)
    d8 = datastore(ax, 8.0, 0.2 + oy, "D8", "Ratings")

    o = 0.3
    s = 9
    flow(ax, vendor_e, p1, "credentials", offset=o, loff=0.65, size=s)
    flow(ax, p1, vendor_e, "session / error", offset=o, loff=0.65, size=s)
    flow(ax, p1, d1, "user record", offset=o, loff=0.6, size=s)
    flow(ax, d1, p1, "stored hash", offset=o, loff=0.6, size=s)

    flow(ax, vendor_e, p2, "profile,\ndaily sales", offset=o, loff=0.95, size=s)
    flow(ax, p2, vendor_e, "sales summary", offset=o, loff=0.75, size=s)
    flow(ax, peer, p2, "vouch", offset=o, loff=0.6, size=s)
    flow(ax, p2, peer, "vouch confirmation", offset=o, loff=0.6, size=s)
    flow(ax, p2, d2, "profile", size=s, loff=0.35)
    flow(ax, p2, d3, "sale entry", size=s, loff=0.3)
    flow(ax, p2, d6, "vouch", size=s, loff=-0.35)
    flow(ax, d2, p3, "years vending", size=s, loff=0.35)
    flow(ax, d3, p3, "30-day sales", size=s, loff=0.3)
    flow(ax, d6, p3, "vouch count", size=s, loff=-0.35)
    flow(ax, d5, p3, "repayment\nrecord", size=s, loff=0.6)
    flow(ax, p4, p3, "score\nrequest", offset=o, loff=0.85, size=s)
    flow(ax, p3, p4, "trust score\n& band", offset=o, loff=0.85, size=s)

    flow(ax, vendor_e, p4, "loan application", offset=o, loff=0.6, size=s, lpos=0.62)
    flow(ax, p4, vendor_e, "loan status, trust score", offset=o, loff=0.6, size=s, lpos=0.62)
    flow(ax, bank, p4, "decision,\ndisbursal", offset=o, loff=0.9, size=s)
    flow(ax, p4, bank, "applications + score,\ndefault report", offset=o, loff=0.9, size=s)
    flow(ax, p4, d4, "loan record", offset=o, loff=1.0, size=s)
    flow(ax, d4, p4, "loan status", offset=o, loff=1.0, size=s)
    flow(ax, p4, d5, "EMI schedule", offset=o, loff=0.6, size=s)
    flow(ax, d5, p4, "overdue EMIs", offset=o, loff=0.6, size=s)

    flow(ax, vendor2, p5, "EMI payment", offset=o, loff=0.6, size=s)
    flow(ax, p5, vendor2, "receipt, EMI status", offset=o, loff=0.6, size=s)
    flow(ax, p5, pg, "payment request", offset=o, loff=0.6, size=s)
    flow(ax, pg, p5, "confirmation", offset=o, loff=0.6, size=s)
    flow(ax, p5, d5, "EMI paid\n(on time / late)", size=s, loff=-0.7)

    flow(ax, vendor2, p6, "licence application", offset=o, loff=0.6, size=s, lpos=0.7)
    flow(ax, p6, vendor2, "licence status", offset=o, loff=0.6, size=s, lpos=0.3)
    flow(ax, muni, p6, "decision,\ncase details", offset=o, loff=0.9, size=s)
    flow(ax, p6, muni, "applications,\ncase updates", offset=o, loff=0.9, size=s)
    flow(ax, p6, d7, "licence / case", offset=o, size=s, loff=1.0)
    flow(ax, d7, p6, "licence\nstatus", offset=o, size=s, loff=0.7)

    flow(ax, cust, p7, "search, payment,\nrating", offset=o, loff=0.9, size=s)
    flow(ax, p7, cust, "vendor list,\nreceipt", offset=o, loff=0.9, size=s)
    flow(ax, d2b, p7, "vendor profiles", size=s, loff=-0.4)
    flow(ax, p7, d8, "rating", offset=o, size=s, loff=0.55)
    flow(ax, d8, p7, "vendor\nratings", offset=o, size=s, loff=0.75)

    text(ax, 0.6, -0.6, "* duplicated entity / data store (drawn twice to avoid crossing lines).  "
         "Bank, Municipal and Customer users also authenticate through 1.0 (flows omitted for clarity).",
         size=9.5, ha="left", style="italic")
    save(fig, out("07_dfd_level1.png"))


def dfd_level2_trust_score():
    W, H = 25.0, 14.5
    fig, ax = canvas(W, H, "DFD Level 2 - Process 3.0 Compute Trust Score")
    req = entity(ax, 6.8, 12.0, "4.0 Process Loan\nApplications", w=3.8)
    d2 = datastore(ax, 1.9, 9.3, "D2", "Profiles", w=3.0)
    d3 = datastore(ax, 1.9, 7.3, "D3", "Sales", w=3.0)
    d5 = datastore(ax, 1.9, 5.3, "D5", "EMIs", w=3.0)
    d6 = datastore(ax, 1.9, 3.3, "D6", "Vouches", w=3.0)

    p31 = process(ax, 7.3, 6.3, "3.1", "Fetch Vendor\nData", r=1.4)
    p32 = process(ax, 12.8, 10.3, "3.2", "Score Sales\nConsistency", r=1.4)
    p33 = process(ax, 12.8, 6.3, "3.3", "Score Repayment\nHistory", r=1.5)
    p34 = process(ax, 12.8, 2.3, "3.4", "Score Vouching\n& Tenure", r=1.4)
    p35 = process(ax, 18.0, 6.3, "3.5", "Aggregate &\nAssign Risk Band", r=1.6)
    out_loan = entity(ax, 22.9, 6.3, "4.0 Process\nLoans *", w=3.2)

    s = 9
    flow(ax, req, p31, "score request\n(vendorId)", size=s, loff=0.85)
    flow(ax, d2, p31, "years vending", size=s, loff=0.35, lpos=0.45)
    flow(ax, d3, p31, "sales (30 days)", size=s, loff=0.3, lpos=0.45)
    flow(ax, d5, p31, "EMI records", size=s, loff=-0.3, lpos=0.45)
    flow(ax, d6, p31, "vouch count", size=s, loff=-0.35, lpos=0.45)
    flow(ax, p31, p32, "active days,\nwindow days", size=s, loff=0.7)
    flow(ax, p31, p33, "on-time EMIs,\nEMIs due", size=s, loff=0.55)
    flow(ax, p31, p34, "vouches,\nyears", size=s, loff=-0.6)
    flow(ax, p32, p35, "0-40 pts", size=s, loff=0.4)
    flow(ax, p33, p35, "0-40 pts\n(20 if no history)", size=s, loff=0.6)
    flow(ax, p34, p35, "0-20 pts", size=s, loff=-0.4)
    flow(ax, p35, out_loan, "score, band,\neligible, breakdown", size=s, loff=1.1, lpos=0.55)

    save(fig, out("08_dfd_level2_trust_score.png"))


if __name__ == "__main__":
    use_case_diagram()
    class_diagram()
    login_sequence()
    loan_sequence()
    loan_state_diagram()
    dfd_level0()
    dfd_level1()
    dfd_level2_trust_score()
    print("Diagrams written to", OUT)
