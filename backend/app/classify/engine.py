"""Hybrid classifier: learned user rules → heuristic rules → ML → channel priors."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from . import categories as C
from .ml import get_model
from .narration import Narration, parse
from .rules import RuleHit, apply_rules, channel_fallback

CREDIT_OK = {"salary", "interest", "refund", "transfer_in", "cash_deposit", "card_payment", "other"}
DEBIT_BLOCK = {"salary", "interest", "refund", "transfer_in", "cash_deposit"}
REVIEW_BELOW = 0.70
STRONG_RULE = 0.75


@dataclass
class UserRule:
    """A correction the user asked us to remember."""
    match: str            # narration key or substring (lower-case)
    category: str
    kind: str = "key"     # key | contains
    direction: Optional[str] = None  # debit | credit | None


@dataclass
class Classification:
    category: str
    category_name: str
    confidence: float
    method: str          # learned | rule | merchant | ml | rule+ml | channel | fallback
    explanation: str
    merchant: str = ""
    counterparty: str = ""
    channel: str = "OTHER"
    vpa: str = ""
    key: str = ""
    needs_review: bool = False
    alternatives: list[dict] = field(default_factory=list)
    self_transfer: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _allowed(cat: str, is_debit: bool, statement_type: str, channel: str = "") -> bool:
    if channel == "CARD" and cat in ("transfer_out", "transfer_in"):
        return False  # card swipes go to merchants, never to people
    if is_debit:
        return cat not in DEBIT_BLOCK
    if statement_type == "credit_card":
        return cat in CREDIT_OK
    return cat in CREDIT_OK | {"investment"}


def _user_hit(n: Narration, is_debit: bool, rules: Iterable[UserRule]) -> Optional[UserRule]:
    key = n.key
    low = n.normalized.lower()
    for r in rules:
        if r.direction and (r.direction == "debit") != is_debit:
            continue
        if r.kind == "key" and r.match == key:
            return r
        if r.kind == "contains" and r.match and r.match in low:
            return r
    return None


HONORIFICS = {"MR", "MRS", "MS", "MISS", "DR", "SHRI", "SMT", "M/S", "KUMARI"}


def _holder_tokens(holder: Optional[str]) -> list[str]:
    if not holder:
        return []
    return [w for w in re.sub(r"[^A-Z ]", " ", holder.upper()).split() if w not in HONORIFICS and len(w) > 1]


def is_self_transfer(n: Narration, holder_tokens: list[str]) -> bool:
    """Counterparty looks like the account holder (UPI truncates names: 'ABDUL LA')."""
    if not holder_tokens or n.channel not in ("UPI", "IMPS", "NEFT", "RTGS", "TRANSFER"):
        return False
    cp = re.sub(r"[^A-Z ]", " ", (n.counterparty or "").upper()).split()
    if not cp:
        return False
    first = holder_tokens[0]
    if cp[0] == first or (len(cp[0]) >= 4 and first.startswith(cp[0])):
        rest = holder_tokens[1:]
        if len(cp) == 1 or not rest:
            return len(cp[0]) >= 4
        return any(r.startswith(cp[1][:2]) for r in rest)
    joined = "".join(cp)
    return len(joined) >= 6 and "".join(holder_tokens).startswith(joined)


def classify_many(items: list[dict], statement_type: str, user_rules: Optional[list[UserRule]] = None,
                  account_holder: Optional[str] = None) -> list[Classification]:
    """items: [{"description", "is_debit", "amount"}] -> one Classification each."""
    user_rules = user_rules or []
    holder = _holder_tokens(account_holder)
    parsed = [parse(it["description"]) for it in items]
    model = get_model()
    preds = model.predict([it["description"] for it in items], [it["is_debit"] for it in items],
                          [it["amount"] for it in items], [statement_type] * len(items))
    out: list[Classification] = []
    for it, n, p in zip(items, parsed, preds):
        is_debit = it["is_debit"]
        base = dict(counterparty=n.counterparty, channel=n.channel, vpa=n.vpa, key=n.key)

        ur = _user_hit(n, is_debit, user_rules)
        if ur:
            out.append(Classification(ur.category, C.name(ur.category), 0.99, "learned",
                                      "You categorised this payee before; applied your rule.", **base))
            continue

        # ML distribution restricted to categories that make sense for the direction
        allowed = {c: v for c, v in p.proba.items() if _allowed(c, is_debit, statement_type, n.channel)}
        mass = sum(allowed.values()) or 1.0
        alts = sorted(((c, v / mass) for c, v in allowed.items()), key=lambda x: -x[1])
        ml_cat, ml_conf = alts[0] if alts else ("other", 0.0)
        ml_conf_norm = ml_conf
        alternatives = [{"category": c, "name": C.name(c), "score": round(s, 3)} for c, s in alts[:3]]
        cue_txt = ", ".join(f"“{w}”" for w in p.cues) if p.cues else "overall wording"

        if is_self_transfer(n, holder):
            cat = "transfer_out" if is_debit else "transfer_in"
            out.append(Classification(cat, C.name(cat), 0.9, "rule",
                                      f"Transfer {'to' if is_debit else 'from'} your own account "
                                      f"(“{n.counterparty}” matches the account holder)",
                                      self_transfer=True, **base))
            continue

        hit: Optional[RuleHit] = apply_rules(n, is_debit, it["amount"], statement_type)
        if hit and hit.confidence >= STRONG_RULE:
            method = "merchant" if hit.rule_id == "merchant" else "rule"
            conf = hit.confidence
            expl = hit.explanation
            if ml_cat == hit.category and ml_conf > 0.5:
                conf = min(0.99, conf + 0.04)
                method = f"{method}+ml"
                expl += f" · model agrees ({ml_conf:.0%})"
            out.append(Classification(hit.category, C.name(hit.category), round(conf, 3), method, expl,
                                      merchant=hit.merchant, needs_review=conf < REVIEW_BELOW,
                                      alternatives=alternatives, **base))
            continue

        weak = hit or channel_fallback(n, is_debit, statement_type)
        # channel priors (P2P / merchant QR) are only overridden by a clearly confident model
        margin = 0.12 if weak and weak.rule_id in ("p2p_out", "p2p_in", "upi_merchant") else 0.05
        if weak and (ml_conf_norm < max(0.7, weak.confidence + margin) or ml_cat in ("other",)):
            conf = weak.confidence
            expl = weak.explanation
            if ml_cat == weak.category:
                conf = min(0.95, max(conf, ml_conf_norm) + 0.08)
                expl += f" · model agrees ({ml_conf:.0%})"
            out.append(Classification(weak.category, C.name(weak.category), round(conf, 3), "channel", expl,
                                      merchant=weak.merchant, needs_review=conf < REVIEW_BELOW,
                                      alternatives=alternatives, **base))
            continue

        if alts and ml_conf_norm >= 0.4:
            out.append(Classification(ml_cat, C.name(ml_cat), round(ml_conf_norm, 3), "ml",
                                      f"Model prediction from {cue_txt}", needs_review=ml_conf_norm < REVIEW_BELOW,
                                      alternatives=alternatives, **base))
            continue

        out.append(Classification("other", C.name("other"), round(ml_conf_norm, 3), "fallback",
                                  "No rule matched and the model was not confident.", needs_review=True,
                                  alternatives=alternatives, **base))
    return out


def counterparty_key(description: str) -> str:
    return parse(description).key


def normalise_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
