# VendorSetu – Street Vendor Formalization & Micro-Credit Platform

CSE3005 Software Engineering project (BML Munjal University, 2026-27).

| Deliverable | Location |
|---|---|
| Complete SRS (IEEE template) – Word | `docs/SRS_VendorSetu.docx` |
| Test Case Document (template Doc T_01) | `docs/Test_Cases_VendorSetu.docx` + `.pdf` |
| Same SRS – PDF | `docs/SRS_VendorSetu.pdf` |
| UML & DFD diagrams (PNG) | `diagrams/` |
| Coded modules (Flask web app) | `app/` |
| Test cases + automated tests | `tests/` |
| Viva preparation notes | `VIVA_GUIDE.md` |

## Run the app

```bash
pip install -r requirements.txt
cd app
python seed_demo.py      # resets the database with demo data
python app.py            # open http://127.0.0.1:5000
```

Demo logins (mobile / password):

| Role | Mobile | Password |
|---|---|---|
| Vendor (Trust Score 71, can apply) | 9876543210 | ramesh123 |
| Vendor (has a pending loan) | 9812345670 | sunita123 |
| Vendor (has a disbursed loan) | 9811122233 | salim123 |
| Bank officer | 9123456780 | bank123 |
| Customer | 9988776655 | priya123 |
| Municipal officer | 9090909090 | muni123 |

## Run the tests

```bash
python tests/run_test_cases.py                # 92 documented cases + 1,894 combinations, writes tests/test_results.json
python tests/run_test_cases.py --module LOAN  # one module (AUTH, SALE, TS, LOAN, EMI); add --details for input/expected/actual
python tests/run_test_cases.py --before-fix   # same cases on the first version (commit 0ce1911): shows the 9 FAILs
python -m pytest tests -v                     # 101 tests: 92 cases + 7 combination suites + 2 integration tests
```

## Rebuild the diagrams and the SRS

```bash
python diagrams/generate_diagrams.py
python tests/run_test_cases.py --before-fix
python tests/run_test_cases.py
python docs/build_srs.py
python docs/build_test_cases.py
```

After rebuilding, open the .docx in Word and press **Ctrl+A, F9** to refresh the Table of Contents
(or run the commands in `docs/finalize_with_word.ps1`, which also exports the PDF).

## Coded modules

| # | Module | File |
|---|---|---|
| 1 | Registration & Login (password hashing, 5-attempt lock, role-based access) | `app/modules/auth.py` |
| 2 | Vendor Profile & Daily Sales Logging | `app/modules/vendor.py` |
| 3 | Alternative Credit (Trust) Scoring Engine | `app/modules/credit_score.py` |
| 4 | Loan Management: application, bank review, disbursal, EMI schedule, repayment | `app/modules/loan.py` |
