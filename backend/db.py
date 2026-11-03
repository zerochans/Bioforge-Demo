from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import data

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except Exception:
    psycopg = None
    dict_row = None
    Jsonb = None

SCHEMA = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS app_users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        salt TEXT,
        iterations INTEGER DEFAULT 240000,
        role TEXT NOT NULL DEFAULT 'member',
        source TEXT NOT NULL DEFAULT 'local',
        disabled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_login TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT,
        license TEXT,
        auth TEXT,
        status TEXT,
        fields JSONB NOT NULL DEFAULT '[]'::jsonb,
        notes TEXT,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_items (
        kind TEXT NOT NULL,
        id TEXT NOT NULL,
        label TEXT,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (kind, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS literature_records (
        id TEXT PRIMARY KEY,
        source TEXT,
        source_id TEXT,
        doi TEXT UNIQUE,
        pmid TEXT,
        pmcid TEXT,
        title TEXT NOT NULL,
        abstract TEXT,
        authors JSONB NOT NULL DEFAULT '[]'::jsonb,
        journal TEXT,
        year INTEGER,
        license TEXT,
        is_oa BOOLEAN NOT NULL DEFAULT FALSE,
        pdf_url TEXT,
        landing_url TEXT,
        category TEXT,
        tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        mesh JSONB NOT NULL DEFAULT '[]'::jsonb,
        keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
        chemicals JSONB NOT NULL DEFAULT '[]'::jsonb,
        retrieved_at TEXT,
        content_hash TEXT,
        fulltext_status TEXT,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        tsv TSVECTOR GENERATED ALWAYS AS (
            to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || coalesce(abstract, '') || ' ' || coalesce(journal, ''))
        ) STORED
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS literature_chunks (
        id BIGINT PRIMARY KEY,
        paper_id TEXT NOT NULL REFERENCES literature_records(id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding vector(1024),
        embedding_model TEXT,
        tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, coalesce(text, ''))) STORED,
        UNIQUE (paper_id, ordinal)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_entities (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        label TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_edges (
        src TEXT NOT NULL,
        predicate TEXT NOT NULL,
        dst TEXT NOT NULL,
        weight DOUBLE PRECISION DEFAULT 1,
        evidence TEXT,
        PRIMARY KEY (src, predicate, dst)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id BIGSERIAL PRIMARY KEY,
        username TEXT,
        action TEXT NOT NULL,
        target TEXT,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS system_meta (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS sources_status_idx ON sources(status)",
    "CREATE INDEX IF NOT EXISTS catalog_items_kind_idx ON catalog_items(kind)",
    "CREATE INDEX IF NOT EXISTS literature_records_year_idx ON literature_records(year DESC)",
    "CREATE INDEX IF NOT EXISTS literature_records_doi_idx ON literature_records(doi)",
    "CREATE INDEX IF NOT EXISTS literature_records_tsv_idx ON literature_records USING GIN(tsv)",
    "CREATE INDEX IF NOT EXISTS literature_chunks_paper_idx ON literature_chunks(paper_id)",
    "CREATE INDEX IF NOT EXISTS literature_chunks_tsv_idx ON literature_chunks USING GIN(tsv)",
    "CREATE INDEX IF NOT EXISTS audit_events_created_idx ON audit_events(created_at DESC)",
)


def _env_file() -> dict[str, str]:
    path = data.RUNTIME_DIR / "secrets" / "postgres.env"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or _env_file().get("DATABASE_URL", "")


def enabled() -> bool:
    return bool(dsn()) and psycopg is not None


def connect():
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    url = dsn()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(url, connect_timeout=4, row_factory=dict_row)


def init_schema() -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in SCHEMA:
                cur.execute(statement)
        conn.commit()
    return {"ok": True, "statements": len(SCHEMA)}


def health() -> dict[str, Any]:
    if not enabled():
        return {"available": False, "reason": "DATABASE_URL or psycopg missing"}
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db, current_user AS username, version() AS version")
            row = cur.fetchone()
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ext = cur.fetchone()
            return {
                "available": True,
                "database": row["db"],
                "username": row["username"],
                "version": row["version"].split(" on ")[0],
                "pgvector": ext["extversion"] if ext else None,
            }
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:240]}


def status() -> dict[str, Any]:
    base = health()
    if not base.get("available"):
        return base
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT count(*) FROM sources) AS sources,
                    (SELECT count(*) FROM catalog_items) AS catalog_items,
                    (SELECT count(*) FROM literature_records) AS literature_records,
                    (SELECT count(*) FROM literature_chunks) AS literature_chunks,
                    (SELECT count(*) FROM literature_chunks WHERE embedding IS NOT NULL) AS embeddings,
                    (SELECT count(*) FROM graph_entities) AS graph_entities,
                    (SELECT count(*) FROM graph_edges) AS graph_edges,
                    (SELECT count(*) FROM app_users) AS users,
                    (SELECT pg_size_pretty(pg_database_size(current_database()))) AS size
            """)
            counts = cur.fetchone()
            cur.execute("SELECT key, value, updated_at FROM system_meta ORDER BY key")
            meta = {row["key"]: {"value": row["value"], "updated_at": row["updated_at"].isoformat()} for row in cur.fetchall()}
        return {
            **base,
            "counts": counts,
            "meta": meta,
            "search": "PostgreSQL tsvector + pgvector-ready chunks",
            "note": "embedding 列为 pgvector(1024)，当前未生成向量；先保留可复现的文本检索，后续接入嵌入模型后再回填。",
        }
    except Exception as exc:
        return {**base, "available": False, "reason": str(exc)[:240]}


def _json(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, (list, dict)):
        return value
    try:
        import json
        return json.loads(value)
    except Exception:
        return value


def search_literature(query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(50, int(limit)))
    with connect() as conn, conn.cursor() as cur:
        try:
            cur.execute("""
                SELECT id, source, doi, pmid, pmcid, title, abstract, authors, journal, year, license,
                       is_oa, landing_url, pdf_url, category, tags, mesh, keywords, chemicals,
                       ts_rank(tsv, websearch_to_tsquery('simple', %s)) AS rank
                FROM literature_records
                WHERE tsv @@ websearch_to_tsquery('simple', %s)
                   OR title ILIKE %s
                   OR abstract ILIKE %s
                ORDER BY rank DESC, year DESC NULLS LAST
                LIMIT %s
            """, (q, q, f"%{q}%", f"%{q}%", limit))
            rows = cur.fetchall()
        except Exception:
            cur.execute("""
                SELECT id, source, doi, pmid, pmcid, title, abstract, authors, journal, year, license,
                       is_oa, landing_url, pdf_url, category, tags, mesh, keywords, chemicals,
                       0::float AS rank
                FROM literature_records
                WHERE title ILIKE %s OR abstract ILIKE %s
                ORDER BY year DESC NULLS LAST
                LIMIT %s
            """, (f"%{q}%", f"%{q}%", limit))
            rows = cur.fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["authors"] = _json(item.get("authors"))
        for key in ("tags", "mesh", "keywords", "chemicals"):
            item[key] = _json(item.get(key))
        if item.get("doi"):
            item["url"] = f"https://doi.org/{item['doi']}"
        elif item.get("pmid"):
            item["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/"
        else:
            item["url"] = item.get("landing_url") or ""
        items.append(item)
    return items


def record_feedback_evidence(
    *,
    model_id: str,
    dataset_id: str,
    target: str,
    measured: float,
    retrained: bool = False,
    retrained_model_id: str | None = None,
    source: str = "wet_lab",
    notes: str = "",
) -> dict[str, Any]:
    """Write a lab feedback observation into the PostgreSQL evidence graph.

    The graph is only a provenance index: the observation remains in the Lab
    SQLite dataset. This function is best-effort and never blocks lab writes.
    """
    if not enabled():
        return {"available": False, "reason": "PostgreSQL not configured", "written": False}
    import hashlib
    import json as _json
    from datetime import datetime, timezone

    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = hashlib.sha256(
        _json.dumps({"model": model_id, "dataset": dataset_id, "target": target, "measured": measured, "created": created}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    feedback_id = f"feedback:{digest}"
    model_entity = f"model:{model_id}"
    dataset_entity = f"dataset:{dataset_id}"
    label = f"wet-lab feedback · {target}={measured:g}"
    evidence = _json.dumps({
        "target": target,
        "measured": measured,
        "source": source,
        "retrained": bool(retrained),
        "retrained_model_id": retrained_model_id,
        "created_utc": created,
        "notes": notes[:500],
    }, ensure_ascii=False)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO graph_entities (id, kind, label) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label",
                (feedback_id, "lab_feedback", label),
            )
            cur.execute(
                "INSERT INTO graph_entities (id, kind, label) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label",
                (model_entity, "model", model_id),
            )
            cur.execute(
                "INSERT INTO graph_entities (id, kind, label) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label",
                (dataset_entity, "dataset", dataset_id),
            )
            edges = [
                (model_entity, "evaluated_by", feedback_id, 1.0, evidence),
                (feedback_id, "appended_to", dataset_entity, 1.0, evidence),
                (feedback_id, "updates", model_entity, 1.0 if retrained else 0.5, evidence),
            ]
            if retrained_model_id:
                new_model = f"model:{retrained_model_id}"
                cur.execute(
                    "INSERT INTO graph_entities (id, kind, label) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label",
                    (new_model, "model", retrained_model_id),
                )
                edges.append((feedback_id, "triggered_retrain", new_model, 1.0, evidence))
            for src, predicate, dst, weight, payload in edges:
                cur.execute(
                    "INSERT INTO graph_edges (src, predicate, dst, weight, evidence) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (src, predicate, dst) DO UPDATE SET weight = EXCLUDED.weight, evidence = EXCLUDED.evidence",
                    (src, predicate, dst, weight, payload),
                )
        return {"available": True, "written": True, "feedback_id": feedback_id, "edges": len(edges)}
    except Exception as exc:
        return {"available": True, "written": False, "reason": str(exc)[:240]}
