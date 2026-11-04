"""Per-page type detection and text-layer extraction.

Detection runs per page (statements can mix digital and scanned pages) and
looks at text *quality*, not just presence: a page whose text layer is mostly
unmapped glyphs is treated as scanned and sent to OCR.
"""
from __future__ import annotations

import unicodedata

import pymupdf

from .models import PageData, PageKind, Rules, Word

MIN_TEXT_CHARS = 40


def _garbage_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    bad = 0
    for c in chars:
        cat = unicodedata.category(c)
        if c == "�" or cat in ("Co", "Cn", "Cc", "Cs"):
            bad += 1
    return bad / len(chars)


def _image_coverage(page: pymupdf.Page) -> float:
    area = page.rect.width * page.rect.height
    if area <= 0:
        return 0.0
    covered = 0.0
    try:
        infos = page.get_image_info()
    except Exception:  # noqa: BLE001
        return 0.0
    for info in infos:
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if not r.is_empty:
            covered += r.width * r.height
    return min(1.0, covered / area)


def classify_page(page: pymupdf.Page) -> tuple[PageKind, int, float]:
    text = page.get_text("text")
    chars = sum(1 for c in text if not c.isspace())
    coverage = _image_coverage(page)
    garbage = _garbage_ratio(text)

    if chars >= MIN_TEXT_CHARS and garbage < 0.15:
        # Real text. A full-page image under a text layer is a scanned page
        # with an embedded OCR layer — still usable, but flagged as hybrid.
        kind: PageKind = "hybrid" if coverage > 0.6 else "text"
    elif coverage > 0.15 or garbage >= 0.15:
        kind = "scanned"
    elif chars == 0 and not page.get_drawings():
        kind = "empty"
    else:
        # Very little text and no image: could be vector-outlined glyphs; OCR it.
        kind = "scanned"
    return kind, chars, coverage


def _transform(page: pymupdf.Page):
    m = page.rotation_matrix
    rotated = page.rotation % 360 != 0

    def tx(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        if not rotated:
            return x0, y0, x1, y1
        r = pymupdf.Rect(x0, y0, x1, y1) * m
        r.normalize()
        return r.x0, r.y0, r.x1, r.y1

    return tx


def _near(c1, c2, tol: float = 0.08) -> bool:
    if c1 is None or c2 is None or len(c1) != len(c2):
        return False
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def hidden_text_boxes(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Text the reader cannot see: painted over by a later opaque shape, or drawn
    in the same colour as the shape behind it (white-on-white).

    Invisible render-mode text (the OCR layer of a searchable scan) is *kept*:
    it is meant to be extracted.
    """
    try:
        traces = page.get_texttrace()
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return []
    fills = []
    for d in drawings[:6000]:
        fill = d.get("fill")
        r = d.get("rect")
        if fill is None or r is None or (d.get("fill_opacity") or 1.0) < 0.9:
            continue
        if r.width * r.height < 20:
            continue
        fills.append((r, d.get("seqno", 0), tuple(fill)))
    if not fills:
        fills = []
    hidden: list[pymupdf.Rect] = []
    white = (1.0, 1.0, 1.0)
    for s in traces:
        if s.get("type") == 3 or (s.get("opacity") or 1.0) == 0:
            continue  # invisible OCR layer: legitimate
        bb = pymupdf.Rect(s["bbox"])
        if bb.is_empty:
            continue
        inner = pymupdf.Rect(bb.x0 + 0.5, bb.y0 + 0.5, bb.x1 - 0.5, bb.y1 - 0.5)
        seq = s.get("seqno", 0)
        color = tuple(s.get("color") or (0, 0, 0))
        covered = any(sq > seq and r.contains(inner) and not _near(fc, color) for r, sq, fc in fills)
        if covered:
            hidden.append(bb)
            continue
        behind = [fc for r, sq, fc in fills if sq < seq and r.contains(inner)]
        bg = behind[-1] if behind else white
        if len(color) == 3 and _near(color, bg, 0.04):
            hidden.append(bb)
    return hidden


def text_words(page: pymupdf.Page, index: int) -> tuple[list[Word], int]:
    """Words of the text layer in displayed coordinates, minus hidden text.

    Returns (words, hidden_word_count).
    """
    tx = _transform(page)
    hidden = hidden_text_boxes(page)
    words: list[Word] = []
    n_hidden = 0
    for x0, y0, x1, y1, text, *_ in page.get_text("words", sort=False):
        text = text.strip()
        if not text:
            continue
        if hidden:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if any(h.x0 - 0.5 <= cx <= h.x1 + 0.5 and h.y0 - 0.5 <= cy <= h.y1 + 0.5 for h in hidden):
                n_hidden += 1
                continue
        a, b, c, d = tx(x0, y0, x1, y1)
        words.append(Word(text=text, x0=a, y0=b, x1=c, y1=d, page=index, conf=1.0, source="text"))
    return words, n_hidden


def vector_rules(page: pymupdf.Page) -> Rules:
    """Horizontal/vertical ruling lines from the page's vector drawings."""
    tx = _transform(page)
    rules = Rules()
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return rules
    for d in drawings[:4000]:
        for item in d.get("items", []):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                x0, y0, x1, y1 = tx(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))
                if abs(y1 - y0) < 1.5 and (x1 - x0) > 15:
                    rules.hlines.append(((y0 + y1) / 2, x0, x1))
                elif abs(x1 - x0) < 1.5 and (y1 - y0) > 8:
                    rules.vlines.append(((x0 + x1) / 2, y0, y1))
            elif kind == "re":
                r = item[1]
                x0, y0, x1, y1 = tx(r.x0, r.y0, r.x1, r.y1)
                w, h = x1 - x0, y1 - y0
                if h < 2.5 and w > 15:
                    rules.hlines.append(((y0 + y1) / 2, x0, x1))
                elif w < 2.5 and h > 8:
                    rules.vlines.append(((x0 + x1) / 2, y0, y1))
                elif w > 15 and h > 4 and d.get("color") is not None:
                    # stroked cell rectangles: their edges are rules
                    rules.hlines.extend([(y0, x0, x1), (y1, x0, x1)])
                    rules.vlines.extend([(x0, y0, y1), (x1, y0, y1)])
    return rules


def text_page(page: pymupdf.Page, index: int, kind: PageKind, chars: int, coverage: float) -> PageData:
    words, n_hidden = text_words(page, index)
    return PageData(
        index=index,
        width=page.rect.width,
        height=page.rect.height,
        kind=kind,
        words=words,
        rules=vector_rules(page),
        char_count=chars,
        image_coverage=round(coverage, 3),
        hidden_words=n_hidden,
    )
