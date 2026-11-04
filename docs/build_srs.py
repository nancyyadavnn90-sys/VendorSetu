"""
build_srs.py - Generates the complete SRS (IEEE / Wiegers template) as a Word document.

    python docs/build_srs.py

Reads: diagrams/*.png, tests/test_results.json, and source code (for the snippets in Appendix D).
Runs:  pytest, so the test summary reflects the code as it is right now.
Writes: docs/SRS_VendorSetu.docx
"""
import inspect
import json
import os
import re
import subprocess
import sys

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAG = os.path.join(ROOT, "diagrams")
OUT = os.path.join(ROOT, "docs", "SRS_VendorSetu.docx")
sys.path.insert(0, os.path.join(ROOT, "app"))

from modules import credit_score, loan  # noqa: E402

GREEN = RGBColor(0x1F, 0x5C, 0x3D)
TEAM = "Nancy Yadav, <<Member 2>>, <<Member 3>>, <<Member 4>>"
DATE = "28 October 2026"

doc = Document()


# ====================================================================== helpers
def set_cell_bg(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def rich(paragraph, text, size=None, bold=False, italic=False, font=None):
    """Add text to a paragraph; **bold** segments are bolded, <<placeholders>> are highlighted yellow."""
    for part in re.split(r"(\*\*.+?\*\*|<<.+?>>)", text):
        if not part:
            continue
        if part.startswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("<<"):
            run = paragraph.add_run("<" + part[2:-2] + ">")
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            run.bold = bold
        else:
            run = paragraph.add_run(part)
            run.bold = bold
        run.italic = italic
        if size:
            run.font.size = Pt(size)
        if font:
            run.font.name = font
    return paragraph


def para(text="", size=None, bold=False, italic=False, align=None, space_after=6, style=None):
    p = doc.add_paragraph(style=style)
    rich(p, text, size=size, bold=bold, italic=italic)
    p.paragraph_format.space_after = Pt(space_after)
    if align:
        p.alignment = align
    return p


def bullet(text):
    p = doc.add_paragraph(style="List Bullet")
    rich(p, text)
    p.paragraph_format.space_after = Pt(2)
    return p


def heading(text, level):
    h = doc.add_heading(text, level)
    h.paragraph_format.keep_with_next = True
    return h


def table(headers, rows, widths, header_bg="DDEBE3", font_size=9.5, bold_first_col=False):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0]
    tr_pr = hdr._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.width = Inches(widths[i])
        cell.paragraphs[0].text = ""
        rich(cell.paragraphs[0], h, size=font_size, bold=True)
        set_cell_bg(cell, header_bg)
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            cells[i].width = Inches(widths[i])
            lines = str(value).split("\n")
            cells[i].paragraphs[0].text = ""
            rich(cells[i].paragraphs[0], lines[0], size=font_size, bold=bold_first_col and i == 0)
            for line in lines[1:]:
                rich(cells[i].add_paragraph(), line, size=font_size)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def code_block(source, size=8.5):
    for line in source.rstrip().split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Inches(0.2)
        run = p.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(size)
        p_pr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "F3F5F2")
        p_pr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


fig_no = [0]


def figure(filename, caption, max_w, max_h):
    path = os.path.join(DIAG, filename)
    w, h = Image.open(path).size
    scale = min(max_w / w, max_h / h)
    doc.add_picture(path, width=Inches(w * scale))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    fig_no[0] += 1
    p = para(f"Figure {fig_no[0]}: {caption}", size=9.5, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    p.paragraph_format.space_after = Pt(10)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def new_section(landscape, margin=1.0):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    if landscape:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Inches(11.69), Inches(8.27)
    else:
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(margin))
    return sec


def add_field(paragraph, instr):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    code = OxmlElement("w:instrText")
    code.set(qn("xml:space"), "preserve")
    code.text = instr
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run._r.extend([begin, code, sep])
    placeholder = paragraph.add_run("Right-click and choose Update Field" if "TOC" in instr else "1")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    placeholder._r.addnext(end)


def req_table(rows):
    table(["ID", "Requirement"], rows, [1.15, 5.1], bold_first_col=True)


def stim_table(rows):
    table(["Stimulus (user action)", "System response"], rows, [2.6, 3.65])


# ====================================================================== document setup
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(11)
for lvl, size in ((1, 16), (2, 13), (3, 11.5)):
    hs = doc.styles[f"Heading {lvl}"]
    hs.font.name = "Calibri"
    hs.font.size = Pt(size)
    hs.font.color.rgb = GREEN
    hs.font.bold = True

sec0 = doc.sections[0]
sec0.page_width, sec0.page_height = Inches(8.27), Inches(11.69)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec0, side, Inches(1.0))

header_p = sec0.header.paragraphs[0]
rich(header_p, "SRS - VendorSetu: Street Vendor Formalization & Micro-Credit Platform   |   CSE3005", size=8.5,
     italic=True)
header_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
footer_p = sec0.footer.paragraphs[0]
footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
rich(footer_p, "Page ", size=9)
add_field(footer_p, "PAGE")

# ====================================================================== cover page
for _ in range(5):
    doc.add_paragraph()
para("Software Requirements Specification", size=30, bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=4)
para("for", size=18, align=WD_ALIGN_PARAGRAPH.RIGHT)
p = para("VendorSetu", size=28, bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=2)
p.runs[0].font.color.rgb = GREEN
para("Street Vendor Formalization & Micro-Credit Platform", size=15, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=30)
para("Version 1.0 approved", size=13, bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=30)
para(f"Prepared by: {TEAM}", size=12, align=WD_ALIGN_PARAGRAPH.RIGHT)
para("B.Tech CSE, Batch 2024 - CSE3005 Software Engineering", size=12, align=WD_ALIGN_PARAGRAPH.RIGHT)
para("BML Munjal University", size=12, bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
para("Submitted to: <<Faculty name>>", size=12, align=WD_ALIGN_PARAGRAPH.RIGHT)
para(DATE, size=12, align=WD_ALIGN_PARAGRAPH.RIGHT)
page_break()

# ====================================================================== TOC + revision history
heading("Table of Contents", 1)
add_field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
page_break()

heading("Revision History", 1)
table(["Name", "Date", "Reason For Changes", "Version"],
      [["Nancy Yadav & team", "28-10-2026",
        "Complete SRS for final evaluation: requirements, analysis models (UML & DFD), prototype implementation "
        "of 4 modules and executed test cases", "1.0"]],
      [1.5, 1.0, 3.0, 0.75])

# ====================================================================== 1 Introduction
heading("1. Introduction", 1)
heading("1.1 Purpose", 2)
para("This Software Requirements Specification (SRS) describes the functional and non-functional requirements of "
     "**VendorSetu, release 1.0** - a web platform that gives India's street vendors a digital business identity, "
     "records their daily sales, converts that history into an alternative credit **Trust Score**, and uses it to "
     "offer progressive micro-loans modelled on the Government of India's PM SVANidhi scheme. The platform also "
     "digitises vending-zone licensing for municipal bodies and lets customers find and pay vendors.")
para("The SRS covers the complete system and all five user classes. Features marked **[Implemented]** are built "
     "and tested in the release-1.0 prototype submitted with this document (Appendix D and E); the remaining "
     "features are fully specified here and scheduled for the next increment.")

heading("1.2 Document Conventions", 2)
for b in [
    "**Requirement IDs:** functional requirements are tagged FR-<feature>-<n> (e.g. FR-LN-3), non-functional "
    "requirements NFR-<category>-<n>, and business rules BR-<n>. IDs are referenced in the source code comments.",
    "**Priorities:** every feature carries a MoSCoW priority (Must / Should / Could / Won't) and a High / Medium / "
    "Low rating. Detailed requirements inherit the priority of their feature unless stated otherwise.",
    "**\"shall\"** marks a mandatory requirement; **\"should\"** marks a desirable one.",
    "**[Implemented]** marks features coded in the release-1.0 prototype.",
    "Amounts are in Indian Rupees (₹). Dates are written DD-MM-YYYY.",
    "Items that are not yet decided are marked **TBD-n** and tracked in Appendix C.",
]:
    bullet(b)

heading("1.3 Intended Audience and Reading Suggestions", 2)
table(["Reader", "Interest", "Suggested sections"], [
    ["Course faculty / evaluators", "Completeness and correctness of the SRS, models and testing",
     "1, 2, 4, Appendix B, D, E"],
    ["Developers", "What to build and the business rules", "2, 3, 4, 5.5, Appendix B, D"],
    ["Testers", "Verifiable requirements and expected behaviour", "4, 5, Appendix E"],
    ["Bank / NBFC partners", "Loan rules, trust score, repayment and default handling", "1.4, 4.3-4.6, 5.3, 6.2"],
    ["Municipal (ULB) officials", "Licensing and dispute features", "2.3, 4.7, 4.8"],
    ["Project manager", "Scope, priorities, assumptions and open issues", "1.4, 2.7, 4 (MoSCoW), Appendix C"],
], [1.7, 2.8, 1.75])
para("Recommended order: read Section 1 and 2 for the overview, then Section 4 for the features, Appendix B for "
     "the diagrams, Section 5 for quality requirements, and Appendix D-E for the prototype and its test results.")

heading("1.4 Product Scope", 2)
para("Street vendors are a large part of India's informal economy, yet most have no formal credit history. Banks "
     "cannot assess them with a CIBIL score, so vendors depend on informal moneylenders. PM SVANidhi showed that "
     "small, progressive working-capital loans work - the restructured scheme (approved by the Union Cabinet in "
     "August 2025, extended to March 2030) targets 1.15 crore beneficiaries with an outlay of ₹7,332 crore - but "
     "application, verification and repayment tracking are still largely manual.")
para("VendorSetu's objectives are to:")
for b in [
    "give every vendor a digital profile and an easy daily sales log (cash or UPI);",
    "compute a transparent **Trust Score (0-100)** from sales consistency, repayment history, peer vouching and "
    "vending tenure, so lenders can assess vendors without a credit bureau history;",
    "offer **progressive loans** of ₹15,000 → ₹25,000 → ₹50,000, where repaying one tier unlocks the next;",
    "let bank/NBFC officers review, approve, disburse and monitor loans with a generated EMI schedule;",
    "digitise vending licences and dispute/eviction cases for municipal officers;",
    "help customers locate nearby vendors, pay digitally and rate hygiene and service.",
]:
    bullet(b)
para("Benefits: faster and fairer credit decisions, lower default risk through progressive limits, a verifiable "
     "business record that helps vendors formalise, and better data for urban local bodies.")

heading("1.5 References", 2)
table(["#", "Document", "Author / Source", "Version / Date"], [
    ["R1", "IEEE Recommended Practice for Software Requirements Specifications (IEEE Std 830)", "IEEE", "1998"],
    ["R2", "Software Requirements Specification template", "Karl E. Wiegers", "1999"],
    ["R3", "PM SVANidhi scheme portal and guidelines (pmsvanidhi.mohua.gov.in)",
     "Ministry of Housing & Urban Affairs, GoI", "Accessed Oct 2026"],
    ["R4", "Cabinet approves restructuring and extension of PM SVANidhi Scheme till 2030", "Union Cabinet (news reports)",
     "27-08-2025"],
    ["R5", "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act", "Government of India",
     "2014"],
    ["R6", "Guidelines on Digital Lending", "Reserve Bank of India", "02-09-2022"],
    ["R7", "Digital Personal Data Protection Act", "Government of India", "2023"],
    ["R8", "Software Engineering, 9th edition", "Ian Sommerville, Pearson", "2011"],
    ["R9", "Software Engineering: A Practitioner's Approach, 8th edition", "Roger S. Pressman, McGraw Hill", "2014"],
    ["R10", "CSE3005 Software Engineering - Course Handout", "BML Munjal University", "2026-27"],
    ["R11", "Test Case Template (Doc T_01)", "Dr Ghazy Assassa", "-"],
], [0.45, 3.0, 1.75, 1.05])

# ====================================================================== 2 Overall description
heading("2. Overall Description", 1)
heading("2.1 Product Perspective", 2)
para("VendorSetu is a **new, self-contained product**. It does not replace the PM SVANidhi portal; it complements "
     "it by producing the evidence a lender needs (a verified sales record and a Trust Score) and by tracking the "
     "loan through its whole life cycle. Today a vendor needs a vending certificate or a Letter of Recommendation "
     "from the urban local body, and then bank paperwork; VendorSetu brings the vendor, the municipal officer and "
     "the lender onto one platform.")
para("Major components and external interfaces (see the Context Diagram, Figure 6):")
for b in [
    "**Web client** - responsive pages used from a smartphone or PC browser by all user classes.",
    "**Application server** - Python/Flask application with four business modules: Authentication, Vendor "
    "Profile & Sales, Trust Score Engine, Loan Management.",
    "**Database** - relational store for users, profiles, sales, vouches, loans and EMI installments.",
    "**External systems** - UPI/payment gateway (EMI and customer payments), SMS/OTP gateway (TBD-4), and the "
    "lender's own core banking system, which performs the actual fund transfer.",
]:
    bullet(b)

heading("2.2 Product Functions", 2)
for b in [
    "**All users:** register, log in with mobile number and password, role-based dashboards.",
    "**Street vendor:** maintain a business profile; log daily sales; view a 30-day summary and Trust Score with its "
    "breakdown; apply for a loan within the eligible tier; view the EMI schedule and pay EMIs; apply for/renew a "
    "vending licence; view the vending-zone map.",
    "**Trust Score Engine:** compute a 0-100 score and risk band; decide loan eligibility (score ≥ 40).",
    "**Bank / NBFC officer:** review applications with Trust Score, approve or reject with remarks, disburse and "
    "generate the EMI schedule, track repayments and mark defaults.",
    "**Municipal officer:** approve/renew vending licences, log dispute or eviction cases, view the vendor registry.",
    "**Customer:** locate vendors by area, pay digitally, rate hygiene and service.",
    "**Peer guarantor:** vouch for another vendor (raises their Trust Score) and join group-lending circles.",
]:
    bullet(b)

heading("2.3 User Classes and Characteristics", 2)
table(["User class", "Characteristics", "Usage / privileges", "Importance"], [
    ["Street Vendor", "Small business owner; basic smartphone skills; may have limited literacy and prefer Hindi or "
     "a regional language", "Daily (sales log); monthly (EMI). Own data only", "Primary - most important"],
    ["Bank / NBFC Officer", "Trained loan officer of a regulated lender; comfortable with web forms",
     "Daily. Reviews and disburses loans; sees vendors' loan data", "Primary"],
    ["Municipal Officer", "Urban local body / Town Vending Committee staff",
     "Weekly. Licences and dispute cases within own ward", "Secondary"],
    ["Customer", "General public with a smartphone", "Occasional. Search, pay, rate", "Secondary"],
    ["Peer Guarantor", "A registered vendor who vouches for another vendor", "Occasional", "Secondary"],
    ["System Administrator", "Technical staff", "Maintenance, backups, user unlock", "Support"],
], [1.35, 2.35, 1.6, 0.95])

heading("2.4 Operating Environment", 2)
for b in [
    "**Server:** any OS that runs Python 3.11+ (developed on Windows 11; deployable on Linux). Flask 3.1, "
    "Werkzeug, Jinja2.",
    "**Database:** SQLite 3 in the prototype; PostgreSQL 15 recommended for production.",
    "**Client:** current Chrome, Edge, Firefox or Safari; Android 8+ smartphones on 3G/4G networks.",
    "**Network:** HTTPS over the public internet.",
]:
    bullet(b)

heading("2.5 Design and Implementation Constraints", 2)
for b in [
    "**Regulatory:** loans must be sanctioned and disbursed by an RBI-regulated entity directly to the borrower's "
    "bank account (RBI Digital Lending Guidelines, R6); VendorSetu records decisions but does not hold funds.",
    "**Privacy:** personal data must be processed with consent and minimised (DPDP Act 2023, R7); full Aadhaar "
    "numbers shall not be stored.",
    "**Devices:** pages must work on low-end Android phones and slow networks (see NFR-PERF-3).",
    "**Architecture:** business logic is kept in UI-independent modules so it can be unit-tested and reused by a "
    "future mobile app or API.",
    "**Technology (prototype):** Python 3.11, Flask, SQLite, server-rendered HTML; coding standard PEP 8.",
    "**Process:** incremental model - Increment 1 delivers all \"Must have\" features (Section 4) by the "
    "November 2026 evaluation.",
]:
    bullet(b)

heading("2.6 User Documentation", 2)
for b in [
    "README with installation, demo accounts and run instructions (delivered).",
    "In-app guidance: field placeholders, plain-language error messages and Trust Score breakdown (delivered).",
    "Test report with executed test cases - Appendix E (delivered).",
    "One-page vendor quick-start guide in Hindi and English (planned, next increment).",
]:
    bullet(b)

heading("2.7 Assumptions and Dependencies", 2)
table(["#", "Assumption / dependency"], [
    ["A-1", "Loan tiers follow the restructured PM SVANidhi scheme (Aug 2025): ₹15,000 / 12 months, ₹25,000 / 18 "
     "months, ₹50,000 / 36 months. The original 2020 scheme used ₹10,000 / ₹20,000 / ₹50,000; tier values are "
     "configurable in one place (TIERS in loan.py)."],
    ["A-2", "An interest rate of 12% p.a. (reducing balance) is assumed for EMI calculation until the partner "
     "lender confirms its rate (TBD-2). Government interest subsidy is credited by the lender, outside this system."],
    ["A-3", "Vendors own or can borrow a smartphone, or are assisted at a Common Service Centre."],
    ["A-4", "Self-reported sales are honest enough to be useful; later increments will cross-check against UPI "
     "receipts to limit inflation."],
    ["A-5", "Trust Score weights (40/40/10/10) are initial values to be re-calibrated with real repayment data (TBD-5)."],
    ["D-1", "Availability of a UPI payment gateway (TBD-3) and an SMS/OTP provider (TBD-4)."],
    ["D-2", "A partner bank/NBFC willing to accept the Trust Score as an input to its credit decision."],
    ["D-3", "Municipal bodies providing vending-zone data and licence rules (TBD-1)."],
], [0.55, 5.7])

# ====================================================================== 3 External interfaces
heading("3. External Interface Requirements", 1)
heading("3.1 User Interfaces", 2)
para("All screens share a top bar (logo, user name and role, Dashboard and Logout links) and show success or error "
     "messages in a coloured banner at the top of the page (green for success, red for errors).")
table(["Screen", "Used by", "Main elements"], [
    ["Landing page", "Everyone", "Short explanation of the 3-step journey; Register and Log in buttons"],
    ["Register / Login", "Everyone", "Name, mobile number, role (picked from four cards), password (+confirm); demo accounts "
     "that fill the login form in one click"],
    ["Vendor dashboard", "Vendor", "Summary cards (Trust Score, 30-day sales, active days, eligible limit / next "
     "EMI); Trust Score ring with risk band and a bar per component; 14-day sales chart with the daily-sale form; "
     "micro-credit card showing the three tiers, the apply form and the loan list; business profile form"],
    ["Loan detail", "Vendor, Officer", "Loan summary; EMI schedule table; Pay button on the next due installment"],
    ["Officer dashboard", "Bank officer", "Count cards per status; applications table (pending first) with a "
     "colour-coded Trust Score; Approve/Reject with remarks; Disburse; Run default check"],
    ["Find vendors", "Customer", "Search by area; vendor cards with business type, zone and UPI ID"],
    ["Municipal dashboard", "Municipal officer", "Vendor registry by zone (licence screens in next increment)"],
], [1.4, 1.2, 3.65])
for b in [
    "Layout is responsive (single column below 640 px) and uses large touch targets for vendors.",
    "Loan status is shown as colour-coded pills (Pending, Approved, Disbursed, Rejected, Defaulted, Closed).",
    "Error messages state what is wrong and how to fix it, e.g. \"Amount exceeds Tier 1 limit of Rs 15,000\".",
]:
    bullet(b)

heading("3.2 Hardware Interfaces", 2)
para("The system has no direct hardware interface. It runs in a browser on smartphones and PCs. Later increments "
     "may use the phone's GPS (vendor location) and camera (scanning a vendor's UPI QR code) through standard "
     "browser APIs.")

heading("3.3 Software Interfaces", 2)
table(["Component", "Version", "Purpose / data exchanged"], [
    ["Python", "3.11", "Runtime for the application server"],
    ["Flask (with Werkzeug, Jinja2)", "3.1", "Web framework, routing, sessions, HTML templates, password hashing"],
    ["SQLite / PostgreSQL", "3.x / 15", "Persistent storage of all entities (Section 6.1)"],
    ["UPI payment gateway", "TBD-3", "Out: payment request (amount, payee UPI ID). In: payment confirmation / failure"],
    ["SMS / OTP gateway", "TBD-4", "Out: OTP, EMI reminders, loan status alerts"],
    ["Map service (OpenStreetMap / Leaflet)", "Future", "Display vending zones and nearby vendors"],
    ["Lender core banking system", "Future (REST/JSON)", "Out: approved loan details. In: disbursal and repayment "
     "confirmation"],
], [1.9, 1.15, 3.2])

heading("3.4 Communications Interfaces", 2)
for b in [
    "All client-server traffic uses HTTPS (TLS 1.2 or higher) in deployment; forms are submitted with HTTP POST.",
    "Sessions use a signed, HttpOnly cookie; no sensitive data is placed in URLs.",
    "Notifications (EMI reminders, loan decisions) will be sent by SMS in the next increment.",
    "Integration with lenders will use a JSON REST API over HTTPS with API-key authentication (future).",
]:
    bullet(b)

# ====================================================================== 4 System features
heading("4. System Features", 1)
para("Functional requirements are organised by feature. Priorities use the MoSCoW technique:")
table(["Priority", "Features", "Release"], [
    ["Must have", "4.1 Registration & Authentication; 4.2 Vendor Profile & Daily Sales; 4.3 Trust Scoring Engine; "
     "4.4 Loan Application & Progressive Lending; 4.5 Loan Review & Disbursal; 4.6 EMI Repayment",
     "1.0 (implemented)"],
    ["Should have", "4.7 Vending Zone Licensing; 4.9 Customer: Locate & Pay Vendors", "1.1"],
    ["Could have", "4.8 Dispute / Eviction Case Logging; 4.10 Peer-Guarantor Group Lending; vendor ratings; "
     "vending-zone map", "1.2"],
    ["Won't have (this release)", "Aadhaar e-KYC, direct credit-bureau reporting, real fund transfer, voice "
     "interface", "Later"],
], [1.4, 3.85, 1.0])

FEATURES = [
    ("4.1 User Registration & Authentication [Implemented]",
     "Lets every user class create an account and log in securely. Priority: **Must have / High**.",
     [["User opens Register, fills name, mobile, role, password", "Validates input, stores the account with a hashed "
       "password, shows \"Registration successful\""],
      ["User enters mobile number and password on Login", "Verifies credentials and opens the role's dashboard"],
      ["User enters a wrong password", "Shows \"Invalid mobile number or password\"; counts the failed attempt"],
      ["Fifth consecutive wrong password", "Locks the account and shows the lock message"],
      ["User opens a page of another role", "Redirects to own dashboard with \"You are not allowed to open that page\""]],
     [["FR-AUTH-1", "The system shall let a new user register with full name, mobile number, password and one role: "
       "Vendor, Bank/NBFC Officer, Municipal Officer or Customer. The name shall have at most 50 characters and "
       "contain only letters, spaces, dots and apostrophes."],
      ["FR-AUTH-2", "The mobile number shall be a valid 10-digit Indian number starting with 6-9 and shall be unique; "
       "otherwise the system shall show \"Enter a valid 10-digit mobile number\" or \"Mobile number already "
       "registered\"."],
      ["FR-AUTH-3", "The password shall have at least 6 characters including at least one letter and one digit."],
      ["FR-AUTH-4", "Passwords shall be stored only as salted one-way hashes."],
      ["FR-AUTH-5", "On successful login the system shall start a session and open the dashboard of the user's role."],
      ["FR-AUTH-6", "After 5 consecutive failed login attempts the account shall be locked; a successful login "
       "resets the counter."],
      ["FR-AUTH-7", "Every page except Landing, Register and Login shall require a logged-in user, and role-specific "
       "pages shall be accessible only to that role."],
      ["FR-AUTH-8", "Mobile-number verification by OTP shall be added when the SMS gateway is available (TBD-4)."]]),
    ("4.2 Vendor Profile & Daily Sales Logging [Implemented]",
     "Creates the vendor's digital business identity and the sales history that feeds the Trust Score. "
     "Priority: **Must have / High**.",
     [["Vendor fills business type, vending zone, years of vending, UPI ID and saves", "Saves or updates the profile; "
       "Trust Score card appears"],
      ["Vendor enters date, amount, payment mode and clicks Log sale", "Validates and stores the entry, refreshes "
       "the 30-day statistics and Trust Score"],
      ["Vendor logs a second entry for the same date", "Rejects with \"Sales already logged for this date\""]],
     [["FR-VEN-1", "A vendor shall be able to create and update a profile: business type, vending zone, years of "
       "vending and optional UPI ID."],
      ["FR-VEN-2", "Business type and vending zone are mandatory; years of vending shall be 0-60."],
      ["FR-VEN-3", "A vendor shall be able to log one sales entry per day with date, amount and payment mode "
       "(Cash or UPI)."],
      ["FR-VEN-4", "The amount shall be a valid number greater than 0 and not more than ₹1,00,000 per day."],
      ["FR-VEN-5", "The sale date shall not be in the future nor more than 90 days old, and only one entry per date "
       "is allowed."],
      ["FR-VEN-6", "Sales can be logged only after the profile is complete."],
      ["FR-VEN-7", "The dashboard shall show active days, total and daily average sales for the last 30 days and the "
       "10 most recent entries."]]),
    ("4.3 Alternative Credit (Trust) Scoring Engine [Implemented]",
     "Replaces the missing CIBIL score with a transparent score built from data the platform observes. "
     "Priority: **Must have / High**. Detailed processing is shown in the Level-2 DFD (Figure 8).",
     [["Vendor opens the dashboard", "Computes and shows the score, risk band and the four component points"],
      ["Vendor applies for a loan", "Computes the score; blocks the application if the score is below 40"]],
     [["FR-TS-1", "The system shall compute a Trust Score from 0 to 100 from the vendor's profile, last-30-day sales, "
       "EMI history and vouches whenever the dashboard is opened or a loan is applied for."],
      ["FR-TS-2", "Score = Sales consistency (active days / 30 × 40) + Repayment history (on-time EMIs / EMIs due × "
       "40) + Peer vouching (min(vouches, 3) / 3 × 10) + Vending tenure (min(years, 5) / 5 × 10), rounded to the "
       "nearest integer."],
      ["FR-TS-3", "A vendor with no EMI due yet shall receive a neutral 20 repayment points."],
      ["FR-TS-4", "Risk band: 70-100 LOW RISK, 40-69 MEDIUM RISK, 0-39 HIGH RISK."],
      ["FR-TS-5", "A score of at least 40 is required to apply for a loan."],
      ["FR-TS-6", "The vendor shall see the points earned in each component, so the score is explainable."]]),
    ("4.4 Loan Application & Progressive Lending [Implemented]",
     "Lets an eligible vendor apply for a working-capital loan whose limit grows as earlier loans are repaid. "
     "Priority: **Must have / High**.",
     [["Vendor enters an amount within the shown tier and clicks Apply", "Checks eligibility, stores the "
       "application as PENDING with a snapshot of the Trust Score"],
      ["Vendor enters an amount above the tier limit", "Rejects with \"Amount exceeds Tier n limit of Rs X\""],
      ["Vendor with a PENDING application clicks Withdraw", "Marks the application WITHDRAWN"]],
     [["FR-LN-1", "An eligible vendor shall be able to apply for a loan by entering the amount."],
      ["FR-LN-2", "Tier limits: Tier 1 up to ₹15,000 for 12 months; Tier 2 up to ₹25,000 for 18 months; Tier 3 up to "
       "₹50,000 for 36 months."],
      ["FR-LN-3", "The eligible tier shall be (number of fully repaid loans + 1), at most 3."],
      ["FR-LN-4", "The amount shall be a valid number greater than 0 and not more than the tier limit."],
      ["FR-LN-5", "A vendor may have only one active loan (Pending, Approved, Disbursed or Defaulted) at a time."],
      ["FR-LN-6", "The application shall store the tier, tenure, interest rate and Trust Score at the time of "
       "applying, with status PENDING; the vendor may withdraw it while it is PENDING."]]),
    ("4.5 Loan Review & Disbursal (Bank / NBFC) [Implemented]",
     "Gives the lender a queue of applications with the Trust Score and controls the loan life cycle. Priority: "
     "**Must have / High**. Life cycle: Figure 5.",
     [["Officer opens the dashboard", "Lists applications, PENDING first, with vendor, amount, tier and Trust Score"],
      ["Officer clicks Approve", "Sets status APPROVED"],
      ["Officer clicks Reject without remarks", "Rejects the action: \"Remarks are required when rejecting\""],
      ["Officer clicks Disburse on an APPROVED loan", "Sets DISBURSED and generates the EMI schedule"],
      ["Officer runs the default check", "Marks loans with an EMI more than 90 days overdue as DEFAULTED"]],
     [["FR-BNK-1", "The officer shall see all applications with vendor name, mobile, date, tier, amount, Trust Score "
       "and status, with PENDING applications first."],
      ["FR-BNK-2", "Only PENDING applications can be approved or rejected."],
      ["FR-BNK-3", "Rejection shall require remarks, which are shown to the vendor."],
      ["FR-BNK-4", "Only users with the Bank/NBFC Officer role can review or disburse loans."],
      ["FR-BNK-5", "Only APPROVED loans can be disbursed; disbursal sets the status to DISBURSED and records the date."],
      ["FR-BNK-6", "On disbursal the system shall generate a monthly reducing-balance EMI schedule: "
       "EMI = P·r·(1+r)^n / ((1+r)^n − 1), r = annual rate / 12; the last EMI absorbs rounding."],
      ["FR-BNK-7", "A DISBURSED loan with any EMI unpaid more than 90 days after its due date shall be marked "
       "DEFAULTED."]]),
    ("4.6 EMI Repayment Tracking [Implemented]",
     "Records repayments, which close the loan, unlock the next tier and raise the Trust Score. Priority: "
     "**Must have / High**.",
     [["Vendor opens a loan", "Shows the schedule with due dates, EMI split and status"],
      ["Vendor pays the next due EMI", "Marks it PAID (on time or late) and refreshes the schedule"],
      ["Vendor pays the last EMI", "Marks the loan CLOSED and shows that the next tier is unlocked"]],
     [["FR-EMI-1", "The vendor shall see each installment's number, due date, EMI, principal, interest and status."],
      ["FR-EMI-2", "Installments shall be paid in order; paying a later one first shows \"Pay earlier installment "
       "#n first\"."],
      ["FR-EMI-3", "The amount paid shall not be less than the EMI due."],
      ["FR-EMI-4", "An installment that is already paid cannot be paid again."],
      ["FR-EMI-5", "The system shall record the payment date and whether it was on or before the due date; this "
       "feeds the repayment component of the Trust Score."],
      ["FR-EMI-6", "When all installments are paid the loan shall become CLOSED and the vendor becomes eligible for "
       "the next tier."]]),
    ("4.7 Vending Zone Licensing",
     "Digitises the vending certificate process of the Street Vendors Act 2014 (R5). Priority: **Should have / "
     "Medium**.",
     [["Vendor submits a licence application for a zone", "Creates the application and notifies the ward's "
       "municipal officer"],
      ["Municipal officer approves", "Issues a licence number with issue and expiry dates"],
      ["Licence is 30 days from expiry", "Sends a renewal reminder to the vendor"]],
     [["FR-LIC-1", "A vendor shall be able to apply for a vending licence for a chosen vending zone."],
      ["FR-LIC-2", "The municipal officer of that ward shall approve or reject the application with remarks."],
      ["FR-LIC-3", "An approved licence shall have a unique number, issue date and expiry date (validity TBD-1)."],
      ["FR-LIC-4", "The vendor shall be reminded 30 days before expiry and be able to renew online."],
      ["FR-LIC-5", "Vendors shall see a map of permitted vending zones."]]),
    ("4.8 Dispute / Eviction Case Logging",
     "Gives municipal officers a record of disputes and eviction notices. Priority: **Could have / Low**.",
     [["Officer logs a case against a vendor or zone", "Creates the case with status OPEN and notifies the vendor"],
      ["Officer resolves the case", "Records the resolution and closes the case"]],
     [["FR-CASE-1", "A municipal officer shall log a case with type (dispute, eviction notice, relocation), "
       "description, vendor and date."],
      ["FR-CASE-2", "The affected vendor shall be notified and able to view the case."],
      ["FR-CASE-3", "A case shall move OPEN → UNDER REVIEW → RESOLVED, with remarks at each step."],
      ["FR-CASE-4", "Eviction cases shall reference the vendor's licence where one exists."]]),
    ("4.9 Customer: Locate, Pay & Rate Vendors",
     "Brings customers onto the platform and gives vendors a source of digital (verifiable) sales. Priority: "
     "**Should have / Medium** (vendor search by area is already implemented).",
     [["Customer searches by area", "Lists matching vendors with business type, zone and UPI ID"],
      ["Customer pays a vendor", "Initiates a UPI payment and stores the receipt"],
      ["Customer rates a vendor after paying", "Stores hygiene and service ratings"]],
     [["FR-CUS-1", "A customer shall be able to search vendors by area or vending zone. [Implemented]"],
      ["FR-CUS-2", "A customer shall be able to view nearby vendors on a map (future)."],
      ["FR-CUS-3", "A customer shall be able to pay a vendor through UPI; the payment shall also be recorded as a "
       "verified sale for the vendor."],
      ["FR-CUS-4", "After a payment, a customer may rate hygiene and service from 1 to 5 stars with a comment."]]),
    ("4.10 Peer-Guarantor Group Lending",
     "Uses the joint-liability model common in Indian microfinance. Priority: **Could have / Low**.",
     [["Vendor A vouches for vendor B", "Records the vouch; B's peer-vouching points increase"],
      ["Vendors form a lending circle", "Creates a group whose members see each other's repayment status"]],
     [["FR-PEER-1", "A vendor shall be able to vouch for another vendor once; a vendor cannot vouch for themself."],
      ["FR-PEER-2", "At most 3 vouches count toward the Trust Score (FR-TS-2)."],
      ["FR-PEER-3", "Vendors shall be able to form lending circles of 3-5 members (rules TBD-7)."],
      ["FR-PEER-4", "If a member's EMI is overdue, the circle's members shall be notified."]]),
]

for title, desc, stims, reqs in FEATURES:
    num = title.split(" ")[0]
    heading(title, 2)
    heading(f"{num}.1 Description and Priority", 3)
    para(desc)
    heading(f"{num}.2 Stimulus/Response Sequences", 3)
    stim_table(stims)
    heading(f"{num}.3 Functional Requirements", 3)
    req_table(reqs)

# ====================================================================== 5 NFRs
heading("5. Other Nonfunctional Requirements", 1)
heading("5.1 Performance Requirements", 2)
req_table([
    ["NFR-PERF-1", "95% of page requests shall complete within 2 seconds with 100 concurrent users."],
    ["NFR-PERF-2", "Trust Score computation for one vendor shall take less than 0.5 seconds."],
    ["NFR-PERF-3", "Each page shall be under 500 KB so it loads within 5 seconds on a 3G connection."],
    ["NFR-PERF-4", "The system shall support at least 10,000 registered vendors and 1 million sales records "
     "without redesign."],
])
heading("5.2 Safety Requirements", 2)
req_table([
    ["NFR-SAFE-1", "No loan shall be disbursed automatically; a human bank officer must approve and disburse "
     "(human-in-the-loop). The Trust Score is an input to, not a replacement for, the lender's decision."],
    ["NFR-SAFE-2", "Every approval, rejection and disbursal shall record the officer and remarks for audit."],
    ["NFR-SAFE-3", "Database backups shall be taken daily and kept for 30 days so financial records are not lost."],
    ["NFR-SAFE-4", "Invalid input shall never corrupt stored data; each operation is validated before it is saved."],
])
heading("5.3 Security Requirements", 2)
req_table([
    ["NFR-SEC-1", "Passwords shall be stored as salted hashes (Werkzeug scrypt/PBKDF2); plain text is never stored."],
    ["NFR-SEC-2", "Accounts shall lock after 5 consecutive failed logins (FR-AUTH-6)."],
    ["NFR-SEC-3", "Role-based access control shall be enforced on the server for every request (FR-AUTH-7)."],
    ["NFR-SEC-4", "All database queries shall use parameterised statements to prevent SQL injection."],
    ["NFR-SEC-5", "Templates shall auto-escape user input to prevent cross-site scripting."],
    ["NFR-SEC-6", "Production deployment shall use HTTPS and a secret key supplied through an environment variable."],
    ["NFR-SEC-7", "A vendor shall only see their own sales and loans; officers see only data needed for their role."],
    ["NFR-SEC-8", "Personal data handling shall comply with the DPDP Act 2023: consent at registration, purpose "
     "limitation and the right to request deletion."],
])
heading("5.4 Software Quality Attributes", 2)
req_table([
    ["NFR-USE-1", "A first-time vendor shall be able to log a day's sale in under 30 seconds."],
    ["NFR-USE-2", "Every error message shall say what went wrong and how to correct it."],
    ["NFR-REL-1", "Loan and EMI state changes shall be atomic (committed together or not at all)."],
    ["NFR-AVL-1", "The service shall be available 99% of the time, excluding announced maintenance."],
    ["NFR-MNT-1", "Business logic shall be separated from the web layer (modules package) and follow PEP 8."],
    ["NFR-MNT-2", "Loan tiers, interest rate and score weights shall be defined as constants in one place each."],
    ["NFR-TST-1", "Every Must-have feature shall have automated tests; all tests shall pass before a release."],
    ["NFR-PRT-1", "The application shall run unchanged on Windows and Linux and in any modern browser."],
])
heading("5.5 Business Rules", 2)
table(["ID", "Rule"], [
    ["BR-1", "Only a Bank/NBFC Officer may approve, reject, disburse or mark a loan as defaulted."],
    ["BR-2", "A vendor may hold only one active loan at a time."],
    ["BR-3", "Loan limits grow progressively: a tier is unlocked only after the previous loan is fully repaid."],
    ["BR-4", "A vendor needs a Trust Score of at least 40 to apply."],
    ["BR-5", "A rejected application must carry the officer's reason."],
    ["BR-6", "An EMI unpaid for more than 90 days after its due date makes the loan DEFAULTED."],
    ["BR-7", "A municipal officer may act only on licences and cases in their own ward."],
    ["BR-8", "A vendor cannot vouch for themself, and only 3 vouches count toward the score."],
], [0.7, 5.55], bold_first_col=True)

# ====================================================================== 6 Other requirements
heading("6. Other Requirements", 1)
heading("6.1 Database Requirements", 2)
table(["Table", "Key columns", "Notes"], [
    ["users", "user_id, name, phone (unique), password_hash, role, failed_attempts, is_locked", "All user classes"],
    ["vendor_profiles", "vendor_id (FK users), business_type, vending_zone, years_vending, upi_id", "1 per vendor"],
    ["sales", "sale_id, vendor_id, sale_date, amount, payment_mode", "Unique (vendor_id, sale_date)"],
    ["vouches", "vouch_id, voucher_id, vendor_id", "Unique (voucher_id, vendor_id)"],
    ["loans", "loan_id, vendor_id, tier, amount, tenure_months, interest_rate, trust_score, status, officer_id, "
     "remarks, applied_on, disbursed_on", "Status per Figure 5"],
    ["emi_installments", "emi_id, loan_id, installment_no, due_date, emi_amount, principal_part, interest_part, "
     "status, paid_on, paid_on_time", "Unique (loan_id, installment_no)"],
    ["licences, cases, ratings", "(next increment)", "Classes VendingLicence, DisputeCase, Rating"],
], [1.4, 3.55, 1.3])
heading("6.2 Legal and Regulatory Requirements", 2)
for b in [
    "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act, 2014 - licensing and Town "
    "Vending Committees.",
    "RBI Guidelines on Digital Lending (2022) - disbursal and repayment directly between borrower and regulated "
    "lender; loan terms shown to the borrower before acceptance.",
    "Digital Personal Data Protection Act, 2023 - consent, purpose limitation, data minimisation.",
]:
    bullet(b)
heading("6.3 Internationalisation Requirements", 2)
para("The interface shall support English and Hindi in release 1.1, with further regional languages added through "
     "translation files (TBD-6). Amounts shall use Indian digit grouping (₹1,00,000).")
heading("6.4 Reuse Objectives", 2)
para("The modules package (auth, vendor, credit_score, loan) has no web dependencies, so the same code can serve a "
     "future mobile app or lender API.")

# ====================================================================== Appendix A
heading("Appendix A: Glossary", 1)
table(["Term", "Meaning"], [
    ["CIBIL", "TransUnion CIBIL - India's best-known credit bureau; issues credit scores"],
    ["DFD", "Data Flow Diagram - shows how data moves between processes, data stores and external entities"],
    ["DPDP Act", "Digital Personal Data Protection Act, 2023"],
    ["EMI", "Equated Monthly Installment - fixed monthly repayment covering principal and interest"],
    ["KYC", "Know Your Customer - identity verification"],
    ["MoSCoW", "Prioritisation technique: Must have, Should have, Could have, Won't have"],
    ["NBFC", "Non-Banking Financial Company, regulated by the RBI"],
    ["PM SVANidhi", "PM Street Vendor's AtmaNirbhar Nidhi - GoI micro-credit scheme for street vendors"],
    ["Peer Guarantor", "A vendor who vouches for another vendor's reliability"],
    ["Progressive lending", "Loan limits that increase after each successful repayment"],
    ["Tier", "Loan level (1-3) that sets the maximum amount and tenure"],
    ["Trust Score", "VendorSetu's 0-100 alternative credit score"],
    ["TVC / ULB", "Town Vending Committee / Urban Local Body (municipal corporation or council)"],
    ["UML", "Unified Modeling Language"],
    ["UPI", "Unified Payments Interface - India's real-time payment system"],
], [1.5, 4.75], bold_first_col=True)

# ====================================================================== Appendix B (landscape)
new_section(landscape=True, margin=0.6)
MAXW = 10.4
heading("Appendix B: Analysis Models", 1)
para("This appendix contains the UML and structured-analysis models of VendorSetu: Use Case, Class, Sequence and "
     "State Transition diagrams, and Data Flow Diagrams at Levels 0, 1 and 2.")

heading("B.1 Use Case Diagram", 2)
figure("01_use_case_diagram.png", "Use Case Diagram", MAXW, 4.3)
para("**How to read it:** stick figures are actors (people or systems outside VendorSetu); ovals are use cases "
     "(goals an actor achieves); the rectangle is the system boundary. A solid line means the actor takes part in "
     "the use case. **«include»** (dashed arrow) means the base use case always performs the included one - "
     "applying for a loan always calculates the Trust Score. **«extend»** means optional behaviour - a customer may "
     "rate a vendor after paying. The hollow triangle shows that a Peer Guarantor is a specialised Street Vendor.")
heading("Use case descriptions", 3)
table(["Field", "UC-05 Apply for Loan", "UC-03 Log Daily Sales"], [
    ["Primary actor", "Street Vendor", "Street Vendor"],
    ["Pre-conditions", "Logged in; profile complete; no active loan", "Logged in; profile complete"],
    ["Main flow", "1. Vendor opens dashboard and sees eligible tier.\n2. Enters amount and clicks Apply.\n"
     "3. System checks for an active loan.\n4. System calculates the Trust Score («include»).\n"
     "5. System checks score ≥ 40 and amount ≤ tier limit.\n6. System saves the application as PENDING and "
     "confirms.", "1. Vendor enters date, amount and payment mode.\n2. Clicks Log sale.\n"
     "3. System validates the entry.\n4. System saves it and refreshes the 30-day summary and Trust Score."],
    ["Alternate flows", "3a. Active loan exists → error, end.\n5a. Score < 40 → \"not eligible\" with score.\n"
     "5b. Amount > limit → error with the limit.", "3a. Amount ≤ 0 or > ₹1,00,000 → error.\n"
     "3b. Future date → error.\n3c. Date already logged → error."],
    ["Post-conditions", "Loan record with status PENDING and Trust Score snapshot", "One new SALES record"],
    ["Requirements", "FR-LN-1 to FR-LN-6, FR-TS-5", "FR-VEN-3 to FR-VEN-7"],
], [1.5, 4.45, 4.45], bold_first_col=True)

page_break()
heading("B.2 Class Diagram", 2)
figure("02_class_diagram.png", "Class Diagram", MAXW, 5.0)
para("**How to read it:** each box is a class with three parts - name, attributes (- private) and operations "
     "(+ public). The hollow-triangle tree shows **inheritance**: Customer, Vendor, BankOfficer and "
     "MunicipalOfficer are kinds of the abstract User. Plain lines are **associations** with multiplicities "
     "(1, 0..1, 0..*), e.g. one Vendor applies for zero or more Loans. The filled diamond is **composition**: "
     "EMIInstallments cannot exist without their Loan. Dashed arrows are **dependencies** - TrustScoreEngine reads "
     "SaleRecords and EMIInstallments and creates a TrustScore value object, and Loan uses the engine to check "
     "eligibility.")

page_break()
heading("B.3 Sequence Diagrams", 2)
figure("03_sequence_login.png", "Sequence Diagram - User Login", MAXW, 4.8)
para("**How to read it:** participants are along the top, time flows downward on the dashed lifelines, and the "
     "thin rectangles show when an object is active. Solid arrows are calls, dashed arrows are returns. The **alt** "
     "frame shows the two possible outcomes: a valid login opens the dashboard; an invalid one increments the "
     "failed-attempt counter (locking the account at 5) and shows an error.")
page_break()
figure("04_sequence_loan.png", "Sequence Diagram - Loan Application, Approval and Disbursal", MAXW, 5.4)
para("Messages 1-14 show the vendor's application: the LoanService checks for an active loan, asks the "
     "TrustScoreEngine for a score (which reads the database and computes the score itself), and then either saves "
     "the PENDING application or returns the reason for refusal. Messages 15-24 show the bank officer approving the "
     "loan and disbursing it, which generates and saves the EMI schedule.")
para("Message names are the real function names in the code (login_user in modules/auth.py; apply_loan, "
     "review_loan, disburse_loan, generate_emi_schedule in modules/loan.py; get_trust_score, compute_trust_score in "
     "modules/credit_score.py). Pages (:LoginPage, :VendorDashboard, :OfficerDashboard) are boundary objects served "
     "by app.py; :AuthController, :LoanService and :TrustScoreEngine are the control objects implemented by those "
     "modules; the entity classes they read and write are the ones in the Class Diagram (Figure 2).")

page_break()
heading("B.4 State Transition Diagram", 2)
figure("05_state_transition_loan.png", "State Transition Diagram - Loan Application Life Cycle", MAXW, 3.8)
table(["State", "Meaning", "Leaves the state when"], [
    ["PENDING", "Application submitted, waiting for the bank", "Officer approves/rejects, or vendor withdraws"],
    ["APPROVED", "Bank has sanctioned the loan", "Officer disburses (EMI schedule created)"],
    ["DISBURSED", "Money released; vendor is repaying", "Last EMI paid (→ CLOSED) or an EMI is >90 days overdue "
     "(→ DEFAULTED)"],
    ["DEFAULTED", "Serious delay in repayment", "All dues cleared (→ CLOSED)"],
    ["REJECTED / WITHDRAWN / CLOSED", "Final states", "-"],
], [2.2, 3.6, 4.6], bold_first_col=True)

page_break()
heading("B.5 Data Flow Diagrams", 2)
para("Notation (Yourdon-DeMarco): rectangles are external entities, circles are processes, open-ended boxes are "
     "data stores, and labelled arrows are data flows.")
figure("06_dfd_level0_context.png", "DFD Level 0 (Context Diagram)", MAXW, 4.6)
para("The **context diagram** treats the whole of VendorSetu as one process (0) and shows only the data it "
     "exchanges with the six external entities.")
page_break()
figure("07_dfd_level1.png", "DFD Level 1", MAXW, 5.5)
para("**Level 1** breaks process 0 into seven processes and shows the data stores D1-D8. Process 3.0 (Trust Score) "
     "reads sales, profiles, vouches and EMI records and passes the score to 4.0 (Loans). Entities and stores "
     "marked * are drawn twice only to avoid crossing lines.")
page_break()
figure("08_dfd_level2_trust_score.png", "DFD Level 2 - Process 3.0 Compute Trust Score", MAXW, 5.2)
para("**Level 2** opens process 3.0: on a score request from 4.0, process 3.1 fetches the vendor's data, 3.2-3.4 "
     "compute the four score components, and 3.5 adds them (0-100), assigns the risk band and returns the result to "
     "4.0, which shows it to the vendor. This matches compute_trust_score() in Appendix D.")
para("**Balancing:** every data flow that enters or leaves a process at one level also appears at the next level - "
     "e.g. the vendor's \"trust score\" output in Level 0 is produced by 3.0 → 4.0 → Vendor in Level 1, and the "
     "\"score request\" from 4.0 into 3.0 in Level 1 is the input of process 3.1 in Level 2.")

# ====================================================================== Appendix C, D (portrait)
new_section(landscape=False, margin=1.0)
heading("Appendix C: To Be Determined List", 1)
table(["#", "Item", "Section"], [
    ["TBD-1", "Licence validity period and fees - set by each city's Town Vending Committee", "4.7"],
    ["TBD-2", "Partner lender's actual interest rate (12% p.a. assumed)", "2.7, 4.5"],
    ["TBD-3", "UPI payment gateway provider", "3.3"],
    ["TBD-4", "SMS/OTP provider for mobile verification and reminders", "3.3, 4.1"],
    ["TBD-5", "Re-calibration of Trust Score weights using real repayment data", "4.3"],
    ["TBD-6", "Regional languages beyond Hindi and English", "6.3"],
    ["TBD-7", "Lending-circle size and joint-liability rules", "4.10"],
], [0.7, 4.45, 1.1], bold_first_col=True)

heading("Appendix D: Implementation (Release 1.0 Prototype)", 1)
heading("D.1 Development Approach and Technology", 2)
para("The project follows an **incremental model**: Increment 1 implements the six \"Must have\" features end-to-end "
     "(four code modules plus the web interface); later increments add the Should/Could features. Technology: "
     "Python 3.11, Flask 3.1, SQLite, Jinja2 templates, pytest.")
heading("D.2 Coded Modules", 2)
table(["Module", "Source file", "Features / requirements", "Key functions"], [
    ["1. Registration & Authentication", "app/modules/auth.py", "4.1 - FR-AUTH-1..7",
     "register_user, login_user"],
    ["2. Vendor Profile & Daily Sales", "app/modules/vendor.py", "4.2 - FR-VEN-1..7",
     "save_profile, log_daily_sale, sales_summary"],
    ["3. Trust Scoring Engine", "app/modules/credit_score.py", "4.3 - FR-TS-1..6",
     "compute_trust_score, get_trust_score"],
    ["4. Loan Management (application, review, disbursal, EMI)", "app/modules/loan.py",
     "4.4-4.6 - FR-LN, FR-BNK, FR-EMI", "apply_loan, review_loan, disburse_loan, generate_emi_schedule, pay_emi"],
    ["Web interface", "app/app.py, app/templates/", "3.1 User Interfaces", "Flask routes per role"],
], [1.75, 1.5, 1.45, 1.55])
heading("D.3 Project Structure", 2)
code_block("""SE_Project/
  app/
    app.py               Flask routes (web layer)
    database.py          SQLite schema + connection helper
    seed_demo.py         creates demo users and data
    modules/
      auth.py            Module 1 - registration & login
      vendor.py          Module 2 - profile & daily sales
      credit_score.py    Module 3 - Trust Score engine
      loan.py            Module 4 - loans, EMI schedule, repayment
    templates/, static/  HTML pages and stylesheet
  tests/
    test_cases.py        documented test cases (Appendix E)
    run_test_cases.py    executes cases, records actual output
    test_vendorsetu.py   pytest wrapper for the same cases
    test_integration.py  end-to-end tests through the web routes
  diagrams/              diagram source (Python) + PNG output
  docs/                  this SRS and its generator""")
heading("D.4 Key Algorithms", 2)
para("Trust Score (FR-TS-2) - excerpt from app/modules/credit_score.py:")
src = inspect.getsource(credit_score.compute_trust_score)
code_block(src.split('    return {')[0] + "    ...")
para("EMI schedule (FR-BNK-6) - excerpt from app/modules/loan.py:")
code_block(inspect.getsource(loan.generate_emi_schedule))
heading("D.5 How to Run", 2)
code_block("""pip install flask pytest
cd app
python seed_demo.py        # creates demo data
python app.py              # open http://127.0.0.1:5000

Demo logins (mobile / password):
  Vendor        9876543210 / ramesh123
  Bank officer  9123456780 / bank123
  Customer      9988776655 / priya123
  Municipal     9090909090 / muni123

python -m pytest tests -v  # run all automated tests""")
heading("D.6 Coding Standards Followed", 2)
for b in [
    "PEP 8 naming (snake_case functions, UPPER_CASE constants) and a module docstring naming the SRS section it "
    "implements.",
    "Business rules raise a single ValidationError type with a user-readable message; the web layer only displays it.",
    "All SQL uses ? parameters (no string concatenation of user input).",
    "Configuration values (tiers, interest rate, score weights, lock-out limit) are named constants.",
    "Functions accept an optional 'today' date so time-dependent rules can be tested deterministically.",
]:
    bullet(b)

# ====================================================================== Appendix E (landscape)
with open(os.path.join(ROOT, "tests", "test_results.json"), encoding="utf-8") as f:
    results = json.load(f)
pytest_run = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, capture_output=True,
                            text=True)
pytest_summary = [ln for ln in pytest_run.stdout.strip().splitlines() if "passed" in ln or "failed" in ln][-1]
with open(os.path.join(ROOT, "tests", "test_results_before_fix.json"), encoding="utf-8") as f:
    before = json.load(f)
failed1 = [r for r in before["results"] if r["remark"] == "FAIL"]
run1 = {r["id"]: r["remark"] for r in before["results"]}

new_section(landscape=True, margin=0.7)
heading("Appendix E: Test Cases and Results", 1)
heading("E.1 Test Strategy", 2)
n_system = sum(r["level"] == "System" for r in results["results"])
n_unit = sum(r["level"] == "Unit" for r in results["results"])
for b in [
    f"**System testing ({n_system} cases):** each case is performed through the web interface exactly as a user "
    "would - fill a form, click a button - and the Expected / Actual Output is the message or value shown on the "
    "page, so every case can be repeated by hand in the demo.",
    f"**Unit testing ({n_unit} cases):** the Trust Score formula is tested directly; the Expected Output shows the "
    "hand calculation (e.g. 40 + 20 + 10 + 10 = 80).",
    "**Design techniques:** positive testing; equivalence partitioning (every invalid class: empty, wrong format, "
    "non-numeric, nan / inf, out of range); boundary-value analysis on both sides of every limit (name 50 / 51, "
    "password 5 / 6, amount 1,00,000 / 1,00,000.01, date 90 / 91 days, score 39 / 40 and 69 / 70, tier limit "
    "15,000 / 15,000.01, 90 / 91 days overdue); combination testing; security testing (role check, forged "
    "requests, SQL injection).",
    f"**Combination testing:** {sum(c['combinations'] for c in results['combinations']):,} combinations of valid and "
    f"invalid values in {len(results['combinations'])} forms (every value of every field with every value of the "
    f"others) were submitted; {sum(c['matched'] for c in results['combinations']):,} gave exactly the result "
    "required by the SRS, with no crash and no invalid data stored.",
    f"**Defects found and fixed:** the first version of the code (commit 0ce1911) failed {len(failed1)} of these "
    f"test cases; {len(results['defects'])} defects (e.g. 'nan' as an amount crashed the app, customers could "
    "open a vendor's loan page) were logged, fixed and re-tested - see E.8.",
    "**Integration testing:** two end-to-end scenarios (register → login → profile → sale → apply → approve → "
    "disburse → pay EMI; role-based access).",
    "**Test automation:** tests/run_test_cases.py executes every case on a fresh, empty database and copies the "
    "on-screen result into the Actual Output column; the same cases run under pytest.",
    f"**Latest automated run:** pytest - {pytest_summary} (documented cases, combination suites and integration "
    "tests). The full "
    "step-by-step version of these cases, with a requirements traceability matrix, is in the separate Test Case "
    "Document (docs/Test_Cases_VendorSetu.docx).",
]:
    bullet(b)

order = ["AUTH", "SALE", "TS", "LOAN", "EMI"]
summary_rows = []
for i, key in enumerate(order, start=2):
    meta = results["modules"][key]
    rows = [r for r in results["results"] if r["module"] == key]
    page_break()
    heading(f"E.{i} {meta['name']}", 2)
    hdr = doc.add_table(rows=4, cols=4)
    hdr.style = "Table Grid"
    hdr.alignment = WD_TABLE_ALIGNMENT.CENTER
    cells = [
        ("Test Case #:", f"{rows[0]['id']} to {rows[-1]['id']}", "Test Case Name:", meta["name"]),
        ("System:", "VendorSetu", "Subsystem:", meta["subsystem"]),
        ("Designed by:", "Nancy Yadav & team", "Design Date:", "-".join(reversed(results["executed_on"].split("-")))),
        ("Executed by:", "Nancy Yadav & team", "Execution Date:", "-".join(reversed(results["executed_on"].split("-")))),
    ]
    widths = [1.3, 3.5, 1.4, 3.9]
    for r_i, values in enumerate(cells):
        for c_i, v in enumerate(values):
            cell = hdr.rows[r_i].cells[c_i]
            cell.width = Inches(widths[c_i])
            rich(cell.paragraphs[0], v, size=9.5, bold=c_i % 2 == 0)
            if c_i % 2 == 0:
                set_cell_bg(cell, "EEF3EF")
    p = para(f"**Short Description:** {meta['description']}", size=10, space_after=2)
    p.paragraph_format.space_before = Pt(6)
    para("**Pre-conditions:** " + " ".join(meta["pre"]), size=10, space_after=6)

    t = table(["TC ID", "Test Scenario", "Type", "Input (Test Data)", "Expected Output", "Actual Output", "Remark"],
              [[r["id"], r["scenario"] + ("" if r["pre"] == "-" else f"\nPre: {r['pre']}"),
                f"{r['level']}\n{r['technique']}", r["input"], r["expected"], r["actual"],
                r["remark"] + (f"\n(Run 1: FAIL, {r['defect']})" if run1.get(r["id"]) == "FAIL" else "")]
               for r in rows],
              [0.8, 1.85, 0.7, 1.7, 1.85, 1.85, 0.65], font_size=8)
    for row in t.rows[1:]:
        remark = row.cells[6]
        set_cell_bg(remark, "D9F0E1" if remark.text.startswith("PASS") else "F8D7D3")
        remark.paragraphs[0].runs[0].bold = True
    para("**Post-conditions:** " + " ".join(meta["post"]), size=10)
    passed = sum(r["remark"] == "PASS" for r in rows)
    summary_rows.append([meta["name"], str(len(rows)), str(passed), str(len(rows) - passed),
                         f"{passed / len(rows) * 100:.0f}%"])

page_break()
heading(f"E.{len(order) + 2} Test Summary", 2)
total = sum(int(r[1]) for r in summary_rows)
total_pass = sum(int(r[2]) for r in summary_rows)
summary_rows.append(["**Total**", f"**{total}**", f"**{total_pass}**", f"**{total - total_pass}**",
                     f"**{total_pass / total * 100:.0f}%**"])
table(["Module", "Test cases", "Passed", "Failed", "Pass rate"], summary_rows, [3.6, 1.2, 1.2, 1.2, 1.2])
table(["Integration test (tests/test_integration.py)", "What it verifies", "Result"], [
    ["test_end_to_end_loan_flow", "Register vendor & officer → login → profile → sale → apply ₹15,000 → approve → "
     "disburse (12 EMIs of ₹1,332.73) → pay EMI #1 on time", "PASS" if pytest_run.returncode == 0 else "See log"],
    ["test_role_based_access", "Customer cannot open the officer page; logged-out user is sent to login",
     "PASS" if pytest_run.returncode == 0 else "See log"],
], [3.0, 5.6, 1.0])
para("Actual outputs above are recorded by executing the code, not typed by hand; re-running "
     "tests/run_test_cases.py and docs/build_srs.py regenerates these tables.", size=10)

heading(f"E.{len(order) + 3} Defects Found by Testing", 2)
para(f"Run 1 executed the same cases on the first version of the code (git commit 0ce1911): {len(failed1)} cases "
     "FAILED. Each was logged as a defect, fixed and re-tested (Run 2, results above). The full Run-1 outputs are in "
     "Section 9 of the Test Case Document.", size=10)
table(["Defect", "Severity", "Found by", "What happened in Run 1", "Fix", "Re-test"],
      [[d["id"], d["severity"], ", ".join(d["cases"]), d["found"], d["fix"], "PASS - closed"]
       for d in results["defects"]], [0.7, 0.7, 1.1, 3.3, 3.3, 0.9], font_size=8.5)

doc.save(OUT)
print("Saved", OUT)
print("pytest:", pytest_summary)
