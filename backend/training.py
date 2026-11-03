from __future__ import annotations

import json
import math
import os
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import data

DB_PATH = data.RUNTIME_DIR / "feedback.db"
MODEL_PATH = data.MODELS_DIR / "active.pkl"
CARD_PATH = data.MODELS_DIR / "model_card.json"
FEATURES = ["process_temp_c", "ph", "tm_c", "dtm_c", "matrix_factor", "is_protein"]


def _connect() -> sqlite3.Connection:
    data.ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            candidate_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            process_temp_c REAL NOT NULL,
            ph REAL NOT NULL,
            tm_c REAL,
            dtm_c REAL,
            matrix_factor REAL,
            predicted_retention REAL,
            measured_retention REAL NOT NULL,
            measured_tm_c REAL,
            n_replicates INTEGER DEFAULT 1,
            source TEXT DEFAULT 'real',
            notes TEXT,
            created_utc TEXT NOT NULL
        )
        """
    )
    conn.commit()
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    return conn


def record_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(payload.get("candidate_id", "")).strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    measured = payload.get("measured_retention")
    if measured is None:
        raise ValueError("measured_retention is required (0-1)")
    measured = float(measured)
    if not 0.0 <= measured <= 1.0:
        raise ValueError("measured_retention must be between 0 and 1")
    ph = float(payload.get("ph", 7.0))
    if not 0.0 <= ph <= 14.0:
        raise ValueError("ph must be between 0 and 14")
    temp = float(payload.get("process_temp_c", 25.0))
    if not -20.0 <= temp <= 200.0:
        raise ValueError("process_temp_c out of range")
    source = str(payload.get("source", "real"))
    if source not in {"real", "synthetic"}:
        raise ValueError("source must be real or synthetic")
    n = int(payload.get("n_replicates", 1))
    if not 1 <= n <= 1000:
        raise ValueError("n_replicates out of range")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO feedback (job_id, candidate_id, kind, process_temp_c, ph, tm_c, dtm_c,
                matrix_factor, predicted_retention, measured_retention, measured_tm_c, n_replicates,
                source, notes, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("job_id"), candidate_id, str(payload.get("kind", "protein")),
                temp, ph, _optional_float(payload.get("tm_c")), _optional_float(payload.get("dtm_c")),
                _optional_float(payload.get("matrix_factor")), _optional_float(payload.get("predicted_retention")),
                measured, _optional_float(payload.get("measured_tm_c")), n, source,
                str(payload.get("notes", ""))[:2000], now,
            ),
        )
        feedback_id = cur.lastrowid
        conn.commit()
    auto = None
    try:
        if feedback_stats()["real_samples"] >= 5:
            auto = train_model(include_synthetic=False)
    except Exception as exc:
        auto = {"trained": False, "reason": str(exc)}
    return {"feedback_id": feedback_id, "created_utc": now, "auto_train": auto}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def feedback_stats() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute("SELECT source, COUNT(*) AS n FROM feedback GROUP BY source").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    by_source = {row["source"]: row["n"] for row in rows}
    return {
        "total": int(total),
        "real_samples": int(by_source.get("real", 0)),
        "synthetic_samples": int(by_source.get("synthetic", 0)),
        "by_source": by_source,
    }


def list_feedback(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def _load_training_rows(include_synthetic: bool) -> list[sqlite3.Row]:
    query = "SELECT * FROM feedback WHERE measured_retention IS NOT NULL"
    params: tuple[Any, ...] = ()
    if not include_synthetic:
        query += " AND source = 'real'"
    query += " ORDER BY id ASC"
    with _connect() as conn:
        return conn.execute(query, params).fetchall()


def _features(row: sqlite3.Row) -> list[float]:
    return [
        float(row["process_temp_c"]),
        float(row["ph"]),
        float(row["tm_c"] or 75.0),
        float(row["dtm_c"] or 0.0),
        float(row["matrix_factor"] or 1.0),
        1.0 if row["kind"] == "protein" else 0.0,
    ]


def _logit(p: float) -> float:
    p = max(1e-4, min(1 - 1e-4, p))
    return math.log(p / (1.0 - p))


def train_model(include_synthetic: bool = False, min_samples: int = 5) -> dict[str, Any]:
    rows = _load_training_rows(include_synthetic)
    if len(rows) < min_samples:
        return {"trained": False, "reason": f"need at least {min_samples} samples, got {len(rows)}", "stats": feedback_stats()}
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import LeaveOneOut
    from sklearn.preprocessing import StandardScaler
    X = np.array([_features(row) for row in rows], dtype=float)
    y = []
    for row in rows:
        measured = float(row["measured_retention"])
        predicted = float(row["predicted_retention"] or measured)
        y.append(_logit(measured) - _logit(predicted))
    y = np.array(y, dtype=float)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    loo = LeaveOneOut()
    errors = []
    for train_idx, test_idx in loo.split(Xs):
        model = Ridge(alpha=2.0)
        model.fit(Xs[train_idx], y[train_idx])
        pred = model.predict(Xs[test_idx])[0]
        pred_ret = 1.0 / (1.0 + math.exp(-(_logit(float(rows[test_idx[0]]["predicted_retention"] or 0.5)) + pred)))
        errors.append(pred_ret - float(rows[test_idx[0]]["measured_retention"]))
    model = Ridge(alpha=2.0)
    model.fit(Xs, y)
    card = {
        "model_version": f"ridge-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": "Ridge correction on logit(retention) residual",
        "features": FEATURES,
        "n_samples": int(len(rows)),
        "include_synthetic": bool(include_synthetic),
        "loo_rmse": round(float(np.sqrt(np.mean(np.square(errors)))), 4),
        "loo_mae": round(float(np.mean(np.abs(errors))), 4),
        "alpha": 2.0,
        "stats": feedback_stats(),
        "caveats": [
            "Correction is only as good as the feedback data; it is not a mechanistic model.",
            "Synthetic feedback must never be mixed into a model used for decisions.",
            "Retraining with <30 samples is exploratory; use external validation.",
        ],
    }
    payload = {"model": model, "scaler": scaler, "features": FEATURES, "card": card}
    data.ensure_dirs()
    tmp = MODEL_PATH.with_suffix(".tmp")
    with tmp.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, MODEL_PATH)
    CARD_PATH.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(MODEL_PATH, 0o600)
        os.chmod(CARD_PATH, 0o600)
    except OSError:
        pass
    return {"trained": True, "card": card}


def load_card() -> dict[str, Any]:
    if not CARD_PATH.exists():
        return {
            "model_version": "mechanistic-prior-1.0",
            "type": "no learned correction active",
            "n_samples": 0,
            "caveats": ["Add real experimental feedback to enable learned correction."],
        }
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def correct_retention(predicted: float, process_temp_c: float, ph: float, tm_c: float, dtm_c: float, matrix_factor: float, is_protein: bool) -> float:
    if not MODEL_PATH.exists():
        return predicted
    try:
        with MODEL_PATH.open("rb") as handle:
            payload = pickle.load(handle)
        X = np.array([[process_temp_c, ph, tm_c, dtm_c, matrix_factor, 1.0 if is_protein else 0.0]], dtype=float)
        delta = float(payload["model"].predict(payload["scaler"].transform(X))[0])
        corrected = 1.0 / (1.0 + math.exp(-(_logit(predicted) + delta)))
        return max(0.0, min(1.0, corrected))
    except Exception:
        return predicted


def delete_all_feedback() -> int:
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        conn.execute("DELETE FROM feedback")
        conn.commit()
    for path in (MODEL_PATH, CARD_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return int(count)


def export_csv() -> str:
    import csv
    import io
    rows = list_feedback(limit=100000)
    output = io.StringIO()
    if not rows:
        return "no feedback\n"
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
