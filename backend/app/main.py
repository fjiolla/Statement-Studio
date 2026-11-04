"""HTTP API for Befree Statement Studio."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import db, service
from .classify import categories as C
from .export import exporter
from .pipeline.ingest import MAX_BYTES

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("befree")

RETENTION_HOURS = float(os.environ.get("BEFREE_RETENTION_HOURS", "24"))
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"
ORIGINS = [o.strip() for o in os.environ.get("BEFREE_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]

app = FastAPI(title="Befree Statement Studio API", version="1.0.0",
              description="Bank & credit-card statement extraction, reconciliation and non-LLM classification.")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_origin_regex=os.environ.get("BEFREE_CORS_REGEX") or None,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
app.add_middleware(GZipMiddleware, minimum_size=2048)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    # warm the classifier + OCR model in the background so the first upload is fast
    def warm():
        try:
            from .classify.ml import get_model
            get_model()
            from .pipeline.ocr import RapidOcrEngine
            RapidOcrEngine._get()
        except Exception as e:  # noqa: BLE001
            log.warning("warm-up failed: %s", e)
    threading.Thread(target=warm, daemon=True).start()

    def janitor():
        while True:
            try:
                n = db.purge_older_than(RETENTION_HOURS)
                if n:
                    log.info("purged %d statement(s) older than %sh", n, RETENTION_HOURS)
            except Exception as e:  # noqa: BLE001
                log.warning("purge failed: %s", e)
            time.sleep(1800)
    threading.Thread(target=janitor, daemon=True).start()


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "retention_hours": RETENTION_HOURS, "max_upload_mb": MAX_BYTES // (1024 * 1024)}


@app.get("/api/categories")
def categories() -> list[dict]:
    return [{"id": c.id, "name": c.name, "kind": c.kind, "icon": c.icon} for c in C.CATEGORIES]


@app.get("/api/model")
def model_card() -> dict:
    from .classify.ml import get_model

    card = dict(get_model().card)
    with db.tx() as conn:
        card["corrections_available"] = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        card["learned_rules"] = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    bench = Path(__file__).resolve().parent / "classify" / "model" / "benchmark.json"
    if bench.exists():
        card["benchmark"] = json.loads(bench.read_text())
    return card


@app.post("/api/model/retrain")
def retrain() -> dict:
    return service.retrain_model()


# ------------------------------------------------------------------ statements

@app.post("/api/statements")
async def upload(file: UploadFile = File(...), password: Optional[str] = Form(None),
                 ocr_engine: str = Form("rapidocr")):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return _err(413, "too_large", f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data:
        return _err(422, "empty_file", "The file is empty.")
    if b"%PDF" not in data[:1024]:
        return _err(422, "not_a_pdf", "Only PDF statements are supported.")
    return service.create_statement(file.filename or "statement.pdf", data, password or None, ocr_engine)


@app.get("/api/samples")
def samples() -> list[dict]:
    index = SAMPLES_DIR / "index.json"
    if not index.exists():
        return []
    return json.loads(index.read_text())


@app.post("/api/samples/{name}")
def load_sample(name: str):
    index = {s["file"]: s for s in samples()}
    if name not in index:
        raise HTTPException(404, "Unknown sample")
    data = (SAMPLES_DIR / name).read_bytes()
    # no password passed: protected samples go through the normal unlock prompt
    return service.create_statement(index[name]["title"] + ".pdf", data, None, is_sample=True)


@app.get("/api/statements")
def list_statements() -> list[dict]:
    return service.list_statements()


@app.get("/api/statements/{sid}")
def get_statement(sid: str):
    s = service.get_statement(sid)
    if s is None:
        raise HTTPException(404, "Statement not found")
    return s


@app.post("/api/statements/{sid}/password")
def password(sid: str, body: dict):
    pw = (body or {}).get("password")
    if not pw:
        return _err(422, "password_required", "Enter the statement password.")
    try:
        return service.submit_password(sid, pw)
    except KeyError:
        raise HTTPException(404, "Statement not found")


@app.get("/api/statements/{sid}/events")
def events(sid: str, after: int = 0):
    try:
        gen = service.statement_events(sid, after)
        first = next(gen)
    except (KeyError, StopIteration):
        raise HTTPException(404, "Statement not found")

    def stream():
        yield f"data: {json.dumps(first)}\n\n"
        for ev in gen:
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/statements/{sid}/pdf")
def statement_pdf(sid: str):
    p = db.file_path(sid, "pdf")
    if not p.exists():
        raise HTTPException(404, "PDF not available")
    return FileResponse(p, media_type="application/pdf", headers={"Cache-Control": "private, max-age=3600"})


@app.delete("/api/statements/{sid}")
def delete(sid: str):
    if not service.delete_statement(sid):
        raise HTTPException(404, "Statement not found")
    return {"deleted": sid}


# ------------------------------------------------------------------ transactions

class TxnPatch(BaseModel):
    category: Optional[str] = None
    apply_to_similar: bool = False
    remember: bool = False
    note: Optional[str] = None
    reviewed: Optional[bool] = None


@app.patch("/api/transactions/{txn_id}")
def patch_txn(txn_id: str, body: TxnPatch):
    try:
        return service.update_transaction(txn_id, body.category, body.apply_to_similar, body.remember, body.note, body.reviewed)
    except KeyError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        return _err(422, "invalid", str(e))


@app.get("/api/transactions/{txn_id}/similar")
def similar(txn_id: str):
    try:
        return service.similar_transactions(txn_id)
    except KeyError:
        raise HTTPException(404, "Transaction not found")


@app.post("/api/transactions/{txn_id}/accept-suggestion")
def accept(txn_id: str):
    try:
        return service.accept_suggestion(txn_id)
    except KeyError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        return _err(422, "no_suggestion", str(e))


# ------------------------------------------------------------------ rules

@app.get("/api/rules")
def rules() -> list[dict]:
    return service.list_rules()


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    if not service.delete_rule(rule_id):
        raise HTTPException(404, "Rule not found")
    return {"deleted": rule_id}


# ------------------------------------------------------------------ export

@app.get("/api/export")
def export(ids: str = Query(..., description="Comma-separated statement ids"), format: str = Query("xlsx"),
           only_review: bool = False):
    sts = []
    for sid in [i for i in ids.split(",") if i]:
        s = service.get_statement(sid)
        if s is None or s["status"] != "done":
            raise HTTPException(404, f"Statement {sid} not ready")
        if only_review:
            s["transactions"] = [t for t in s["transactions"] if t["needs_review"] and not t["reviewed"]]
        sts.append(s)
    if not sts:
        raise HTTPException(422, "No statements selected")
    fmt = format.lower()
    if fmt == "csv":
        body, media = exporter.to_csv(sts), "text/csv; charset=utf-8"
    elif fmt in ("xlsx", "excel"):
        fmt = "xlsx"
        body, media = exporter.to_xlsx(sts), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise HTTPException(422, "format must be xlsx or csv")
    name = exporter.filename_for(sts, fmt)
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
