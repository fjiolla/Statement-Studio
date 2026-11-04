"""Parsing of dates and amounts as they appear in Indian bank statements."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

RE_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(\d{4}|\d{2})(?!\d)")
RE_ISO_DATE = re.compile(r"(?<!\d)(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)")
RE_TEXT_DATE = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.,']*({_MON})[\s\-/.,']*(\d{{4}}|\d{{2}})(?!\d)", re.I)
RE_TEXT_DATE_US = re.compile(rf"\b({_MON})[\s\-.]*(\d{{1,2}}),?[\s\-.]+(\d{{4}})(?!\d)", re.I)
RE_DAY_MON = re.compile(rf"^(\d{{1,2}})[\s\-/.]*({_MON})\b\.?$", re.I)
RE_COMPACT_DATE = re.compile(r"^(\d{2})(\d{2})(\d{4})$")

RE_DATE_START = re.compile(
    rf"^\s*(?:\d{{1,2}}\s?[/\-.]\s?\d{{1,2}}\s?[/\-.]\s?\d{{2,4}}|\d{{4}}[/\-.]\d{{1,2}}[/\-.]\d{{1,2}}|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?[\s\-/.,']*{_MON}\b|{_MON}[\s\-.]*\d{{1,2}},?\s+\d{{4}})",
    re.I,
)


def _year(y: str) -> int:
    v = int(y)
    if len(y) == 2:
        v += 2000 if v < 70 else 1900
    return v


def _month(name: str) -> int:
    key = name.lower().rstrip(".")
    return MONTHS.get(key) or MONTHS[key[:3]]


def _safe(y: int, m: int, d: int) -> Optional[date]:
    try:
        if 1900 <= y <= 2100:
            return date(y, m, d)
    except ValueError:
        return None
    return None


def infer_month_first(samples: list[str]) -> bool:
    """Numeric dates are day-first (Indian) unless the column proves otherwise:
    a first component > 12 settles day-first; a second component > 12 settles month-first."""
    day_first = month_first = 0
    for s in samples:
        m = RE_NUMERIC_DATE.search(s or "")
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            day_first += 1
        elif b > 12 >= a:
            month_first += 1
    return month_first > 0 and day_first == 0


def parse_date(text: str, year_hint: Optional[int] = None, allow_compact: bool = False,
               month_first: bool = False) -> Optional[date]:
    """Parse the first date in `text`. Day-first unless the document is month-first."""
    if not text:
        return None
    t = text.strip()
    m = RE_TEXT_DATE.search(t)
    if m:
        return _safe(_year(m.group(3)), _month(m.group(2)), int(m.group(1)))
    m = RE_ISO_DATE.search(t)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = RE_NUMERIC_DATE.search(t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        if month_first:
            d, mo = mo, d
        got = _safe(y, mo, d)
        if got is None and mo > 12 >= d:  # tolerate the odd MM/DD export
            got = _safe(y, d, mo)
        return got
    m = RE_TEXT_DATE_US.search(t)
    if m:
        return _safe(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
    m = RE_DAY_MON.match(t)
    if m and year_hint:
        return _safe(year_hint, _month(m.group(2)), int(m.group(1)))
    if allow_compact:
        m = RE_COMPACT_DATE.match(re.sub(r"\s", "", t))
        if m:
            return _safe(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def looks_like_date_start(text: str) -> bool:
    return bool(RE_DATE_START.match(text or ""))


def contains_date(text: str) -> bool:
    return bool(RE_NUMERIC_DATE.search(text) or RE_TEXT_DATE.search(text) or RE_ISO_DATE.search(text))


# ------------------------------------------------------------------ amounts

_OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1",
                                "i": "1", "!": "1", "S": "5", "§": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})

RE_AMOUNT = re.compile(
    r"(?P<neg>[-−–(])?\s*(?:₹|rs\.?|inr)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d+)"
    r"\s*(?P<close>\))?\s*(?P<suf>\(?\s*(?:cr|dr|c|d)\b\.?\s*\)?|-(?!\s*(?:₹|rs\.?|inr)?\s*\d))?",
    re.I,
)
RE_HAS_DIGIT = re.compile(r"\d")
RE_MONEYISH = re.compile(r"^[-−–(]?\s*(?:₹|rs\.?|inr)?\s*\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})\s*\)?\s*(?:\(?(?:cr|dr)\)?\.?)?$|^\d+\.\d{2}$", re.I)


def is_money_token(text: str) -> bool:
    return bool(RE_MONEYISH.match((text or "").strip()))


def _fix_ocr_number(s: str) -> str:
    # Letter→digit repair only inside tokens that are already mostly digits ("2,O00.5O"),
    # never across the cell (that would turn "INR" into "1NR").
    def fix_token(tok: str) -> str:
        digits = sum(c.isdigit() for c in tok)
        alnum = sum(c.isalnum() for c in tok)
        return tok.translate(_OCR_DIGIT_FIX) if digits and digits >= 0.6 * alnum else tok
    # strip currency prefixes first: OCR glues them on ("Rs.90,959.05") and "s" would become "5"
    s = re.sub(r"(?i)(?<![a-z])(rs\.?|inr|₹)\s*(?=[\dOoSlI§])", " ", s)
    core = " ".join(fix_token(t) for t in s.split(" ") if t)
    # "1,34.801.21" / "5.949.54" -> separators misread: all but the last are grouping
    # applied to every number in the cell, so "-INR 1.938.70" and "-16.857.38" are repaired too
    core = re.sub(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{2,3})+)[.,](\d{2})(?![\d.,])",
                  lambda m: re.sub(r"[.,]", "", m.group(1)) + "." + m.group(2), core)
    # "400 00" -> "400.00" (decimal point lost)
    core = re.sub(r"^(\d[\d,]*)\s(\d{2})(?=\s*(?:cr|dr)?$)", r"\1.\2", core.strip(), flags=re.I)
    # "2,000,00" -> "2,000.00" (decimal comma misread)
    core = re.sub(r",(\d{2})(?=\s*(?:cr|dr|\(|$))", r".\1", core, flags=re.I) if "." not in core else core
    return core


def _normalise_suffix(s: str) -> str:
    # OCR sometimes renders "Cr" as "αr", "Gr", "Cr." etc.
    return re.sub(r"(?<=[\d\s])[αaGgCcеe][rR]\.?\b", "Cr", s)


def parse_amount(text: str, ocr: bool = False, strict: bool = False) -> tuple[Optional[float], Optional[str]]:
    """Return (absolute value, marker) where marker is 'cr', 'dr' or None.

    Handles Indian grouping (1,20,749.89), ₹/Rs prefixes, parentheses and
    leading/trailing minus for negatives, and Cr/Dr suffixes in any casing.
    """
    if not text:
        return None, None
    t = text.strip().replace("−", "-").replace("–", "-")
    if t in {"-", "--", "—", "nil", "NIL", "Nil"}:
        return None, None
    if ocr:
        t = _normalise_suffix(_fix_ocr_number(t))
    t = re.sub(r"(?<=\d)\s+(?=[,.]\d)|(?<=[,.])\s+(?=\d)", "", t)

    best = None
    for m in RE_AMOUNT.finditer(t):
        num = m.group("num")
        if not num:
            continue
        has_dec = "." in num
        score = (2 if has_dec else 0) + (1 if "," in num else 0)
        if best is None or score > best[0]:
            best = (score, m)
    if best is None:
        return None, None
    m = best[1]
    num = m.group("num")
    # bare integers without separators are usually reference numbers, not money
    if "." not in num and "," not in num and (len(num) > 7 or strict):
        return None, None
    value = float(num.replace(",", ""))
    marker = None
    suf = (m.group("suf") or "").lower().strip("(). ")
    if suf in ("cr", "c"):
        marker = "cr"
    elif suf in ("dr", "d"):
        marker = "dr"
    elif m.group("neg") or suf == "-":
        marker = "neg"
    if marker is None and re.search(r"\bcr\b", t, re.I):
        marker = "cr"
    elif marker is None and re.search(r"\bdr\b", t, re.I):
        marker = "dr"
    return value, marker


def signed_balance(text: str, ocr: bool = False) -> Optional[float]:
    v, marker = parse_amount(text, ocr=ocr)
    if v is None:
        return None
    return -v if marker in ("dr", "neg") else v
