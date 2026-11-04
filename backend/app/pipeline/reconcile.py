"""Running-balance reconciliation and statement-level integrity checks.

For bank accounts every row must satisfy  balance[i] = balance[i-1] + credit - debit.
That one equation lets us:
  * detect newest-first statements and put them in chronological order
  * infer debit/credit when a statement only has an unsigned Amount column
  * repair a single misread digit (OCR) and say whether the balance or the
    amount was wrong, by looking at whether the *next* row agrees
  * surface rows that genuinely don't add up instead of silently exporting them
Card statements have no running balance, so we check totals instead:
previous outstanding + debits − credits = total due.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .metadata import Metadata
from .models import Txn

TOL = 0.011
AUTO_FIX_CONF = 0.85


@dataclass
class Check:
    name: str
    status: str  # pass | fail | warn | skip
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class ReconResult:
    order: str = "ascending"
    checkable: int = 0
    ok: int = 0
    corrected: int = 0
    mismatched: int = 0
    opening_balance: Optional[float] = None
    opening_source: str = "none"
    closing_balance: Optional[float] = None
    total_debits: float = 0.0
    total_credits: float = 0.0
    integrity_score: Optional[float] = None
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "order": self.order, "checkable_rows": self.checkable, "ok_rows": self.ok,
            "corrected_rows": self.corrected, "mismatched_rows": self.mismatched,
            "opening_balance": self.opening_balance, "opening_source": self.opening_source,
            "closing_balance": self.closing_balance, "total_debits": round(self.total_debits, 2),
            "total_credits": round(self.total_credits, 2), "integrity_score": self.integrity_score,
            "checks": [c.to_dict() for c in self.checks],
        }


def _fmt(v: Optional[float]) -> str:
    return "—" if v is None else f"₹{v:,.2f}"


def _chain_score(txns: list[Txn]) -> int:
    score, prev = 0, None
    for t in txns:
        if t.balance is None:
            continue
        if prev is not None:
            diff = t.balance - prev
            amt = (t.credit or 0) + (t.debit or 0)
            if t.direction_source == "unknown":
                score += abs(abs(diff) - amt) < TOL
            else:
                score += abs(diff - t.amount) < TOL
        prev = t.balance
    return score


def _orient(txns: list[Txn]) -> tuple[list[Txn], str]:
    dated = [t.date for t in txns if t.date]
    if len(dated) >= 2 and dated[0] != dated[-1]:
        if dated[0] > dated[-1]:
            return list(reversed(txns)), "descending"
        return txns, "ascending"
    if any(t.balance is not None for t in txns):
        rev = list(reversed(txns))
        if _chain_score(rev) > _chain_score(txns):
            return rev, "descending"
    return txns, "ascending"


def _plausible_misread(a: Optional[float], b: Optional[float]) -> bool:
    """True if two amounts differ the way an OCR misread would: ≤2 digits changed,
    or one digit dropped/added."""
    if a is None or b is None:
        return False
    sa, sb = f"{abs(a):.2f}".replace(".", ""), f"{abs(b):.2f}".replace(".", "")
    if len(sa) == len(sb):
        return sum(x != y for x, y in zip(sa, sb)) <= 2
    if abs(len(sa) - len(sb)) == 1:
        short, long_ = sorted((sa, sb), key=len)
        return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))
    return False


def _set_direction(t: Txn, signed: float, source: str) -> None:
    amt = abs(signed)
    if signed >= 0:
        t.credit, t.debit = amt, None
    else:
        t.debit, t.credit = amt, None
    t.direction_source = source


def _matches(prev: float, t: Txn) -> bool:
    if t.balance is None:
        return False
    diff = t.balance - prev
    if t.direction_source == "unknown":
        return abs(abs(diff) - ((t.debit or 0) + (t.credit or 0))) < TOL
    return abs(diff - t.amount) < TOL


def reconcile(txns: list[Txn], statement_type: str, opening_hint: Optional[float], md: Metadata) -> tuple[list[Txn], ReconResult]:
    res = ReconResult()
    if not txns:
        return txns, res
    txns, res.order = _orient(txns)

    if statement_type == "credit_card":
        _reconcile_card(txns, opening_hint, md, res)
    else:
        _reconcile_bank(txns, opening_hint, md, res)

    _impute_dates(txns)
    _common_checks(txns, md, res)
    for i, t in enumerate(txns):
        t.index = i
    return txns, res


def _impute_dates(txns: list[Txn]) -> None:
    """Recover dates OCR could not read, only when the neighbours pin down a single answer.

    Rows are chronological, so an unreadable date lies between its neighbours. If the
    fragment still shows the day ("24 - 2025") and exactly one date in that window has
    that day, or both neighbours share a date, we use it and say so.
    """
    import re
    from datetime import timedelta

    for i, t in enumerate(txns):
        if t.date is not None:
            continue
        prev = next((x.date for x in reversed(txns[:i]) if x.date), None)
        nxt = next((x.date for x in txns[i + 1:] if x.date), None)
        if prev is None or nxt is None or nxt < prev:
            continue
        guess = None
        if prev == nxt:
            guess = prev
        else:
            m = re.match(r"\D*(\d{1,2})\b", t.raw_date or "")
            if m and (nxt - prev).days <= 62:
                day = int(m.group(1))
                window = [prev + timedelta(days=k) for k in range((nxt - prev).days + 1)]
                fits = [d for d in window if d.day == day]
                if len(fits) == 1:
                    guess = fits[0]
        if guess:
            t.date = guess
            t.flags = [f for f in t.flags if f != "date_unparsed"] + ["date_inferred"]
            t.notes.append(f"OCR could not read the date (“{(t.raw_date or '').strip()}”); "
                           f"inferred {guess:%d %b %Y} from the neighbouring rows.")


def _reconcile_bank(txns: list[Txn], opening_hint: Optional[float], md: Metadata, res: ReconResult) -> None:
    has_balance = sum(t.balance is not None for t in txns)
    opening = opening_hint
    res.opening_source = "statement_row" if opening is not None else "none"
    if opening is None and md.get("opening_balance") is not None:
        opening, res.opening_source = md.get("opening_balance"), "header"

    # same-day reordering: some banks print intra-day rows in an order that breaks the chain
    i = 1
    while i < len(txns) - 1:
        a, b = txns[i], txns[i + 1]
        prev = txns[i - 1].balance
        if prev is not None and a.date == b.date and not _matches(prev, a) and _matches(prev, b):
            if b.balance is not None and _matches(b.balance, a):
                txns[i], txns[i + 1] = b, a
                b.notes.append("Reordered within the same day to follow the running balance.")
        i += 1

    prev = opening
    for i, t in enumerate(txns):
        if t.balance is None:
            t.recon_status = "unverified"
            if prev is not None:
                prev = prev + t.amount if t.direction_source != "unknown" else None
            continue
        if prev is None:
            # first row with no opening balance: derive it if direction is known
            if t.direction_source != "unknown":
                opening = round(t.balance - t.amount, 2)
                res.opening_source = "derived"
            t.recon_status = "unverified"
            prev = t.balance
            continue

        res.checkable += 1
        diff = round(t.balance - prev, 2)
        amt = (t.credit or 0) + (t.debit or 0)
        nxt = next((x for x in txns[i + 1:] if x.balance is not None), None)

        if t.direction_source == "unknown":
            if abs(abs(diff) - amt) < TOL:
                _set_direction(t, diff, "balance")
                t.recon_status = "ok"
                res.ok += 1
                prev = t.balance
                continue
        elif abs(diff - t.amount) < TOL:
            t.recon_status = "ok"
            res.ok += 1
            prev = t.balance
            continue
        elif abs(diff + t.amount) < TOL:
            if t.source == "ocr":
                # OCR geometry can drop an amount into the neighbouring column
                _set_direction(t, diff, "balance")
                t.flags.append("direction_corrected")
                t.notes.append("Debit/credit swapped to agree with the running balance.")
                t.recon_status = "corrected"
                res.corrected += 1
            else:
                side = "credit" if t.amount > 0 else "debit"
                t.flags.append("direction_conflict")
                t.notes.append(f"Printed as a {side}, but the balance moved the other way by the same amount. "
                               "Kept as printed — the statement itself is inconsistent here.")
                t.recon_status = "mismatch"
                res.mismatched += 1
            prev = t.balance
            continue

        # Mismatch. For OCR rows decide whether the balance or the amount was misread
        # (the next row agrees with the expected vs. the printed balance) and repair it
        # only if the two values differ like a misread digit. Text-layer numbers are
        # exact, so a mismatch there is reported, never "fixed".
        signed = t.amount if t.direction_source != "unknown" else None
        expected = round(prev + (signed or 0), 2)
        fixed = False
        if t.source == "ocr":
            bal_wrong = signed is not None and nxt is not None and _matches(expected, nxt) \
                and not _matches(t.balance, nxt) and _plausible_misread(t.balance, expected)
            amt_wrong = not bal_wrong and (nxt is None or _matches(t.balance, nxt)) and _plausible_misread(amt, abs(diff))
            # Only overwrite what OCR was unsure about; a confident read that disagrees with the
            # balance is more likely a genuine inconsistency, so it becomes a one-click suggestion.
            if bal_wrong and t.balance_conf < AUTO_FIX_CONF:
                original = t.balance
                t.balance = expected
                t.flags.append("balance_corrected")
                t.notes.append(f"OCR was unsure of the balance ({_fmt(original)}, {t.balance_conf:.0%} confidence); "
                               f"corrected to {_fmt(expected)} because the next row continues from it.")
                fixed = True
            elif amt_wrong and t.amount_conf < AUTO_FIX_CONF:
                original = amt
                _set_direction(t, diff, "balance")
                t.flags.append("amount_corrected")
                t.notes.append(f"OCR was unsure of the amount ({_fmt(original)}, {t.amount_conf:.0%} confidence); "
                               f"the running balance implies {_fmt(abs(diff))}.")
                fixed = True
            elif bal_wrong:
                t.suggestion = {"field": "balance", "value": expected,
                                "reason": "The next row's balance continues from this value."}
            elif amt_wrong:
                t.suggestion = {"field": "amount", "value": abs(diff), "direction": "credit" if diff > 0 else "debit",
                                "reason": "The change in running balance implies this amount."}
        if fixed:
            t.recon_status = "corrected"
            res.corrected += 1
        else:
            t.flags.append("balance_mismatch")
            t.notes.append(f"Expected balance {_fmt(expected)}, statement shows {_fmt(t.balance)} "
                           f"(difference {_fmt(round(t.balance - expected, 2))}).")
            t.recon_status = "mismatch"
            res.mismatched += 1
        prev = t.balance

    # rows whose direction never resolved fall back to debit and get flagged
    for t in txns:
        if t.direction_source == "unknown":
            t.direction_source = "default"
            t.flags.append("direction_unverified")

    res.opening_balance = opening
    last_bal = next((t.balance for t in reversed(txns) if t.balance is not None), None)
    res.closing_balance = last_bal
    res.total_debits = sum(t.debit or 0 for t in txns)
    res.total_credits = sum(t.credit or 0 for t in txns)

    if has_balance:
        if res.checkable:
            pct = 100.0 * (res.ok + 0.9 * res.corrected) / res.checkable
            res.integrity_score = round(pct, 1)
        status = "pass" if res.mismatched == 0 else ("warn" if res.mismatched <= max(1, res.checkable // 20) else "fail")
        res.checks.append(Check("Running balance", status,
                                f"{res.ok} of {res.checkable} rows reconcile exactly"
                                + (f", {res.corrected} auto-corrected" if res.corrected else "")
                                + (f", {res.mismatched} don't add up" if res.mismatched else "") + "."))
    else:
        res.checks.append(Check("Running balance", "skip", "The statement has no balance column."))

    if opening is not None and last_bal is not None:
        expected = round(opening + res.total_credits - res.total_debits, 2)
        ok = abs(expected - last_bal) < 0.05
        res.checks.append(Check("Opening + credits − debits = closing", "pass" if ok else "fail",
                                f"{_fmt(opening)} + {_fmt(res.total_credits)} − {_fmt(res.total_debits)} = {_fmt(expected)}"
                                f" vs closing {_fmt(last_bal)}."))
    stated_close = md.get("closing_balance")
    if stated_close is not None and last_bal is not None:
        ok = abs(abs(stated_close) - abs(last_bal)) < 0.05
        res.checks.append(Check("Closing balance matches statement summary", "pass" if ok else "warn",
                                f"Summary shows {_fmt(stated_close)}, last transaction balance is {_fmt(last_bal)}."
                                + ("" if ok else " The file may be a partial statement or include uncleared funds.")))


def _reconcile_card(txns: list[Txn], opening_hint: Optional[float], md: Metadata, res: ReconResult) -> None:
    opening = opening_hint
    res.opening_source = "statement_row" if opening is not None else "none"
    if opening is None and md.get("opening_balance") is not None:
        opening, res.opening_source = md.get("opening_balance"), "header"
    res.opening_balance = opening
    res.total_debits = sum(t.debit or 0 for t in txns)
    res.total_credits = sum(t.credit or 0 for t in txns)
    total_due = md.get("total_due")
    expected = round((opening or 0) + res.total_debits - res.total_credits, 2)
    res.closing_balance = expected
    for t in txns:
        t.recon_status = "unverified"
    if total_due is None:
        res.checks.append(Check("Total due", "skip", "No total-due figure found to compare against."))
        return
    ok = abs(expected - total_due) < 0.05
    res.checks.append(Check("Previous balance + debits − credits = total due", "pass" if ok else "warn",
                            f"{_fmt(opening or 0)} + {_fmt(res.total_debits)} − {_fmt(res.total_credits)} = {_fmt(expected)}"
                            f" vs total due {_fmt(total_due)}."
                            + ("" if ok else " Fees, interest or unbilled items may be reported separately.")))
    res.checkable = len(txns)
    if ok:
        for t in txns:
            t.recon_status = "ok"
        res.ok = len(txns)
        res.integrity_score = 100.0
    else:
        res.integrity_score = round(max(0.0, 100.0 - 100.0 * abs(expected - total_due) / max(total_due, 1.0)), 1)


def _common_checks(txns: list[Txn], md: Metadata, res: ReconResult) -> None:
    pf, pt = md.get("period_from"), md.get("period_to")
    src = md.fields.get("period_from").source if md.fields.get("period_from") else None
    outside = 0
    today = date.today()
    seen: dict[tuple, int] = {}
    unparsed = 0
    for t in txns:
        if t.date is None:
            unparsed += 1
            continue
        if src == "label" and pf and pt and not (pf <= t.date <= pt):
            # card statements often include the previous-due row dated before the period
            t.flags.append("date_outside_period")
            outside += 1
        if t.date > today:
            t.flags.append("future_date")
        key = (t.date, round(t.amount, 2), t.description, t.balance)
        if t.balance is not None and key in seen:
            t.flags.append("possible_duplicate")
            t.notes.append("Identical to an earlier row including the balance — may be a repeated extraction.")
        seen[key] = t.index
    if unparsed:
        res.checks.append(Check("Dates parsed", "warn", f"{unparsed} row(s) have a date that could not be read."))
    else:
        res.checks.append(Check("Dates parsed", "pass", f"All {len(txns)} transaction dates parsed."))
    if src == "label" and pf and pt:
        res.checks.append(Check("Dates within statement period", "pass" if not outside else "warn",
                                f"{outside} row(s) fall outside {pf:%d %b %Y} – {pt:%d %b %Y}." if outside
                                else f"All dates fall within {pf:%d %b %Y} – {pt:%d %b %Y}."))
