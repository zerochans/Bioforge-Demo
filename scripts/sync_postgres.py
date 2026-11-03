#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import auth, data, db  # noqa: E402

try:
    from psycopg.types.json import Jsonb
except Exception:
    Jsonb = None

LITERATURE_DB = Path(os.environ.get("BIOFORGE_LITERATURE_DB", "/media/h3c/Win11Pro X64/data/literature/bioforge_literature.db"))


def as_json(value):
    if value is None:
        return Jsonb([]) if Jsonb else []
    if isinstance(value, (list, dict)):
        return Jsonb(value) if Jsonb else value
    try:
        parsed = json.loads(value)
        return Jsonb(parsed) if Jsonb else parsed
    except Exception:
        return Jsonb([value]) if Jsonb else [value]


def sync_catalogs(cur):
    for source in data.sources():
        cur.execute(
            """
            INSERT INTO sources (id, name, url, license, auth, status, fields, notes, data, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (id) DO UPDATE SET name=excluded.name, url=excluded.url, license=excluded.license,
                auth=excluded.auth, status=excluded.status, fields=excluded.fields, notes=excluded.notes,
                data=excluded.data, updated_at=now()
            """,
            (
                source.get("id"), source.get("name", source.get("id", "")), source.get("url"),
                source.get("license"), source.get("auth"), source.get("status"),
                Jsonb(source.get("fields", [])) if Jsonb else source.get("fields", []),
                source.get("notes"), Jsonb(source) if Jsonb else source,
            ),
        )
    for filename in data.PACK_FILES:
        payload = data.load(filename)
        kind = filename.removesuffix(".json")
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for index, item in enumerate(items):
            item_id = str(item.get("id") or f"{kind}-{index}")
            label = item.get("title") or item.get("name") or item.get("label") or item_id
            cur.execute(
                """
                INSERT INTO catalog_items (kind, id, label, data, updated_at)
                VALUES (%s,%s,%s,%s,now())
                ON CONFLICT (kind, id) DO UPDATE SET label=excluded.label, data=excluded.data, updated_at=now()
                """,
                (kind, item_id, label, Jsonb(item) if Jsonb else item),
            )


def _rows(conn, sql):
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql)]


def sync_literature(cur):
    if not LITERATURE_DB.exists():
        return {"papers": 0, "chunks": 0, "entities": 0, "edges": 0}
    conn = sqlite3.connect(str(LITERATURE_DB))
    papers = _rows(conn, "SELECT * FROM papers")
    chunks = _rows(conn, "SELECT * FROM chunks")
    entities = _rows(conn, "SELECT * FROM entities")
    edges = _rows(conn, "SELECT * FROM edges")
    for row in papers:
        cur.execute(
            """
            INSERT INTO literature_records (
                id, source, source_id, doi, pmid, pmcid, title, abstract, authors, journal, year,
                license, is_oa, pdf_url, landing_url, category, tags, mesh, keywords, chemicals,
                retrieved_at, content_hash, fulltext_status, data
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                source=excluded.source, source_id=excluded.source_id, doi=excluded.doi, pmid=excluded.pmid,
                pmcid=excluded.pmcid, title=excluded.title, abstract=excluded.abstract, authors=excluded.authors,
                journal=excluded.journal, year=excluded.year, license=excluded.license, is_oa=excluded.is_oa,
                pdf_url=excluded.pdf_url, landing_url=excluded.landing_url, category=excluded.category,
                tags=excluded.tags, mesh=excluded.mesh, keywords=excluded.keywords, chemicals=excluded.chemicals,
                retrieved_at=excluded.retrieved_at, content_hash=excluded.content_hash,
                fulltext_status=excluded.fulltext_status, data=excluded.data
            """,
            (
                row["id"], row.get("source"), row.get("source_id"), row.get("doi"), row.get("pmid"), row.get("pmcid"),
                row["title"], row.get("abstract"), as_json(row.get("authors")), row.get("journal"), row.get("year"),
                row.get("license"), bool(row.get("is_oa")), row.get("pdf_url"), row.get("landing_url"),
                row.get("category"), as_json(row.get("tags")), as_json(row.get("mesh")), as_json(row.get("keywords")),
                as_json(row.get("chemicals")), row.get("retrieved_at"), row.get("content_hash"),
                row.get("fulltext_status"), Jsonb(row) if Jsonb else row,
            ),
        )
    cur.executemany(
        """
        INSERT INTO literature_chunks (id, paper_id, ordinal, text)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET paper_id=excluded.paper_id, ordinal=excluded.ordinal, text=excluded.text
        """,
        [(row["id"], row["paper_id"], row["ordinal"], row["text"]) for row in chunks],
    )
    cur.execute("TRUNCATE graph_entities, graph_edges")
    cur.executemany("INSERT INTO graph_entities (id, kind, label) VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                    [(row["id"], row["kind"], row["label"]) for row in entities])
    cur.executemany(
        "INSERT INTO graph_edges (src, predicate, dst, weight, evidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        [(row["src"], row["predicate"], row["dst"], row.get("weight", 1), row.get("evidence")) for row in edges],
    )
    conn.close()
    return {"papers": len(papers), "chunks": len(chunks), "entities": len(entities), "edges": len(edges)}


def sync_user(cur):
    account = auth.ensure_account()
    cur.execute(
        """
        INSERT INTO app_users (username, password_hash, salt, iterations, role, source, disabled)
        VALUES (%s,%s,%s,%s,'owner','local',false)
        ON CONFLICT (username) DO UPDATE SET password_hash=excluded.password_hash, salt=excluded.salt,
            iterations=excluded.iterations, source=excluded.source
        """,
        (account["username"], account["hash"], account["salt"], int(account.get("iterations", 240000))),
    )
    return account["username"]


def main():
    result = {"schema": db.init_schema()}
    with db.connect() as conn, conn.cursor() as cur:
        sync_catalogs(cur)
        user = sync_user(cur)
        result["literature"] = sync_literature(cur)
        result["user"] = user
        cur.execute(
            "INSERT INTO system_meta (key, value, updated_at) VALUES ('last_sync', %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=now()",
            (Jsonb({"source": "local JSON + SQLite", "literature_db": str(LITERATURE_DB), **result["literature"]}) if Jsonb else result["literature"],),
        )
        cur.execute(
            "INSERT INTO system_meta (key, value, updated_at) VALUES ('embedding', %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=now()",
            (Jsonb({"status": "pending", "dimension": 1024, "note": "pgvector column ready; no embeddings generated yet"}) if Jsonb else {},),
        )
        conn.commit()
        cur.execute("ANALYZE")
        conn.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
