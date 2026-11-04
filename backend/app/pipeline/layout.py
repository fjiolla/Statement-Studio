"""Geometry-driven table reconstruction.

Works on `Word` boxes so it is independent of the PDF's internal text order
(some banks, e.g. IndusInd, emit amounts/dates/narrations as separate streams).

Steps per page:
  1. group words into visual lines
  2. find the transaction header (may span 2–3 physical lines)
  3. derive column zones (header cells, refined by vertical rules if present)
  4. split table lines into rows, using horizontal rules when they cleanly
     separate rows (handles vertically-centred cells), otherwise anchoring a
     new row on every line that starts with a date
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .models import BBox, Column, Line, PageData, RawRow, TableLayout, Word
from .normalize import contains_date, is_money_token, looks_like_date_start

MONEY_ROLES = ("debit", "credit", "amount", "balance")
DATE_ROLES = ("date", "value_date")
TEXT_ROLES = ("description", "ref", "other", "serial", "crdr")

ROLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("serial", re.compile(r"^(s\.?\s*no\.?|sl\.?\s*no\.?|sr\.?\s*no\.?|sno|#|no\.?)$")),
    ("value_date", re.compile(r"\bvalue\b(\s*(date|dt)\b)?|मूल्य\s*दिनांक")),
    ("date", re.compile(r"\b(date|dt)\b|दिनांक|तारीख|तिथि")),
    ("crdr", re.compile(r"^(cr\s*/\s*dr|dr\s*/\s*cr|type|dr\s*cr|cr\s*dr|d\s*/\s*c|c\s*/\s*d|txn\s*type|dr\s*/\s*cr\.?)$")),
    ("debit", re.compile(r"withdraw|debit|^dr\b|\(dr\)|paid\s*out|money\s*out|spent|outflow|नामे|डेबिट|निकासी")),
    ("credit", re.compile(r"deposit|credit|^cr\b|\(cr\)|paid\s*in|money\s*in|receipt|inflow|जमा|क्रेडिट")),
    ("balance", re.compile(r"balance|\bbal\b|शेष|बकाया")),
    ("amount", re.compile(r"amount|\bamt\b|राशि")),
    ("ref", re.compile(r"chq|cheque|\bre[ft]\b|re[ft]\.|instrument|tran\s*id|txn\s*id|transaction\s*id|\butr\b")),
    ("description", re.compile(r"narration|particular|description|details|remark|transaction|narrative|विवरण|ब्योरा")),
]

STOP_PATTERNS = [re.compile(p, re.I) for p in (
    r"^page\s*(no\.?)?\s*[:.]?\s*\d", r"\bpage\s*\d+\s*(of|/)\s*\d+", r"^\*?\s*closing balance includes",
    r"^statement\s+summary", r"^summary\s+of\s+(account|transactions)", r"computer[- ]generated",
    r"^for any queries", r"^important information", r"^reward points", r"^your reward points",
    r"^legends?\b", r"^abbreviations", r"^\(?end of statement", r"^grand total", r"^total\b(?!\s*\d)",
    r"^the limits and effective", r"^registered office", r"^unless the constituent",
    r"^contents of this statement", r"^please (do not|note)", r"^\*+\s*end", r"^transaction total",
    r"^international transactions", r"^opening balance\s+(dr|debits?)",
)]

OPENING_LINE = re.compile(r"brought\s*forward|b\s*/\s*f|opening\s*bal|balance\s*forward|carried\s*forward", re.I)
RE_UNIT_LABEL = re.compile(r"^\(?\s*(rs\.?|inr|₹|amt\.?|no\.?|in\s*rs\.?)\s*\)?$", re.I)
HEADER_VOCAB = re.compile(
    r"^(\(?inr\)?|\(?rs\.?\)?|₹|no\.?|amt\.?|amount|date|dt|value|ref|cheque|chq|number|"
    r"withdrawal|deposit|debit|credit|balance|narration|particulars|details|description|remarks|"
    r"transaction|txn|tran|id|s|sl|sr|cr|dr|/|\(in|rs\.\)|in|out|paid|total|"
    r"दिनांक|तारीख|तिथि|विवरण|ब्योरा|नामे|डेबिट|निकासी|जमा|क्रेडिट|शेष|बकाया|राशि|संदर्भ|चेक|मूल्य|सं\.?|क्र\.?)$", re.I)


# ----------------------------------------------------------------- lines

def group_lines(words: list[Word]) -> list[Line]:
    """Cluster words into visual lines by vertical overlap."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: (w.yc, w.x0))
    bands: list[list] = []  # [y0, y1, words]
    for w in ws:
        h = max(w.h, 0.1)
        placed = False
        for band in reversed(bands[-4:]):
            by0, by1 = band[0], band[1]
            overlap = min(by1, w.y1) - max(by0, w.y0)
            if overlap >= 0.5 * min(h, by1 - by0):
                band[2].append(w)
                n = len(band[2])
                band[0] = by0 + (w.y0 - by0) / n
                band[1] = by1 + (w.y1 - by1) / n
                placed = True
                break
        if not placed:
            bands.append([w.y0, w.y1, [w]])
    lines = [Line(words=sorted(b[2], key=lambda w: w.x0), page=b[2][0].page) for b in bands]
    lines.sort(key=lambda ln: ln.yc)
    return lines


def median_height(lines: list[Line]) -> float:
    hs = [w.h for ln in lines for w in ln.words if w.h > 0]
    return statistics.median(hs) if hs else 10.0


def chunks(line: Line, gap_factor: float = 0.9) -> list[list[Word]]:
    """Split a line into phrases separated by gaps wider than ~one character height."""
    out: list[list[Word]] = []
    cur: list[Word] = []
    for w in line.words:
        if cur:
            gap = w.x0 - cur[-1].x1
            if gap > gap_factor * max(cur[-1].h, w.h, 1.0):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _norm(text: str) -> str:
    t = text.lower().replace("₹", " ")
    t = re.sub(r"\((inr|rs\.?|in rs\.?)\s*\)|\binr\b", " ", t)
    t = re.sub(r"[^a-z0-9/#.\s\u0900-\u097f]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def role_of(text: str) -> str | None:
    t = _norm(text)
    if not t:
        return None
    for role, pat in ROLE_PATTERNS:
        if pat.search(t):
            if role == "value_date" and "date" not in t and "dt" not in t and t != "value":
                continue
            return role
    return None


def _is_data_line(line: Line) -> bool:
    return any(is_money_token(w.text) for w in line.words) or contains_date(line.text)


# ----------------------------------------------------------------- header

@dataclass
class _Cell:
    words: list[Word]

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in sorted(self.words, key=lambda w: (round(w.yc), w.x0)))


def _split_multi_money(cell: _Cell) -> list[_Cell]:
    """'Amount (Rs.) Balance (Rs.)' glued into one phrase -> two cells."""
    words = sorted(cell.words, key=lambda w: w.x0)
    roles = [role_of(w.text) for w in words]
    money = {r for r in roles if r in MONEY_ROLES}
    # Only genuinely distinct money columns glued together: "... Balance" after another
    # money word, or a debit+credit pair. "Withdrawal Amt." / "Value Dt" stay whole.
    if not ("balance" in money and len(money) > 1) and not {"debit", "credit"} <= money:
        return [cell]
    cuts = []
    seen: set[str] = set()
    for i, r in enumerate(roles):
        if r in ("balance", "credit", "debit") and seen and r not in seen and i > 0:
            if not (r in ("credit", "debit") and seen == {"amount"}):
                cuts.append(i)
        if r in MONEY_ROLES:
            seen.add(r)
    if not cuts:
        return [cell]
    parts, start = [], 0
    for c in cuts:
        parts.append(_Cell(words[start:c]))
        start = c
    parts.append(_Cell(words[start:]))
    return [p for p in parts if p.words]


def _line_roles(line: Line) -> list[str]:
    roles = []
    for ch in chunks(line):
        for cell in _split_multi_money(_Cell(ch)):
            r = role_of(cell.text)
            if r:
                roles.append(r)
    return roles


def header_score(line: Line) -> int:
    if _is_data_line(line) or len(line.words) > 30:
        return 0
    roles = set(_line_roles(line))
    has_date = bool(roles & set(DATE_ROLES))
    has_money = bool(roles & set(MONEY_ROLES))
    if not (has_date and has_money):
        return 0
    return len(roles)


def find_header(lines: list[Line], page_rules=None) -> tuple[TableLayout, int, int] | None:
    """Return (layout, first_band_line_idx, last_band_line_idx)."""
    best = None
    for i, ln in enumerate(lines):
        s = header_score(ln)
        # stacked headers ("Trans." over "Date", "Closing" over "Balance") only qualify together
        if i + 1 < len(lines) and not _is_data_line(ln):
            nxt = lines[i + 1]
            close = nxt.y0 - ln.y1 < 0.9 * median_height([ln])
            if close and not _is_data_line(nxt) and len(nxt.words) <= 14:
                roles = set(_line_roles(ln)) | set(_line_roles(nxt))
                # words stacked in one cell ("Paid" over "Out") only mean something read vertically
                roles |= {role_of(c.label) for c in _columns_from_chunks([ln, nxt])} - {None}
                if roles & set(DATE_ROLES) and roles & set(MONEY_ROLES):
                    s = max(s, len(roles))
        if s >= 3 and (best is None or s > best[0]):
            best = (s, i)
            if s >= 5:
                break
    if best is None:
        return None
    k = best[1]
    hline = lines[k]
    hh = median_height([hline])
    lo, hi = k, k
    # extend the band to stacked header fragments ("Value"/"Date", "Withdrawal Amount"/"(INR)")
    for direction in (-1, 1):
        j = k
        for _ in range(2):
            n = j + direction
            if n < 0 or n >= len(lines):
                break
            cand = lines[n]
            gap = (lines[j].y0 - cand.y1) if direction < 0 else (cand.y0 - lines[j].y1)
            if gap > 0.9 * hh or _is_data_line(cand) or len(cand.words) > 12:
                break
            if cand.x1 < hline.x0 - 5 or cand.x0 > hline.x1 + 5:
                break
            vocab = sum(1 for w in cand.words if HEADER_VOCAB.match(w.text.strip(" :")) or role_of(w.text))
            # continuation lines are header words ("Date", "(INR)"), never an opening-balance row
            if vocab < max(1, -(-len(cand.words) // 2)) or OPENING_LINE.search(cand.text):
                break
            j = n
        if direction < 0:
            lo = j
        else:
            hi = j

    band_lines = lines[lo:hi + 1]
    header_words = [x for ln in band_lines for w in ln.words for x in _unglue(w)]
    body = []
    for ln in lines[hi + 1:hi + 81]:
        if _is_stop(ln):
            break
        body.append(ln)
    spans = _column_spans(header_words, body, page_rules, band_lines[0].y0, band_lines[-1].y1)

    columns: list[Column] = []
    if spans:
        groups: list[list[Word]] = [[] for _ in spans]
        for w in header_words:
            idx = min(range(len(spans)), key=lambda i: 0 if spans[i][0] <= w.xc <= spans[i][1]
                      else min(abs(w.xc - spans[i][0]), abs(w.xc - spans[i][1])))
            groups[idx].append(w)
        for (sx0, sx1), ws in zip(spans, groups):
            if ws:
                label = _Cell(ws).text
                columns.append(Column(role=role_of(label) or "other", label=label,
                                      x0=min(sx0, min(w.x0 for w in ws)), x1=max(sx1, max(w.x1 for w in ws))))
            elif columns:
                columns[-1].x1 = sx1  # unlabeled span: data overflow of the left column
            else:
                columns.append(Column(role="other", label="", x0=sx0, x1=sx1))
        # a labelled column whose header holds two roles ("Amount (Rs.) Balance (Rs.)")
        columns = _split_compound(columns, header_words)
        # labels of two different fields inside one span: data had no gutter (tight padding)
        columns = _split_by_label_clusters(columns, header_words)
        # a column labelled only with a unit ("(Rs.)", "(INR)", "Amt.") belongs to its left neighbour:
        # right-aligned numbers sit under the unit, not under "Balance"
        merged_cols: list[Column] = []
        for col in columns:
            if merged_cols and col.role == "other" and RE_UNIT_LABEL.match(col.label.strip()):
                merged_cols[-1].x1 = col.x1
                merged_cols[-1].label = f"{merged_cols[-1].label} {col.label}"
            else:
                merged_cols.append(col)
        columns = merged_cols
    if len({c.role for c in columns}) < 3:
        columns = _columns_from_chunks(band_lines)

    # adjacent cells with the same role are one column split by alignment ("जमा" + "Credit")
    joined: list[Column] = []
    for c in columns:
        if joined and c.role == joined[-1].role and c.role not in ("other", "date"):
            joined[-1].x1 = max(joined[-1].x1, c.x1)
            joined[-1].label = f"{joined[-1].label} {c.label}"
        else:
            joined.append(c)
    columns = joined

    # disambiguate duplicates
    dates = [c for c in columns if c.role == "date"]
    if len(dates) > 1 and not any(c.role == "value_date" for c in columns):
        for c in dates[1:]:
            c.role = "value_date"
    if not any(c.role == "date" for c in columns):
        for c in columns:
            if c.role == "value_date":
                c.role = "date"
                break
    if not any(c.role == "description" for c in columns):
        others = [c for c in columns if c.role == "other"]
        if others:
            max(others, key=lambda c: c.x1 - c.x0).role = "description"
    for role in ("debit", "credit", "balance", "amount", "description", "ref", "crdr"):
        same = [c for c in columns if c.role == role]
        for extra in same[1:]:
            extra.role = "other"

    _set_zones(columns, page_rules, band_lines[0].y0, band_lines[-1].y1)
    _fix_date_column(columns, body)
    layout = TableLayout(columns=columns, header_y0=band_lines[0].y0, header_y1=band_lines[-1].y1,
                         page=hline.page)
    return layout, lo, hi


def _unglue(w: Word) -> list[Word]:
    """OCR sometimes fuses neighbouring header labels ("TransactiorTransaction"):
    split at a lower→Upper boundary inside a long word, apportioning the box."""
    m = re.search(r"(?<=[a-z]{3})(?=[A-Z][a-z]{2})", w.text)
    if w.source != "ocr" or len(w.text) < 10 or not m:
        return [w]
    k = m.start()
    cut = w.x0 + (w.x1 - w.x0) * k / len(w.text)
    return [Word(w.text[:k], w.x0, w.y0, cut - 1, w.y1, w.page, w.conf, w.source),
            Word(w.text[k:], cut + 1, w.y0, w.x1, w.y1, w.page, w.conf, w.source)]


def _fix_date_column(columns: list[Column], body: list[Line]) -> None:
    """Headers can be misread; dates can't hide. If the column labelled as the date holds
    few dates but another column holds them on most rows, that one is the date column."""
    if not body or not columns:
        return
    rows = body[:60]
    def date_share(col: Column) -> float:
        hits = 0
        for ln in rows:
            txt = " ".join(w.text for w in ln.words if col.zx0 <= w.xc < col.zx1)
            hits += looks_like_date_start(txt)
        return hits / len(rows)
    shares = [date_share(c) for c in columns]
    cur = next((i for i, c in enumerate(columns) if c.role == "date"), None)
    best = max(range(len(columns)), key=lambda i: shares[i])
    if shares[best] < 0.3 or (cur is not None and shares[cur] >= 0.5 * shares[best]):
        return
    if cur is not None:
        columns[cur].role = "other"
    columns[best].role = "date"


def _dedupe(xs: list[float], tol: float = 3.0) -> list[float]:
    out: list[float] = []
    for x in sorted(xs):
        if not out or x - out[-1] > tol:
            out.append(x)
    return out


def _column_spans(header_words: list[Word], body: list[Line], rules, hy0: float, hy1: float) -> list[tuple[float, float]]:
    """Column x-spans: from vertical rules when the table is ruled, else from whitespace gutters."""
    if not header_words:
        return []
    hx0 = min(w.x0 for w in header_words)
    hx1 = max(w.x1 for w in header_words)
    width = max(1.0, hx1 - hx0)

    if rules is not None and rules.vlines:
        vx = _dedupe([x for x, y0, y1 in rules.vlines if y0 <= hy1 + 2 and y1 >= hy0 - 2
                      and hx0 - 0.1 * width <= x <= hx1 + 0.1 * width])
        if len(vx) >= 3:
            edges = vx
            if hx0 < edges[0] - 4:
                edges = [hx0 - 1] + edges
            if hx1 > edges[-1] + 4:
                edges = edges + [hx1 + 1]
            spans = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1) if edges[i + 1] - edges[i] > 6]
            spans = [s for s in spans if any(s[0] <= w.xc <= s[1] for w in header_words)]
            if len(spans) >= 3:
                return spans

    rows = []
    for ln in body:
        is_row = any(is_money_token(w.text) for w in ln.words) or contains_date(ln.text)
        if not is_row and (ln.x1 - ln.x0) > 0.6 * width:
            continue  # banner / footer text across the table
        rows.append(ln)
    words = list(header_words) + [w for ln in rows for w in ln.words]
    x0 = min(w.x0 for w in words)
    x1 = max(w.x1 for w in words)
    res = 0.5
    n = int((x1 - x0) / res) + 2
    occ = [0] * n
    for w in words:
        for b in range(int((w.x0 - x0) / res), int((w.x1 - x0) / res) + 1):
            occ[b] += 1
    tol = 0 if len(rows) < 25 else len(rows) // 25
    hs = sorted(w.h for w in words)
    min_gap_bins = int(max(2.5, 0.35 * hs[len(hs) // 2]) / res)

    spans: list[tuple[float, float]] = []
    start = None
    gap = 0
    for i, c in enumerate(occ):
        if c > tol:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap_bins:
                spans.append((x0 + start * res, x0 + (i - gap + 1) * res))
                start, gap = None, 0
    if start is not None:
        spans.append((x0 + start * res, x0 + (n - gap) * res))
    return spans


def _split_compound(columns: list[Column], header_words: list[Word]) -> list[Column]:
    out: list[Column] = []
    for col in columns:
        ws = sorted([w for w in header_words if col.x0 - 1 <= w.xc <= col.x1 + 1], key=lambda w: w.x0)
        parts = _split_multi_money(_Cell(ws)) if ws else []
        same_row = parts and all(abs(p.words[0].yc - parts[0].words[0].yc) < 2 for p in parts)
        if len(parts) > 1 and same_row:
            for i, p in enumerate(parts):
                px0 = col.x0 if i == 0 else p.x0 - 1
                px1 = col.x1 if i == len(parts) - 1 else parts[i + 1].x0 - 1
                out.append(Column(role=role_of(p.text) or "other", label=p.text, x0=px0, x1=px1))
        else:
            out.append(col)
    return out


def _split_by_label_clusters(columns: list[Column], header_words: list[Word]) -> list[Column]:
    out: list[Column] = []
    for col in columns:
        ws = [w for w in header_words if col.x0 - 1 <= w.xc <= col.x1 + 1]
        if len(ws) < 2:
            out.append(col)
            continue
        h = statistics.median(w.h for w in ws)
        # cluster label words by horizontal extent across all header lines
        clusters: list[list[Word]] = []
        for w in sorted(ws, key=lambda w: w.x0):
            if clusters and w.x0 - max(x.x1 for x in clusters[-1]) < 0.9 * h:
                clusters[-1].append(w)
            else:
                clusters.append([w])
        roles = [role_of(_Cell(c).text) for c in clusters]
        named = [(c, r) for c, r in zip(clusters, roles) if r]
        if len(named) < 2 or len({r for _, r in named}) < 2:
            out.append(col)
            continue
        # attach unnamed fragments ("(INR)") to the nearest named cluster on their left
        merged: list[tuple[list[Word], str]] = []
        for c, r in zip(clusters, roles):
            if r or not merged:
                merged.append((list(c), r or "other"))
            else:
                merged[-1][0].extend(c)
        for i, (c, r) in enumerate(merged):
            cx0 = col.x0 if i == 0 else (max(w.x1 for w in merged[i - 1][0]) + min(w.x0 for w in c)) / 2
            cx1 = col.x1 if i == len(merged) - 1 else (max(w.x1 for w in c) + min(w.x0 for w in merged[i + 1][0])) / 2
            out.append(Column(role=r, label=_Cell(c).text, x0=cx0, x1=cx1))
    return out


def _columns_from_chunks(band_lines: list[Line]) -> list[Column]:
    cells: list[_Cell] = []
    for ln in band_lines:
        for ch in chunks(ln):
            cells.extend(_split_multi_money(_Cell(ch)))
    merged: list[_Cell] = []
    for c in sorted(cells, key=lambda c: c.x0):
        target = None
        for m in merged:
            ov = min(m.x1, c.x1) - max(m.x0, c.x0)
            same_line = any(abs(w.yc - cw.yc) < 2 for w in m.words for cw in c.words)
            if ov > 0.25 * min(m.x1 - m.x0, c.x1 - c.x0) and not same_line:
                target = m
                break
        if target:
            target.words.extend(c.words)
        else:
            merged.append(_Cell(list(c.words)))
    merged.sort(key=lambda c: c.x0)
    return [Column(role=role_of(c.text) or "other", label=c.text, x0=c.x0, x1=c.x1) for c in merged]


def _set_zones(columns: list[Column], rules, hy0: float, hy1: float) -> None:
    vxs = []
    if rules is not None:
        vxs = sorted(x for x, y0, y1 in rules.vlines if y0 <= hy1 + 2 and y1 >= hy0 - 2)
    for i, col in enumerate(columns):
        if i == 0:
            col.zx0 = float("-inf")
        if i + 1 < len(columns):
            nxt = columns[i + 1]
            lo, hi = col.x1, nxt.x0
            between = [x for x in vxs if lo - 3 <= x <= hi + 3]
            if between:
                b = min(between, key=lambda x: abs(x - (lo + hi) / 2))
            else:
                b = (lo + hi) / 2
            col.zx1 = b
            nxt.zx0 = b
        else:
            col.zx1 = float("inf")


def column_for(word: Word, columns: list[Column]) -> Column:
    x = word.xc
    for c in columns:
        if c.zx0 <= x < c.zx1:
            return c
    return columns[-1]


# ----------------------------------------------------------------- rows

@dataclass
class _LineCells:
    line: Line
    cells: dict[str, list[Word]]

    def text(self, role: str) -> str:
        return " ".join(w.text for w in self.cells.get(role, []))

    def has_money(self) -> bool:
        return any(is_money_token(w.text) or _ocr_money(w) for r in MONEY_ROLES for w in self.cells.get(r, []))


def _ocr_money(w: Word) -> bool:
    return w.source == "ocr" and bool(re.match(r"^[\d,.\s]+$", w.text)) and "." in w.text


RE_MONEY_CELL_WORD = re.compile(r"^[-−–(]?(₹|rs\.?|inr)?[\d,.\-()]*\d[\d,.\-()]*(cr|dr)?\.?\)?$|^\(?(cr|dr|c|d)\)?\.?$|^\(?[αaеegc][rг]\)?\.?$|^[-−–(]?(₹|rs\.?|inr)?\.?$|^[-—]$", re.I)


def split_cells(line: Line, layout: TableLayout) -> _LineCells:
    cells: dict[str, list[Word]] = {}
    cols = layout.columns
    for w in line.words:
        c = column_for(w, cols)
        if c.role in MONEY_ROLES and not RE_MONEY_CELL_WORD.match(w.text):
            # narration overflowing into a money column belongs to the text column on its left
            i = cols.index(c)
            left = next((x for x in reversed(cols[:i]) if x.role in ("description", "ref", "other")), None)
            if left is not None:
                c = left
        elif c.role in MONEY_ROLES and re.fullmatch(r"\d{8,}", w.text):
            # long bare digit runs are references, not money
            i = cols.index(c)
            left = next((x for x in reversed(cols[:i]) if x.role in ("description", "ref", "other")), None)
            if left is not None:
                c = left
        cells.setdefault(c.role, []).append(w)
    return _LineCells(line, cells)


def _is_anchor(lc: _LineCells, layout: TableLayout) -> bool:
    date_role = "date" if "date" in layout.roles() else "value_date"
    t = lc.text(date_role)
    if looks_like_date_start(t):
        return True
    if date_role != "value_date" and "value_date" in layout.roles() and looks_like_date_start(lc.text("value_date")):
        return True
    # OCR may garble a date beyond recognition; a full date-ish token in the date zone still counts.
    compact = re.sub(r"[^0-9A-Za-z]", "", t)
    return lc.line.words[0].source == "ocr" and bool(re.match(r"^[0-9OoQDlI]{6,8}[0-9]{0,2}$", compact)) and len(compact) >= 8


def _is_stop(line: Line) -> bool:
    t = line.text.strip()
    return any(p.search(t) for p in STOP_PATTERNS)


def _footerish(lc: _LineCells, layout: TableLayout) -> bool:
    """A non-anchor line spreading across money columns without numbers = footer/banner."""
    roles_hit = [r for r in lc.cells if lc.cells[r]]
    money_hit = [r for r in roles_hit if r in MONEY_ROLES]
    if not money_hit:
        return False
    if lc.has_money():
        return False
    return len(roles_hit) >= 3


RE_DATE_FRAGMENT = re.compile(r"^(\d{1,4}|[A-Za-z]{3}\.?|\d{1,2}[\s\-/][A-Za-z]{3}|[\-/.,])$")


def _foreign_date_text(lc: _LineCells, layout: TableLayout) -> bool:
    """Continuation lines may carry a wrapped year ('2018') in the date column, never prose."""
    for role in DATE_ROLES:
        for w in lc.cells.get(role, []):
            if not RE_DATE_FRAGMENT.match(w.text.strip()):
                return True
    return False


def _bands(rules, y0: float, y1: float, x0: float, x1: float) -> list[float]:
    if rules is None:
        return []
    width = max(1.0, x1 - x0)
    ys = sorted(y for y, a, b in rules.hlines if y0 - 2 <= y <= y1 + 2 and (min(b, x1) - max(a, x0)) > 0.4 * width)
    dedup: list[float] = []
    for y in ys:
        if not dedup or y - dedup[-1] > 3:
            dedup.append(y)
    return dedup


def build_rows(lines: list[Line], layout: TableLayout, rules, start_idx: int,
               prev_row: RawRow | None = None) -> tuple[list[RawRow], RawRow | None]:
    """Turn the lines after the header into RawRows. Returns (rows, continuation_target)."""
    mh = median_height(lines[start_idx:]) if start_idx < len(lines) else 10.0
    table_x0 = min(c.x0 for c in layout.columns)
    table_x1 = max(c.x1 for c in layout.columns)

    body: list[_LineCells] = []
    for ln in lines[start_idx:]:
        # OCR boxes carry padding, so compare line centres rather than edges
        if ln.yc < layout.header_y1 and ln.page == layout.page:
            continue
        lc = split_cells(ln, layout)
        if not _is_anchor(lc, layout) and _is_stop(ln):
            break
        body.append(lc)
    if not body:
        return [], prev_row

    anchors = [i for i, lc in enumerate(body) if _is_anchor(lc, layout)]
    # balance-based anchors: a line holding a balance while the open row already has one
    if "balance" in layout.roles():
        anchors_set = set(anchors)
        open_has_bal = False
        for i, lc in enumerate(body):
            has_bal = any(is_money_token(w.text) or _ocr_money(w) for w in lc.cells.get("balance", []))
            if i in anchors_set:
                open_has_bal = has_bal
            elif has_bal and open_has_bal and lc.has_money():
                anchors_set.add(i)
            elif has_bal:
                open_has_bal = True
        anchors = sorted(anchors_set)

    groups: list[list[_LineCells]] = []
    leading: list[_LineCells] = []

    interior = _bands(rules, layout.header_y1 + 2, body[-1].line.y1 - 1, table_x0, table_x1)
    # the header's bottom edge and the end of the body are implicit row boundaries
    hy = sorted(set([min(layout.header_y1, body[0].line.y0 - 0.5)] + interior + [body[-1].line.y1 + 1]))
    band_mode = False
    if len(anchors) >= 2 and len(interior) >= 1:
        def band_of(y: float) -> int:
            for bi in range(len(hy) - 1):
                if hy[bi] <= y < hy[bi + 1]:
                    return bi
            return -1
        anchor_bands = [band_of(body[i].line.yc) for i in anchors]
        valid = [b for b in anchor_bands if b >= 0]
        if len(valid) >= 0.7 * len(anchors) and len(set(valid)) >= 0.95 * len(valid):
            band_mode = True
            by_band: dict[int, list[_LineCells]] = {}
            for lc in body:
                by_band.setdefault(band_of(lc.line.yc), []).append(lc)
            anchor_band_set = set(valid)
            for b in sorted(k for k in by_band if k >= 0):
                if b in anchor_band_set:
                    band = by_band[b]
                    ai = next(i for i, lc in enumerate(band) if _is_anchor(lc, layout) or lc in [body[j] for j in anchors])
                    # a dateless line with its own amount above the date (e.g. "Opening Balance") is its own row
                    head = band[:ai]
                    if head and any(lc.has_money() or OPENING_LINE.search(lc.line.text) for lc in head):
                        groups.append(head)
                        band = band[ai:]
                    groups.append(band)
                elif groups:
                    # band without a date: continuation of the previous row unless it is a footer
                    extra = [lc for lc in by_band[b] if not _footerish(lc, layout)]
                    if extra and not any(lc.has_money() for lc in extra):
                        groups[-1].extend(extra)
                else:
                    leading.extend(by_band[b])

    nearest_mode = False
    if not band_mode and anchors:
        # Vertically-centred rows without rules: description lines sit *above* the
        # date as well as below it. Detect via text-only lines just before the first
        # anchor plus multi-line rows elsewhere, then attach each line to the closest date.
        first = anchors[0]
        pre = [lc for lc in body[:first] if set(lc.cells) <= {"description", "ref", "other"}]
        tight = pre and body[first].line.y0 - pre[-1].line.y1 < 0.8 * mh
        multi = any(b - a > 1 for a, b in zip(anchors, anchors[1:]))
        if tight and multi and len(pre) == first:
            nearest_mode = True
            anchor_lcs = [body[i] for i in anchors]
            groups = [[lc] for lc in anchor_lcs]
            last_anchor_y = anchor_lcs[-1].line.yc
            for i, lc in enumerate(body):
                if i in anchors:
                    continue
                if lc.line.yc > last_anchor_y and (lc.line.y0 - body[i - 1].line.y1 > 2.6 * mh
                                                   or _footerish(lc, layout)):
                    break
                k = min(range(len(anchor_lcs)), key=lambda j: abs(anchor_lcs[j].line.yc - lc.line.yc))
                groups[k].append(lc)
            for g in groups:
                g.sort(key=lambda lc: lc.line.yc)

    if not band_mode and not nearest_mode:
        current: list[_LineCells] | None = None
        anchor_set = set(anchors)
        for i, lc in enumerate(body):
            if i in anchor_set:
                current = [lc]
                groups.append(current)
                continue
            if current is None:
                leading.append(lc)
                continue
            gap = lc.line.y0 - current[-1].line.y1
            if gap > 2.6 * mh or _footerish(lc, layout) or _foreign_date_text(lc, layout):
                break
            current.append(lc)

    rows: list[RawRow] = []
    for g in groups:
        rows.append(_to_raw(g, table_x0, table_x1))

    # Text at the top of a continuation page that belongs to the last row of the previous page.
    if prev_row is not None and leading and not band_mode and not nearest_mode:
        # all-caps short names are card-holder / add-on sub-headings, not wrapped narration
        tail = [lc for lc in leading if set(lc.cells) <= {"description", "ref", "other"}
                and not re.fullmatch(r"(?:[A-Z][A-Z.']+\s?){2,5}", lc.line.text.strip())]
        if tail and len(tail) == len(leading) and len(tail) <= 3:
            for lc in tail:
                for role, ws in lc.cells.items():
                    prev_row.cells.setdefault(role, []).append(" ".join(w.text for w in ws))
    return rows, (rows[-1] if rows else prev_row)


def _to_raw(group: list[_LineCells], tx0: float, tx1: float) -> RawRow:
    cells: dict[str, list[str]] = {}
    confs: list[float] = []
    role_conf: dict[str, float] = {}
    for lc in group:
        for role, ws in lc.cells.items():
            cells.setdefault(role, []).append(" ".join(w.text for w in ws))
            if role in MONEY_ROLES or role in DATE_ROLES:
                confs.extend(w.conf for w in ws)
                role_conf[role] = min([role_conf.get(role, 1.0)] + [w.conf for w in ws])
    page = group[0].line.page
    y0 = min(lc.line.y0 for lc in group)
    y1 = max(lc.line.y1 for lc in group)
    x0 = min(tx0, min(lc.line.x0 for lc in group))
    x1 = max(tx1, max(lc.line.x1 for lc in group))
    return RawRow(page=page, cells=cells, bboxes=[BBox(page, x0 - 2, y0 - 1.5, x1 + 2, y1 + 1.5)],
                  min_conf=min(confs) if confs else 1.0, role_conf=role_conf)


def page_lines(page: PageData) -> list[Line]:
    return group_lines(page.words)
