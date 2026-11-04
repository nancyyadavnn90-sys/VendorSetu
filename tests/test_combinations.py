"""pytest entry point for combination testing:  python -m pytest tests -v"""
import pytest

import combinations


@pytest.mark.parametrize("suite", combinations.SUITES, ids=[s.__name__ for s in combinations.SUITES])
def test_every_combination(suite):
    r = suite()
    assert r["crashes"] == 0, f"{r['crashes']} combinations crashed the app: {r['mismatches']}"
    assert r["matched"] == r["combinations"], f"{r['combinations'] - r['matched']} wrong results: {r['mismatches']}"
