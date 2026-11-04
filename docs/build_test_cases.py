"""
build_test_cases.py - Generates the standalone Test Case Document (Doc T_01 template format).

    python tests/run_test_cases.py --before-fix   # Run 1: the first version of the code (commit 0ce1911)
    python tests/run_test_cases.py                # Run 2: the current code
    python docs/build_test_cases.py               # writes docs/Test_Cases_VendorSetu.docx
"""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "Test_Cases_VendorSetu.docx")
GREEN = RGBColor(0x1F, 0x5C, 0x3D)
TEAM = "Nancy Yadav, <<Member 2>>, <<Member 3>>, <<Member 4>>"
ORDER = ["AUTH", "SALE", "TS", "LOAN", "EMI"]

with open(os.path.join(ROOT, "tests", "test_results.json"), encoding="utf-8") as f:
    data = json.load(f)
results, modules, defects, combos = data["results"], data["modules"], data["defects"], data["combinations"]
executed = "-".join(reversed(data["executed_on"].split("-")))
BEFORE = os.path.join(ROOT, "tests", "test_results_before_fix.json")
if not os.path.exists(BEFORE):
    sys.exit("First run:  python tests/run_test_cases.py --before-fix")
with open(BEFORE, encoding="utf-8") as f:
    before = json.load(f)
run1 = {r["id"]: r for r in before["results"]}
combos1 = {c["form"]: c for c in before["combinations"]}
failed1 = [r for r in before["results"] if r["remark"] == "FAIL"]
pytest_run = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, capture_output=True, text=True)
pytest_summary = [ln for ln in pytest_run.stdout.strip().splitlines() if "passed" in ln or "failed" in ln][-1]

doc = Document()


# ---------------------------------------------------------------- helpers
def shade(cell, color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def rich(p, text, size=None, bold=False, italic=False):
    for part in re.split(r"(\*\*.+?\*\*|<<.+?>>)", text):
        if not part:
            continue
        if part.startswith("**"):
            run = p.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("<<"):
            run = p.add_run("<" + part[2:-2] + ">")
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            run.bold = bold
        else:
            run = p.add_run(part)
            run.bold = bold
        run.italic = italic
        if size:
            run.font.size = Pt(size)
    return p


def para(text="", size=None, bold=False, italic=False, align=None, after=6):
    p = doc.add_paragraph()
    rich(p, text, size=size, bold=bold, italic=italic)
    p.paragraph_format.space_after = Pt(after)
    if align is not None:
        p.alignment = align
    return p


def heading(text, level):
    h = doc.add_heading(text, level)
    h.paragraph_format.keep_with_next = True
    return h


def table(headers, rows, widths, size=9, header_bg="DDEBE3", bold_first=False):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tr_pr = t.rows[0]._tr.get_or_add_trPr()
    rep = OxmlElement("w:tblHeader")
    rep.set(qn("w:val"), "true")
    tr_pr.append(rep)
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.width = Inches(widths[i])
        rich(c.paragraphs[0], h, size=size, bold=True)
        shade(c, header_bg)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].width = Inches(widths[i])
            lines = str(v).split("\n")
            rich(cells[i].paragraphs[0], lines[0], size=size, bold=bold_first and i == 0)
            for ln in lines[1:]:
                rich(cells[i].add_paragraph(), ln, size=size)
    for row in t.rows:
        no_split(row)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def box(title, lines):
    """Single-cell bordered box, like the template's Pre-conditions / Post-conditions boxes."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    c.width = Inches(10.4)
    no_split(t.rows[0])
    rich(c.paragraphs[0], title, size=9.5, bold=True)
    for i, ln in enumerate(lines, start=1):
        rich(c.add_paragraph(), f"{i}. {ln}", size=9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def add_page_field(p):
    run = p.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("separate", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
    num = p.add_run("1")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    num._r.addnext(end)


# ---------------------------------------------------------------- page setup (landscape A4)
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(10.5)
for lvl, size in ((1, 16), (2, 13)):
    hs = doc.styles[f"Heading {lvl}"]
    hs.font.name = "Calibri"
    hs.font.size = Pt(size)
    hs.font.color.rgb = GREEN
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = Inches(11.69), Inches(8.27)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Inches(0.6))
for side in ("top_margin", "bottom_margin"):
    setattr(sec, side, Inches(0.45))
sec.header_distance = sec.footer_distance = Inches(0.25)
rich(sec.header.paragraphs[0], "Test Case Document - VendorSetu   |   CSE3005 Software Engineering", size=8.5,
     italic=True).alignment = WD_ALIGN_PARAGRAPH.RIGHT
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
rich(fp, "Page ", size=9)
add_page_field(fp)

# ---------------------------------------------------------------- cover
for _ in range(4):
    doc.add_paragraph()
para("Test Case Document", size=30, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
p = para("VendorSetu", size=24, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
p.runs[0].font.color.rgb = GREEN
para("Street Vendor Formalization & Micro-Credit Platform", size=14, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
para("Version 1.1  ·  Based on SRS v1.0 and Test Case Template (Doc T_01)", size=11,
     align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
para(f"Prepared by: {TEAM}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
para("B.Tech CSE, Batch 2024 - CSE3005 Software Engineering - BML Munjal University", size=12,
     align=WD_ALIGN_PARAGRAPH.CENTER)
para("Submitted to: <<Faculty name>>", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
para(f"Test execution date: {executed}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
page_break()

# ---------------------------------------------------------------- 1 test plan
level_count = defaultdict(int)
for r in results:
    level_count[r["level"]] += 1
heading("1. Test Plan Summary", 1)
table(["Item", "Details"], [
    ["Objective", "Verify that the four implemented modules of VendorSetu meet their functional requirements "
     "(SRS Section 4.1-4.6) and reject invalid input with the correct message."],
    ["Modules under test", "1. Registration & Login  2. Vendor Profile & Daily Sales  3. Trust Scoring Engine  "
     "4. Loan Application & Bank Review  5. EMI Schedule & Repayment (Module 4 continued)"],
    ["Test levels", f"System testing through the web interface: {level_count['System']} cases - the tester fills "
     f"forms and clicks buttons; the output is the message or value shown on screen.\n"
     f"Unit testing of the Trust Score formula: {level_count['Unit']} cases.\n"
     f"Combination testing: {sum(c['combinations'] for c in combos):,} automatically generated combinations of "
     f"valid and invalid field values in {len(combos)} forms (Section 8).\n"
     "Integration testing: 2 end-to-end scenarios (tests/test_integration.py)."],
    ["Design techniques", "Positive testing (valid input); equivalence partitioning - every invalid class of every "
     "field (empty, wrong format, non-numeric, nan / inf, out of range); boundary-value analysis on both sides of "
     "every limit (name 50 / 51, password 5 / 6, amount 1,00,000 / 1,00,000.01, date 90 / 91 days, score 39 / 40 "
     "and 69 / 70, tier limit 15,000 / 15,000.01, EMI 1 paisa short, 90 / 91 days overdue); combination testing "
     "(several invalid fields at once, decision tables); state-based testing (loan life cycle); security testing "
     "(role check, forged requests, SQL injection)."],
    ["Test runs", f"Run 1 - the first version of the code (git commit 0ce1911): {len(failed1)} test cases FAILED "
     f"and {len(defects)} defects were logged (Section 9).\nRun 2 - after fixing the defects, the same cases "
     "were executed again (regression testing); the results in Sections 3-8 are from Run 2."],
    ["Environment", "Windows 11, Python 3.11, Flask 3.1, SQLite 3; Chrome / Edge browser."],
    ["Tools", "pytest; Flask test client (drives the real web routes); tests/run_test_cases.py records each "
     "Actual Output automatically."],
    ["Test data", "Every case starts from a fresh, empty database; the data each case needs is listed in its "
     "Pre-condition column."],
    ["Entry criteria", "Code of all four modules complete; application starts without errors."],
    ["Exit criteria", "All documented test cases and combinations executed; every defect found fixed and "
     "re-tested; every Must-have requirement traced to at least one passing test case (Section 10)."],
], [1.8, 8.6], size=9.5, bold_first=True)

# ---------------------------------------------------------------- 2 summary
heading("2. Test Results Summary", 1)
rows, tp, tt, tf1 = [], 0, 0, 0
for key in ORDER:
    rs = [r for r in results if r["module"] == key]
    passed = sum(r["remark"] == "PASS" for r in rs)
    f1 = sum(run1[r["id"]]["remark"] == "FAIL" for r in rs)
    tp, tt, tf1 = tp + passed, tt + len(rs), tf1 + f1
    rows.append([modules[key]["name"], f"{rs[0]['id']} to {rs[-1]['id']}", str(len(rs)), str(len(rs) - f1), str(f1),
                 str(passed), str(len(rs) - passed), f"{passed / len(rs) * 100:.0f}%"])
rows.append(["**Total**", "", f"**{tt}**", f"**{tt - tf1}**", f"**{tf1}**", f"**{tp}**", f"**{tt - tp}**",
             f"**{tp / tt * 100:.0f}%**"])
table(["Module", "Test case IDs", "Cases", "Run 1 passed", "Run 1 failed", "Run 2 passed", "Run 2 failed",
       "Final pass rate"], rows, [2.9, 1.9, 0.7, 0.95, 0.95, 0.95, 0.95, 1.0], size=9.5)

TECHS = ["Positive", "Negative", "Negative (EP)", "BVA", "Combination", "Security"]
trow = []
for key in ORDER:
    rs = [r for r in results if r["module"] == key]
    trow.append([modules[key]["name"]] + [str(sum(r["technique"] == t for r in rs)) for t in TECHS] + [str(len(rs))])
trow.append(["**Total**"] + [f"**{sum(r['technique'] == t for r in results)}**" for t in TECHS] + [f"**{tt}**"])
para("**Test cases by design technique** (EP = equivalence partitioning, BVA = boundary-value analysis; a BVA case "
     "tests the values on both sides of a limit):", size=10, after=2)
table(["Module"] + TECHS + ["Total"], trow, [2.9, 0.95, 0.95, 1.1, 0.8, 1.05, 0.9, 0.7], size=9.5)
c_total = sum(c["combinations"] for c in combos)
c_ok = sum(c["matched"] for c in combos)
para(f"**Combination testing:** {c_ok:,} of {c_total:,} combinations gave the expected result in Run 2 "
     f"(Run 1: {sum(c['matched'] for c in combos1.values()):,} of {c_total:,}, with "
     f"{sum(c['crashes'] for c in combos1.values())} server crashes) - see Section 8.", size=10)
para(f"**Automated run (pytest):** {pytest_summary} - the {tt} documented cases above, the {len(combos)} combination "
     f"suites and 2 integration tests. Executed on {executed}.", size=10)
para("**How the Actual Output is obtained:** tests/run_test_cases.py performs each case's steps on the running "
     "application and copies the message shown on the page into the Actual Output column; the Remark is PASS only "
     "if it matches the Expected Output exactly. Nothing in the Actual Output column is typed by hand.", size=10)
para("**Repeating a case by hand in the demo:** the demo data (python seed_demo.py) already contains loans, so loan "
     "numbers such as #1 will differ; the messages are otherwise identical.", size=10)

def remark_text(r):
    """Final remark; a case that failed in Run 1 says so and names the defect it found."""
    if run1[r["id"]]["remark"] == "FAIL":
        return f"{r['remark']}\n(Run 1: FAIL, {r['defect']} fixed)"
    return r["remark"]


# ---------------------------------------------------------------- 3-7 module sections
for n, key in enumerate(ORDER, start=3):
    meta = modules[key]
    rs = [r for r in results if r["module"] == key]
    page_break()
    heading(f"{n}. {meta['name']}", 1)
    hdr = doc.add_table(rows=5, cols=4)
    hdr.style = "Table Grid"
    hdr.alignment = WD_TABLE_ALIGNMENT.CENTER
    fields = [
        ("Test Case #:", f"{rs[0]['id']} to {rs[-1]['id']}", "Test Case Name:", meta["name"]),
        ("System:", "VendorSetu", "Subsystem:", meta["subsystem"]),
        ("Designed by:", "Nancy Yadav & team", "Design Date:", executed),
        ("Executed by:", "Nancy Yadav & team", "Execution Date:", executed),
        ("Short Description:", meta["description"], "", ""),
    ]
    widths = [1.45, 3.75, 1.45, 3.75]
    for ri, values in enumerate(fields):
        for ci, v in enumerate(values):
            c = hdr.rows[ri].cells[ci]
            c.width = Inches(widths[ci])
            rich(c.paragraphs[0], v, size=9.5, bold=ci % 2 == 0)
            if ci % 2 == 0 and v:
                shade(c, "EEF3EF")
    last = hdr.rows[4].cells
    merged = last[1].merge(last[3])
    merged.paragraphs[0].text = ""
    rich(merged.paragraphs[0], meta["description"], size=9.5)
    for extra in merged.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    box("Pre-conditions", meta["pre"])
    t = table(["TC ID", "Test Scenario", "Type", "Pre-condition", "Test Steps", "Input (Test Data)",
               "Expected Output", "Actual Output", "Remark"],
              [[r["id"], r["scenario"], f"{r['level']}\n{r['technique']}", r["pre"],
                "\n".join(f"{i}. {s}" for i, s in enumerate(r["steps"], start=1)),
                r["input"], r["expected"], r["actual"], remark_text(r)] for r in rs],
              [0.72, 1.0, 0.68, 1.1, 1.7, 1.3, 1.6, 1.6, 0.62], size=7.5)
    for row in t.rows[1:]:
        remark = row.cells[8]
        shade(remark, "D9F0E1" if remark.text.startswith("PASS") else "F8D7D3")
        remark.paragraphs[0].runs[0].bold = True
    box("Post-conditions", meta["post"])

# ---------------------------------------------------------------- 8 combination testing
page_break()
heading("8. Combination Testing", 1)
para("Single test cases check one rule at a time. To check that the rules also work together, every form was "
     "tested with **every combination** of the values below (cartesian product): valid values, every invalid class "
     "and the boundary values of each field. For each combination an independent oracle written from the SRS rules "
     "(tests/combinations.py) gives the message that must appear. A combination passes only if the message is "
     "exactly that, the app does not crash, and a rejected input leaves the database unchanged.", size=10)
table(["Form", "Values tried for each field", "Combinations", "Run 1 (first version)", "Run 2 (after fixes)",
       "Result"],
      [[c["form"], "\n".join(f"**{k}:** {', '.join(v)}" for k, v in c["values"].items()), f"{c['combinations']:,}",
        f"{combos1[c['form']]['matched']:,} matched, "
        f"{combos1[c['form']]['combinations'] - combos1[c['form']]['matched']:,} wrong, "
        f"{combos1[c['form']]['crashes']} crashed",
        f"{c['matched']:,} matched, {c['combinations'] - c['matched']:,} wrong, {c['crashes']} crashed",
        "PASS" if c["matched"] == c["combinations"] else "FAIL"] for c in combos]
      + [["**Total**", "", f"**{c_total:,}**",
          f"**{sum(c['matched'] for c in combos1.values()):,} matched**", f"**{c_ok:,} matched**", ""]],
      [1.2, 4.6, 0.9, 1.45, 1.45, 0.7], size=8)
para("**Rule order when several fields are wrong:** the first broken rule in form order is reported - "
     "Register: passwords match, name, mobile, password, role; Daily sales: date, amount, date range, payment mode, "
     "profile, duplicate date; Loan: amount format, active loan, Trust Score, amount range. TC-AUTH-15, TC-SALE-17 and "
     "TC-LOAN-13 are documented examples.", size=9.5)
para("**Role x page access:** each of the 6 roles sends each of the 10 requests. Expected: a guest is sent to Log in; "
     "officer pages only for the bank officer; a loan page only for its vendor and bank officers (another vendor sees "
     "'own loans only'); vendor forms only for vendors.", size=9.5)

# ---------------------------------------------------------------- 9 defect report
page_break()
heading("9. Defect Report (Run 1) and Re-test (Run 2)", 1)
para(f"Run 1 executed the same test cases on the first version of the code (git commit 0ce1911). {len(failed1)} "
     "cases FAILED; their real Actual Output is shown below. Each failure was logged as a defect and fixed, and the "
     "whole suite was executed again (regression testing).", size=10)
t = table(["TC ID", "Test Scenario", "Input", "Expected Output", "Actual Output (Run 1)", "Remark",
           "Actual Output (Run 2, after fix)", "Remark"],
          [[r["id"], r["scenario"], r["input"], r["expected"], r["actual"], f"FAIL\n{r['defect']}",
            next(x for x in results if x["id"] == r["id"])["actual"],
            next(x for x in results if x["id"] == r["id"])["remark"]] for r in failed1],
          [0.72, 1.1, 1.3, 1.6, 1.85, 0.55, 1.6, 0.55], size=7.5)
for row in t.rows[1:]:
    for ci, color in ((5, "F8D7D3"), (7, "D9F0E1" if row.cells[7].text == "PASS" else "F8D7D3")):
        shade(row.cells[ci], color)
        row.cells[ci].paragraphs[0].runs[0].bold = True
heading("Defect log", 2)
table(["Defect ID", "Severity", "Found by", "What happened (Run 1)", "Cause", "Fix", "Re-test (Run 2)"],
      [[d["id"], d["severity"], ", ".join(d["cases"]), d["found"], d["cause"], d["fix"],
        "PASS - closed" if all(next(x for x in results if x["id"] == c)["remark"] == "PASS" for c in d["cases"])
        else "FAIL - open"] for d in defects],
      [0.7, 0.65, 0.95, 2.4, 2.2, 2.4, 0.95], size=8, bold_first=True)

# ---------------------------------------------------------------- 10 traceability
page_break()
heading("10. Requirements Traceability Matrix", 1)
para("Each requirement from the SRS that the implemented modules cover, and the test cases that verify it.", size=10)
trace = defaultdict(list)
for r in results:
    for req in r["reqs"]:
        trace[req].append(r["id"])


def req_key(req):
    prefix, _, num = req.rpartition("-")
    order = ["FR-AUTH", "FR-VEN", "FR-TS", "FR-LN", "FR-BNK", "FR-EMI", "BR", "NFR-SEC"]
    return (order.index(prefix) if prefix in order else 99, int(num))


table(["Requirement", "Verified by test case(s)", "Status"],
      [[req, ", ".join(ids), "Covered - PASS" if all(
          next(x for x in results if x["id"] == i)["remark"] == "PASS" for i in ids) else "FAIL"]
       for req, ids in sorted(trace.items(), key=lambda kv: req_key(kv[0]))],
      [1.6, 6.8, 1.6], size=9.5, bold_first=True)

# ---------------------------------------------------------------- 9 re-execution
heading("11. How to Re-execute the Tests", 1)
for line in ["cd SE_Project",
             "python tests/run_test_cases.py                 (Run 2: every case + combination testing, PASS/FAIL)",
             "python tests/run_test_cases.py --module LOAN   (one module only: AUTH, SALE, TS, LOAN or EMI)",
             "python tests/run_test_cases.py --details       (also prints Input / Expected / Actual of each case)",
             "python tests/run_test_cases.py --before-fix    (Run 1: same cases on the first version - shows FAILs)",
             "python -m pytest tests -v                      (same cases, combination suites, integration tests)",
             "python docs/build_test_cases.py                (regenerates this document from the latest runs)"]:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(line)
    r.font.name = "Consolas"
    r.font.size = Pt(9.5)

doc.save(OUT)
print("Saved", OUT)
print("pytest:", pytest_summary)
