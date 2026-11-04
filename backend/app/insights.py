"""Analytics computed from stored transactions (cheap; done on read)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from .classify import categories as C


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) and s else s


def compute(txns: list[dict], statement_type: str) -> dict:
    inflow = outflow = 0.0
    income = spend = transfers_in = transfers_out = self_moves = 0.0
    by_cat: dict[str, dict] = {}
    monthly: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0, "spend": 0.0, "income": 0.0})
    daily_spend: dict[str, float] = defaultdict(float)
    balance_by_day: dict[str, float] = {}
    payees: dict[str, dict] = {}
    channels: dict[str, float] = defaultdict(float)

    for t in txns:
        cat = t["category"]
        meta = C.BY_ID.get(cat, C.BY_ID["other"])
        dr, cr = t.get("debit") or 0.0, t.get("credit") or 0.0
        d = _d(t.get("date"))
        month = d.strftime("%Y-%m") if d else "unknown"
        inflow += cr
        outflow += dr
        monthly[month]["inflow"] += cr
        monthly[month]["outflow"] += dr
        if t.get("self_transfer"):
            self_moves += dr + cr
        elif meta.kind == "income":
            income += cr
            monthly[month]["income"] += cr
        elif meta.kind == "expense":
            spend += dr - cr  # refunds on expense categories reduce spend
            monthly[month]["spend"] += dr
            if d and dr:
                daily_spend[d.isoformat()] += dr
        else:
            transfers_in += cr
            transfers_out += dr

        entry = by_cat.setdefault(cat, {"category": cat, "name": meta.name, "kind": meta.kind, "icon": meta.icon,
                                        "debit": 0.0, "credit": 0.0, "count": 0})
        entry["debit"] += dr
        entry["credit"] += cr
        entry["count"] += 1
        if t.get("channel"):
            channels[t["channel"]] += dr

        if dr and not t.get("self_transfer") and cat not in ("cash_withdrawal", "charges", "tax"):
            label = t.get("merchant") or t.get("counterparty") or ""
            if label:
                p = payees.setdefault(label.lower(), {"label": label, "total": 0.0, "count": 0, "category": cat})
                p["total"] += dr
                p["count"] += 1
        if d and t.get("balance") is not None:
            balance_by_day[d.isoformat()] = t["balance"]

    cats = sorted(by_cat.values(), key=lambda e: -(e["debit"] + e["credit"]))
    spend_total = sum(e["debit"] for e in cats if e["kind"] == "expense") or 1.0
    for e in cats:
        e["debit"] = round(e["debit"], 2)
        e["credit"] = round(e["credit"], 2)
        e["share_of_spend"] = round(e["debit"] / spend_total, 4) if e["kind"] == "expense" else None

    months = [{"month": m, **{k: round(v, 2) for k, v in vals.items()}, "net": round(vals["inflow"] - vals["outflow"], 2)}
              for m, vals in sorted(monthly.items())]
    largest = sorted(txns, key=lambda t: -max(t.get("debit") or 0, t.get("credit") or 0))[:5]
    review = [t["id"] for t in txns if t.get("needs_review") and not t.get("reviewed")]
    flagged = [t["id"] for t in txns if t.get("recon_status") == "mismatch"]

    dated = [_d(t["date"]) for t in txns if t.get("date")]
    span_days = (max(dated) - min(dated)).days + 1 if dated else 0
    return {
        "totals": {
            "inflow": round(inflow, 2), "outflow": round(outflow, 2), "net": round(inflow - outflow, 2),
            "income": round(income, 2), "spend": round(spend, 2), "transfers_in": round(transfers_in, 2),
            "transfers_out": round(transfers_out, 2), "self_transfers": round(self_moves, 2),
            "count": len(txns), "debit_count": sum(1 for t in txns if t.get("debit")),
            "credit_count": sum(1 for t in txns if t.get("credit")),
            "avg_daily_spend": round(spend / span_days, 2) if span_days else 0.0, "span_days": span_days,
        },
        "categories": cats,
        "monthly": months,
        "balance_series": [{"date": k, "balance": v} for k, v in sorted(balance_by_day.items())],
        "daily_spend": [{"date": k, "amount": round(v, 2)} for k, v in sorted(daily_spend.items())],
        "top_payees": sorted(({**p, "total": round(p["total"], 2)} for p in payees.values()), key=lambda p: -p["total"])[:8],
        "channels": [{"channel": k, "outflow": round(v, 2)} for k, v in sorted(channels.items(), key=lambda kv: -kv[1]) if v],
        "largest": [t["id"] for t in largest],
        "review_ids": review,
        "flagged_ids": flagged,
    }
