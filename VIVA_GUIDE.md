# Viva Guide – VendorSetu (aasaan bhasha mein)

## 1. Project kya hai? (30-second pitch)

> "Sir, India mein street vendors (sabzi wale, chai wale, chaat wale) ke paas koi credit history nahi hoti,
> isliye bank unhe loan nahi dete aur woh moneylender se mehenge byaaj par paisa lete hain. Government ki
> **PM SVANidhi** scheme isi problem ke liye hai, lekin process abhi bhi kaafi manual hai.
> **VendorSetu** ek web platform hai jahan vendor roz apni sales log karta hai, us data se system ek
> **Trust Score (0–100)** banata hai — CIBIL score ki jagah — aur us score ke basis par bank officer
> chhote loan deta hai: pehle ₹15,000, woh chuka do to ₹25,000, phir ₹50,000 (progressive lending)."

**Real-world grounding:** Aug 2025 mein Cabinet ne PM SVANidhi restructure ki — tiers ab ₹15,000 (12 months)
→ ₹25,000 (18 months) → ₹50,000 (36 months), scheme March 2030 tak extend, 1.15 crore beneficiaries ka target.
Pehle (2020) tiers ₹10k/₹20k/₹50k the. Agar sir poochein "10k/20k/50k kyun nahi?" → "restructured scheme ke
latest amounts use kiye hain; code mein `TIERS` constant change karke dono support ho jaate hain."

## 2. Actors (users) kaun hain?

| Actor | Kya karta hai |
|---|---|
| Street Vendor | Profile banata hai, roz sales log karta hai, Trust Score dekhta hai, loan apply karta hai, EMI bharta hai |
| Bank / NBFC Officer | Loan applications dekhta hai (score ke saath), approve/reject karta hai, disburse karta hai, defaults track karta hai |
| Municipal Officer | Vending licence approve/renew karta hai, dispute/eviction case log karta hai |
| Customer | Paas ke vendors dhundhta hai, digitally pay karta hai, hygiene rating deta hai |
| Peer Guarantor | Doosre vendor ke liye "vouch" karta hai (guarantee) — isse uska Trust Score badhta hai |

## 3. Trust Score kaise banta hai? (sabse important — sir zaroor poochenge)

| Component | Max points | Formula |
|---|---|---|
| Sales consistency | 40 | (pichhle 30 din mein kitne din sale log kiya / 30) × 40 |
| Repayment history | 40 | (time par bhari EMIs / due EMIs) × 40 — naye vendor ko neutral 20 |
| Peer vouching | 10 | min(vouches, 3) / 3 × 10 |
| Vending tenure | 10 | min(saal, 5) / 5 × 10 |

- 70+ = LOW RISK, 40–69 = MEDIUM RISK, 40 se kam = HIGH RISK (loan nahi milega)
- **Example:** 30/30 din sales, koi loan nahi, 3 vouches, 5 saal → 40 + 20 + 10 + 10 = **80**
- Score **explainable** hai — vendor ko har component ke points dikhte hain.
- **Human-in-the-loop:** score sirf input hai; final decision bank officer ka hai (AI-assisted SE topic se link).

## 4. Loan ka life cycle (State diagram yahi dikhata hai)

`PENDING → APPROVED → DISBURSED → CLOSED`
- PENDING se REJECTED (officer, remarks zaroori) ya WITHDRAWN (vendor khud)
- DISBURSED se DEFAULTED agar koi EMI 90 din se zyada overdue
- Last EMI bharte hi CLOSED → agla tier unlock

EMI formula (reducing balance): **EMI = P·r·(1+r)ⁿ / ((1+r)ⁿ − 1)**, r = 12%/12 = 1% per month.
₹15,000, 12 months → **₹1,332.73** per month (test case TC-EMI-01 isko verify karta hai).

## 5. Diagrams — matlab, use, kaise padhein

### Use Case Diagram (Figure 1)
- **Kya dikhata hai:** system *kya* karta hai, *kaun* use karta hai — "what", "how" nahi.
- **Elements:** stick figure = actor; oval = use case (goal); rectangle = system boundary; line = actor us use case mein participate karta hai.
- **«include»:** base use case *hamesha* doosre ko call karta hai — "Apply for Loan" include karta hai "Calculate Trust Score".
- **«extend»:** optional behaviour — "Rate Hygiene" extend karta hai "Pay Vendor" (pay ke baad rating optional).
- **Generalization (khokhla triangle):** Peer Guarantor ek special type ka Vendor hai.
- **Kaise banaya:** 1) actors list kiye, 2) har actor ke goals = use cases, 3) common steps ko include mein nikala, 4) optional steps extend mein.

### Class Diagram (Figure 2)
- **Kya dikhata hai:** system ka static structure — classes, unke attributes/methods aur relationships.
- **Box ke 3 hisse:** naam | attributes (`-` private) | methods (`+` public).
- **Inheritance (khokhla triangle):** Customer, Vendor, BankOfficer, MunicipalOfficer — sab `User` (abstract) se inherit karte hain (login, phone, password common hai).
- **Association + multiplicity:** Vendor `1` —— `0..*` Loan = ek vendor ke zero ya zyada loans.
- **Composition (bhara diamond):** Loan ◆—— EMIInstallment — loan delete to EMIs bhi khatam (EMI loan ke bina exist nahi karti).
- **Dependency (dashed arrow):** TrustScoreEngine, SaleRecord aur EMIInstallment ko *read* karta hai.

### Sequence Diagrams (Figure 3 & 4)
- **Kya dikhata hai:** ek scenario mein objects ke beech messages *time order* mein.
- Upar participants, neeche dashed lifeline (time neeche jaata hai), patle rectangle = activation (object kaam kar raha hai).
- Solid arrow = call, dashed arrow = return.
- **alt frame** = if/else — Login mein: sahi password → dashboard; galat → error + failed attempt count (5 par lock).
- Loan wale diagram mein: vendor apply → LoanService → TrustScoreEngine → Database → score ≥ 40 to PENDING save; phir bank officer approve → disburse → EMI schedule generate.

### State Transition Diagram (Figure 5)
- **Kya dikhata hai:** ek object (yahan **Loan**) ki life ke states aur kis event se state badalti hai.
- Kaala dot = start, double circle = end, rounded box = state, arrow par `event [guard] / action`.
- Example: `payEMI() [last EMI paid] / unlock next tier` → DISBURSED se CLOSED.

### Data Flow Diagrams (Figure 6, 7, 8)
- **Kya dikhata hai:** data kahan se aata hai, kahan process hota hai, kahan store hota hai (control flow nahi).
- Notation: rectangle = external entity, circle = process, open box = data store (D1, D2…), arrow = data flow (naam ke saath).
- **Level 0 (Context):** poora system ek circle; sirf bahar ke entities ke saath data exchange.
- **Level 1:** system ko 7 processes mein toda (1.0 Accounts … 7.0 Customer services) + data stores.
- **Level 2:** process 3.0 (Trust Score) ko 3.1–3.5 mein toda — exactly code ke `compute_trust_score()` jaisa.
- **Rule (balancing):** child level ke inputs/outputs parent ke inputs/outputs se match hone chahiye. Humare DFD balanced hain: Level 0 mein vendor ko "trust score" milta hai → Level 1 mein woh 3.0 → 4.0 → Vendor flow hai; Level 1 mein 4.0 se 3.0 ko "score request" jaata hai → Level 2 mein wahi 3.1 ka input hai.
- `*` wale entity/store duplicate hain — sirf lines cross na hon isliye do baar draw kiye.

## 6. Coded modules (kya code kiya)

| Module | File | Kya karta hai |
|---|---|---|
| 1. Registration & Login | `app/modules/auth.py` | phone validation, password hashing, 5 galat attempts par lock, role-based pages |
| 2. Profile & Daily Sales | `app/modules/vendor.py` | profile save, roz ki sale (1 per day, future date nahi, ₹0 nahi), 30-din summary |
| 3. Trust Score Engine | `app/modules/credit_score.py` | upar wala formula, risk band, eligibility |
| 4. Loan Management | `app/modules/loan.py` | apply (tier limit, ek active loan), approve/reject, disburse + EMI schedule, EMI pay, default check |

**Architecture point:** business logic (`modules/`) web layer (`app.py`) se alag hai → har module ko bina server chalaye unit-test kar sakte hain (low coupling, high cohesion).

## 7. Testing (kya bolna hai)

- **92 documented test cases**, 5 modules (Login 20, Profile & Sales 19, Trust Score 14, Loan 21, EMI 18) - sab **PASS**.
- Har case mein: TC ID, Scenario, Type (level + technique), Pre-condition, Test Steps, Input, Expected Output, Actual Output, Remark.
- Alag document: `docs/Test_Cases_VendorSetu.docx` / `.pdf` (template Doc T_01 format) + SRS Appendix E.
- Techniques: **Positive**, **Negative (equivalence partitioning)** - har invalid class (empty, galat format, abc, nan/inf, range ke bahar), **BVA** - har limit ke dono taraf (name 50/51, password 5/6, amount 1,00,000/1,00,000.01, date 90/91 din purani, score 39/40 aur 69/70, loan 15,000/15,000.01, EMI 1 paisa kam, 90/91 din overdue), **Combination** (ek saath kai galat fields), **Security** (role check, forged request, SQL injection).
- **Combination testing:** 7 forms ke har field ki valid + invalid values ka har combination (cartesian product) = **1,894 combinations** automatically chalaye. Har combination ka expected result ek alag "oracle" (SRS rules se likha) batata hai. Sab match + 0 crash.
- **Test cases FAIL bhi hue the (Run 1):** wahi tests pehle version (git commit 0ce1911) par chalaye to **9 cases FAIL** hue aur 327 combinations galat aaye (9 baar server crash). 6 defects log kiye (DEF-01 ... DEF-06), fix kiye, phir dobara chalaye (regression) -> sab PASS. Test doc Section 9 mein asli Run-1 output hai.
  - DEF-01: amount mein `nan` -> server crash (HTTP 500). DEF-02: 1900 ki date wali sale accept. DEF-03: EMI `nan`/`inf` se PAID. DEF-04: name "12345" accept. DEF-05: customer kisi vendor ka loan page dekh sakta tha. DEF-06: error message do baar.
- **Actual Output haath se nahi likha** - `tests/run_test_cases.py` app chalake screen ka message copy karta hai.
- **Post-conditions bhi check hote hain** - galat input par database mein kuch nahi badalta; password plain text mein save nahi hota.
- **Traceability matrix** (test doc Section 10): har requirement kis test case se verify hui.
- Total `pytest`: **101 passed** (92 cases + 7 combination suites + 2 integration).

### Sir ke saamne tests chalane ke commands
```
python tests/run_test_cases.py --module AUTH --details   (ek module, input/expected/actual ke saath)
python tests/run_test_cases.py --before-fix --no-combinations   (purana code: 9 FAIL dikhenge)
python tests/run_test_cases.py                            (naya code: 92/92 PASS + 1894 combinations, ~1 min)
python -m pytest tests -v                                 (101 passed, ~2 min)
```
- Live fail dikhana ho to: `app/modules/auth.py` mein `MAX_FAILED_ATTEMPTS = 5` ko 3 karo, save karo, `python tests/run_test_cases.py --module AUTH` -> TC-AUTH-07 aur TC-AUTH-19 FAIL. Wapas 5 karo -> PASS.
- Sir demo data par case repeat karein to loan number (#1) alag aayega kyunki demo mein pehle se loans hain - baaki message same.

## 8. Demo ka order (5 minute)

1. `start_demo.bat` par double-click (ya `cd app`, `python seed_demo.py`, `python app.py`) → browser mein `http://127.0.0.1:5000`
2. Login page par "Demo accounts" mein **Vendor · Ramesh** dabao (form khud bhar jaata hai) → Trust Score 71 LOW RISK, ring aur 4 component bars dikhao → 14 din ka sales chart dikhao → ₹15,000 loan apply karo. (Aaj ki sale seed data mein pehle se hai, isliye "Log sale" dabane par "Sales already logged for this date" aayega — yeh bhi ek validation dikhane ka achha example hai.)
3. Logout → login **Bank officer** (9123456780 / bank123) → Ramesh ka loan Approve → Disburse (12 EMIs of ₹1,332.73).
4. Sunita ka pending loan bina remarks Reject karke dikhao → error "Remarks are required when rejecting".
5. Wapas Ramesh → loan View → EMI #1 Pay → "paid on time".
6. Ek galat case: 20,000 apply karo → "Amount exceeds Tier 1 limit".
7. Terminal mein `python -m pytest tests -v` → 101 passed.

## 9. Possible viva questions

- **Functional vs non-functional?** Functional = system kya kare (FR-LN-4: amount ≤ tier limit). Non-functional = kitna achha kare (NFR-PERF-1: 2 second response, NFR-SEC-1: password hashed).
- **MoSCoW kya hai?** Must / Should / Could / Won't — humare 6 Must features code ho gaye; licensing Should; disputes, peer circles Could; Aadhaar e-KYC Won't (is release mein).
- **SDLC model kaunsa?** Incremental — Increment 1 mein saare Must-have features.
- **Cohesion/coupling?** Har module ek hi kaam karta hai (high cohesion); modules sirf function calls se jude hain, UI se independent (low coupling).
- **Verification vs validation?** Verification = "product sahi bana rahe hain?" (tests requirements se match). Validation = "sahi product bana rahe hain?" (vendor ki actual problem solve hoti hai?).
- **Security?** Password hash (plain text nahi), parameterised SQL (SQL injection se bachav), Jinja auto-escape (XSS), account lock, role check har request par.
- **Trust Score galat ho sakta hai?** Haan — vendor sales badha ke log kar sakta hai. Mitigation: aage UPI receipts se cross-check (assumption A-4), aur final decision human officer ka.

## 10. Kal se pehle yeh zaroor karo

- SRS cover page par yellow highlighted `<Member 2>`, `<Member 3>`, `<Member 4>` aur `<Faculty name>` bharo (Word mein open karke).
- Laptop par ek baar demo chala ke dekh lo.
