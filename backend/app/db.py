"""SQLite persistence (stdlib sqlite3, JSON columns). Small, dependency-free, and
swappable for Postgres behind the same functions if the prototype grows."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

DATA_DIR = Path(os.environ.get("BEFREE_DATA_DIR", Path(__file__).resolve().parents[1] / "data" / "runtime"))
DB_PATH = DATA_DIR / "befree.db"
FILES_DIR = DATA_DIR / "files"

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS statements (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT,
    status TEXT NOT NULL,            -- queued | processing | needs_password | done | failed
    error_code TEXT,
    error TEXT,
    statement_type TEXT,
    document_type TEXT,
    bank_name TEXT,
    account_key TEXT,
    page_count INTEGER,
    ocr_engine TEXT,
    meta TEXT,                       -- JSON: extracted account fields
    recon TEXT,                      -- JSON: reconciliation result
    pages TEXT,                      -- JSON: per-page detection info
    warnings TEXT,                   -- JSON list
    timings TEXT,                    -- JSON
    columns TEXT,                    -- JSON
    recurring TEXT,                  -- JSON list
    is_sample INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    date TEXT, value_date TEXT, raw_date TEXT,
    description TEXT NOT NULL, reference TEXT,
    debit REAL, credit REAL, balance REAL,
    category TEXT NOT NULL, model_category TEXT NOT NULL,
    confidence REAL, method TEXT, explanation TEXT,
    merchant TEXT, counterparty TEXT, channel TEXT, vpa TEXT, key TEXT,
    needs_review INTEGER DEFAULT 0, reviewed INTEGER DEFAULT 0, self_transfer INTEGER DEFAULT 0,
    alternatives TEXT, flags TEXT, notes TEXT, bboxes TEXT, suggestion TEXT,
    recon_status TEXT, direction_source TEXT, source TEXT, ocr_confidence REAL,
    recurring_id TEXT, user_note TEXT, page INTEGER
);
CREATE INDEX IF NOT EXISTS ix_txn_statement ON transactions(statement_id, idx);
CREATE INDEX IF NOT EXISTS ix_txn_key ON transactions(key);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    match TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL, direction TEXT,
    label TEXT, hits INTEGER DEFAULT 0,
    UNIQUE(match, kind, direction)
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    txn_id TEXT, description TEXT NOT NULL, is_debit INTEGER NOT NULL, amount REAL NOT NULL,
    statement_type TEXT NOT NULL, from_category TEXT, to_category TEXT NOT NULL
);
"""

JSON_COLS = {"meta", "recon", "pages", "warnings", "timings", "columns", "recurring",
             "alternatives", "flags", "notes", "bboxes", "suggestion"}


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init() -> None:
    global _initialised
    with _init_lock:
        if _initialised:
            return
        conn = _connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()
        _initialised = True


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    init()
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def encode(row: dict) -> dict:
    return {k: (json.dumps(v, default=str) if k in JSON_COLS and v is not None else v) for k, v in row.items()}


def decode(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    out = dict(row)
    for k in JSON_COLS & out.keys():
        if out[k] is not None:
            out[k] = json.loads(out[k])
    return out


def insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    row = encode(row)
    cols = ", ".join(row)
    qs = ", ".join("?" for _ in row)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({qs})", list(row.values()))


def update(conn: sqlite3.Connection, table: str, key: str, value: Any, fields: dict) -> None:
    fields = encode(fields)
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {key} = ?", [*fields.values(), value])


def file_path(statement_id: str, suffix: str = "pdf") -> Path:
    return FILES_DIR / f"{statement_id}.{suffix}"


def purge_older_than(hours: float) -> int:
    """Privacy: drop statements (and their files) older than the retention window."""
    cutoff = time.time() - hours * 3600
    with tx() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM statements WHERE created_at < ? AND is_sample = 0", (cutoff,))]
        for sid in ids:
            conn.execute("DELETE FROM transactions WHERE statement_id = ?", (sid,))
            conn.execute("DELETE FROM statements WHERE id = ?", (sid,))
            for suffix in ("pdf", "upload"):
                p = file_path(sid, suffix)
                if p.exists():
                    p.unlink()
    return len(ids)
