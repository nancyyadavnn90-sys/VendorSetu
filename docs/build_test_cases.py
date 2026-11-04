"""
build_test_cases.py - Generates the Test Case Document in the course format (Test Case Template, Doc T_01).

    python tests/run_test_cases.py --before-fix   # Run 1: the first version of the code (commit 0ce1911)
    python tests/run_test_cases.py                # Run 2: the current code
    python docs/build_test_cases.py               # writes docs/Test_Cases_VendorSetu.docx

Every test case is laid out like the template: a header box, Pre-conditions, the Step table and
Post-conditions - one test case per page.
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
BLUE = RGBColor(0x1F, 0x3B, 0x8F)          # the template writes the filled-in values in blue
TEAM = "Nancy Yadav, Vishesh Gupta, Vishal Verma, Purva Joshi, Harshul Saini"
FACULTY = "Dr. Harsh Taneja"
ORDER = ["AUTH", "SALE", "TS", "LOAN", "EMI"]
WIDTH = 10.45

with open(os.path.join(ROOT, "tests", "test_results.json"), encoding="utf-8") as f:
    data = json.load(f)
results, modules, defects = data["results"], data["modules"], data["defects"]
combos = data.get("combinations", [])
executed = "-".join(reversed(data["executed_on"].split("-")))
BEFORE = os.path.join(ROOT, "tests", "test_results_before_fix.json")
if not os.path.exists(BEFORE):
    sys.exit("First run:  python tests/run_test_cases.py --before-fix")
with open(BEFORE, encoding="utf-8") as f:
    before = json.load(f)
run1 = {r["id"]: r for r in before["results"]}
combos1 = {c["form"]: c for c in before.get("combinations", [])}
failed1 = [r for r in before["results"] if r["result"] == "FAIL"]
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


def rich(p, text, size=None, bold=False, italic=False, color=None):
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
            if color:
                run.font.color.rgb = color
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


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def repeat_header(row):
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(el)


def tight(p, after=0):
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(0)
    return p


def table(headers, rows, widths, size=9, header_bg="DDDDDD", bold_first=False):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    repeat_header(t.rows[0])
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.width = Inches(widths[i])
        tight(rich(c.paragraphs[0], h, size=size, bold=True))
        shade(c, header_bg)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].width = Inches(widths[i])
            lines = str(v).split("\n")
            tight(rich(cells[i].paragraphs[0], lines[0], size=size, bold=bold_first and i == 0))
            for ln in lines[1:]:
                tight(rich(cells[i].add_paragraph(), ln, size=size))
    for row in t.rows:
        no_split(row)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def box(title, lines, numbered=False):
    """Single-cell bordered box, like the template's Pre-conditions / Post-conditions boxes."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    c.width = Inches(WIDTH)
    no_split(t.rows[0])
    tight(rich(c.paragraphs[0], title, size=10, bold=True))
    for i, ln in enumerate(lines, start=1):
        tight(rich(c.add_paragraph(), f"{i}. {ln}" if numbered else ln, size=9.5))
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(0)
    gap.paragraph_format.line_spacing = Pt(8)


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


def mark(cell, ok):
    shade(cell, "D9F0E1" if ok else "F8D7D3")
    for r in cell.paragraphs[0].runs:
        r.bold = True


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
rich(sec.header.paragraphs[0], "Test Case Document - VendorSetu   |   CSE3005 Software Engineering   |   Template "
     "Doc T_01", size=8.5, italic=True).alignment = WD_ALIGN_PARAGRAPH.RIGHT
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
rich(fp, "Page ", size=9)
add_page_field(fp)

n_cases = len(results)
n_steps = sum(len(r["steps"]) for r in results)
steps_ok = sum(s["result"] == "PASS" for r in results for s in r["steps"])
cases_ok = sum(r["result"] == "PASS" for r in results)
per_module = defaultdict(list)
for r in results:
    per_module[r["module"]].append(r)

# ---------------------------------------------------------------- cover
for _ in range(4):
    doc.add_paragraph()
para("Test Case Document", size=30, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
p = para("VendorSetu", size=24, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
p.runs[0].font.color.rgb = GREEN
para("Street Vendor Formalization & Micro-Credit Platform", size=14, align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
para(f"{n_cases} test cases ({len(ORDER)} modules x 6) in the format of the Test Case Template (Doc T_01)", size=11,
     align=WD_ALIGN_PARAGRAPH.CENTER, after=24)
para(f"Prepared by: {TEAM}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
para("B.Tech CSE, Batch 2024 - CSE3005 Software Engineering - BML Munjal University", size=12,
     align=WD_ALIGN_PARAGRAPH.CENTER)
para(f"Submitted to: {FACULTY}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
para(f"Test execution date: {executed}", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
page_break()

# ---------------------------------------------------------------- 1 test plan and summary
heading("1. Test Plan and Results Summary", 1)
table(["Item", "Details"], [
    ["Objective", "Verify that the four implemented modules of VendorSetu meet their functional requirements (SRS "
     "4.1-4.6) and reject invalid input with the correct message."],
    ["Test cases", f"6 test cases for each of the {len(ORDER)} tested modules ({n_cases} in total, {n_steps} steps), "
     "written in the format of the course Test Case Template (Doc T_01): header, pre-conditions, steps with the "
     "expected system response, Pass/Fail, comment, and post-conditions. Like the template's Example 2, each test "
     "case tests the happy path and also its failure conditions."],
    ["Design techniques (Comment column)", "Positive (valid input); Negative / equivalence partitioning (EP) - every "
     "invalid class; boundary-value analysis (BVA) - both sides of each limit; Combination - several wrong fields at "
     "once; Security - forged requests, role checks, SQL injection; 'Check post-condition' steps look inside the "
     "database."],
    ["Levels", "System testing through the web interface (24 test cases): the Actual Output is the message or value "
     "shown on screen. Unit testing of the Trust Score formula (TC-TS-02 to TC-TS-06)."],
    ["Test runs", f"Run 1 - the first version of the code (git commit 0ce1911): {len(failed1)} test cases FAILED; "
     f"{len(defects)} defects were logged (Section 7).\nRun 2 - after fixing them, all test cases were executed "
     "again (regression testing). Sections 2-6 show Run 2."],
    ["Environment / tools", "Windows 11, Python 3.11, Flask 3.1, SQLite; pytest and the Flask test client. "
     "tests/run_test_cases.py performs every step on a fresh database and copies the on-screen result into the "
     "Actual Output column - nothing in that column is typed by hand."],
], [2.0, 8.4], size=9.5, bold_first=True)

rows, tf1 = [], 0
for n, key in enumerate(ORDER, start=2):
    rs = per_module[key]
    f1 = sum(run1[r["id"]]["result"] == "FAIL" for r in rs)
    tf1 += f1
    ok = sum(r["result"] == "PASS" for r in rs)
    st = sum(len(r["steps"]) for r in rs)
    st_ok = sum(s["result"] == "PASS" for r in rs for s in r["steps"])
    rows.append([f"{n}. {modules[key]['name']}", f"{rs[0]['id']} to {rs[-1]['id']}", str(len(rs)), str(st), str(f1),
                 f"{ok} / {len(rs)}", f"{st_ok} / {st}"])
rows.append(["**Total**", "", f"**{n_cases}**", f"**{n_steps}**", f"**{tf1}**", f"**{cases_ok} / {n_cases}**",
             f"**{steps_ok} / {n_steps}**"])
table(["Module (section)", "Test cases", "Cases", "Steps", "Run 1: cases failed", "Run 2: cases passed",
       "Run 2: steps passed"], rows, [3.0, 2.0, 0.7, 0.7, 1.3, 1.35, 1.35], size=9.5)
para(f"**Automated run (pytest):** {pytest_summary} - the {n_cases} test cases, the combination suites and 2 "
     f"integration tests. Executed on {executed}.", size=10)
para("**Repeating a step by hand in the demo:** the demo data (python seed_demo.py) already contains loans, so loan "
     "numbers such as #1 will differ; the messages are otherwise identical.", size=10)


# ---------------------------------------------------------------- 2-6 test cases (template layout)
def header_box(r):
    meta = modules[r["module"]]
    hdr = doc.add_table(rows=5, cols=6)
    hdr.style = "Table Grid"
    hdr.alignment = WD_TABLE_ALIGNMENT.CENTER
    fields = [
        ("Test Case #:", r["id"], "Test Case Name:", r["name"], "Page:", "1 of 1"),
        ("System:", "VendorSetu", "Subsystem:", meta["subsystem"], "Type:", r["level"] + " test"),
        ("Designed by:", "Nancy Yadav & team", "Design Date:", executed, "Requirements:", ", ".join(r["reqs"])),
        ("Executed by:", "Nancy Yadav & team", "Execution Date:", executed, "Result:", r["result"]),
        ("Short Description:", r["description"], "", "", "", ""),
    ]
    widths = [1.25, 2.1, 1.25, 3.25, 1.05, 1.55]
    for ri, values in enumerate(fields):
        for ci, v in enumerate(values):
            c = hdr.rows[ri].cells[ci]
            c.width = Inches(widths[ci])
            tight(rich(c.paragraphs[0], v, size=9.5, bold=ci % 2 == 0, color=None if ci % 2 == 0 else BLUE))
        no_split(hdr.rows[ri])
    mark(hdr.rows[3].cells[5], r["result"] == "PASS")
    last = hdr.rows[4].cells
    merged = last[1].merge(last[5])
    for extra in merged.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    merged.paragraphs[0].text = ""
    tight(rich(merged.paragraphs[0], r["description"], size=9.5, color=BLUE))
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(0)
    gap.paragraph_format.line_spacing = Pt(8)


def comment(r, s):
    first = run1[r["id"]]["steps"][s["no"] - 1]
    if first["result"] == "FAIL":
        return f"{s['note']}\nRun 1: FAIL ({s['defect'] or 'see Section 7'}, fixed)" if s["note"] else \
            f"Run 1: FAIL ({s['defect']}, fixed)"
    return s["note"]


for n, key in enumerate(ORDER, start=2):
    rs = per_module[key]
    page_break()
    heading(f"{n}. {modules[key]['name']}  ({rs[0]['id']} to {rs[-1]['id']})", 1)
    for i, r in enumerate(rs):
        if i:
            page_break()
        header_box(r)
        box("Pre-conditions", r["pre"])
        t = table(["Step", "Action", "Input (Test Data)", "Expected System Response", "Actual Output", "Pass/ Fail",
                   "Comment"],
                  [[str(s["no"]), f"**{s['action']}**" if s["action"].startswith("Check post-condition") else s["action"],
                    s["data"], s["expected"], s["actual"], s["result"].title(), comment(r, s)] for s in r["steps"]],
                  [0.42, 1.95, 1.7, 2.05, 2.05, 0.55, 1.73], size=8.5)
        for row in t.rows[1:]:
            mark(row.cells[5], row.cells[5].text == "Pass")
        box("Post-conditions", r["post"], numbered=True)

# ---------------------------------------------------------------- 7 defect report
page_break()
heading("7. Defect Report - Run 1 (first version) and Re-test - Run 2", 1)
para(f"Run 1 executed the same test cases on the first version of the code (git commit 0ce1911): {len(failed1)} test "
     "cases FAILED. The real Actual Output of every failed step is shown below. Each failure was logged as a defect, "
     "fixed, and the whole suite was executed again (regression testing).", size=10)
now = {r["id"]: r for r in results}
fail_rows = []
for r in failed1:
    for s in r["steps"]:
        if s["result"] == "FAIL":
            again = now[r["id"]]["steps"][s["no"] - 1]
            fail_rows.append([f"{r['id']}\nstep {s['no']}", s["data"], s["expected"], s["actual"],
                              f"Fail\n{s['defect']}" if s["defect"] else "Fail", again["actual"],
                              again["result"].title()])
t = table(["Test case / step", "Input (Test Data)", "Expected System Response", "Actual Output (Run 1)", "Pass/ Fail",
           "Actual Output (Run 2, after fix)", "Pass/ Fail"], fail_rows, [0.95, 1.6, 1.95, 2.35, 0.6, 1.95, 0.6],
          size=8)
for row in t.rows[1:]:
    mark(row.cells[4], False)
    mark(row.cells[6], row.cells[6].text == "Pass")
para("A 'Check post-condition' step fails in Run 1 when invalid input was stored in the database; it has no defect "
     "of its own - it is caused by the defect in the steps above it.", size=9, italic=True)
heading("Defect log", 2)
table(["Defect", "Severity", "Found by", "What happened (Run 1)", "Cause", "Fix", "Re-test (Run 2)"],
      [[d["id"], d["severity"], "\n".join(d["cases"]), d["found"], d["cause"], d["fix"],
        "Pass - closed" if all(now[c.split()[0]]["result"] == "PASS" for c in d["cases"]) else "Fail - open"]
       for d in defects], [0.65, 0.65, 1.15, 2.4, 2.1, 2.45, 0.85], size=8, bold_first=True)

# ---------------------------------------------------------------- 8 combination testing
if combos:
    page_break()
    heading("8. Combination Testing (supporting the test cases)", 1)
    para("In addition to the documented test cases, every form was submitted with every combination (cartesian "
         "product) of the valid, invalid and boundary values below. An oracle written from the SRS rules "
         "(tests/combinations.py) gives the message each combination must show; a combination passes only if the "
         "message matches, the app does not crash and rejected input leaves the database unchanged.", size=10)
    c_total = sum(c["combinations"] for c in combos)
    table(["Form", "Values tried for each field", "Combinations", "Run 1 (first version)", "Run 2 (after fixes)"],
          [[c["form"], "\n".join(f"**{k}:** {', '.join(v)}" for k, v in c["values"].items()), f"{c['combinations']:,}",
            f"{combos1[c['form']]['matched']:,} correct, {combos1[c['form']]['crashes']} crashed" if combos1 else "-",
            f"{c['matched']:,} correct, {c['crashes']} crashed"] for c in combos]
          + [["**Total**", "", f"**{c_total:,}**",
              f"**{sum(c['matched'] for c in combos1.values()):,} correct**" if combos1 else "",
              f"**{sum(c['matched'] for c in combos):,} correct**"]],
          [1.3, 5.2, 0.95, 1.5, 1.5], size=8)

# ---------------------------------------------------------------- 9 traceability
page_break()
heading("9. Requirements Traceability Matrix", 1)
para("Each SRS requirement covered by the implemented modules, and the test cases that verify it.", size=10)
trace = defaultdict(list)
for r in results:
    for req in r["reqs"]:
        trace[req].append(r["id"])


def req_key(req):
    prefix, _, num = req.rpartition("-")
    order = ["FR-AUTH", "FR-VEN", "FR-TS", "FR-LN", "FR-BNK", "FR-EMI", "BR", "NFR-SEC"]
    return (order.index(prefix) if prefix in order else 99, int(num))


table(["Requirement", "Verified by test case(s)", "Status"],
      [[req, ", ".join(ids), "Covered - Pass" if all(now[i]["result"] == "PASS" for i in ids) else "Fail"]
       for req, ids in sorted(trace.items(), key=lambda kv: req_key(kv[0]))],
      [1.6, 6.8, 1.6], size=9.5, bold_first=True)

heading("10. How to Re-execute the Tests", 1)
for line in ["cd C:\\Users\\nancy\\OneDrive\\Desktop\\SE_Project",
             "python tests/run_test_cases.py --module AUTH --details   (one module, every step's input / expected / "
             "actual)",
             "python tests/run_test_cases.py --before-fix              (Run 1: first version - shows the FAILED steps)",
             "python tests/run_test_cases.py                           (Run 2: all test cases + combination testing)",
             "python -m pytest tests -v                                (the same test cases under pytest)",
             "python docs/build_test_cases.py                          (regenerates this document)"]:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(line)
    r.font.name = "Consolas"
    r.font.size = Pt(9.5)

doc.save(OUT)
print("Saved", OUT)
print("pytest:", pytest_summary)
