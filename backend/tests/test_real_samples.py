"""Regression tests on the real-world sample statements (skipped if not present)."""
import pytest

from conftest import REAL
from app.pipeline.pipeline import extract_statement

pytestmark = pytest.mark.skipif(not REAL.exists(), reason="real sample PDFs not available")


def run(name, pw=None):
    return extract_statement((REAL / name).read_bytes(), pw)


@pytest.mark.parametrize("name,count,order", [
    ("hdfc_text.pdf", 85, "ascending"), ("icici_bank_statement_text.pdf", 110, "ascending"),
    ("sbi_bank_statement_text.pdf", 32, "ascending"),
])
def test_text_statements_reconcile_fully(name, count, order):
    out = run(name)
    assert len(out.txns) == count
    assert out.recon.order == order
    assert out.recon.mismatched == 0 and out.recon.integrity_score == 100.0


def test_union_password_descending():
    out = run("union_protected.pdf", "123456")
    assert len(out.txns) == 137 and out.recon.order == "descending" and out.recon.mismatched == 0
    assert out.metadata.get("ifsc") == "UBIN0567221"


def test_indusind_tampering_detected():
    out = run("induslnd_bank_statement_text.pdf")
    assert any(c.name == "Document integrity" and c.status == "fail" for c in out.recon.checks)
    assert out.recon.mismatched >= 1
    # inconsistent rows are reported, never silently rewritten
    assert not any("amount_corrected" in t.flags or "balance_corrected" in t.flags for t in out.txns)


@pytest.mark.slow
def test_indian_bank_card_total_due():
    out = run("credit_sample/credit_statement_image.pdf")
    assert out.metadata.statement_type == "credit_card"
    assert out.recon.opening_balance == 46.26 and out.metadata.get("total_due") == 2364.52
    assert any(c.status == "pass" and "total due" in c.name for c in out.recon.checks)
