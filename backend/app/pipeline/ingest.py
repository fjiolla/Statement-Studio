"""Open, validate, decrypt and (if needed) repair an uploaded PDF."""
from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass

import pymupdf

log = logging.getLogger(__name__)
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_BYTES = 40 * 1024 * 1024
MAX_PAGES = 300


class IngestError(Exception):
    code = "ingest_error"
    http_status = 422

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotAPdf(IngestError):
    code = "not_a_pdf"


class PasswordRequired(IngestError):
    code = "password_required"
    http_status = 401


class InvalidPassword(IngestError):
    code = "invalid_password"
    http_status = 401


class CorruptPdf(IngestError):
    code = "corrupt_pdf"


class TooLarge(IngestError):
    code = "too_large"
    http_status = 413


@dataclass
class OpenedPdf:
    doc: pymupdf.Document
    sha256: str
    was_encrypted: bool
    was_repaired: bool
    clean_bytes: bytes  # decrypted copy, safe to hand to a browser PDF viewer


def _repair(data: bytes, password: str | None) -> bytes:
    """Rewrite the file with qpdf (via pikepdf): fixes broken xref/object streams."""
    import pikepdf

    try:
        with pikepdf.open(io.BytesIO(data), password=password or "") as pdf:
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()
    except pikepdf.PasswordError as e:
        raise InvalidPassword("The password is incorrect.") from e
    except Exception as e:  # noqa: BLE001
        raise CorruptPdf(f"The PDF is damaged and could not be repaired ({e.__class__.__name__}).") from e


def open_pdf(data: bytes, password: str | None = None) -> OpenedPdf:
    if len(data) > MAX_BYTES:
        raise TooLarge(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if b"%PDF" not in data[:1024]:
        raise NotAPdf("This file is not a PDF.")

    sha = hashlib.sha256(data).hexdigest()
    repaired = False
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001
        data = _repair(data, password)
        repaired = True
        doc = pymupdf.open(stream=data, filetype="pdf")

    encrypted = bool(doc.needs_pass)
    if encrypted:
        if not password:
            raise PasswordRequired("This statement is password protected.")
        if not doc.authenticate(password):
            raise InvalidPassword("The password is incorrect.")

    # A doc that opens but exposes no pages usually has a broken object stream.
    if doc.page_count == 0:
        data = _repair(data, password)
        repaired = True
        doc = pymupdf.open(stream=data, filetype="pdf")
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise InvalidPassword("The password is incorrect.")
    if doc.page_count == 0:
        raise CorruptPdf("The PDF has no readable pages.")
    if doc.page_count > MAX_PAGES:
        raise TooLarge(f"Statements longer than {MAX_PAGES} pages are not supported.")

    clean = data
    if encrypted:
        # Produce an unencrypted copy so the in-app viewer can display it.
        clean = _repair(data, password)
    return OpenedPdf(doc=doc, sha256=sha, was_encrypted=encrypted, was_repaired=repaired, clean_bytes=clean)
