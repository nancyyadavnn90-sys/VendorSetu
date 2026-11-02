"""pytest entry point:  python -m pytest tests -v"""
import pytest

from test_cases import CASES


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_case(case):
    assert case.run() == case.expected
