"""Train the bundled classifier and record benchmark numbers for the model card.

Usage: python scripts/train_model.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.classify.engine import classify_many  # noqa: E402
from app.classify.ml import BUNDLED_DIR, train  # noqa: E402
from app.classify.synth import Example  # noqa: E402

gold_rows = json.loads((Path(__file__).resolve().parents[1] / "tests/data/gold_narrations.json").read_text())
gold = [Example(g["text"], g["is_debit"], g["amount"], g["statement_type"], g["label"]) for g in gold_rows]
model = train(save_dir=BUNDLED_DIR, gold=gold)

hits = review = 0
for st in ("bank_account", "credit_card"):
    rows = [g for g in gold_rows if g["statement_type"] == st]
    res = classify_many([{"description": g["text"], "is_debit": g["is_debit"], "amount": g["amount"]} for g in rows], st)
    hits += sum(r.category == g["label"] for r, g in zip(res, rows))
    review += sum(r.needs_review for r in res)
bench = {
    "gold_set": "161 hand-labelled narrations from 8 real Indian bank & card statements (HDFC, ICICI, SBI, Union, IndusInd, Indian Bank)",
    "hybrid_accuracy": round(hits / len(gold_rows), 4),
    "ml_only_accuracy": model.card["gold"]["accuracy"],
    "flagged_for_review": review,
    "note": "The gold set was used for error analysis while writing rules, so treat it as a regression benchmark. "
            "The synthetic hold-out (unseen names) is the blind ML score.",
    "ml_holdout": model.card["holdout"],
}
(BUNDLED_DIR / "benchmark.json").write_text(json.dumps(bench, indent=2))
print(json.dumps(bench, indent=2))
