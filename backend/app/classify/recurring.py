"""Recurring-payment detection (subscriptions, EMIs, SIPs, rent, salary).

Groups transactions by counterparty + direction, then looks for a stable
cadence (weekly → yearly) with consistent amounts.
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

CADENCES = [
    ("weekly", 6, 8), ("fortnightly", 13, 16), ("monthly", 26, 35), ("bi-monthly", 55, 66),
    ("quarterly", 84, 96), ("half-yearly", 175, 190), ("yearly", 350, 380),
]
SKIP_CATEGORIES = {"cash_withdrawal", "cash_deposit"}


@dataclass
class RecurringGroup:
    id: str
    label: str
    category: str
    direction: str
    cadence: str
    average_amount: float
    count: int
    first_date: date
    last_date: date
    next_expected: Optional[date]
    txn_indices: list[int] = field(default_factory=list)
    amount_varies: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "category": self.category, "direction": self.direction,
            "cadence": self.cadence, "average_amount": round(self.average_amount, 2), "count": self.count,
            "first_date": self.first_date.isoformat(), "last_date": self.last_date.isoformat(),
            "next_expected": self.next_expected.isoformat() if self.next_expected else None,
            "txn_indices": self.txn_indices, "amount_varies": self.amount_varies,
        }


def detect(rows: list[dict]) -> list[RecurringGroup]:
    """rows: [{index, date, amount, is_debit, key, label, category}]"""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if not r.get("date") or not r.get("key") or r.get("category") in SKIP_CATEGORIES:
            continue
        groups.setdefault((r["key"], r["is_debit"]), []).append(r)

    found: list[RecurringGroup] = []
    for (key, is_debit), items in groups.items():
        if len(items) < 3:
            continue
        items.sort(key=lambda r: r["date"])
        # collapse same-day duplicates (split payments) into one occurrence
        days: list[dict] = []
        for it in items:
            if days and days[-1]["date"] == it["date"]:
                days[-1] = {**days[-1], "amount": days[-1]["amount"] + it["amount"],
                            "indices": days[-1]["indices"] + [it["index"]]}
            else:
                days.append({**it, "indices": [it["index"]]})
        if len(days) < 3:
            continue
        gaps = [(b["date"] - a["date"]).days for a, b in zip(days, days[1:])]
        med = statistics.median(gaps)
        cadence = next((name for name, lo, hi in CADENCES if lo <= med <= hi), None)
        if not cadence:
            continue
        lo, hi = next((lo, hi) for name, lo, hi in CADENCES if name == cadence)
        regular = sum(lo * 0.8 <= g <= hi * 1.25 for g in gaps) / len(gaps)
        if regular < 0.7:
            continue
        amounts = [d["amount"] for d in days]
        mean = statistics.mean(amounts)
        spread = (statistics.pstdev(amounts) / mean) if mean else 1
        tolerance = 0.3 if items[0].get("category") in ("salary", "utilities") else 0.18
        if spread > tolerance:
            continue
        idx = [i for d in days for i in d["indices"]]
        found.append(RecurringGroup(
            id="rec_" + hashlib.sha1(f"{key}|{is_debit}".encode()).hexdigest()[:10], label=items[-1]["label"] or key,
            category=items[-1]["category"], direction="debit" if is_debit else "credit", cadence=cadence,
            average_amount=mean, count=len(days), first_date=days[0]["date"], last_date=days[-1]["date"],
            next_expected=days[-1]["date"] + timedelta(days=int(round(med))), txn_indices=idx,
            amount_varies=spread > 0.02,
        ))
    found.sort(key=lambda g: -g.average_amount * g.count)
    return found
