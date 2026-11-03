"""Model Lab: versioned tabular data, regression models, uncertainty and BO.

The lab is deliberately local-first and dependency-light: scikit-learn models
over user-supplied formulation/process/outcome tables. It does not train a
foundation model and it does not turn synthetic or simulated data into
experimental evidence.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from . import __version__, data

DB_PATH = data.RUNTIME_DIR / "lab.db"
ARTIFACT_DIR = data.MODELS_DIR / "lab"
DEMO_CSV = data.DATA_DIR / "lab_demo.csv"
DEMO_META = data.DATA_DIR / "lab_demo.meta.json"

SOURCE_TYPES = ("measured", "literature", "simulation", "synthetic", "mixed")
ALGORITHMS = ("auto", "ridge", "random_forest", "gradient_boosting", "gaussian_process", "ensemble")
MAX_IMPORT_ROWS = 20_000
MAX_DATASET_ROWS = 50_000
MAX_COLUMNS = 200
MAX_CELL_CHARS = 4_000
SCHEMA_VERSION = "1.0"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{3,100}$")
_TRAIN_LOCK = threading.Lock()
_MISSING = {"", "na", "n/a", "nan", "null", "none", "nil", "-", "--", "—", "n.d.", "nd"}
_OUTCOME_HINTS = ("stability", "shelf_life", "shelflife", "retention", "score", "particle", "size", "viscosity", "diameter", "yield", "response", "target", "measured", "tm_c", "dtm_c")
_ID_NAMES = {"id", "sample_id", "sample", "uuid", "guid", "batch", "batch_id", "name", "label", "notes", "note", "comment", "created", "created_at", "date", "time"}


class LabError(Exception):
    def __init__(self, message: str, status: int = 422, code: str = "lab_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}{stamp}-{secrets.token_hex(3)}"


def _validate_id(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not ID_RE.match(value):
        raise LabError(f"无效的 {label}", 422, "invalid_id")
    return value


def _connect() -> sqlite3.Connection:
    data.ensure_dirs()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ARTIFACT_DIR, 0o700)
    except OSError:
        pass
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            schema_json TEXT NOT NULL,
            hash TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            row_index INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            notes TEXT NOT NULL DEFAULT '',
            created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_observations_dataset ON observations(dataset_id, row_index);
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            target TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            resolved_algorithm TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            n_samples INTEGER NOT NULL,
            version INTEGER NOT NULL,
            parent_model_id TEXT,
            metrics_json TEXT NOT NULL,
            card_json TEXT NOT NULL,
            artifact_path TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_models_dataset ON models(dataset_id, created_utc);
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            dataset_id TEXT,
            model_id TEXT,
            input_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model_id, created_utc);
        """
    )
    conn.commit()


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text.lower() in _MISSING:
        return None
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS]
    return text


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace("\u00a0", "")
    if not text:
        return None
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _canonical_rows(rows: list[dict[str, Any]], columns: list[str]) -> str:
    cleaned = [{column: row.get(column) for column in columns} for row in rows]
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_rows(rows: list[dict[str, Any]], columns: list[str]) -> str:
    return hashlib.sha256(_canonical_rows(rows, columns).encode("utf-8")).hexdigest()


def infer_schema(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise LabError("数据为空：至少需要一行。", 422, "empty_dataset")
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            name = str(key).strip()
            if not name:
                raise LabError("存在空列名。", 422, "empty_column")
            if "\x00" in name:
                raise LabError("列名不能包含空字节。", 422, "bad_column")
            if len(name) > 120:
                raise LabError(f"列名过长：{name[:40]}…", 422, "bad_column")
            if name not in seen:
                seen.add(name)
                columns.append(name)
    if len(columns) > MAX_COLUMNS:
        raise LabError(f"列数过多：{len(columns)} > {MAX_COLUMNS}", 422, "too_many_columns")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        clean: dict[str, Any] = {}
        for column in columns:
            clean[column] = _clean_cell(row.get(column))
        normalized.append(clean)
    rows[:] = normalized

    schema_columns: list[dict[str, Any]] = []
    warnings: list[str] = []
    for column in columns:
        values = [row.get(column) for row in rows]
        present = [value for value in values if value is not None]
        missing = len(values) - len(present)
        numeric_values: list[float] = []
        convertible = 0
        for value in present:
            number = _to_float(value)
            if number is not None:
                convertible += 1
                numeric_values.append(number)
        numeric_ratio = convertible / len(present) if present else 0.0
        is_numeric = bool(present) and numeric_ratio >= 0.9
        unique_count = len({str(value) for value in present})
        lower_name = column.strip().lower()

        if is_numeric:
            for row in rows:
                row[column] = _to_float(row.get(column))
            coerced = sum(1 for value in present if _to_float(value) is None)
            if coerced:
                warnings.append(f"数值列 {column} 有 {coerced} 个无法转换的值已置空。")
            arr = np.array(numeric_values, dtype=float)
            outcome_like = any(hint in lower_name for hint in _OUTCOME_HINTS)
            identifier_like = lower_name in _ID_NAMES or lower_name.endswith("_id") or lower_name.endswith("_uuid")
            role = "identifier" if identifier_like else "outcome" if outcome_like else "numeric"
            item = {
                "name": column,
                "type": "numeric",
                "role": role,
                "non_null": len(arr),
                "missing": missing,
                "missing_rate": round(missing / len(rows), 4),
                "unique": int(len(np.unique(arr))),
                "min": round(float(np.min(arr)), 6) if len(arr) else None,
                "max": round(float(np.max(arr)), 6) if len(arr) else None,
                "mean": round(float(np.mean(arr)), 6) if len(arr) else None,
                "median": round(float(np.median(arr)), 6) if len(arr) else None,
                "std": round(float(np.std(arr, ddof=1)), 6) if len(arr) > 1 else 0.0,
                "examples": [round(float(x), 4) for x in numeric_values[:3]],
                "default_feature": not identifier_like and not outcome_like,
                "target_candidate": not identifier_like and len(arr) >= 5 and len(np.unique(arr)) >= 3,
                "leakage_risk": bool(outcome_like),
            }
        else:
            is_identifier = lower_name in _ID_NAMES or lower_name.endswith("_id") or lower_name.endswith("_uuid")
            if is_identifier:
                role = "identifier"
            elif unique_count <= 60:
                role = "categorical"
            else:
                role = "text"
            examples: list[str] = []
            for value in present:
                text = str(value)
                if text not in examples:
                    examples.append(text)
                if len(examples) >= 3:
                    break
            item = {
                "name": column,
                "type": "categorical" if role == "categorical" else "text",
                "role": role,
                "non_null": len(present),
                "missing": missing,
                "missing_rate": round(missing / len(rows), 4),
                "unique": unique_count,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "std": None,
                "examples": examples,
                "default_feature": role == "categorical" and unique_count <= 40,
                "target_candidate": False,
                "leakage_risk": False,
            }
            if missing / len(rows) > 0.5:
                warnings.append(f"列 {column} 缺失率超过 50%。")
        schema_columns.append(item)

    if not any(item["type"] == "numeric" for item in schema_columns):
        warnings.append("没有识别出数值列；无法训练回归模型。")
    target_candidates = [item["name"] for item in schema_columns if item["target_candidate"]]
    feature_candidates = [item["name"] for item in schema_columns if item["default_feature"]]
    if not target_candidates:
        warnings.append("没有可用的数值目标列。")
    return {
        "schema_version": SCHEMA_VERSION,
        "row_count": len(rows),
        "columns": schema_columns,
        "target_candidates": target_candidates,
        "feature_candidates": feature_candidates,
        "warnings": warnings[:30],
    }


def _normalize_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise LabError("数据为空。", 422, "empty_dataset")
    if len(rows) > MAX_IMPORT_ROWS:
        raise LabError(f"单次导入最多 {MAX_IMPORT_ROWS} 行。", 413, "too_many_rows")
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise LabError("每一行必须是对象/字典。", 422, "bad_row")
        item: dict[str, Any] = {}
        for key, value in raw.items():
            name = str(key).strip()
            if name in item:
                raise LabError(f"重复列名：{name}", 422, "duplicate_column")
            item[name] = value
        normalized.append(item)
    return normalized


def parse_csv(content: str) -> list[dict[str, Any]]:
    text = content.lstrip("\ufeff")
    if not text.strip():
        raise LabError("CSV 内容为空。", 422, "empty_csv")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        raise LabError("CSV 没有表头。", 422, "no_header")
    header = [str(name).strip() for name in header]
    if not header or not any(header):
        raise LabError("CSV 没有表头。", 422, "no_header")
    if len(set(header)) != len(header):
        raise LabError("CSV 表头有重复列名。", 422, "duplicate_column")
    rows: list[dict[str, Any]] = []
    for line_no, values in enumerate(reader, start=2):
        if not values or all(not str(value).strip() for value in values):
            continue
        if len(values) > len(header):
            raise LabError(f"CSV 第 {line_no} 行列数多于表头。请检查逗号或引号。", 422, "bad_csv_row")
        padded = values + [""] * (len(header) - len(values))
        rows.append({header[index]: padded[index] for index in range(len(header))})
        if len(rows) > MAX_IMPORT_ROWS:
            raise LabError(f"单次导入最多 {MAX_IMPORT_ROWS} 行。", 413, "too_many_rows")
    return rows


def parse_json(content: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LabError(f"JSON 解析失败：{exc.msg}", 422, "bad_json")
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        payload = payload["rows"]
    if not isinstance(payload, list):
        raise LabError("JSON 必须是对象数组，或 {\"rows\": [...]}。", 422, "bad_json_shape")
    return _normalize_columns(payload)


def _dedupe(rows: list[dict[str, Any]], columns: list[str]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        key = json.dumps({column: row.get(column) for column in columns}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        output.append(row)
    return output, duplicates


def _dataset_row_to_dict(row: sqlite3.Row, include_schema: bool = True) -> dict[str, Any]:
    schema = json.loads(row["schema_json"])
    result = {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "source_type": row["source_type"],
        "row_count": row["row_count"],
        "hash": row["hash"],
        "hash_short": row["hash"][:12],
        "is_demo": bool(row["is_demo"]),
        "created_utc": row["created_utc"],
        "updated_utc": row["updated_utc"],
        "target_candidates": schema.get("target_candidates", []),
        "feature_candidates": schema.get("feature_candidates", []),
        "warnings": schema.get("warnings", []),
        "schema_version": row["schema_version"],
    }
    if include_schema:
        result["schema"] = schema
    return result


def _dataset_row(conn: sqlite3.Connection, dataset_id: str) -> sqlite3.Row:
    dataset_id = _validate_id(dataset_id, "数据集 ID")
    row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if row is None:
        raise LabError("数据集不存在。", 404, "dataset_not_found")
    return row


def _load_rows(conn: sqlite3.Connection, dataset_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT data_json FROM observations WHERE dataset_id = ? ORDER BY row_index ASC, id ASC", (dataset_id,)
    ).fetchall()
    return [json.loads(row["data_json"]) for row in rows]


def get_dataset(dataset_id: str, preview_limit: int = 8) -> dict[str, Any]:
    with _connect() as conn:
        row = _dataset_row(conn, dataset_id)
        result = _dataset_row_to_dict(row)
        previews = conn.execute(
            "SELECT data_json, source, notes, created_utc FROM observations WHERE dataset_id = ? ORDER BY id ASC LIMIT ?",
            (row["id"], max(1, min(50, preview_limit))),
        ).fetchall()
        recent = conn.execute(
            "SELECT data_json, source, notes, created_utc FROM observations WHERE dataset_id = ? ORDER BY id DESC LIMIT ?",
            (row["id"], max(1, min(20, preview_limit))),
        ).fetchall()
        result["preview"] = [dict(json.loads(item["data_json"]), _source=item["source"], _created_utc=item["created_utc"]) for item in previews]
        result["recent"] = [dict(json.loads(item["data_json"]), _source=item["source"], _created_utc=item["created_utc"]) for item in recent]
        result["models"] = [dict(model) for model in conn.execute(
            "SELECT id, target, resolved_algorithm, n_samples, version, created_utc, metrics_json FROM models WHERE dataset_id = ? ORDER BY created_utc DESC LIMIT 20",
            (row["id"],),
        ).fetchall()]
        for model in result["models"]:
            model["metrics"] = json.loads(model.pop("metrics_json"))
        result["training"] = _training_readiness(result)
        result["demo_available"] = DEMO_CSV.exists()
        return result


def _training_readiness(dataset: dict[str, Any]) -> dict[str, Any]:
    source = dataset.get("source_type")
    needs_synthetic = source in {"synthetic", "mixed"}
    n = int(dataset.get("row_count") or 0)
    return {
        "allowed": bool(dataset.get("target_candidates")),
        "needs_synthetic_opt_in": needs_synthetic,
        "min_rows_met": n >= 8,
        "n_rows": n,
        "reasons": [] if dataset.get("target_candidates") and n >= 8 else (
            ([] if dataset.get("target_candidates") else ["没有数值目标列"])
            + ([] if n >= 8 else ["至少需要 8 行有效数据"])
        ),
    }


def list_datasets() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM datasets ORDER BY created_utc DESC").fetchall()
    return {"items": [_dataset_row_to_dict(row, include_schema=False) for row in rows]}


def import_dataset(
    *,
    name: str,
    content: str,
    source_type: str = "measured",
    format: str = "csv",
    description: str = "",
    dedupe: bool = True,
    is_demo: bool = False,
) -> dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        raise LabError("数据集名称不能为空。", 422, "missing_name")
    if len(name) > 80:
        raise LabError("数据集名称最长 80 字。", 422, "name_too_long")
    if source_type not in SOURCE_TYPES:
        raise LabError(f"source_type 必须是 {', '.join(SOURCE_TYPES)}。", 422, "bad_source_type")
    if format not in {"csv", "json"}:
        raise LabError("format 必须是 csv 或 json。", 422, "bad_format")
    if not content or not str(content).strip():
        raise LabError("文件内容为空。", 422, "empty_file")
    if len(content.encode("utf-8")) > 8_000_000:
        raise LabError("导入内容超过 8 MB。", 413, "payload_too_large")
    rows = parse_csv(content) if format == "csv" else parse_json(content)
    rows = _normalize_columns(rows)
    schema = infer_schema(rows)
    columns = [item["name"] for item in schema["columns"]]
    if dedupe:
        rows, duplicates = _dedupe(rows, columns)
    else:
        duplicates = 0
    if not rows:
        raise LabError("去重后没有数据。", 422, "empty_after_dedupe")
    if len(rows) > MAX_DATASET_ROWS:
        raise LabError(f"数据集最多 {MAX_DATASET_ROWS} 行。", 413, "too_many_rows")
    schema = infer_schema(rows)
    columns = [item["name"] for item in schema["columns"]]
    digest = _hash_rows(rows, columns)
    dataset_id = _new_id("DS-")
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO datasets (id, name, description, source_type, schema_version, schema_json, hash, row_count, is_demo, created_utc, updated_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, name, str(description or "")[:2000], source_type, SCHEMA_VERSION, json.dumps(schema, ensure_ascii=False), digest, len(rows), 1 if is_demo else 0, now, now),
        )
        conn.executemany(
            "INSERT INTO observations (dataset_id, row_index, data_json, source, notes, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            [(dataset_id, index, json.dumps(row, ensure_ascii=False), "import", "", now) for index, row in enumerate(rows)],
        )
        conn.commit()
    result = get_dataset(dataset_id)
    result["import"] = {"duplicates_skipped": duplicates, "rows": len(rows), "format": format, "hash": digest}
    return result


def import_demo() -> dict[str, Any]:
    if not DEMO_CSV.exists():
        raise LabError("演示数据文件不存在。", 404, "demo_missing")
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM datasets WHERE is_demo = 1 ORDER BY created_utc ASC LIMIT 1").fetchone()
        if existing is not None:
            result = _dataset_row_to_dict(existing)
            result["import"] = {"created": False, "rows": existing["row_count"]}
            return result
    meta: dict[str, Any] = {}
    if DEMO_META.exists():
        try:
            meta = json.loads(DEMO_META.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    content = DEMO_CSV.read_text(encoding="utf-8")
    result = import_dataset(
        name=meta.get("name") or "演示配方实验（合成数据）",
        content=content,
        source_type="synthetic",
        format="csv",
        description=meta.get("description") or "合成演示数据，仅用于验证流程。",
        dedupe=True,
        is_demo=True,
    )
    result["import"]["created"] = True
    result["import"]["demo_sha256"] = meta.get("sha256")
    return result


def append_rows(
    dataset_id: str,
    rows: list[dict[str, Any]],
    *,
    source: str = "manual",
    notes: str = "",
    retrain_model_id: str | None = None,
) -> dict[str, Any]:
    dataset_id = _validate_id(dataset_id, "数据集 ID")
    rows = _normalize_columns(rows)
    if len(rows) + 0 > MAX_IMPORT_ROWS:
        raise LabError(f"单次追加最多 {MAX_IMPORT_ROWS} 行。", 413, "too_many_rows")
    if len(str(source)) > 40:
        raise LabError("source 过长。", 422, "bad_source")
    notes = str(notes or "")[:1000]
    with _connect() as conn:
        dataset = _dataset_row(conn, dataset_id)
        existing = _load_rows(conn, dataset_id)
        if len(existing) + len(rows) > MAX_DATASET_ROWS:
            raise LabError(f"数据集最多 {MAX_DATASET_ROWS} 行。", 413, "too_many_rows")
        all_rows = existing + rows
        schema = infer_schema(all_rows)
        columns = [item["name"] for item in schema["columns"]]
        digest = _hash_rows(all_rows, columns)
        now = _now()
        start = conn.execute("SELECT COALESCE(MAX(row_index), -1) + 1 FROM observations WHERE dataset_id = ?", (dataset_id,)).fetchone()[0]
        conn.executemany(
            "INSERT INTO observations (dataset_id, row_index, data_json, source, notes, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            [(dataset_id, start + index, json.dumps(row, ensure_ascii=False), source, notes, now) for index, row in enumerate(rows)],
        )
        conn.execute(
            "UPDATE datasets SET schema_json = ?, hash = ?, row_count = ?, updated_utc = ? WHERE id = ?",
            (json.dumps(schema, ensure_ascii=False), digest, len(all_rows), now, dataset_id),
        )
        conn.commit()
    result = get_dataset(dataset_id)
    result["append"] = {"rows": len(rows), "total_rows": len(all_rows), "source": source, "hash": digest}
    if retrain_model_id:
        result["retrain"] = retrain_model(retrain_model_id)
    return result


def delete_dataset(dataset_id: str) -> dict[str, Any]:
    dataset_id = _validate_id(dataset_id, "数据集 ID")
    with _connect() as conn:
        dataset = _dataset_row(conn, dataset_id)
        models = conn.execute("SELECT id, artifact_path FROM models WHERE dataset_id = ?", (dataset_id,)).fetchall()
        conn.execute("DELETE FROM models WHERE dataset_id = ?", (dataset_id,))
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
    for model in models:
        path = Path(model["artifact_path"])
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        try:
            (path.parent / f"{model['id']}.card.json").unlink()
        except OSError:
            pass
    return {"deleted": dataset_id, "name": dataset["name"], "models_deleted": len(models)}


def dataset_csv(dataset_id: str) -> str:
    with _connect() as conn:
        dataset = _dataset_row(conn, dataset_id)
        schema = json.loads(dataset["schema_json"])
        rows = _load_rows(conn, dataset["id"])
    columns = [item["name"] for item in schema["columns"]]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_safe(row.get(column)) for column in columns])
    return output.getvalue()


def template_csv() -> str:
    if DEMO_CSV.exists():
        rows = parse_csv(DEMO_CSV.read_text(encoding="utf-8"))[:3]
        if rows:
            columns = list(rows[0].keys())
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(columns)
            for row in rows:
                writer.writerow([row.get(column, "") for column in columns])
            return output.getvalue()
    return "sample_id,protein_type,protein_pct,ph,stability_days\nS001,whey,4.0,6.5,45\n"


def _csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float, np.integer, np.floating)):
        return value
    text = str(value)
    if text.startswith(("=", "+", "@", "\t", "\r")):
        return "'" + text
    if text.startswith("-") and not re.fullmatch(r"-[0-9.]+", text):
        return "'" + text
    return text


def _load_demo_meta() -> dict[str, Any]:
    if not DEMO_META.exists():
        return {}
    try:
        return json.loads(DEMO_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def dataset_demo_csv() -> str:
    if not DEMO_CSV.exists():
        raise LabError("演示数据文件不存在。", 404, "demo_missing")
    return DEMO_CSV.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Model training


def _df_from_rows(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pd.DataFrame:
    columns = [item["name"] for item in schema["columns"]]
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[columns]
    for item in schema["columns"]:
        name = item["name"]
        if item["type"] == "numeric":
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        else:
            frame[name] = frame[name].map(lambda value: None if value is None else str(value))
    return frame


def _resolve_features(dataset: dict[str, Any], target: str, features: list[str] | None) -> list[str]:
    schema = dataset["schema"]
    columns = {item["name"]: item for item in schema["columns"]}
    if target not in columns:
        raise LabError(f"目标列不存在：{target}", 422, "unknown_target")
    if columns[target]["type"] != "numeric":
        raise LabError("目标列必须是数值型。", 422, "target_not_numeric")
    if features is None:
        features = [name for name in schema.get("feature_candidates", []) if name != target]
    if not isinstance(features, list) or not features:
        raise LabError("请至少选择一个特征列。", 422, "no_features")
    resolved: list[str] = []
    for name in features:
        if not isinstance(name, str) or name not in columns:
            raise LabError(f"特征列不存在：{name}", 422, "unknown_feature")
        if name == target:
            raise LabError("目标列不能同时作为特征。", 422, "target_in_features")
        item = columns[name]
        if item["type"] not in {"numeric", "categorical"}:
            raise LabError(f"列 {name} 是文本/标识符，不能作为默认特征。", 422, "text_feature")
        if item.get("role") == "identifier":
            raise LabError(f"列 {name} 是标识符/批次号，不能作为特征。", 422, "identifier_feature")
        if item["type"] == "categorical" and item["unique"] > 60:
            raise LabError(f"列 {name} 的类别过多（{item['unique']} > 60）。", 422, "high_cardinality")
        if name not in resolved:
            resolved.append(name)
    if len(resolved) > 40:
        raise LabError("默认训练最多支持 40 个特征列。", 422, "too_many_features")
    return resolved


def _training_frame(dataset: dict[str, Any], target: str, features: list[str]) -> pd.DataFrame:
    with _connect() as conn:
        rows = _load_rows(conn, dataset["id"])
    frame = _df_from_rows(rows, dataset["schema"])
    frame = frame.dropna(subset=[target])
    frame = frame[frame[features].notna().any(axis=1)]
    return frame


def _cv_scheme(n: int, folds: int, group_column: str | None, groups: pd.Series | None) -> tuple[Any, str]:
    from sklearn.model_selection import GroupKFold, KFold
    folds = max(2, min(10, int(folds)))
    if group_column:
        if groups is None:
            raise LabError("分组列为空。", 422, "bad_group")
        if groups.isna().any():
            raise LabError("分组列不能有缺失值。", 422, "bad_group")
        if groups.nunique() < folds:
            raise LabError(f"分组数 {groups.nunique()} 少于折数 {folds}。", 422, "bad_group")
        return GroupKFold(n_splits=folds), "GroupKFold"
    folds = min(folds, n)
    return KFold(n_splits=folds, shuffle=True, random_state=42), "KFold"


def _feature_importance(pipeline: Any, X: pd.DataFrame, y: np.ndarray, seed: int) -> list[dict[str, Any]]:
    from sklearn.inspection import permutation_importance
    if len(X) > 700:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(len(X), size=700, replace=False))
        X = X.iloc[idx]
        y = y[idx]
    try:
        result = permutation_importance(
            pipeline, X, y, scoring="neg_mean_absolute_error", n_repeats=5,
            random_state=seed, n_jobs=1,
        )
        means = np.asarray(result.importances_mean, dtype=float)
    except Exception:
        means = np.zeros(X.shape[1], dtype=float)
    means = np.maximum(means, 0.0)
    total = float(np.sum(means))
    rows = []
    for name, value in zip(X.columns, means):
        rows.append({
            "feature": str(name),
            "delta_mae": round(float(value), 6),
            "share": round(float(value / total), 4) if total > 0 else 0.0,
        })
    rows.sort(key=lambda item: (-item["delta_mae"], item["feature"]))
    return rows[:15]


def _target_stats(values: np.ndarray) -> dict[str, Any]:
    if len(values) == 0:
        return {}
    return {
        "min": round(float(np.min(values)), 6),
        "max": round(float(np.max(values)), 6),
        "mean": round(float(np.mean(values)), 6),
        "median": round(float(np.median(values)), 6),
        "std": round(float(np.std(values, ddof=1)), 6) if len(values) > 1 else 0.0,
    }


def _feature_stats(frame: pd.DataFrame, features: list[str], schema: dict[str, Any]) -> dict[str, Any]:
    columns = {item["name"]: item for item in schema["columns"]}
    stats: dict[str, Any] = {}
    for name in features:
        item = columns.get(name, {})
        series = frame[name]
        if item.get("type") == "numeric":
            numeric = pd.to_numeric(series, errors="coerce")
            stats[name] = {
                "type": "numeric",
                "min": round(float(numeric.min()), 6) if numeric.notna().any() else None,
                "max": round(float(numeric.max()), 6) if numeric.notna().any() else None,
                "median": round(float(numeric.median()), 6) if numeric.notna().any() else None,
                "q05": round(float(numeric.quantile(0.05)), 6) if numeric.notna().any() else None,
                "q95": round(float(numeric.quantile(0.95)), 6) if numeric.notna().any() else None,
                "missing_rate": round(float(numeric.isna().mean()), 4),
            }
        else:
            counts = series.dropna().astype(str).value_counts()
            stats[name] = {
                "type": "categorical",
                "values": [str(value) for value in counts.index.tolist()[:60]],
                "counts": [int(value) for value in counts.tolist()[:60]],
                "missing_rate": round(float(series.isna().mean()), 4),
            }
    return stats


class LabRegressor(RegressorMixin, BaseEstimator):
    """A small picklable regressor bundle with an uncertainty estimate."""

    def __init__(self, kind: str = "ridge", seed: int = 42, sigma: float = 0.0):
        self.kind = kind
        self.seed = seed
        self.sigma = sigma

    def fit(self, X: Any, y: Any) -> "LabRegressor":
        from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
        from sklearn.linear_model import Ridge

        n_features = np.asarray(X).shape[1]
        if self.kind == "ridge":
            self.members_ = [("ridge", Ridge(alpha=1.0))]
        elif self.kind == "random_forest":
            self.members_ = [("rf", RandomForestRegressor(
                n_estimators=220, max_features=0.8, min_samples_leaf=1,
                random_state=self.seed, n_jobs=2,
            ))]
        elif self.kind == "gradient_boosting":
            self.members_ = [("hgb", HistGradientBoostingRegressor(
                max_iter=350, learning_rate=0.055, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=self.seed, early_stopping=False,
            ))]
        elif self.kind == "gaussian_process":
            kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(
                length_scale=np.ones(n_features), length_scale_bounds=(1e-2, 1e3)
            ) + WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1e1))
            self.members_ = [("gp", GaussianProcessRegressor(
                kernel=kernel, normalize_y=True, n_restarts_optimizer=1, random_state=self.seed,
            ))]
        elif self.kind == "ensemble":
            self.members_ = [
                ("rf", RandomForestRegressor(
                    n_estimators=220, max_features=0.8, min_samples_leaf=1,
                    random_state=self.seed, n_jobs=2,
                )),
                ("hgb", HistGradientBoostingRegressor(
                    max_iter=350, learning_rate=0.055, max_leaf_nodes=15,
                    l2_regularization=1.0, random_state=self.seed + 1, early_stopping=False,
                )),
                ("ridge", Ridge(alpha=1.0)),
            ]
        else:
            raise ValueError(f"unknown model kind: {self.kind}")
        for _, member in self.members_:
            member.fit(X, y)
        self.n_features_in_ = n_features
        return self

    def predict(self, X: Any) -> np.ndarray:
        predictions = np.vstack([member.predict(X) for _, member in self.members_])
        return np.mean(predictions, axis=0)

    def predict_std(self, X: Any) -> np.ndarray:
        means = []
        variances = []
        for name, member in self.members_:
            if name == "gp":
                mean, std = member.predict(X, return_std=True)
                means.append(np.asarray(mean, dtype=float))
                variances.append(np.square(np.asarray(std, dtype=float)))
            elif name == "rf":
                tree_predictions = np.vstack([tree.predict(X) for tree in member.estimators_])
                means.append(np.mean(tree_predictions, axis=0))
                variances.append(np.var(tree_predictions, axis=0))
            else:
                means.append(np.asarray(member.predict(X), dtype=float))
                variances.append(np.full(len(means[-1]), float(self.sigma) ** 2))
        mean_matrix = np.vstack(means)
        variance_matrix = np.vstack(variances)
        combined_variance = np.mean(variance_matrix, axis=0)
        combined_variance = np.maximum(combined_variance, np.var(mean_matrix, axis=0))
        return np.sqrt(np.maximum(combined_variance, 1e-12))


def train_model(
    *,
    dataset_id: str,
    target: str,
    features: list[str] | None = None,
    algorithm: str = "auto",
    include_synthetic: bool = False,
    cv_folds: int = 5,
    group_column: str | None = None,
    parent_model_id: str | None = None,
) -> dict[str, Any]:
    if not _TRAIN_LOCK.acquire(blocking=False):
        raise LabError("已有训练任务在运行，请稍后重试。", 429, "training_busy")
    try:
        return _train_model_locked(
            dataset_id=dataset_id, target=target, features=features, algorithm=algorithm,
            include_synthetic=include_synthetic, cv_folds=cv_folds,
            group_column=group_column, parent_model_id=parent_model_id,
        )
    finally:
        _TRAIN_LOCK.release()


def _train_model_locked(**kwargs: Any) -> dict[str, Any]:
    from sklearn.base import BaseEstimator, RegressorMixin
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    dataset_id = _validate_id(kwargs["dataset_id"], "数据集 ID")
    target = str(kwargs.get("target") or "").strip()
    algorithm = str(kwargs.get("algorithm") or "auto")
    if algorithm not in ALGORITHMS:
        raise LabError(f"未知算法：{algorithm}", 422, "bad_algorithm")
    include_synthetic = bool(kwargs.get("include_synthetic"))
    cv_folds = int(kwargs.get("cv_folds") or 5)
    group_column = kwargs.get("group_column")
    with _connect() as conn:
        dataset_row = _dataset_row(conn, dataset_id)
    dataset = _dataset_row_to_dict(dataset_row)
    source_type = dataset["source_type"]
    if source_type in {"synthetic", "mixed"} and not include_synthetic:
        raise LabError("该数据集包含合成数据。请显式勾选“允许合成数据”后再训练。", 422, "synthetic_opt_in_required")
    schema = dataset["schema"]
    features = _resolve_features(dataset, target, kwargs.get("features"))
    if group_column:
        group_column = str(group_column)
        if group_column not in {item["name"] for item in schema["columns"]}:
            raise LabError("分组列不存在。", 422, "unknown_group")
    frame = _training_frame(dataset, target, features)
    n = len(frame)
    if n < 8:
        raise LabError(f"有效训练样本不足：{n} < 8。", 422, "not_enough_rows")
    if n > 50_000:
        raise LabError("训练样本超过 5 万行上限。", 413, "too_many_rows")
    y = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(y)
    frame = frame.loc[valid].reset_index(drop=True)
    y = y[valid]
    if len(y) < 8:
        raise LabError("有效目标值不足 8 条。", 422, "not_enough_target")
    if len(np.unique(y)) < 2:
        raise LabError("目标列是常数，无法训练回归模型。", 422, "constant_target")
    columns = {item["name"]: item for item in schema["columns"]}
    numeric_features = [name for name in features if columns[name]["type"] == "numeric"]
    categorical_features = [name for name in features if columns[name]["type"] == "categorical"]
    if not numeric_features and not categorical_features:
        raise LabError("没有可用特征。", 422, "no_features")
    if algorithm == "gaussian_process" and n > 800:
        raise LabError("高斯过程最多支持 800 行；请改用自动/随机森林/集成。", 422, "gp_too_large")
    if algorithm == "auto":
        if n < 25:
            resolved = "gaussian_process"
        elif n < 300:
            resolved = "random_forest"
        else:
            resolved = "ensemble"
    else:
        resolved = algorithm
    if resolved == "gaussian_process" and n > 800:
        resolved = "random_forest"
    groups = frame[group_column].astype(str) if group_column else None
    splitter, scheme = _cv_scheme(n, cv_folds, group_column, groups)

    transformers = []
    if numeric_features:
        transformers.append(("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), numeric_features))
    if categorical_features:
        transformers.append(("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical_features))
    preprocessor = ColumnTransformer(transformers, remainder="drop")


    X = frame[features]
    oof_pred = np.full(len(frame), np.nan, dtype=float)
    oof_std = np.full(len(frame), np.nan, dtype=float)
    baseline_pred = np.full(len(frame), np.nan, dtype=float)
    fold_metrics: list[dict[str, Any]] = []
    split_iterator = splitter.split(X, y, groups) if groups is not None else splitter.split(X)
    for fold_index, (train_idx, test_idx) in enumerate(split_iterator, start=1):
        pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("model", LabRegressor(kind=resolved, seed=42 + fold_index, sigma=0.0)),
        ])
        pipeline.fit(X.iloc[train_idx], y[train_idx])
        pred = np.asarray(pipeline.predict(X.iloc[test_idx]), dtype=float)
        std = np.asarray(pipeline.named_steps["model"].predict_std(pipeline.named_steps["preprocessor"].transform(X.iloc[test_idx])), dtype=float)
        oof_pred[test_idx] = pred
        oof_std[test_idx] = std
        baseline_pred[test_idx] = float(np.median(y[train_idx]))
        fold_metrics.append({
            "fold": fold_index,
            "n_test": int(len(test_idx)),
            "mae": round(float(mean_absolute_error(y[test_idx], pred)), 6),
            "rmse": round(float(math.sqrt(mean_squared_error(y[test_idx], pred))), 6),
        })
    if np.isnan(oof_pred).any():
        raise LabError("交叉验证没有覆盖全部样本。", 500, "cv_incomplete")
    residuals = oof_pred - y
    rmse = float(math.sqrt(mean_squared_error(y, oof_pred)))
    mae = float(mean_absolute_error(y, oof_pred))
    r2 = float(r2_score(y, oof_pred))
    denom = np.where(np.abs(y) > 1e-9, np.abs(y), np.nan)
    mape = float(np.nanmean(np.abs(residuals) / denom) * 100.0) if np.isfinite(denom).any() else None
    baseline_mae = float(mean_absolute_error(y, baseline_pred))
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(y))
    final_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model", LabRegressor(kind=resolved, seed=42, sigma=sigma)),
    ])
    final_pipeline.fit(X, y)
    final_pipeline.named_steps["model"].sigma = sigma

    feature_importance = _feature_importance(final_pipeline, X, y, seed=42)
    importance = _feature_stats(frame, features, schema)
    target_values = _target_stats(y)
    parity_indices = np.linspace(0, len(y) - 1, num=min(len(y), 300), dtype=int)
    parity = [{
        "actual": round(float(y[i]), 5),
        "predicted": round(float(oof_pred[i]), 5),
        "std": round(float(oof_std[i]), 5) if np.isfinite(oof_std[i]) else None,
    } for i in parity_indices]

    warnings: list[str] = []
    leakage_features = [name for name in features if columns[name].get("leakage_risk")]
    if leakage_features:
        warnings.append("以下特征可能是同批实验的结果/结局列，存在数据泄漏风险：" + "、".join(leakage_features[:8]))
    if source_type == "synthetic":
        warnings.append("该数据集是合成数据；模型只能用于流程验证，不能用于真实产品决策。")
    elif source_type == "mixed":
        warnings.append("该数据集包含合成/混合来源；结果只能作为探索性证据。")
    elif source_type == "literature":
        warnings.append("数据来自文献整理，需核对单位、批次、统计口径和原始实验条件。")
    elif source_type == "simulation":
        warnings.append("数据来自模拟；模拟偏差尚未用湿实验校准。")
    if n < 30:
        warnings.append("样本少于 30 条，交叉验证误差很不稳定；不要外推到新配方空间。")
    if group_column:
        warnings.append(f"按 {group_column} 分组交叉验证，降低同组泄漏风险。")
    else:
        warnings.append("未设置分组列；若同批次/同配方有多条记录，普通 KFold 可能高估泛化。")
    if scheme == "KFold":
        warnings.append("随机 KFold 适用于独立样本；时间序列或批次数据应设置分组列。")
    if n <= 12:
        warnings.append("极小样本：建议用 Ridge 或 GP，并优先做外部验证。")

    metrics = {
        "r2": round(r2, 5),
        "mae": round(mae, 5),
        "rmse": round(rmse, 5),
        "mape_pct": round(mape, 4) if mape is not None else None,
        "baseline_mae": round(baseline_mae, 5),
        "residual_sigma": round(sigma, 6),
        "n": int(n),
        "n_features": len(features),
        "n_folds": int(splitter.get_n_splits()),
        "improvement_vs_baseline": round(1.0 - mae / baseline_mae, 4) if baseline_mae > 0 else None,
    }
    model_id = _new_id("MDL-")
    now = _now()
    with _connect() as conn:
        version = int(conn.execute(
            "SELECT COUNT(*) FROM models WHERE dataset_id = ? AND target = ? AND algorithm = ?",
            (dataset_id, target, algorithm),
        ).fetchone()[0]) + 1
    card = {
        "model_id": model_id,
        "model_version": f"lab-{now[:10].replace('-', '')}-v{version}",
        "created_utc": now,
        "package_version": __version__,
        "task": "tabular_regression",
        "dataset": {
            "id": dataset_id,
            "name": dataset["name"],
            "source_type": source_type,
            "hash": dataset["hash"],
            "row_count": dataset["row_count"],
            "is_demo": dataset["is_demo"],
        },
        "target": target,
        "target_stats": target_values,
        "features": features,
        "feature_types": {name: columns[name]["type"] for name in features},
        "leakage_risk_features": leakage_features,
        "algorithm_requested": algorithm,
        "algorithm_resolved": resolved,
        "cv": {"scheme": scheme, "folds": int(splitter.get_n_splits()), "group_column": group_column},
        "metrics": metrics,
        "fold_metrics": fold_metrics,
        "parity": parity,
        "feature_importance": feature_importance,
        "feature_stats": importance,
        "n_samples": n,
        "n_features": len(features),
        "training_config": {
            "dataset_id": dataset_id,
            "target": target,
            "features": features,
            "algorithm": algorithm,
            "include_synthetic": include_synthetic,
            "cv_folds": int(splitter.get_n_splits()),
            "group_column": group_column,
        },
        "warnings": warnings,
        "caveats": [
            "这是表格回归模型，不是机理模型或食品/药物安全结论。",
            "预测区间来自交叉验证残差/树集成/GP 方差，未经过外部校准。",
            "合成、模拟和文献数据不能替代湿实验。",
            "超出训练范围的配方属于外推，应视为待验证假设。",
        ],
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / f"{model_id}.joblib"
    payload = {
        "pipeline": final_pipeline,
        "features": features,
        "target": target,
        "card": card,
        "residual_sigma": sigma,
        "feature_stats": importance,
        "target_stats": target_values,
    }
    import joblib
    joblib.dump(payload, artifact_path, compress=3)
    try:
        os.chmod(artifact_path, 0o600)
    except OSError:
        pass
    artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    card_path = ARTIFACT_DIR / f"{model_id}.card.json"
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(card_path, 0o600)
    except OSError:
        pass
    with _connect() as conn:
        conn.execute(
            "INSERT INTO models (id, dataset_id, target, algorithm, resolved_algorithm, created_utc, n_samples, version, parent_model_id, metrics_json, card_json, artifact_path, artifact_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (model_id, dataset_id, target, algorithm, resolved, now, n, version, kwargs.get("parent_model_id"), json.dumps(metrics, ensure_ascii=False), json.dumps(card, ensure_ascii=False), str(artifact_path), artifact_sha),
        )
        conn.commit()
    return {"model": card, "artifact_sha256": artifact_sha}


def list_models(dataset_id: str | None = None) -> dict[str, Any]:
    with _connect() as conn:
        if dataset_id:
            dataset_id = _validate_id(dataset_id, "数据集 ID")
            rows = conn.execute("SELECT * FROM models WHERE dataset_id = ? ORDER BY created_utc DESC", (dataset_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM models ORDER BY created_utc DESC").fetchall()
    items = []
    for row in rows:
        try:
            card = json.loads(row["card_json"])
        except Exception:
            card = {}
        items.append({
            "id": row["id"],
            "dataset_id": row["dataset_id"],
            "target": row["target"],
            "algorithm": row["algorithm"],
            "resolved_algorithm": row["resolved_algorithm"],
            "created_utc": row["created_utc"],
            "n_samples": row["n_samples"],
            "version": row["version"],
            "parent_model_id": row["parent_model_id"],
            "metrics": json.loads(row["metrics_json"]),
            "dataset": card.get("dataset", {}),
            "cv": card.get("cv", {}),
            "warnings": card.get("warnings", []),
        })
    return {"items": items}


def _model_row(model_id: str) -> tuple[sqlite3.Row, dict[str, Any]]:
    model_id = _validate_id(model_id, "模型 ID")
    with _connect() as conn:
        row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if row is None:
        raise LabError("模型不存在。", 404, "model_not_found")
    return row, json.loads(row["card_json"])


def get_model(model_id: str) -> dict[str, Any]:
    row, card = _model_row(model_id)
    artifact = Path(row["artifact_path"])
    return {
        "model": card,
        "artifact": {
            "exists": artifact.exists(),
            "sha256": row["artifact_sha256"],
            "size_bytes": artifact.stat().st_size if artifact.exists() else 0,
        },
        "dataset_id": row["dataset_id"],
    }


def retrain_model(model_id: str) -> dict[str, Any]:
    row, card = _model_row(model_id)
    config = card.get("training_config") or {}
    return train_model(
        dataset_id=row["dataset_id"],
        target=row["target"],
        features=config.get("features"),
        algorithm=config.get("algorithm") or "auto",
        include_synthetic=True,
        cv_folds=int(config.get("cv_folds") or 5),
        group_column=config.get("group_column"),
        parent_model_id=model_id,
    )


def _load_artifact(model_id: str) -> tuple[sqlite3.Row, dict[str, Any], dict[str, Any]]:
    row, card = _model_row(model_id)
    path = Path(row["artifact_path"])
    if not path.exists():
        raise LabError("模型文件不存在，请重新训练。", 404, "artifact_missing")
    import joblib
    payload = joblib.load(path)
    return row, card, payload


def predict(model_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise LabError("至少提供一条记录。", 422, "no_records")
    if len(records) > 5000:
        raise LabError("单次最多预测 5000 条。", 413, "too_many_records")
    _, card, payload = _load_artifact(model_id)
    features = payload["features"]
    feature_stats = payload["feature_stats"]
    frame = pd.DataFrame([{name: record.get(name) for name in features} for record in records])
    schema = {
        "columns": [
            {"name": name, "type": feature_stats.get(name, {}).get("type", "numeric")}
            for name in features
        ]
    }
    typed = _df_from_rows([{name: row.get(name) for name in features} for row in frame.to_dict(orient="records")], schema)
    predictions = np.asarray(payload["pipeline"].predict(typed), dtype=float)
    try:
        std = np.asarray(payload["pipeline"].named_steps["model"].predict_std(
            payload["pipeline"].named_steps["preprocessor"].transform(typed)
        ), dtype=float)
    except Exception:
        std = np.full(len(predictions), float(payload.get("residual_sigma") or 0.0))
    outputs = []
    for index, (mean, uncertainty) in enumerate(zip(predictions, std)):
        warnings: list[str] = []
        for name in features:
            stats = feature_stats.get(name, {})
            value = records[index].get(name)
            if stats.get("type") == "numeric" and value is not None:
                number = _to_float(value)
                if number is not None and stats.get("min") is not None and number < stats["min"]:
                    warnings.append(f"{name} 低于训练范围（{stats['min']}）")
                if number is not None and stats.get("max") is not None and number > stats["max"]:
                    warnings.append(f"{name} 高于训练范围（{stats['max']}）")
            elif stats.get("type") == "categorical" and value is not None:
                if str(value) not in set(stats.get("values") or []):
                    warnings.append(f"{name} 有训练中未出现的类别：{value}")
        outputs.append({
            "prediction": round(float(mean), 6),
            "uncertainty": round(float(uncertainty), 6),
            "lower_95": round(float(mean - 1.96 * uncertainty), 6),
            "upper_95": round(float(mean + 1.96 * uncertainty), 6),
            "warnings": warnings[:8],
        })
    return {"model_id": model_id, "target": payload["target"], "predictions": outputs}


def _space_for_model(card: dict[str, Any], overrides: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    stats = card.get("feature_stats") or {}
    features = card.get("features") or []
    overrides = overrides or {}
    if not isinstance(overrides, dict):
        raise LabError("space 必须是对象。", 422, "bad_space")
    unknown = [name for name in overrides if name not in features]
    if unknown:
        raise LabError(f"搜索空间包含未知特征：{', '.join(unknown[:5])}", 422, "bad_space")
    space: dict[str, Any] = {}
    warnings: list[str] = []
    for name in features:
        info = stats.get(name) or {}
        if info.get("type") == "numeric":
            low, high = info.get("min"), info.get("max")
            if low is None or high is None:
                raise LabError(f"特征 {name} 没有可用的数值范围。", 422, "bad_feature")
            rule = overrides.get(name) or {}
            request_low = _to_float(rule.get("min")) if isinstance(rule, dict) else None
            request_high = _to_float(rule.get("max")) if isinstance(rule, dict) else None
            if request_low is None:
                request_low = low
            if request_high is None:
                request_high = high
            if request_low > request_high:
                raise LabError(f"{name} 的最小值大于最大值。", 422, "bad_range")
            if request_low < low or request_high > high:
                warnings.append(f"{name} 的搜索范围已收窄到训练数据范围 [{low}, {high}]。")
                request_low = max(request_low, low)
                request_high = min(request_high, high)
            space[name] = {"type": "numeric", "min": float(request_low), "max": float(request_high)}
        else:
            values = [str(value) for value in (info.get("values") or [])]
            if not values:
                raise LabError(f"特征 {name} 没有可用类别。", 422, "bad_feature")
            rule = overrides.get(name) or {}
            requested = rule.get("values") if isinstance(rule, dict) else None
            if requested is not None:
                if not isinstance(requested, list) or not requested:
                    raise LabError(f"{name} 的 values 必须是非空数组。", 422, "bad_values")
                requested = [str(value) for value in requested]
                if any(value not in values for value in requested):
                    raise LabError(f"{name} 的搜索空间包含训练中未出现的类别。", 422, "bad_values")
                values = requested
            space[name] = {"type": "categorical", "values": values}
    return space, warnings


def _normal_cdf(value: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(value / math.sqrt(2.0)))


def _normal_pdf(value: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * np.square(value)) / math.sqrt(2.0 * math.pi)


def optimize(
    *,
    model_id: str,
    direction: str = "maximize",
    n_candidates: int = 5,
    search_size: int = 2048,
    space: dict[str, Any] | None = None,
    seed: int = 42,
    min_distance: float = 0.06,
) -> dict[str, Any]:
    if direction not in {"maximize", "minimize"}:
        raise LabError("direction 必须是 maximize 或 minimize。", 422, "bad_direction")
    n_candidates = max(1, min(20, int(n_candidates)))
    search_size = max(256, min(8000, int(search_size)))
    if search_size < n_candidates:
        search_size = n_candidates * 20
    row, card, payload = _load_artifact(model_id)
    features = payload["features"]
    stats = payload["feature_stats"]
    space_used, warnings = _space_for_model(card, space)
    rng = np.random.default_rng(int(seed))
    matrix: dict[str, Any] = {}
    for name in features:
        rule = space_used[name]
        if rule["type"] == "numeric":
            matrix[name] = rng.uniform(rule["min"], rule["max"], size=search_size)
        else:
            values = rule["values"]
            matrix[name] = rng.choice(values, size=search_size, replace=True)
    candidates_frame = pd.DataFrame(matrix)
    schema = {
        "columns": [
            {"name": name, "type": stats.get(name, {}).get("type", "numeric")}
            for name in features
        ]
    }
    typed = _df_from_rows(candidates_frame.to_dict(orient="records"), schema)
    pipeline = payload["pipeline"]
    mean = np.asarray(pipeline.predict(typed), dtype=float)
    try:
        std = np.asarray(pipeline.named_steps["model"].predict_std(
            pipeline.named_steps["preprocessor"].transform(typed)
        ), dtype=float)
    except Exception:
        std = np.full(len(mean), float(payload.get("residual_sigma") or 0.0))
    target_stats = payload.get("target_stats") or {}
    best_observed = target_stats.get("max") if direction == "maximize" else target_stats.get("min")
    if best_observed is None:
        raise LabError("模型没有可用的目标统计。", 422, "bad_model")
    target_range = float(target_stats.get("max", 0.0)) - float(target_stats.get("min", 0.0))
    variance_floor = max(float(payload.get("residual_sigma") or 0.0), max(target_range, 1.0) * 1e-4)
    std = np.maximum(std, variance_floor)
    if direction == "maximize":
        improvement = mean - float(best_observed)
    else:
        improvement = float(best_observed) - mean
    z = improvement / std
    ei = improvement * _normal_cdf(z) + std * _normal_pdf(z)
    bounds: dict[str, tuple[float, float]] = {}
    for name in features:
        rule = space_used[name]
        if rule["type"] == "numeric":
            bounds[name] = (float(rule["min"]), float(rule["max"]))
    keys = []
    for index in range(search_size):
        key_parts = []
        for name in features:
            value = matrix[name][index]
            if space_used[name]["type"] == "numeric":
                key_parts.append(f"{float(value):.5f}")
            else:
                key_parts.append(str(value))
        keys.append("|".join(key_parts))
    order = sorted(range(search_size), key=lambda index: (-float(ei[index]), keys[index]))
    selected: list[int] = []
    def distance(a: int, b: int) -> float:
        parts = []
        for name in features:
            rule = space_used[name]
            if rule["type"] == "numeric":
                low, high = bounds[name]
                spread = max(high - low, 1e-12)
                parts.append(abs(float(matrix[name][a]) - float(matrix[name][b])) / spread)
            else:
                parts.append(0.0 if str(matrix[name][a]) == str(matrix[name][b]) else 1.0)
        return float(np.sqrt(np.mean(np.square(parts)))) if parts else 0.0
    seen_keys: set[str] = set()
    for index in order:
        if keys[index] in seen_keys:
            continue
        seen_keys.add(keys[index])
        if all(distance(index, chosen) >= float(min_distance) for chosen in selected):
            selected.append(index)
        if len(selected) >= n_candidates:
            break
    if len(selected) < n_candidates:
        for index in order:
            if index in selected or keys[index] in {keys[chosen] for chosen in selected}:
                continue
            selected.append(index)
            if len(selected) >= n_candidates:
                break
    proposals = []
    for rank, index in enumerate(selected, start=1):
        features_out = {
            name: (round(float(matrix[name][index]), 5) if space_used[name]["type"] == "numeric" else str(matrix[name][index]))
            for name in features
        }
        uncertainty = float(std[index])
        confidence = "high" if uncertainty <= max(target_range * 0.10, 1e-9) else "medium" if uncertainty <= max(target_range * 0.25, 1e-9) else "low"
        proposals.append({
            "rank": rank,
            "candidate_id": f"C{rank:02d}",
            "features": features_out,
            "predicted": round(float(mean[index]), 6),
            "uncertainty": round(uncertainty, 6),
            "lower_95": round(float(mean[index] - 1.96 * uncertainty), 6),
            "upper_95": round(float(mean[index] + 1.96 * uncertainty), 6),
            "acquisition": round(float(ei[index]), 6),
            "confidence": confidence,
        })
    if n_candidates:
        best_index = selected[0] if selected else order[0]
        if float(ei[best_index]) <= 1e-12:
            warnings.append("所有候选的 EI 接近 0；模型可能已经没有明显改进空间，或数据方差过大。")
    if card.get("dataset", {}).get("source_type") == "synthetic":
        warnings.append("演示模型基于合成数据；候选只用于验证优化流程。")
    if n_candidates > len(selected):
        warnings.append(f"去重/多样性筛选后只有 {len(selected)} 个候选。")
    result = {
        "run_id": _new_id("RUN-"),
        "model_id": model_id,
        "model_version": card.get("model_version"),
        "target": card.get("target"),
        "direction": direction,
        "observed_best": round(float(best_observed), 6),
        "observed_range": target_stats,
        "search_size": search_size,
        "space": space_used,
        "candidates": proposals,
        "warnings": warnings[:12],
        "created_utc": _now(),
        "notice": "候选是模型 + EI 采集函数的建议，不是实验结果；必须进行虚拟复核/湿实验验证。",
    }
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, kind, dataset_id, model_id, input_json, result_json, created_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (result["run_id"], "bayesian_optimization", row["dataset_id"], model_id, json.dumps({"direction": direction, "n_candidates": n_candidates, "search_size": search_size, "space": space, "seed": seed}, ensure_ascii=False), json.dumps(result, ensure_ascii=False), result["created_utc"]),
        )
        conn.commit()
    return result


def get_run(run_id: str) -> dict[str, Any]:
    run_id = _validate_id(run_id, "运行 ID")
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise LabError("运行记录不存在。", 404, "run_not_found")
    result = json.loads(row["result_json"])
    result["input"] = json.loads(row["input_json"])
    result["kind"] = row["kind"]
    return result


def run_csv(run_id: str) -> str:
    result = get_run(run_id)
    candidates = result.get("candidates") or []
    if not candidates:
        return "no candidates\n"
    features = list(candidates[0].get("features", {}).keys())
    columns = features + ["predicted", "uncertainty", "lower_95", "upper_95", "acquisition", "confidence", "rank", "candidate_id"]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for candidate in candidates:
        row = dict(candidate.get("features") or {})
        row.update({key: candidate.get(key) for key in columns if key not in row})
        writer.writerow([_csv_safe(row.get(column)) for column in columns])
    return output.getvalue()


def record_feedback(
    *,
    model_id: str,
    features: dict[str, Any],
    measured: dict[str, Any],
    notes: str = "",
    retrain: bool = False,
) -> dict[str, Any]:
    row, card = _model_row(model_id)
    target = card.get("target") or row["target"]
    if not isinstance(features, dict) or not features:
        raise LabError("缺少候选特征。", 422, "no_features")
    if not isinstance(measured, dict) or target not in measured:
        raise LabError(f"measured 必须包含目标列 {target}。", 422, "missing_measurement")
    value = _to_float(measured[target])
    if value is None:
        raise LabError("实测值必须是数值。", 422, "bad_measurement")
    allowed = set(card.get("features") or [])
    unknown = [name for name in features if name not in allowed]
    if unknown:
        raise LabError(f"候选特征不属于该模型：{', '.join(unknown[:5])}", 422, "unknown_feature")
    record = dict(features)
    record[target] = value
    appended = append_rows(
        row["dataset_id"], [record], source="wet_lab", notes=notes,
        retrain_model_id=model_id if retrain else None,
    )
    retrained_model_id = ((appended.get("retrain") or {}).get("model") or {}).get("model_id")
    try:
        from . import db as evidence_db
        graph_write = evidence_db.record_feedback_evidence(
            model_id=model_id,
            dataset_id=row["dataset_id"],
            target=target,
            measured=value,
            retrained=bool(retrain and retrained_model_id),
            retrained_model_id=retrained_model_id,
            source="wet_lab",
            notes=notes,
        )
    except Exception as exc:
        graph_write = {"available": False, "written": False, "reason": str(exc)[:240]}
    appended["feedback"] = {
        "model_id": model_id, "target": target, "measured": value,
        "retrained": bool(retrain), "evidence_graph": graph_write,
    }
    return appended


def overview() -> dict[str, Any]:
    with _connect() as conn:
        dataset_count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        model_count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        latest = conn.execute("SELECT * FROM models ORDER BY created_utc DESC LIMIT 3").fetchall()
    latest_models = []
    for row in latest:
        card = json.loads(row["card_json"])
        latest_models.append({
            "id": row["id"], "target": row["target"], "algorithm": row["resolved_algorithm"],
            "metrics": json.loads(row["metrics_json"]), "dataset": card.get("dataset", {}),
            "created_utc": row["created_utc"],
        })
    demo_meta = _load_demo_meta()
    return {
        "version": __version__,
        "datasets": int(dataset_count),
        "models": int(model_count),
        "runs": int(run_count),
        "latest_models": latest_models,
        "demo": {
            "available": DEMO_CSV.exists(),
            "rows": demo_meta.get("rows"),
            "source_type": demo_meta.get("source_type"),
            "description": demo_meta.get("description"),
            "sha256": demo_meta.get("sha256"),
        },
        "policy": {
            "synthetic_requires_opt_in": True,
            "max_import_rows": MAX_IMPORT_ROWS,
            "max_dataset_rows": MAX_DATASET_ROWS,
            "no_automatic_experimental_claims": True,
        },
    }
