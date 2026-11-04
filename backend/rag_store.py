from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import data

DB_PATH = Path(os.environ.get("BIOFORGE_RAG_DB", str(data.RUNTIME_DIR / "rag" / "rag.sqlite3")))
_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    quality_score REAL NOT NULL DEFAULT 0,
    quality_label TEXT NOT NULL DEFAULT 'insufficient',
    engine TEXT NOT NULL DEFAULT 'langgraph',
    record_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_runs_status ON rag_runs(status, created_at DESC);
CREATE TABLE IF NOT EXISTS rag_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    corrected_answer TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES rag_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_rag_reviews_run ON rag_reviews(run_id, created_at DESC);
CREATE TABLE IF NOT EXISTS rag_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    reward REAL NOT NULL,
    dimension TEXT NOT NULL DEFAULT 'overall',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES rag_runs(id)
);
CREATE TABLE IF NOT EXISTS rag_relation_weights (
    key TEXT PRIMARY KEY,
    weight REAL NOT NULL DEFAULT 0,
    samples INTEGER NOT NULL DEFAULT 0,
    reward_sum REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init() -> None:
    with _LOCK, _connect() as conn:
        conn.executescript(SCHEMA)


def save_run(record: dict[str, Any]) -> dict[str, Any]:
    init()
    run_id = str(record["id"])
    created = record.get("created_at") or _now()
    status = record.get("status") or "pending_review"
    quality = record.get("quality") or {}
    record["status"] = status
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO rag_runs
                (id, created_at, updated_at, question, status, quality_score, quality_label, engine, record_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=excluded.updated_at,
                status=excluded.status,
                quality_score=excluded.quality_score,
                quality_label=excluded.quality_label,
                record_json=excluded.record_json
            """,
            (
                run_id,
                created,
                _now(),
                str(record.get("question", ""))[:4000],
                status,
                float(quality.get("score", 0)),
                str(quality.get("label", "insufficient")),
                str(record.get("engine", "langgraph")),
                payload,
            ),
        )
    return record


def get_run(run_id: str) -> dict[str, Any] | None:
    init()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT record_json, status FROM rag_runs WHERE id=?", (run_id,)).fetchone()
    if row is None:
        return None
    record = json.loads(row["record_json"])
    record["status"] = row["status"]
    return record


def update_run(record: dict[str, Any]) -> dict[str, Any]:
    return save_run(record)


def set_status(run_id: str, status: str) -> None:
    init()
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE rag_runs SET status=?, updated_at=? WHERE id=?", (status, _now(), run_id))


def list_runs(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    init()
    limit = max(1, min(200, int(limit)))
    with _LOCK, _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT record_json, status FROM rag_runs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT record_json, status FROM rag_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    items = []
    for row in rows:
        record = json.loads(row["record_json"])
        record["status"] = row["status"]
        items.append(record)
    return items


def add_review(run_id: str, action: str, reviewer: str, note: str = "", corrected_answer: str = "") -> dict[str, Any]:
    init()
    with _LOCK, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO rag_reviews (run_id, action, reviewer, note, corrected_answer, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, action, reviewer[:120], note[:4000], corrected_answer[:12000], _now()),
        )
        review_id = int(cursor.lastrowid)
    return {"id": review_id, "run_id": run_id, "action": action, "reviewer": reviewer, "note": note, "created_at": _now()}


def reviews(run_id: str, limit: int = 50) -> list[dict[str, Any]]:
    init()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rag_reviews WHERE run_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (run_id, max(1, min(200, limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def add_feedback(run_id: str, reward: float, dimension: str = "overall", note: str = "") -> dict[str, Any]:
    init()
    reward = max(-1.0, min(1.0, float(reward)))
    with _LOCK, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO rag_feedback (run_id, reward, dimension, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, reward, dimension[:80], note[:2000], _now()),
        )
        feedback_id = int(cursor.lastrowid)
    return {"id": feedback_id, "run_id": run_id, "reward": reward, "dimension": dimension, "created_at": _now()}


def feedback(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    init()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rag_feedback WHERE run_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (run_id, max(1, min(500, limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def relation_weight(key: str) -> float:
    init()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT weight FROM rag_relation_weights WHERE key=?", (key,)).fetchone()
    return float(row["weight"]) if row else 0.0


def update_relation_weight(key: str, reward: float, learning_rate: float = 0.08) -> float:
    init()
    reward = max(-1.0, min(1.0, float(reward)))
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT weight, samples, reward_sum FROM rag_relation_weights WHERE key=?", (key,)).fetchone()
        if row is None:
            weight, samples, reward_sum = 0.0, 0, 0.0
        else:
            weight, samples, reward_sum = float(row["weight"]), int(row["samples"]), float(row["reward_sum"])
        weight = max(-1.0, min(1.0, weight + learning_rate * (reward - weight)))
        samples += 1
        reward_sum += reward
        conn.execute(
            """
            INSERT INTO rag_relation_weights (key, weight, samples, reward_sum, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET weight=excluded.weight, samples=excluded.samples,
                reward_sum=excluded.reward_sum, updated_at=excluded.updated_at
            """,
            (key[:500], weight, samples, reward_sum, _now()),
        )
    return round(weight, 4)


def weights(limit: int = 50) -> list[dict[str, Any]]:
    init()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rag_relation_weights ORDER BY ABS(weight) DESC, updated_at DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


def stats() -> dict[str, Any]:
    init()
    with _LOCK, _connect() as conn:
        one = lambda sql: conn.execute(sql).fetchone()[0]
        pending = one("SELECT COUNT(*) FROM rag_runs WHERE status='pending_review'")
        runs = one("SELECT COUNT(*) FROM rag_runs")
        reviews_n = one("SELECT COUNT(*) FROM rag_reviews")
        feedback_n = one("SELECT COUNT(*) FROM rag_feedback")
    return {
        "database": str(DB_PATH),
        "runs": runs,
        "pending_review": pending,
        "reviews": reviews_n,
        "feedback": feedback_n,
    }
