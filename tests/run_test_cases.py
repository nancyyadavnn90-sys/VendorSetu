"""
run_test_cases.py - Executes every documented test case (and the combination suites) and records the Actual Output.

    python tests/run_test_cases.py                   all cases + combination testing, writes tests/test_results.json
    python tests/run_test_cases.py --module LOAN     only one module (AUTH, SALE, TS, LOAN, EMI); nothing is written
    python tests/run_test_cases.py --details         also print Input / Expected / Actual of every case
    python tests/run_test_cases.py --before-fix      run the SAME cases on the first version of the code
                                                     (git commit 0ce1911) to show the cases that FAILED before the
                                                     defects were fixed; writes tests/test_results_before_fix.json

docs/build_test_cases.py and docs/build_srs.py read the JSON files to fill the "Actual Output" and "Remark" columns.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
V1_COMMIT = "0ce1911"            # the version submitted before testing found the defects
OUT = os.path.join(HERE, "test_results.json")
OUT_BEFORE_FIX = os.path.join(HERE, "test_results_before_fix.json")


def run(module=None, details=False, combos=True, out=None, label="current code"):
    from test_cases import CASES, DEFECTS, MODULES        # imported here so --before-fix can switch the app first
    import combinations

    cases = [c for c in CASES if module is None or c.module == module]
    print(f"Running {len(cases)} test cases on the {label}\n")
    results, current = [], None
    for case in cases:
        if case.module != current:
            current = case.module
            print(f"--- {MODULES[current]['name']} ---")
        try:
            actual = case.run()
        except Exception as e:                        # an unexpected crash is a failure, not a test-runner error
            actual = f"ERROR: {type(e).__name__}: {e}"
        remark = "PASS" if actual == case.expected else "FAIL"
        results.append({"id": case.id, "module": case.module, "level": case.level, "technique": case.technique,
                        "defect": case.defect, "scenario": case.scenario, "pre": case.pre, "steps": case.steps,
                        "input": case.input, "expected": case.expected, "actual": actual, "remark": remark,
                        "reqs": case.reqs})
        print(f"{case.id:<11} {remark}  [{case.technique}] {case.scenario}")
        if details or remark == "FAIL":
            print(f"            input:    {case.input}\n            expected: {case.expected}\n"
                  f"            actual:   {actual}")

    passed = sum(r["remark"] == "PASS" for r in results)
    print(f"\n{passed}/{len(results)} test cases passed, {len(results) - passed} failed")

    combo_results = []
    if combos:
        print("\nCombination testing (every combination of valid and invalid values in each form):")
        combo_results = combinations.run_all()
        total = sum(r["combinations"] for r in combo_results)
        ok = sum(r["matched"] for r in combo_results)
        crashes = sum(r["crashes"] for r in combo_results)
        print(f"\n{ok}/{total} combinations gave the expected result, {total - ok} did not ({crashes} crashed)")

    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"executed_on": date.today().isoformat(), "code_version": label, "modules": MODULES,
                       "defects": DEFECTS, "results": results, "combinations": combo_results}, f, indent=2)
        print("Results written to", out)
    return passed == len(results)


def before_fix(args):
    """Extract app/ from the first commit into a temporary folder and run this script against it."""
    try:
        tar = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", V1_COMMIT, "app"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"Could not read commit {V1_COMMIT} with git: {e}")
    tmp = tempfile.mkdtemp(prefix="vendorsetu_v1_")
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(tmp)
    env = dict(os.environ, VENDORSETU_APP_DIR=os.path.join(tmp, "app"))
    cmd = [sys.executable, os.path.abspath(__file__), "--internal-before-fix"]
    cmd += ["--module", args.module] if args.module else []
    cmd += ["--details"] if args.details else []
    cmd += ["--no-combinations"] if args.no_combinations else []
    subprocess.run(cmd, env=env, cwd=HERE)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--module", choices=["AUTH", "SALE", "TS", "LOAN", "EMI"], help="run one module only")
    p.add_argument("--details", action="store_true", help="print input / expected / actual for every case")
    p.add_argument("--no-combinations", action="store_true", help="skip the combination suites (faster)")
    p.add_argument("--before-fix", action="store_true", help=f"run on the first version (commit {V1_COMMIT})")
    p.add_argument("--internal-before-fix", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.before_fix:
        return before_fix(args)
    full = args.module is None and not args.no_combinations
    if args.internal_before_fix:
        run(args.module, args.details, not args.no_combinations, OUT_BEFORE_FIX if full else None,
            label=f"FIRST VERSION of the code (commit {V1_COMMIT}, before the defects were fixed)")
    else:
        run(args.module, args.details, not args.no_combinations, OUT if full else None)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
