"""End-to-end extraction: PDF bytes -> structured statement (pre-classification)."""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .extract import fallback_parse, rows_to_txns
from .ingest import IngestError, open_pdf
from .layout import build_rows, find_header, page_lines
from .metadata import Metadata, extract_metadata
from .models import Line, PageData, RawRow, TableLayout, Txn
from .ocr import get_engine, ocr_page
from .pages import classify_page, text_page
from .reconcile import ReconResult, reconcile

ProgressFn = Callable[[dict], None]


class NoTransactionsFound(IngestError):
    code = "no_transactions"


@dataclass
class ExtractionOutput:
    sha256: str
    page_count: int
    pages: list[PageData]
    metadata: Metadata
    txns: list[Txn]
    recon: ReconResult
    document_type: str  # text | scanned | mixed
    was_encrypted: bool
    was_repaired: bool
    clean_pdf: bytes
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    columns: list[dict] = field(default_factory=list)
    parser: str = "layout"


def _same_table(a: TableLayout, b: TableLayout) -> bool:
    """Same header repeated: the table spans the same horizontal extent."""
    ax0, ax1 = min(c.x0 for c in a.columns), max(c.x1 for c in a.columns)
    bx0, bx1 = min(c.x0 for c in b.columns), max(c.x1 for c in b.columns)
    return abs(ax0 - bx0) < 12 and abs(ax1 - bx1) < 24


def _noop(_: dict) -> None:
    pass


def extract_statement(data: bytes, password: Optional[str] = None, ocr_engine: str = "rapidocr",
                      progress: ProgressFn = _noop) -> ExtractionOutput:
    t0 = time.perf_counter()
    progress({"stage": "open", "message": "Opening PDF"})
    opened = open_pdf(data, password)
    doc = opened.doc
    n = doc.page_count
    timings: dict[str, float] = {"open": round(time.perf_counter() - t0, 3)}

    # ---- 1. per-page detection + words
    engine = None
    pages: list[PageData] = []
    t1 = time.perf_counter()
    for i, page in enumerate(doc):
        kind, chars, cov = classify_page(page)
        progress({"stage": "detect", "page": i, "total": n, "kind": kind,
                  "message": f"Page {i + 1}: {'text layer' if kind in ('text', 'hybrid') else 'scanned image'}"})
        if kind in ("text", "hybrid"):
            pages.append(text_page(page, i, kind, chars, cov))
        elif kind == "empty":
            pages.append(PageData(index=i, width=page.rect.width, height=page.rect.height, kind="empty",
                                  words=[], rules=text_page(page, i, kind, 0, 0).rules))
        else:
            engine = engine or get_engine(ocr_engine)
            progress({"stage": "ocr", "page": i, "total": n, "message": f"Reading page {i + 1} of {n} with OCR"})
            pd = ocr_page(page, i, engine, chars=chars, coverage=cov)
            pages.append(pd)
            progress({"stage": "ocr_done", "page": i, "total": n, "confidence": pd.ocr_confidence,
                      "seconds": pd.ocr_seconds, "message": f"Page {i + 1} read ({pd.ocr_seconds}s)"})
    timings["read_pages"] = round(time.perf_counter() - t1, 3)

    kinds = {p.kind for p in pages if p.kind != "empty"}
    doc_type = "scanned" if kinds == {"scanned"} else ("text" if "scanned" not in kinds else "mixed")

    # ---- 2. tables
    progress({"stage": "parse", "message": "Rebuilding transaction tables"})
    t2 = time.perf_counter()
    lines_by_page: dict[int, list[Line]] = {p.index: page_lines(p) for p in pages}
    rows: list[RawRow] = []
    layout: Optional[TableLayout] = None
    prev_row: Optional[RawRow] = None
    excluded: dict[int, list[tuple[float, float]]] = {}
    for p in pages:
        lines = lines_by_page[p.index]
        if not lines:
            continue
        found = find_header(lines, p.rules)
        if found:
            new_layout, lo, hi = found
            # A repeated header on a sparse page (few rows) gives weaker column evidence;
            # if it is the same table as before but resolves fewer fields, keep the earlier geometry.
            if layout is not None and new_layout.roles() < layout.roles() and _same_table(layout, new_layout):
                kept = copy.deepcopy(layout)
                kept.page, kept.header_y0, kept.header_y1 = p.index, new_layout.header_y0, new_layout.header_y1
                new_layout = kept
            layout = new_layout
            page_layout, start = layout, hi + 1
            excluded.setdefault(p.index, []).append((layout.header_y0 - 1, layout.header_y1 + 1))
        elif layout is not None:
            page_layout = copy.deepcopy(layout)
            page_layout.page = p.index
            page_layout.header_y0 = page_layout.header_y1 = -1.0
            start = 0
        else:
            continue
        page_rows, prev_row = build_rows(lines, page_layout, p.rules, start, prev_row)
        for r in page_rows:
            r.roles = page_layout.roles()
            for b in r.bboxes:
                excluded.setdefault(b.page, []).append((b.y0, b.y1))
        rows.extend(page_rows)

    # Metadata from everything that is not part of the transaction table.
    meta_lines = {
        pi: [ln for ln in lines if not any(y0 <= ln.yc <= y1 for y0, y1 in excluded.get(pi, []))]
        for pi, lines in lines_by_page.items()
    }
    md = extract_metadata(meta_lines, [])
    year_hint = None
    for key in ("period_to", "statement_date", "period_from"):
        if md.get(key):
            year_hint = md.get(key).year
            break

    ocr_pages = {p.index for p in pages if p.kind == "scanned"}
    parser = "layout"
    warnings: list[str] = []
    opening_hint = None
    if rows:
        ex = rows_to_txns(rows, set().union(*(r.roles for r in rows)), md.statement_type, ocr_pages, year_hint)
        txns, opening_hint = ex.txns, ex.opening_balance
        warnings.extend(ex.warnings[:10])
    else:
        txns = []
    if not txns:
        all_lines = [ln for pi in sorted(lines_by_page) for ln in lines_by_page[pi]]
        txns = fallback_parse(all_lines, md.statement_type, year_hint)
        parser = "fallback"
        if txns:
            warnings.append("No transaction table header was recognised; used the line-pattern fallback parser.")
    if not txns:
        if doc_type == "scanned" and all((p.ocr_confidence or 0) < 0.5 for p in pages if p.kind == "scanned"):
            raise NoTransactionsFound("The scan is too unclear to read. Try a higher-resolution scan.")
        raise NoTransactionsFound("No transactions were found. Is this a bank or credit card statement?")
    timings["parse"] = round(time.perf_counter() - t2, 3)

    # ---- 3. reconcile
    progress({"stage": "reconcile", "message": "Reconciling running balances"})
    t3 = time.perf_counter()
    dates = [t.date for t in txns if t.date]
    if dates and not md.get("period_from"):
        md.set("period_from", min(dates), "derived")
        md.set("period_to", max(dates), "derived")
    txns, recon = reconcile(txns, md.statement_type, opening_hint, md)
    timings["reconcile"] = round(time.perf_counter() - t3, 3)

    if opened.was_encrypted:
        warnings.append("Statement was password protected; it was decrypted in memory for processing.")
    if opened.was_repaired:
        warnings.append("The PDF had structural damage and was repaired before reading.")
    hidden_pages = [p.index + 1 for p in pages if p.hidden_words]
    from .reconcile import Check
    if hidden_pages:
        n_hidden = sum(p.hidden_words for p in pages)
        warnings.append(f"{n_hidden} hidden or covered-up text fragment(s) on page(s) {', '.join(map(str, hidden_pages))} "
                        "were ignored. The PDF appears to have been edited after it was generated.")
        recon.checks.append(Check("Document integrity", "fail",
                                  f"Text hidden under shapes or drawn invisibly on page(s) {', '.join(map(str, hidden_pages))}."))
    elif doc_type != "scanned":
        recon.checks.append(Check("Document integrity", "pass", "No hidden or covered-up text found."))
    low_ocr = [p.index + 1 for p in pages if p.kind == "scanned" and (p.ocr_confidence or 1) < 0.75 and p.words]
    if low_ocr:
        warnings.append(f"Low OCR confidence on page(s) {', '.join(map(str, low_ocr))}; review highlighted rows.")

    columns = [{"role": c.role, "label": c.label} for c in (layout.columns if layout else [])]
    timings["total"] = round(time.perf_counter() - t0, 3)
    return ExtractionOutput(
        sha256=opened.sha256, page_count=n, pages=pages, metadata=md, txns=txns, recon=recon,
        document_type=doc_type, was_encrypted=opened.was_encrypted, was_repaired=opened.was_repaired,
        clean_pdf=opened.clean_bytes, warnings=warnings, timings=timings, columns=columns, parser=parser,
    )
