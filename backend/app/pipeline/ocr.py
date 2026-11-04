"""OCR for scanned pages.

Engines are pluggable behind `OcrEngine`. RapidOCR (PP-OCR models on ONNX
Runtime — a classical deep-learning OCR, not an LLM) is the default because it
was markedly more accurate than Tesseract on low-DPI Indian statements
(IFSC codes, slash dates, balances). Tesseract is kept as a fallback.

Every engine returns *word* boxes which are converted to PDF points so the OCR
path feeds exactly the same layout engine as the text-layer path.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf

from .models import PageData, Rules, Word

log = logging.getLogger(__name__)

DEFAULT_DPI = 300
MAX_SIDE_PX = 3600


@dataclass
class OcrWord:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float


class OcrEngine:
    name = "base"

    def recognize(self, img: np.ndarray) -> list[OcrWord]:  # BGR uint8
        raise NotImplementedError

    @staticmethod
    def available() -> bool:
        return True


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"
    _engine = None
    _lock = threading.Lock()

    @classmethod
    def _get(cls):
        if cls._engine is None:
            with cls._lock:
                if cls._engine is None:
                    from rapidocr import RapidOCR

                    try:
                        cls._engine = RapidOCR(params={"Global.log_level": "error"})
                    except Exception:  # noqa: BLE001
                        cls._engine = RapidOCR()
        return cls._engine

    def recognize(self, img: np.ndarray) -> list[OcrWord]:
        engine = self._get()
        with self._lock:  # onnxruntime sessions are shared; serialise calls
            res = engine(img, return_word_box=True)
        out: list[OcrWord] = []
        if res is None or res.txts is None:
            return out
        word_results = getattr(res, "word_results", None) or [()] * len(res.txts)
        for line_text, line_score, box, words in zip(res.txts, res.scores, res.boxes, word_results):
            xs, ys = box[:, 0], box[:, 1]
            lx0, ly0, lx1, ly1 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
            if words:
                for wt, ws, wb in words:
                    wb = np.asarray(wb, dtype=float)
                    t = str(wt).strip()
                    if not t:
                        continue
                    out.append(OcrWord(t, float(min(ws, 1.0) * 0.5 + line_score * 0.5),
                                       float(wb[:, 0].min()), ly0, float(wb[:, 0].max()), ly1))
            else:
                out.extend(_split_line(line_text, float(line_score), lx0, ly0, lx1, ly1))
        return out


class TesseractEngine(OcrEngine):
    name = "tesseract"

    @staticmethod
    def available() -> bool:
        import shutil

        return shutil.which("tesseract") is not None

    def recognize(self, img: np.ndarray) -> list[OcrWord]:
        import pytesseract

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        data = pytesseract.image_to_data(gray, config="--psm 6", output_type=pytesseract.Output.DICT)
        out: list[OcrWord] = []
        for i, t in enumerate(data["text"]):
            t = (t or "").strip()
            conf = float(data["conf"][i])
            if not t or conf < 0:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            out.append(OcrWord(t, conf / 100.0, x, y, x + w, y + h))
        return out


def _split_line(text: str, score: float, x0: float, y0: float, x1: float, y1: float) -> list[OcrWord]:
    """Fallback when an engine gives only line boxes: split by spaces, proportional x."""
    parts = text.split()
    if not parts:
        return []
    total = max(1, len(text))
    words, cursor = [], 0
    for p in parts:
        start = text.index(p, cursor)
        end = start + len(p)
        cursor = end
        words.append(OcrWord(p, score, x0 + (x1 - x0) * start / total, y0, x0 + (x1 - x0) * end / total, y1))
    return words


ENGINES: dict[str, type[OcrEngine]] = {"rapidocr": RapidOcrEngine, "tesseract": TesseractEngine}


def get_engine(name: str | None) -> OcrEngine:
    cls = ENGINES.get((name or "rapidocr").lower(), RapidOcrEngine)
    if not cls.available():
        cls = RapidOcrEngine
    return cls()


# ---------------------------------------------------------------- image prep

def render(page: pymupdf.Page, dpi: int = DEFAULT_DPI) -> tuple[np.ndarray, float]:
    """Render the page (rotation applied) to BGR; returns image and px-per-point scale."""
    longest = max(page.rect.width, page.rect.height)
    scale = dpi / 72.0
    if longest * scale > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR), scale


def estimate_skew(gray: np.ndarray) -> float:
    """Skew angle in degrees from long horizontal structures (text lines / rules)."""
    inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, gray.shape[1] // 60), 1))
    merged = cv2.dilate(inv, kernel, iterations=1)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles = []
    for c in contours:
        (_, _), (w, h), a = cv2.minAreaRect(c)
        if w < h:
            w, h = h, w
            a = a - 90
        if w > gray.shape[1] * 0.15 and h < w / 8:
            if a > 45:
                a -= 90
            if a < -45:
                a += 90
            angles.append(a)
    if len(angles) < 3:
        return 0.0
    return float(np.median(angles))


def deskew(img: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = estimate_skew(gray)
    if abs(angle) < 0.25 or abs(angle) > 12:
        return img, 0.0
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    return rotated, angle


def dark_bands(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Wide, short, mostly-ink regions: header bars with light text on a dark fill."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    dark = (gray < 110).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 9)))
    out = []
    for c in cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 0.25 * w or ch < 12 or ch > 0.12 * h:
            continue
        region = gray[y:y + ch, x:x + cw]
        if region.mean() <= 100 and (region < 110).mean() >= 0.6:
            out.append((x, y, cw, ch))
    return out


def reread_dark_bands(img: np.ndarray, words: list[OcrWord], engine: OcrEngine) -> list[OcrWord]:
    """OCR each dark bar on its own, inverted, and keep that read if it is better.
    Done per band so the rest of the page's recognition is untouched."""
    for x, y, cw, ch in dark_bands(img):
        pad = 4
        y0, y1 = max(0, y - pad), min(img.shape[0], y + ch + pad)
        crop = 255 - img[y0:y1, x:x + cw]
        crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        band_words = [OcrWord(bw.text, bw.conf, bw.x0 - 12 + x, bw.y0 - 12 + y0, bw.x1 - 12 + x, bw.y1 - 12 + y0)
                      for bw in engine.recognize(crop)]
        inside = [w for w in words if x <= (w.x0 + w.x1) / 2 <= x + cw and y0 <= (w.y0 + w.y1) / 2 <= y1]
        score_new = sum(len(w.text) * w.conf for w in band_words)
        score_old = sum(len(w.text) * w.conf for w in inside)
        if band_words and score_new > score_old:
            ids = {id(w) for w in inside}
            words = [w for w in words if id(w) not in ids] + band_words
    return words


def image_rules(img: np.ndarray, scale: float) -> Rules:
    """Detect table ruling lines with morphology; returned in PDF points."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    inv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 10)
    h, w = gray.shape
    rules = Rules()

    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 25), 1))
    horiz = cv2.morphologyEx(inv, cv2.MORPH_OPEN, hk)
    for c in cv2.findContours(horiz, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > w * 0.12 and ch < 12:
            rules.hlines.append(((y + ch / 2) / scale, x / scale, (x + cw) / scale))

    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(25, h // 70)))
    vert = cv2.morphologyEx(inv, cv2.MORPH_OPEN, vk)
    for c in cv2.findContours(vert, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, cw, ch = cv2.boundingRect(c)
        if ch > h * 0.015 and cw < 12:
            rules.vlines.append(((x + cw / 2) / scale, y / scale, (y + ch) / scale))
    return rules


def _mostly_vertical(words: list[OcrWord]) -> bool:
    if len(words) < 10:
        return False
    tall = sum(1 for w in words if (w.y1 - w.y0) > 1.8 * (w.x1 - w.x0) and len(w.text) > 2)
    return tall / len(words) > 0.5


def ocr_page(page: pymupdf.Page, index: int, engine: OcrEngine, dpi: int = DEFAULT_DPI,
             chars: int = 0, coverage: float = 0.0) -> PageData:
    t0 = time.perf_counter()
    img, scale = render(page, dpi)
    img, angle = deskew(img)
    words = reread_dark_bands(img, engine.recognize(img), engine)

    if _mostly_vertical(words):
        # Page content is rotated 90°: try both directions, keep the more confident read.
        best = (words, img)
        best_conf = np.mean([w.conf for w in words]) if words else 0
        for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            cand_img = cv2.rotate(img, rot)
            cand = engine.recognize(cand_img)
            conf = np.mean([w.conf for w in cand]) if cand else 0
            if cand and conf > best_conf and not _mostly_vertical(cand):
                best, best_conf = (cand, cand_img), conf
        words, img = best

    rules = image_rules(img, scale)
    out = [Word(text=w.text, x0=w.x0 / scale, y0=w.y0 / scale, x1=w.x1 / scale, y1=w.y1 / scale,
                page=index, conf=round(w.conf, 4), source="ocr") for w in words]
    mean_conf = float(np.mean([w.conf for w in out])) if out else 0.0
    data = PageData(
        index=index,
        width=img.shape[1] / scale,
        height=img.shape[0] / scale,
        kind="scanned",
        words=out,
        rules=rules,
        char_count=chars,
        image_coverage=round(coverage, 3),
        ocr_engine=engine.name,
        ocr_confidence=round(mean_conf, 4),
        ocr_seconds=round(time.perf_counter() - t0, 2),
    )
    if angle:
        log.info("page %s deskewed by %.2f°", index, angle)
    return data
