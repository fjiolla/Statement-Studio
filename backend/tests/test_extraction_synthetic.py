"""Field-level accuracy against exact ground truth for generated statements."""
import json

import pytest

from conftest import SAMPLES, TRUTH
from app.pipeline.pipeline import extract_statement
from app.pipeline.ingest import PasswordRequired, InvalidPassword


def _load(name, password=None):
    out = extract_statement((SAMPLES / f"{name}.pdf").read_bytes(), password)
    truth = json.loads((TRUTH / f"{name}.json").read_text())
    return out, truth


def _field_accuracy(out, truth):
    got = out.txns
    exp = truth["transactions"]
    assert len(got) == len(exp), f"expected {len(exp)} rows, got {len(got)}"
    hits = {"date": 0, "debit": 0, "credit": 0, "balance": 0}
    for g, e in zip(got, exp):
        hits["date"] += (g.date.isoformat() if g.date else None) == e["date"]
        hits["debit"] += (g.debit or None) == (e["debit"] or None)
        hits["credit"] += (g.credit or None) == (e["credit"] or None)
        hits["balance"] += g.balance == e["balance"]
    return {k: v / len(exp) for k, v in hits.items()}


def test_text_statement_is_exact():
    out, truth = _load("aurora_savings")
    acc = _field_accuracy(out, truth)
    assert all(v == 1.0 for v in acc.values()), acc
    assert out.document_type == "text"
    assert out.recon.mismatched == 0 and out.recon.integrity_score == 100.0
    assert out.recon.opening_balance == truth["opening_balance"]
    md = out.metadata
    assert md.get("account_number") == truth["account_number"]
    assert md.get("ifsc") == truth["ifsc"]
    assert md.get("account_holder") == truth["account_holder"]
    # wrapped narrations are rebuilt into one description
    assert any(t.description.startswith("NEFT CR-CITI0000001-ORBITAL SYSTEM") and "SALARY" in t.description for t in out.txns)


@pytest.mark.slow
def test_scanned_statement_ocr_accuracy():
    out, truth = _load("aurora_savings_scanned")
    assert out.document_type == "scanned"
    acc = _field_accuracy(out, truth)
    assert acc["date"] >= 0.97 and acc["balance"] >= 0.97 and acc["debit"] >= 0.97 and acc["credit"] >= 0.97, acc
    assert out.recon.integrity_score >= 95


def test_password_newest_first_signed_amounts():
    with pytest.raises(PasswordRequired):
        extract_statement((SAMPLES / "nimbus_protected.pdf").read_bytes())
    with pytest.raises(InvalidPassword):
        extract_statement((SAMPLES / "nimbus_protected.pdf").read_bytes(), "wrong")
    out, truth = _load("nimbus_protected", "demo1234")
    assert out.was_encrypted and out.recon.order == "descending"
    acc = _field_accuracy(out, truth)  # returned in chronological order
    assert all(v == 1.0 for v in acc.values()), acc
    assert out.metadata.get("ifsc") == truth["ifsc"]


def test_credit_card_statement():
    out, truth = _load("nimbus_card")
    assert out.metadata.statement_type == "credit_card"
    acc = _field_accuracy(out, truth)
    assert acc["debit"] == 1.0 and acc["credit"] == 1.0 and acc["date"] == 1.0
    assert out.metadata.get("total_due") == truth["total_due"]
    assert out.metadata.get("card_number") == truth["card_number"]
    assert any(c.name.startswith("Previous balance") and c.status == "pass" for c in out.recon.checks)


def test_not_a_statement_is_rejected():
    import pymupdf
    from app.pipeline.pipeline import NoTransactionsFound

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Quarterly newsletter. Nothing to see here.")
    with pytest.raises(NoTransactionsFound):
        extract_statement(doc.tobytes())


def test_garbage_bytes_rejected():
    from app.pipeline.ingest import NotAPdf

    with pytest.raises(NotAPdf):
        extract_statement(b"hello, I am not a pdf")
