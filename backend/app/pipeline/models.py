"""Internal data structures shared by every pipeline stage.

All coordinates are PDF points in *displayed* page space (origin top-left,
rotation already applied). Text-layer words and OCR words are converted to the
same `Word` shape so a single layout engine can parse both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

PageKind = Literal["text", "scanned", "hybrid", "empty"]
StatementType = Literal["bank_account", "credit_card"]


@dataclass(slots=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int
    conf: float = 1.0
    source: Literal["text", "ocr"] = "text"

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def w(self) -> float:
        return self.x1 - self.x0


@dataclass(slots=True)
class Line:
    words: list[Word]
    page: int

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def y0(self) -> float:
        return min(w.y0 for w in self.words)

    @property
    def y1(self) -> float:
        return max(w.y1 for w in self.words)

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(slots=True)
class Rules:
    """Ruling lines found on a page (from vector drawings or image morphology)."""

    hlines: list[tuple[float, float, float]] = field(default_factory=list)  # (y, x0, x1)
    vlines: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y0, y1)


@dataclass(slots=True)
class PageData:
    index: int
    width: float
    height: float
    kind: PageKind
    words: list[Word]
    rules: Rules
    char_count: int = 0
    image_coverage: float = 0.0
    ocr_engine: Optional[str] = None
    ocr_confidence: Optional[float] = None
    ocr_seconds: Optional[float] = None
    hidden_words: int = 0


@dataclass(slots=True)
class Column:
    role: str
    label: str
    x0: float
    x1: float
    # zone boundaries used to assign data words (filled by the layout engine)
    zx0: float = float("-inf")
    zx1: float = float("inf")


@dataclass(slots=True)
class TableLayout:
    columns: list[Column]
    header_y0: float
    header_y1: float
    page: int

    def roles(self) -> set[str]:
        return {c.role for c in self.columns}


@dataclass(slots=True)
class BBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> dict:
        return {"page": self.page, "x0": round(self.x0, 2), "y0": round(self.y0, 2),
                "x1": round(self.x1, 2), "y1": round(self.y1, 2)}


@dataclass
class RawRow:
    """One table row as reconstructed from lines: text per column role."""

    page: int
    cells: dict[str, list[str]]
    bboxes: list[BBox]
    min_conf: float = 1.0
    roles: set[str] = field(default_factory=set)
    role_conf: dict[str, float] = field(default_factory=dict)

    def text(self, role: str, sep: str = " ") -> str:
        return sep.join(self.cells.get(role, [])).strip()


@dataclass
class Txn:
    """A normalised transaction (pre-classification)."""

    index: int
    date: Optional[date]
    value_date: Optional[date]
    description: str
    reference: str
    debit: Optional[float]
    credit: Optional[float]
    balance: Optional[float]
    bboxes: list[BBox]
    page: int
    raw_date: str = ""
    direction_source: str = "column"  # column | marker | balance | default
    confidence: float = 1.0
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    recon_status: str = "unverified"  # ok | mismatch | corrected | unverified
    source: str = "text"  # text | ocr
    amount_conf: float = 1.0
    balance_conf: float = 1.0
    suggestion: Optional[dict] = None  # {"field": "balance"|"amount", "value": float, "reason": str}
    minus_signed: bool = False         # amount printed with a leading/trailing minus

    @property
    def amount(self) -> float:
        return (self.credit or 0.0) - (self.debit or 0.0)
