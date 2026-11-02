"""
run_test_cases.py - Executes every documented test case and records the Actual Output.

    python tests/run_test_cases.py

Writes tests/test_results.json, which docs/build_srs.py reads to fill the
"Actual Output" and "Remark" columns of the test-case tables.
"""
import json
import os
from datetime import date

from test_cases import CASES, MODULES

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results.json")


def main():
    results = []
    for case in CASES:
        try:
            actual = case.run()
        except Exception as e:                       # an unexpected crash is a failure, not a test-runner error
            actual = f"ERROR: {type(e).__name__}: {e}"
        remark = "PASS" if actual == case.expected else "FAIL"
        results.append({"id": case.id, "module": case.module, "level": case.level, "scenario": case.scenario,
                        "pre": case.pre, "steps": case.steps, "input": case.input, "expected": case.expected,
                        "actual": actual, "remark": remark, "reqs": case.reqs})
        print(f"{case.id:<11} {remark}  {case.scenario}")
        if remark == "FAIL":
            print(f"            expected: {case.expected}\n            actual:   {actual}")

    passed = sum(r["remark"] == "PASS" for r in results)
    print(f"\n{passed}/{len(results)} test cases passed")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"executed_on": date.today().isoformat(), "modules": MODULES, "results": results}, f, indent=2)
    print("Results written to", OUT)


if __name__ == "__main__":
    main()
