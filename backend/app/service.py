"""Application service: processing jobs, persistence, corrections and learning."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Iterator, Optional

from . import db, insights
from .classify import categories as C
from .classify.engine import UserRule, classify_many
from .classify.recurring import detect as detect_recurring
from .pipeline.ingest import IngestError, InvalidPassword, PasswordRequired
from .pipeline.pipeline import extract_statement

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="statement")


# ------------------------------------------------------------------ progress hub

class ProgressHub:
    """In-memory event log per statement, consumed by the SSE endpoint."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}
        self._cond = threading.Condition()

    def publish(self, sid: str, event: dict) -> None:
        with self._cond:
            evs = self._events.setdefault(sid, [])
            evs.append({**event, "seq": len(evs), "ts": round(time.time(), 3)})
            self._cond.notify_all()

    def reset(self, sid: str) -> None:
        with self._cond:
            self._events[sid] = []

    def stream(self, sid: str, start: int = 0, timeout: float = 300) -> Iterator[dict]:
        deadline = time.time() + timeout
        i = start
        while time.time() < deadline:
            with self._cond:
                evs = self._events.get(sid, [])
                if i >= len(evs):
                    self._cond.wait(timeout=10)
                    evs = self._events.get(sid, [])
                batch = evs[i:]
            for ev in batch:
                i += 1
                yield ev
                if ev.get("stage") in ("done", "failed", "needs_password"):
                    return
            if not batch:
                yield {"stage": "heartbeat"}


hub = ProgressHub()


# ------------------------------------------------------------------ helpers

def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _account_key(meta: dict) -> Optional[str]:
    num = (meta.get("account_number") or meta.get("card_number") or "").replace(" ", "")
    if not num:
        return None
    return f"{(meta.get('bank_name') or 'bank').lower()}:{num[-4:]}"


def load_user_rules(conn) -> list[UserRule]:
    return [UserRule(match=r["match"], category=r["category"], kind=r["kind"], direction=r["direction"])
            for r in conn.execute("SELECT * FROM rules ORDER BY id DESC")]


# ------------------------------------------------------------------ create / process

def create_statement(filename: str, data: bytes, password: Optional[str] = None, ocr_engine: str = "rapidocr",
                     is_sample: bool = False) -> dict:
    import hashlib

    sha = hashlib.sha256(data).hexdigest()
    with db.tx() as conn:
        # same file again: reuse the finished result, or the copy still waiting for its password
        dup = conn.execute("SELECT id, status FROM statements WHERE sha256 = ? AND status IN ('done', 'needs_password') "
                           "ORDER BY status = 'done' DESC, created_at DESC", (sha,)).fetchone()
        if dup and not (dup["status"] == "needs_password" and password):
            return {"id": dup["id"], "status": dup["status"], "duplicate": dup["status"] == "done"}
        sid = uuid.uuid4().hex[:12]
        db.insert(conn, "statements", {"id": sid, "created_at": time.time(), "filename": filename[:200], "sha256": sha,
                                       "status": "queued", "ocr_engine": ocr_engine, "is_sample": int(is_sample)})
    db.file_path(sid, "upload").write_bytes(data)
    hub.reset(sid)
    hub.publish(sid, {"stage": "queued", "message": "Queued"})
    _executor.submit(_run, sid, password, ocr_engine)
    return {"id": sid, "status": "queued", "duplicate": False}


def submit_password(sid: str, password: str) -> dict:
    with db.tx() as conn:
        row = conn.execute("SELECT status, ocr_engine FROM statements WHERE id = ?", (sid,)).fetchone()
    if row is None:
        raise KeyError(sid)
    if row["status"] != "needs_password":
        return {"id": sid, "status": row["status"]}
    with db.tx() as conn:
        db.update(conn, "statements", "id", sid, {"status": "queued", "error": None, "error_code": None})
    hub.reset(sid)
    hub.publish(sid, {"stage": "queued", "message": "Unlocking statement"})
    _executor.submit(_run, sid, password, row["ocr_engine"] or "rapidocr")
    return {"id": sid, "status": "queued"}


def _run(sid: str, password: Optional[str], ocr_engine: str) -> None:
    upload = db.file_path(sid, "upload")
    try:
        data = upload.read_bytes()
    except FileNotFoundError:
        _fail(sid, "missing_file", "The uploaded file is no longer available. Please upload it again.")
        return
    with db.tx() as conn:
        db.update(conn, "statements", "id", sid, {"status": "processing"})
    try:
        out = extract_statement(data, password, ocr_engine, progress=lambda e: hub.publish(sid, e))
    except PasswordRequired as e:
        _needs_password(sid, e.code, e.message)
        return
    except InvalidPassword as e:
        _needs_password(sid, e.code, e.message)
        return
    except IngestError as e:
        _fail(sid, e.code, e.message)
        return
    except Exception as e:  # noqa: BLE001
        log.exception("processing failed for %s", sid)
        _fail(sid, "internal_error", f"Unexpected error while reading the statement ({e.__class__.__name__}).")
        return

    try:
        hub.publish(sid, {"stage": "classify", "message": f"Classifying {len(out.txns)} transactions"})
        meta = {k: f.to_dict()["value"] for k, f in out.metadata.fields.items()}
        meta_sources = {k: f.source for k, f in out.metadata.fields.items()}
        stype = out.metadata.statement_type
        with db.tx() as conn:
            rules = load_user_rules(conn)
        items = [{"description": t.description, "is_debit": (t.debit or 0) > 0, "amount": t.debit or t.credit or 0.0}
                 for t in out.txns]
        cls = classify_many(items, stype, rules, account_holder=meta.get("account_holder"))

        rows = []
        for t, c, it in zip(out.txns, cls, items):
            rows.append({
                "id": f"{sid}_{t.index:05d}", "statement_id": sid, "idx": t.index, "date": _iso(t.date),
                "value_date": _iso(t.value_date), "raw_date": t.raw_date, "description": t.description,
                "reference": t.reference, "debit": t.debit, "credit": t.credit, "balance": t.balance,
                "category": c.category, "model_category": c.category, "confidence": c.confidence, "method": c.method,
                "explanation": c.explanation, "merchant": c.merchant, "counterparty": c.counterparty, "channel": c.channel,
                "vpa": c.vpa, "key": c.key, "needs_review": int(c.needs_review or t.recon_status == "mismatch"),
                "reviewed": 0, "self_transfer": int(c.self_transfer), "alternatives": c.alternatives, "flags": t.flags,
                "notes": t.notes, "bboxes": [b.to_dict() for b in t.bboxes], "suggestion": t.suggestion,
                "recon_status": t.recon_status, "direction_source": t.direction_source, "source": t.source,
                "ocr_confidence": t.confidence if t.source == "ocr" else None, "recurring_id": None, "user_note": None,
                "page": t.page,
            })
        rec = detect_recurring([{"index": r["idx"], "date": date.fromisoformat(r["date"]) if r["date"] else None,
                                 "amount": r["debit"] or r["credit"] or 0.0, "is_debit": bool(r["debit"]),
                                 "key": (r["merchant"] or r["key"] or "").lower(),
                                 "label": r["merchant"] or r["counterparty"], "category": r["category"]} for r in rows])
        for g in rec:
            g.id = f"{g.id}_{sid[:4]}"
            for i in g.txn_indices:
                rows[i]["recurring_id"] = g.id

        pages = [{"index": p.index, "kind": p.kind, "width": round(p.width, 2), "height": round(p.height, 2),
                  "char_count": p.char_count, "image_coverage": p.image_coverage, "ocr_engine": p.ocr_engine,
                  "ocr_confidence": p.ocr_confidence, "ocr_seconds": p.ocr_seconds, "hidden_words": p.hidden_words,
                  "words": len(p.words)} for p in out.pages]
        meta["_sources"] = meta_sources
        with db.tx() as conn:
            conn.execute("DELETE FROM transactions WHERE statement_id = ?", (sid,))
            for r in rows:
                db.insert(conn, "transactions", r)
            db.update(conn, "statements", "id", sid, {
                "status": "done", "statement_type": stype, "document_type": out.document_type,
                "bank_name": meta.get("bank_name"), "account_key": _account_key(meta), "page_count": out.page_count,
                "meta": meta, "recon": out.recon.to_dict(), "pages": pages, "warnings": out.warnings,
                "timings": out.timings, "columns": out.columns, "recurring": [g.to_dict() for g in rec],
                "error": None, "error_code": None,
            })
        db.file_path(sid, "pdf").write_bytes(out.clean_pdf)
        upload.unlink(missing_ok=True)
        hub.publish(sid, {"stage": "done", "message": "Statement ready", "transactions": len(rows)})
    except Exception as e:  # noqa: BLE001
        log.exception("post-processing failed for %s", sid)
        _fail(sid, "internal_error", f"Unexpected error while saving results ({e.__class__.__name__}).")


def _fail(sid: str, code: str, message: str) -> None:
    with db.tx() as conn:
        db.update(conn, "statements", "id", sid, {"status": "failed", "error_code": code, "error": message})
    db.file_path(sid, "upload").unlink(missing_ok=True)
    hub.publish(sid, {"stage": "failed", "code": code, "message": message})


def _needs_password(sid: str, code: str, message: str) -> None:
    with db.tx() as conn:
        db.update(conn, "statements", "id", sid, {"status": "needs_password", "error_code": code, "error": message})
    hub.publish(sid, {"stage": "needs_password", "code": code, "message": message})


# ------------------------------------------------------------------ reads

def _txns(conn, sid: str) -> list[dict]:
    rows = [db.decode(r) for r in conn.execute("SELECT * FROM transactions WHERE statement_id = ? ORDER BY idx", (sid,))]
    for r in rows:
        for k in ("needs_review", "reviewed", "self_transfer"):
            r[k] = bool(r[k])
        r["category_name"] = C.name(r["category"])
    return rows


def list_statements() -> list[dict]:
    with db.tx() as conn:
        rows = [db.decode(r) for r in conn.execute(
            "SELECT id, created_at, filename, status, error, error_code, statement_type, document_type, bank_name, "
            "account_key, page_count, meta, recon, is_sample FROM statements ORDER BY created_at DESC")]
        counts = {r["statement_id"]: (r["n"], r["review"]) for r in conn.execute(
            "SELECT statement_id, COUNT(*) n, SUM(needs_review AND NOT reviewed) review FROM transactions GROUP BY statement_id")}
    for r in rows:
        n, review = counts.get(r["id"], (0, 0))
        meta = r.pop("meta") or {}
        recon = r.pop("recon") or {}
        r.update({"transactions": n, "review_count": review or 0, "account_holder": meta.get("account_holder"),
                  "account_number": meta.get("account_number") or meta.get("card_number"),
                  "period_from": meta.get("period_from"), "period_to": meta.get("period_to"),
                  "integrity_score": recon.get("integrity_score"), "is_sample": bool(r["is_sample"])})
    _mark_overlaps(rows)
    return rows


def _mark_overlaps(rows: list[dict]) -> None:
    by_acct: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("account_key") and r.get("period_from") and r["status"] == "done":
            by_acct.setdefault(r["account_key"], []).append(r)
    for group in by_acct.values():
        for a in group:
            a["overlaps_with"] = [b["id"] for b in group if b is not a and a["period_from"] <= b["period_to"]
                                  and b["period_from"] <= a["period_to"]]


def get_statement(sid: str) -> Optional[dict]:
    with db.tx() as conn:
        s = db.decode(conn.execute("SELECT * FROM statements WHERE id = ?", (sid,)).fetchone())
        if s is None:
            return None
        txns = _txns(conn, sid) if s["status"] == "done" else []
    s["is_sample"] = bool(s["is_sample"])
    s["transactions"] = txns
    s["insights"] = insights.compute(txns, s.get("statement_type") or "bank_account") if txns else None
    s.pop("sha256", None)
    return s


def statement_events(sid: str, start: int = 0) -> Iterator[dict]:
    with db.tx() as conn:
        row = conn.execute("SELECT status, error, error_code FROM statements WHERE id = ?", (sid,)).fetchone()
    if row is None:
        raise KeyError(sid)
    if row["status"] in ("done", "failed", "needs_password") and not hub._events.get(sid):
        yield {"stage": row["status"], "message": row["error"] or "", "code": row["error_code"], "seq": 0}
        return
    yield from hub.stream(sid, start)


def delete_statement(sid: str) -> bool:
    with db.tx() as conn:
        cur = conn.execute("DELETE FROM statements WHERE id = ?", (sid,))
        conn.execute("DELETE FROM transactions WHERE statement_id = ?", (sid,))
    for suffix in ("pdf", "upload"):
        db.file_path(sid, suffix).unlink(missing_ok=True)
    return cur.rowcount > 0


# ------------------------------------------------------------------ corrections & learning

def similar_transactions(txn_id: str) -> dict:
    with db.tx() as conn:
        t = conn.execute("SELECT key, statement_id, debit FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        if t is None:
            raise KeyError(txn_id)
        if not t["key"]:
            return {"ids": [], "count": 0}
        is_debit = t["debit"] is not None
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM transactions WHERE key = ? AND id != ? AND (debit IS NOT NULL) = ?", (t["key"], txn_id, is_debit))]
    return {"ids": ids, "count": len(ids)}


def update_transaction(txn_id: str, category: Optional[str] = None, apply_to_similar: bool = False,
                       remember: bool = False, note: Optional[str] = None, reviewed: Optional[bool] = None) -> dict:
    if category is not None and category not in C.BY_ID:
        raise ValueError(f"Unknown category {category}")
    with db.tx() as conn:
        t = db.decode(conn.execute("SELECT t.*, s.statement_type FROM transactions t JOIN statements s "
                                   "ON s.id = t.statement_id WHERE t.id = ?", (txn_id,)).fetchone())
        if t is None:
            raise KeyError(txn_id)
        changed = [txn_id]
        fields: dict[str, Any] = {}
        if note is not None:
            fields["user_note"] = note[:500]
        if reviewed is not None:
            fields["reviewed"] = int(reviewed)
        if category is not None:
            fields.update({"category": category, "method": "user", "confidence": 1.0, "reviewed": 1, "needs_review": 0,
                           "explanation": "Set by you"})
            if category != t["model_category"]:
                db.insert(conn, "corrections", {
                    "created_at": time.time(), "txn_id": txn_id, "description": t["description"],
                    "is_debit": int(t["debit"] is not None), "amount": t["debit"] or t["credit"] or 0.0,
                    "statement_type": t["statement_type"] or "bank_account", "from_category": t["model_category"],
                    "to_category": category})
        if fields:
            db.update(conn, "transactions", "id", txn_id, fields)
        if category is not None and apply_to_similar and t["key"]:
            is_debit = t["debit"] is not None
            others = [r["id"] for r in conn.execute(
                "SELECT id FROM transactions WHERE key = ? AND id != ? AND (debit IS NOT NULL) = ? AND method != 'user'",
                (t["key"], txn_id, is_debit))]
            for oid in others:
                db.update(conn, "transactions", "id", oid, {
                    "category": category, "method": "learned", "confidence": 0.97, "needs_review": 0, "reviewed": 1,
                    "explanation": "Matched your correction for the same payee"})
            changed += others
        if category is not None and remember and t["key"]:
            conn.execute("INSERT OR REPLACE INTO rules (created_at, match, kind, category, direction, label) VALUES (?,?,?,?,?,?)",
                         (time.time(), t["key"], "key", category, "debit" if t["debit"] is not None else "credit",
                          t["merchant"] or t["counterparty"] or t["description"][:40]))
        rows = [db.decode(r) for r in conn.execute(
            f"SELECT * FROM transactions WHERE id IN ({','.join('?' for _ in changed)})", changed)]
    for r in rows:
        for k in ("needs_review", "reviewed", "self_transfer"):
            r[k] = bool(r[k])
        r["category_name"] = C.name(r["category"])
    return {"updated": rows, "count": len(rows)}


def accept_suggestion(txn_id: str) -> dict:
    with db.tx() as conn:
        t = db.decode(conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone())
        if t is None:
            raise KeyError(txn_id)
        sug = t.get("suggestion")
        if not sug:
            raise ValueError("No suggestion for this transaction")
        fields: dict[str, Any] = {"suggestion": None, "recon_status": "corrected", "reviewed": 1}
        notes = list(t.get("notes") or [])
        if sug["field"] == "balance":
            notes.append(f"You accepted the balance correction ({t['balance']} → {sug['value']}).")
            fields["balance"] = sug["value"]
        else:
            notes.append(f"You accepted the amount correction ({t['debit'] or t['credit']} → {sug['value']}).")
            if sug.get("direction") == "credit":
                fields.update({"credit": sug["value"], "debit": None})
            else:
                fields.update({"debit": sug["value"], "credit": None})
        fields["notes"] = notes
        fields["flags"] = [f for f in (t.get("flags") or []) if f != "balance_mismatch"] + ["user_corrected"]
        fields["needs_review"] = 0
        db.update(conn, "transactions", "id", txn_id, fields)
        row = db.decode(conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone())
    row["category_name"] = C.name(row["category"])
    return row


def list_rules() -> list[dict]:
    with db.tx() as conn:
        out = [dict(r) for r in conn.execute("SELECT * FROM rules ORDER BY created_at DESC")]
    for r in out:
        r["category_name"] = C.name(r["category"])
    return out


def delete_rule(rule_id: int) -> bool:
    with db.tx() as conn:
        return conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,)).rowcount > 0


def retrain_model() -> dict:
    from .classify.ml import train
    from .classify.synth import Example

    with db.tx() as conn:
        corr = [Example(r["description"], bool(r["is_debit"]), r["amount"], r["statement_type"], r["to_category"])
                for r in conn.execute("SELECT * FROM corrections")]
    model = train(extra=corr)
    return model.card
