"""Account / card holder details from the non-table parts of the statement.

Labels are matched on visual lines; the value is taken to the right of the
label (skipping ':' and wide tab gaps) and, if nothing is there, from the box
directly below it (card statements use label-over-value tiles).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from .models import Line, Word
from .normalize import RE_NUMERIC_DATE, RE_TEXT_DATE, parse_amount, parse_date

IFSC_BANKS = {
    "SBIN": "State Bank of India", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank", "INDB": "IndusInd Bank", "UBIN": "Union Bank of India",
    "IDIB": "Indian Bank", "PUNB": "Punjab National Bank", "BARB": "Bank of Baroda", "CNRB": "Canara Bank",
    "YESB": "Yes Bank", "IDFB": "IDFC FIRST Bank", "FDRL": "Federal Bank", "BKID": "Bank of India",
    "MAHB": "Bank of Maharashtra", "CBIN": "Central Bank of India", "IOBA": "Indian Overseas Bank",
    "UCBA": "UCO Bank", "AUBL": "AU Small Finance Bank", "RATN": "RBL Bank", "SIBL": "South Indian Bank",
    "KVBL": "Karur Vysya Bank", "DBSS": "DBS Bank", "SCBL": "Standard Chartered", "CITI": "Citibank",
    "HSBC": "HSBC", "PSIB": "Punjab & Sind Bank", "JAKA": "J&K Bank", "KARB": "Karnataka Bank",
    "TMBL": "Tamilnad Mercantile Bank", "CSBK": "CSB Bank", "DLXB": "Dhanlaxmi Bank", "ESFB": "Equitas SFB",
    "UJVN": "Ujjivan SFB", "PYTM": "Paytm Payments Bank", "AIRP": "Airtel Payments Bank", "IPOS": "India Post Payments Bank",
}

BANK_KEYWORDS: list[tuple[str, re.Pattern]] = [
    ("IndusInd Bank", re.compile(r"indusind", re.I)),
    ("HDFC Bank", re.compile(r"\bhdfc\s*bank\b|hdfcbank", re.I)),
    ("ICICI Bank", re.compile(r"\bicici\b", re.I)),
    ("State Bank of India", re.compile(r"state\s*bank\s*of\s*india|\bsbi\b", re.I)),
    ("Axis Bank", re.compile(r"axis\s*bank", re.I)),
    ("Kotak Mahindra Bank", re.compile(r"\bkotak\b", re.I)),
    ("Union Bank of India", re.compile(r"union\s*bank", re.I)),
    ("Indian Bank", re.compile(r"\bindian\s*bank\b", re.I)),
    ("Punjab National Bank", re.compile(r"punjab\s*national|\bpnb\b", re.I)),
    ("Bank of Baroda", re.compile(r"bank\s*of\s*baroda", re.I)),
    ("Canara Bank", re.compile(r"canara\s*bank", re.I)),
    ("Yes Bank", re.compile(r"\byes\s*bank\b", re.I)),
    ("IDFC FIRST Bank", re.compile(r"idfc", re.I)),
    ("Federal Bank", re.compile(r"federal\s*bank", re.I)),
    ("Bank of India", re.compile(r"\bbank\s*of\s*india\b", re.I)),
    ("RBL Bank", re.compile(r"\brbl\s*bank\b", re.I)),
    ("SBI Card", re.compile(r"sbi\s*card", re.I)),
    ("American Express", re.compile(r"american\s*express|\bamex\b", re.I)),
]

RE_IFSC = re.compile(r"\b([A-Z]{4})([0O])([A-Z0-9]{6})\b")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_CARD = re.compile(r"\b(\d{4})[\s-]?([\dXx*]{2,4})[\s-]?([\dXx*]{2,4})[\s-]?(\d{3,4})\b")
RE_ACCOUNT = re.compile(r"[0-9Xx*]{6,20}")
RE_REWARDS = re.compile(r"\b(reward|points|earned|redeemed|cashback\s*earned)\b", re.I)
RE_SALUTATION = re.compile(r"^(mr|mrs|ms|miss|m/s|shri|smt|dr|kumari)\.?$", re.I)

# (field, label regex, kind)
LABELS: list[tuple[str, re.Pattern, str]] = [
    ("card_number", re.compile(r"(credit\s*)?card\s*(no|number)\b\.?", re.I), "card"),
    ("account_number", re.compile(r"\b(account|a/c|acct|ac)\.?\s*(no|number|num)\b\.?|\baccount\s*#", re.I), "account"),
    ("account_holder", re.compile(r"\b(account|customer|card\s*holder|a/c)\s*name\b|^name\b", re.I), "name"),
    ("ifsc", re.compile(r"\b(rtgs\s*/\s*neft\s*)?ifs\s*c?(\s*code)?\b", re.I), "ifsc"),
    ("micr", re.compile(r"\bmicr(\s*code)?\b", re.I), "digits"),
    ("customer_id", re.compile(r"\b(customer|cust)\.?\s*(id|no)\b|\bcif\s*(no|number|id)?\b\.?|\bcrn\b", re.I), "digits"),
    ("branch", re.compile(r"\b(home\s*|account\s*)?branch(\s*name)?\b(?!\s*(code|address|email|phone|e-mail))", re.I), "text"),
    ("account_type", re.compile(r"\baccount\s*(type|description)\b|\bproduct(\s*name)?\b(?!\s*code)", re.I), "text"),
    ("currency", re.compile(r"\bcurrency\b", re.I), "text"),
    ("statement_date", re.compile(r"\bstatement\s*date\b|\bdate\s*of\s*statement\b|\bgeneration\s*date\b|^date\b", re.I), "date"),
    ("payment_due_date", re.compile(r"\b(payment\s*)?due\s*date\b", re.I), "date"),
    ("credit_limit", re.compile(r"\b(total\s*)?credit\s*limit\b", re.I), "amount"),
    ("available_credit", re.compile(r"\bavailable\s*credit\s*(limit)?\b", re.I), "amount"),
    ("cash_limit", re.compile(r"\b(available\s*)?cash\s*(withdrawal\s*)?limit\b", re.I), "amount"),
    ("total_due", re.compile(r"\btotal\s*(amount\s*|amt\.?\s*)?dues?\b|\btotal\s*outstanding\b", re.I), "amount"),
    ("minimum_due", re.compile(r"\bmin(imum)?\.?\s*(amount\s*|amt\.?\s*)?due\b", re.I), "amount"),
    ("opening_balance", re.compile(r"\bopening\s*bal(ance)?\b|\bprevious\s*balance\b|\bbalance\s*as\s*on\b", re.I), "amount"),
    ("closing_balance", re.compile(r"\bclosing\s*bal(ance)?\b|\bclear\s*balance\b|\beffective\s*available\s*balance\b", re.I), "amount"),
]
_LABEL_START = re.compile("|".join(f"(?:{p.pattern})" for _, p, _ in LABELS), re.I)
NAME_STOP = re.compile(r"\b(bank|statement|account|branch|india|limited|ltd|road|nagar|street|floor|"
                       r"customer|summary|details|transaction|page|period|date|balance|address|email|phone|"
                       r"credit|card|welcome|savings?|current|nomination|registered|joint|holders?|"
                       r"city|state|pin|code|mobile|search|advanced|detailed|deposit|ifsc|micr)\b", re.I)


@dataclass
class Field:
    value: Any
    source: str = "label"  # label | pattern | inferred | derived
    page: Optional[int] = None

    def to_dict(self) -> dict:
        v = self.value.isoformat() if isinstance(self.value, date) else self.value
        return {"value": v, "source": self.source, "page": self.page}


@dataclass
class Metadata:
    fields: dict[str, Field] = field(default_factory=dict)
    statement_type: str = "bank_account"

    def get(self, key: str) -> Any:
        f = self.fields.get(key)
        return f.value if f else None

    def set(self, key: str, value: Any, source: str = "label", page: Optional[int] = None,
            overwrite: bool = False) -> None:
        if value in (None, "", []):
            return
        if key in self.fields and not overwrite:
            return
        self.fields[key] = Field(value, source, page)


def _fix_ifsc(text: str) -> Optional[str]:
    m = RE_IFSC.search(text.upper().replace(" ", ""))
    if not m:
        return None
    return f"{m.group(1)}0{m.group(3)}"


def _value_words(line: Line, start: int) -> list[Word]:
    """Words after a label: skip separators, stop at the next label or a wide gap."""
    words = line.words
    out: list[Word] = []
    i = start
    while i < len(words) and words[i].text.strip() in (":", "-", ":-", "—", "|", "–"):
        i += 1
    for j in range(i, len(words)):
        w = words[j]
        if out:
            gap = w.x0 - out[-1].x1
            if gap > 3.2 * max(w.h, 1):
                break
            rest = " ".join(x.text for x in words[j:j + 4])
            if _LABEL_START.match(rest) and not re.match(r"^[\d:]", w.text):
                break
        t = w.text.lstrip(":").strip()
        if not t:
            continue
        out.append(w)
    return out


def _value_below(lines: list[Line], idx: int, label_words: list[Word]) -> list[Word]:
    lx0 = min(w.x0 for w in label_words)
    lx1 = max(w.x1 for w in label_words)
    ly1 = max(w.y1 for w in label_words)
    h = max(w.h for w in label_words)
    for nxt in lines[idx + 1: idx + 3]:
        if nxt.y0 - ly1 > 2.5 * h:
            break
        hits = [w for w in nxt.words if w.xc >= lx0 - 30 and w.xc <= lx1 + 30]
        if hits:
            return hits
    return []


def _match_labels(line: Line) -> list[tuple[str, str, int, int]]:
    """Return (field, kind, first_word_idx, after_label_word_idx) for labels in a line."""
    words = line.words
    joined = ""
    starts = []
    for w in words:
        starts.append(len(joined))
        joined += w.text + " "
    found = []
    taken: set[int] = set()
    for fname, pat, kind in LABELS:
        for m in pat.finditer(joined):
            wi = max(i for i, s in enumerate(starts) if s <= m.start())
            we = max(i for i, s in enumerate(starts) if s < m.end())
            if any(k in taken for k in range(wi, we + 1)):
                continue
            # labels must not be preceded by other text in the same tight phrase (avoid "...Payment Due Date" ambiguity)
            found.append((fname, kind, wi, we + 1))
            taken.update(range(wi, we + 1))
    found.sort(key=lambda t: t[2])
    return found


def _coerce(kind: str, words: list[Word], year_hint: Optional[int] = None) -> Any:
    text = " ".join(w.text for w in words).strip(" :-")
    if not text:
        return None
    if kind == "account":
        cleaned = re.sub(r"\(.*?\)", "", text)
        m = RE_ACCOUNT.search(cleaned.replace(" ", ""))
        return m.group(0) if m and sum(c.isdigit() for c in m.group(0)) >= 4 else None
    if kind == "card":
        m = RE_CARD.search(text)
        return " ".join(m.groups()).upper() if m else None
    if kind == "ifsc":
        return _fix_ifsc(text)
    if kind == "digits":
        m = re.search(r"\d{5,20}", text.replace(" ", ""))
        return m.group(0) if m else None
    if kind == "date":
        return parse_date(text, year_hint=year_hint, allow_compact=False)
    if kind == "amount":
        tokens = [w.text for w in words]
        for t in reversed(tokens):
            v, marker = parse_amount(t)
            if v is not None and ("." in t or "," in t or v < 1e7):
                return v
        return None
    if kind == "name":
        t = re.sub(r"^[:\s-]+", "", text)
        t = re.split(r"\s{2,}|\s-\s|\d", t)[0].strip()
        return t.title() if t and len(t) >= 3 and not NAME_STOP.search(t) else None
    if kind == "text":
        t = text.strip(" :-")
        if not t or t == "-" or len(t) >= 80:
            return None
        # a neighbouring column header is not a value ("Branch | Amt. Paid Rs.")
        if _LABEL_START.search(t) or re.search(r"\b(amt|rs\.?|paid|cheque|dd\s*no|bank\s*name)\b", t, re.I):
            return None
        return t
    return text


def extract_metadata(lines_by_page: dict[int, list[Line]], txn_dates: list[date]) -> Metadata:
    md = Metadata()
    pages = sorted(lines_by_page)
    year_hint = max(txn_dates).year if txn_dates else None
    scan_pages = pages[:2] + ([pages[-1]] if len(pages) > 2 else [])

    for p in scan_pages:
        lines = lines_by_page[p]
        for i, line in enumerate(lines):
            if RE_REWARDS.search(line.text):
                continue  # reward-point tiles reuse "Opening/Closing Balance" labels
            for fname, kind, wi, after in _match_labels(line):
                if fname in md.fields:
                    continue
                label_words = line.words[wi:after]
                vals = _value_words(line, after)
                value = _coerce(kind, vals, year_hint) if vals else None
                if value is None:
                    below = _value_below(lines, i, label_words)
                    value = _coerce(kind, below, year_hint) if below else None
                    # a label sitting above another label row is a tile header; avoid grabbing labels
                    if value is not None and kind == "text" and _LABEL_START.search(str(value)):
                        value = None
                md.set(fname, value, "label", p)

    all_text = {p: "\n".join(ln.text for ln in lines_by_page[p]) for p in pages}
    first_text = all_text[pages[0]] if pages else ""
    meta_text = "\n".join(all_text[p] for p in scan_pages)

    # ---- statement type
    cc_hits = sum(bool(re.search(p, meta_text, re.I)) for p in (
        r"credit\s*card", r"card\s*(no|number)", r"minimum\s*(amount|amt\.?)\s*due", r"payment\s*due\s*date",
        r"credit\s*limit", r"total\s*(amount\s*)?dues?|total\s*amt\.?\s*due"))
    md.statement_type = "credit_card" if cc_hits >= 3 or (cc_hits >= 2 and "card_number" in md.fields) else "bank_account"

    # ---- IFSC fallback: first IFSC-shaped token outside the transaction table
    if "ifsc" not in md.fields:
        for p in scan_pages:
            for ln in lines_by_page[p]:
                v = _fix_ifsc(ln.text) if re.search(r"ifs", ln.text, re.I) else None
                if v:
                    md.set("ifsc", v, "pattern", p)
                    break

    # ---- account number fallbacks: "028501527472(INR) - VIKAS SAINI"
    m = re.search(r"\b(\d{9,18})\s*(?:\(inr\))?\s*-\s*([A-Za-z][A-Za-z .]{3,40}?)(?:\s*-\s*\d|\n|$)", meta_text, re.I | re.M)
    if m:
        md.set("account_number", m.group(1), "pattern")
        md.set("account_holder", m.group(2).strip().title(), "pattern")

    # ---- holder name fallbacks
    if "account_holder" not in md.fields and pages:
        md.set("account_holder", _infer_name(_segments(lines_by_page[pages[0]])), "inferred", pages[0])

    # ---- email: the customer's, not the bank's / branch's
    for em in RE_EMAIL.finditer(first_text):
        addr = em.group(0).lower().rstrip(".")
        domain = addr.split("@", 1)[1]
        local = addr.split("@", 1)[0]
        if re.search(r"bank|sbi\.co|\.gov|indusind|hdfc|icici|axis|kotak|idfc|canara|federal|pnb|rbl|yesbank|"
                     r"unionbank|indianbank|bankofbaroda|amex|citi", domain):
            continue
        if re.search(r"^(reachus|customer\.?care|care|support|info|creditcard|service|cards?)$", local):
            continue
        md.set("email", addr, "pattern", pages[0])
        break

    # ---- period
    period = _find_period(lines_by_page, scan_pages, year_hint)
    if period:
        md.set("period_from", period[0], "label")
        md.set("period_to", period[1], "label")
    elif txn_dates:
        md.set("period_from", min(txn_dates), "derived")
        md.set("period_to", max(txn_dates), "derived")

    # ---- bank
    bank = None
    ifsc = md.get("ifsc")
    if ifsc and ifsc[:4] in IFSC_BANKS:
        bank = IFSC_BANKS[ifsc[:4]]
    if not bank:
        scores: dict[str, int] = {}
        for name, pat in BANK_KEYWORDS:
            n = len(pat.findall(meta_text))
            if n:
                scores[name] = n
        if scores:
            bank = max(scores, key=lambda k: (scores[k], -[b for b, _ in BANK_KEYWORDS].index(k)))
    if not bank and pages:
        # unknown bank: its name is usually the letterhead, e.g. "AURORA BANK"
        for ln in lines_by_page[pages[0]][:8]:
            m = re.search(r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,3}\s+BANK(?:\s+LTD\.?|\s+LIMITED)?)\b", ln.text)
            if m and not NAME_STOP.search(m.group(1).rsplit(" ", 1)[0]):
                bank = m.group(1).title().replace("Ltd", "Ltd.").replace("..", ".")
                md.set("bank_name", bank, "inferred", pages[0])
                break
    if bank:
        md.set("bank_name", bank, "pattern" if not ifsc else "label")

    if md.get("currency") is None:
        md.set("currency", "INR", "derived")
    return md


def _segments(lines: list[Line]) -> list[Line]:
    """Split lines at wide gaps so side-by-side blocks (address | account box) separate."""
    out: list[Line] = []
    for ln in lines:
        cur: list[Word] = []
        for w in ln.words:
            if cur and w.x0 - cur[-1].x1 > 4.0 * max(w.h, 1):
                out.append(Line(words=cur, page=ln.page))
                cur = []
            cur.append(w)
        if cur:
            out.append(Line(words=cur, page=ln.page))
    out.sort(key=lambda s: (round(s.yc / 3), s.x0))
    return out


def _infer_name(lines: list[Line]) -> Optional[str]:
    for i, ln in enumerate(lines[:40]):
        words = [w.text for w in ln.words]
        if not words:
            continue
        if RE_SALUTATION.match(words[0]):
            rest = words[1:]
            if not rest and i + 1 < len(lines):
                rest = [w.text for w in lines[i + 1].words]
            name = " ".join(rest)
            name = re.split(r"\s{2,}|\d|,", name)[0].strip()
            if 3 <= len(name) <= 50 and not NAME_STOP.search(name):
                return f"{words[0].rstrip('.').title()}. {name.title()}"
    for ln in lines[:25]:
        t = ln.text.strip()
        ws = t.split()
        if 2 <= len(ws) <= 5 and all(re.fullmatch(r"[A-Z][A-Z.]*", w) for w in ws) and not NAME_STOP.search(t):
            return t.title()
    return None


def _dates_in(text: str, year_hint: Optional[int]) -> list[date]:
    out = []
    for m in list(RE_TEXT_DATE.finditer(text)) + list(RE_NUMERIC_DATE.finditer(text)):
        d = parse_date(m.group(0), year_hint=year_hint)
        if d:
            out.append((m.start(), d))
    out.sort()
    return [d for _, d in out]


def _find_period(lines_by_page: dict[int, list[Line]], pages: list[int], year_hint) -> Optional[tuple[date, date]]:
    pat = re.compile(r"\b(period|from|statement\s+of\s+account|account\s+statement)\b", re.I)
    for p in pages:
        lines = lines_by_page[p]
        for i, ln in enumerate(lines):
            if not pat.search(ln.text):
                continue
            # only dates *after* the keyword: "Statement Date: X   Period From A To B"
            kw = [m for m in pat.finditer(ln.text)]
            text = ln.text[kw[0].start():] if kw else ln.text
            for m in kw:
                sub = ln.text[m.start():]
                if len(_dates_in(sub, year_hint)) >= 2:
                    text = sub
                    break
            ds = _dates_in(text, year_hint)
            j = i + 1
            while len(ds) < 2 and j < min(len(lines), i + 4):
                text += " " + lines[j].text
                ds = _dates_in(text, year_hint)
                j += 1
            for a, b in zip(ds, ds[1:]):
                if a < b and 6 <= (b - a).days <= 800:
                    return a, b
    return None
