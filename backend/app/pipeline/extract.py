"""RawRow -> Txn normalisation, plus a header-less fallback parser."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .layout import median_height
from .models import BBox, Line, RawRow, Txn
from .normalize import infer_month_first, is_money_token, looks_like_date_start, parse_amount, parse_date, signed_balance

RE_OPENING = re.compile(r"\b(brought\s*forward|b\s*/\s*f\b|bal(ance)?\s*b/?f|opening\s*bal(ance)?|"
                        r"previous\s*(statement\s*)?(outstanding|balance)|balance\s*forward|bal\s*fwd)\b", re.I)
RE_CLOSING = re.compile(r"\b(carried\s*forward|c\s*/\s*f\b|closing\s*bal(ance)?|balance\s*c/?f)\b", re.I)


@dataclass
class ExtractResult:
    txns: list[Txn] = field(default_factory=list)
    opening_balance: Optional[float] = None
    closing_balance_row: Optional[float] = None
    dropped_rows: int = 0
    warnings: list[str] = field(default_factory=list)


def _clean_desc(parts: list[str]) -> str:
    text = " ".join(p.strip() for p in parts if p and p.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:|")


def _clean_ref(parts: list[str]) -> str:
    vals = [p.strip() for p in parts if p and p.strip() not in ("", "-", "--")]
    out = ""
    for v in vals:
        # a reference that wrapped mid-token ("MAB00011671487" + "5")
        if out and re.match(r"^[0-9A-Z]{1,3}$", v) and re.search(r"[0-9A-Z]$", out):
            out += v
        else:
            out = f"{out} {v}".strip()
    return out


def rows_to_txns(rows: list[RawRow], roles: set[str], statement_type: str, ocr_pages: set[int],
                 year_hint: Optional[int]) -> ExtractResult:
    res = ExtractResult()
    # An unlabelled/unknown column holding only Cr/Dr markers is the direction column,
    # whatever its header says.
    if "crdr" not in roles and "amount" in roles:
        vals = [r.text("other").strip().lower().strip(".()") for r in rows if r.text("other").strip()]
        if vals and sum(v in ("cr", "dr", "c", "d", "credit", "debit") for v in vals) >= 0.9 * len(vals):
            for r in rows:
                if "other" in r.cells:
                    r.cells["crdr"] = r.cells.pop("other")
            roles = roles | {"crdr"}
    date_role0 = "date" if "date" in roles else "value_date"
    month_first = infer_month_first([r.text(date_role0) for r in rows])
    # Money columns whose values almost always have decimals: a bare integer in them is stray
    # text (an overflowing reference or narration), not an amount.
    money_tokens = [tok for r in rows for role in ("debit", "credit", "amount")
                    for tok in r.text(role).split() if any(ch.isdigit() for ch in tok)]
    with_dec = sum(1 for tok in money_tokens if re.search(r"\d\.\d{2}\b", tok))
    strict = bool(money_tokens) and with_dec / len(money_tokens) >= 0.85
    for row in rows:
        ocr = row.page in ocr_pages
        date_role = "date" if "date" in roles else "value_date"
        raw_date = row.text(date_role)
        d = parse_date(raw_date, year_hint=year_hint, allow_compact=ocr, month_first=month_first)
        vd = parse_date(row.text("value_date"), year_hint=year_hint, allow_compact=ocr,
                        month_first=month_first) if "value_date" in roles else None
        if d is None and vd is not None:
            d = vd

        desc_parts = row.cells.get("description", [])
        description = _clean_desc(desc_parts)
        if not description and row.cells.get("other"):
            description = _clean_desc(row.cells["other"])
        reference = _clean_ref(row.cells.get("ref", []))

        debit = credit = None
        direction_source = "column"
        is_neg = False
        flags: list[str] = []
        if "debit" in roles or "credit" in roles:
            dv, _ = parse_amount(row.text("debit"), ocr=ocr, strict=strict)
            cv, _ = parse_amount(row.text("credit"), ocr=ocr, strict=strict)
            debit = dv if dv else None
            credit = cv if cv else None
        if debit is None and credit is None and "amount" in roles:
            av, marker = parse_amount(row.text("amount"), ocr=ocr, strict=strict)
            crdr = row.text("crdr").lower()
            if "cr" in crdr or "c" == crdr.strip():
                marker = "cr"
            elif "dr" in crdr or "d" == crdr.strip():
                marker = "dr"
            if av:
                if marker == "cr":
                    credit, direction_source = av, "marker"
                elif marker in ("dr", "neg"):
                    debit, direction_source = av, "marker"
                    is_neg = marker == "neg"
                elif statement_type == "credit_card":
                    debit, direction_source = av, "default"
                else:
                    # direction decided later from the running balance
                    debit, direction_source = av, "unknown"
        balance = signed_balance(row.text("balance"), ocr=ocr) if "balance" in roles else None

        full_text = f"{description} {reference}"
        if RE_OPENING.search(full_text) and (len(description) < 60):
            amt = balance if balance is not None else (debit if debit is not None else credit)
            if statement_type == "credit_card" and amt is not None and credit is not None and debit is None:
                amt = -amt
            if res.opening_balance is None and amt is not None:
                res.opening_balance = amt
            continue
        if RE_CLOSING.search(full_text) and debit is None and credit is None:
            if balance is not None:
                res.closing_balance_row = balance
            continue

        if debit is None and credit is None:
            res.dropped_rows += 1
            if description:
                res.warnings.append(f"Skipped a row without an amount on page {row.page + 1}: “{description[:60]}”")
            continue
        if d is None:
            flags.append("date_unparsed")

        txn = Txn(index=len(res.txns), date=d, value_date=vd, description=description or "(no description)",
                  reference=reference, debit=debit, credit=credit, balance=balance, bboxes=row.bboxes,
                  page=row.page, raw_date=raw_date, direction_source=direction_source,
                  confidence=round(min(1.0, row.min_conf), 4), flags=flags,
                  source="ocr" if ocr else "text",
                  amount_conf=min(row.role_conf.get(r, 1.0) for r in ("debit", "credit", "amount")),
                  balance_conf=row.role_conf.get("balance", 1.0))
        txn.minus_signed = is_neg
        res.txns.append(txn)

    # Signed-amount columns: if some amounts carry a minus and none carry Cr/Dr, the
    # unsigned ones are credits (otherwise the first row, with no prior balance, can't be decided).
    signed = [t for t in res.txns if t.direction_source == "marker" and t.debit is not None]
    marked_cr = [t for t in res.txns if t.direction_source == "marker" and t.credit is not None]
    if signed and not marked_cr and all(t.minus_signed for t in signed):
        for t in res.txns:
            if t.direction_source == "unknown":
                t.credit, t.debit, t.direction_source = t.debit, None, "sign"
    return res


# ------------------------------------------------------------ fallback parser

RE_TRAILING_MONEY = re.compile(r"(?:\s+(-|[-(]?\d[\d,]*\.\d{2}\)?(?:\s*\(?(?:cr|dr)\)?\.?)?))+\s*$", re.I)


def fallback_parse(lines: list[Line], statement_type: str, year_hint: Optional[int]) -> list[Txn]:
    """Header-less parsing: lines that start with a date and end with money tokens.

    The last money token is the balance when there are ≥2; direction comes from
    Cr/Dr markers or, later, from the balance chain.
    """
    txns: list[Txn] = []
    mh = median_height(lines)
    last: Optional[Txn] = None
    last_line: Optional[Line] = None
    for ln in lines:
        text = ln.text
        if looks_like_date_start(text):
            money = [w for w in ln.words if is_money_token(w.text) or w.text == "-"]
            money_vals = [parse_amount(w.text) for w in money if w.text != "-"]
            if not money_vals:
                continue
            d = parse_date(text, year_hint=year_hint)
            first_money_x = min(w.x0 for w in money)
            desc_words = [w for w in ln.words if w.x1 <= first_money_x and not looks_like_date_start(w.text)]
            desc = " ".join(w.text for w in desc_words)
            desc = re.sub(r"^\s*\d{1,2}[/\-. ]\w{2,3}[/\-. ]\d{2,4}\s*", "", desc)
            balance = None
            amt, marker = money_vals[0]
            if len(money_vals) >= 2 and statement_type != "credit_card":
                bv, bm = money_vals[-1]
                balance = -bv if bm in ("dr", "neg") else bv
                amt, marker = money_vals[-2]
            debit = credit = None
            src = "marker"
            if marker == "cr":
                credit = amt
            elif marker in ("dr", "neg"):
                debit = amt
            else:
                debit = amt
                src = "default" if statement_type == "credit_card" else "unknown"
            last = Txn(index=len(txns), date=d, value_date=None, description=desc.strip() or "(no description)",
                       reference="", debit=debit, credit=credit, balance=balance,
                       bboxes=[BBox(ln.page, ln.x0 - 2, ln.y0 - 1.5, ln.x1 + 2, ln.y1 + 1.5)], page=ln.page,
                       raw_date=text[:12], direction_source=src,
                       confidence=min(w.conf for w in ln.words), flags=["fallback_parser"],
                       source=ln.words[0].source)
            txns.append(last)
            last_line = ln
        elif last is not None and last_line is not None and ln.page == last_line.page \
                and ln.y0 - last_line.y1 < 1.5 * mh and not any(is_money_token(w.text) for w in ln.words):
            last.description = f"{last.description} {text}".strip()
            b = last.bboxes[-1]
            b.y1 = max(b.y1, ln.y1 + 1.5)
            last_line = ln
        else:
            last_line = None if last is None else last_line
    return txns
