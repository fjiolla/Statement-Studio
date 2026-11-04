import json
from pathlib import Path

from app.classify.engine import classify_many, is_self_transfer
from app.classify.narration import parse

GOLD = Path(__file__).parent / "data" / "gold_narrations.json"


def test_gold_accuracy():
    gold = json.loads(GOLD.read_text())
    hits = 0
    for st in ("bank_account", "credit_card"):
        rows = [g for g in gold if g["statement_type"] == st]
        res = classify_many([{"description": g["text"], "is_debit": g["is_debit"], "amount": g["amount"]} for g in rows], st)
        hits += sum(r.category == g["label"] for r, g in zip(res, rows))
    assert hits / len(gold) >= 0.93


def test_direction_constraints():
    res = classify_many([{"description": "NEFT CR ACME PVT LTD SALARY", "is_debit": True, "amount": 50000}], "bank_account")
    assert res[0].category != "salary"


def test_every_result_is_explained():
    res = classify_many([{"description": "UPI/DR/123456789012/SWIGGY/YESB/swiggy@ybl/order", "is_debit": True, "amount": 420},
                         {"description": "SHREE SAI MEDICAL STORE PUNE", "is_debit": True, "amount": 310}], "bank_account")
    assert res[0].category == "food" and res[0].merchant == "Swiggy"
    assert res[1].category == "health"
    assert all(r.explanation for r in res)


def test_self_transfer():
    n = parse("UPIAR/124611861260/DR/ABDUL LA/CNRB/0749101056362@")
    assert is_self_transfer(n, ["ABDUL", "LATHEEF", "U", "K"])
    assert not is_self_transfer(parse("UPIAR/1246/DR/NUSAI R A/BARB/nusair714@okax"), ["ABDUL", "LATHEEF"])


def test_learned_rule_wins():
    from app.classify.engine import UserRule
    key = parse("IMPS-823317383520-SHIVAM GOND-KKBK-XXXXX X4834-PERSONAL").key
    res = classify_many([{"description": "IMPS-823317383520-SHIVAM GOND-KKBK-XXXXX X4834-PERSONAL", "is_debit": True, "amount": 1200}],
                        "bank_account", [UserRule(match=key, category="rent", direction="debit")])
    assert res[0].category == "rent" and res[0].method == "learned"
