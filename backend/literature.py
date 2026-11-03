from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import query_text

DB_PATH = Path(os.environ.get(
    "BIOFORGE_LITERATURE_DB",
    "/media/h3c/Win11Pro X64/data/literature/bioforge_literature.db",
))


def _connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def stats() -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        return {"available": False, "papers": 0, "notice": "本地文献库尚未建立。"}
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]
        concepts = conn.execute("""
            SELECT en.label, COUNT(*) AS n
            FROM edges e JOIN entities en ON en.id = e.dst
            WHERE e.predicate = 'mentions'
            GROUP BY e.dst ORDER BY n DESC LIMIT 8
        """).fetchall()
        return {
            "available": True,
            "papers": one("SELECT COUNT(*) FROM papers"),
            "open_access": one("SELECT COUNT(*) FROM papers WHERE is_oa = 1"),
            "with_fulltext": one("SELECT COUNT(*) FROM papers WHERE fulltext_path IS NOT NULL"),
            "chunks": one("SELECT COUNT(*) FROM chunks"),
            "entities": one("SELECT COUNT(*) FROM entities"),
            "edges": one("SELECT COUNT(*) FROM edges"),
            "top_concepts": [{"concept": row[0], "papers": row[1]} for row in concepts],
            "notice": "Europe PMC OA 元数据与本地 BM25 索引；不是系统综述。",
        }
    except sqlite3.Error as exc:
        return {"available": False, "papers": 0, "notice": f"文献库读取失败：{exc}"}
    finally:
        conn.close()


def _terms(query: str) -> list[str]:
    return query_text.terms(query)


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    expansion = query_text.expand_query(query)
    terms = query_text.terms(query)
    if not terms:
        return []
    conn = _connect()
    if conn is None:
        return []
    fts_query = " OR ".join(f'"{word}"' for word in terms)
    try:
        rows = conn.execute("""
            SELECT p.id, p.title, p.year, p.doi, p.pmcid, p.license, p.category,
                   p.tags, p.mesh, p.keywords, p.chemicals, p.abstract,
                   bm25(chunks_fts) AS bm25_rank,
                   snippet(chunks_fts, 0, '<mark>', '</mark>', '…', 20) AS snippet
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN papers p ON p.id = c.paper_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts)
            LIMIT ?
        """, (fts_query, max(1, min(60, int(limit) * 3)))).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    results = []
    for row in rows:
        item = dict(row)
        for key in ("tags", "mesh", "keywords", "chemicals"):
            raw = item.pop(key, "[]")
            try:
                item[key] = json.loads(raw or "[]")
            except ValueError:
                item[key] = []
        abstract = item.pop("abstract", "") or ""
        bm25_rank = float(item.pop("bm25_rank", 0) or 0)
        item["abstract"] = abstract[:420]
        score, matched = query_text.relevance(query, f"{item.get('title', '')} {abstract} {item.get('snippet', '')}")
        item["relevance"] = score
        item["strength"] = query_text.strength(score)
        item["match_terms"] = matched
        item["bm25"] = round(bm25_rank, 4)
        item["query_expanded"] = expansion["expanded"]
        item["url"] = (
            f"https://europepmc.org/article/PMC/{item['pmcid']}" if item.get("pmcid")
            else f"https://doi.org/{item['doi']}" if item.get("doi")
            else "https://europepmc.org/"
        )
        results.append(item)
    results.sort(key=lambda item: (item.get("relevance", 0), -float(item.get("bm25", 0))), reverse=True)
    return results[:max(1, min(30, int(limit)))]


def topic_map() -> dict[str, Any]:
    return {
        "version": "3.2",
        "rule": "title + abstract 关键词映射；MeSH/作者关键词作为附加标签。",
        "topics": {
            "docking": ["docking", "ligand binding", "binding affinity", "virtual screening"],
            "molecular-dynamics": ["molecular dynamics", "md simulation", "gromacs", "force field"],
            "protein-structure": ["protein structure", "alphafold", "crystal structure", "homology model"],
            "formulation": ["formulation", "encapsulation", "delivery system", "emulsion", "hydrogel"],
            "food-protein": ["food protein", "whey", "lactoglobulin", "casein", "soy protein", "gelatin"],
            "bioactive": ["quercetin", "curcumin", "polyphenol", "flavonoid", "bioactive peptide"],
            "maillard": ["maillard", "glycation", "browning", "advanced glycation"],
            "analytics": ["spectroscopy", "mass spectrometry", "chromatography", "nmr", "ftir"],
            "machine-learning": ["machine learning", "deep learning", "neural network", "random forest"],
            "knowledge-graph": ["knowledge graph", "ontology", "semantic web", "text mining"],
            "safety": ["toxicity", "allergen", "food safety", "risk assessment"],
        },
    }
