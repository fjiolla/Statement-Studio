"""Generalisation: random bank layouts (header wording incl. Hindi, column order,
debit/credit encodings, date & number formats, rules, wrapping, order, page breaks)
must extract exactly. See scripts/layout_fuzz.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from layout_fuzz import check  # noqa: E402


@pytest.mark.parametrize("seed", range(100))
def test_random_text_layout(seed):
    ok, msg, lay = check(seed)
    assert ok, f"{msg} | scheme={lay.scheme} date={lay.date_fmt} labels={lay.labels}"


@pytest.mark.slow
def test_random_scanned_layouts():
    results = [check(seed, scan=True)[0] for seed in range(900, 910)]
    assert sum(results) >= 8, f"only {sum(results)}/10 scanned layouts exact"
