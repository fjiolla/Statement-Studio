"""Evaluate the hybrid classifier (and the ML model alone) on the hand-labelled gold set."""
import sys, json, collections
sys.path.insert(0, __file__.rsplit("/scripts", 1)[0])
from app.classify.engine import classify_many
from app.classify.ml import get_model
gold = json.load(open(__file__.rsplit("/scripts", 1)[0] + "/tests/data/gold_narrations.json"))
by_type = collections.defaultdict(list)
for g in gold: by_type[g["statement_type"]].append(g)
hits = 0; errs = []; methods = collections.Counter(); review = 0
for st, rows in by_type.items():
    res = classify_many([{"description": g["text"], "is_debit": g["is_debit"], "amount": g["amount"]} for g in rows], st)
    for g, c in zip(rows, res):
        methods[c.method.split("+")[0]] += 1
        review += c.needs_review
        if c.category == g["label"]: hits += 1
        else: errs.append((g["label"], c.category, round(c.confidence, 2), c.method, g["text"][:70]))
m = get_model()
pred = m.predict([g["text"] for g in gold], [g["is_debit"] for g in gold], [g["amount"] for g in gold], [g["statement_type"] for g in gold])
ml_hits = sum(p.category == g["label"] for p, g in zip(pred, gold))
print(f"gold rows: {len(gold)}")
print(f"hybrid accuracy: {hits/len(gold):.1%}   ML-only accuracy: {ml_hits/len(gold):.1%}   flagged for review: {review}")
print("decided by:", dict(methods))
for e in errs: print("  MISS expected=%-14s got=%-14s %.2f %-9s %s" % e)
