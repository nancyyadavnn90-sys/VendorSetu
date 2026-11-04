"""pytest entry point:  python -m pytest tests -v   (one pytest test per documented test case)"""
import pytest

from test_cases import CASES


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_case(case):
    actuals = case.run()
    failed = [f"step {i}: expected {s.expected!r}, actual {act!r}"
              for i, (s, act) in enumerate(zip(case.steps, actuals), start=1) if act != s.expected]
    assert not failed, "\n".join(failed)
