#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import httpx

DEFAULT_ROOT = Path("/media/h3c/Win11Pro X64/data/literature")
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
USER_AGENT = "BioForgeLiterature/1.0 (+local research; metadata and OA only)"
DEFAULT_QUERIES = [
    "protein formulation",
    "molecular dynamics protein",
    "molecular docking ligand",
    "protein structure prediction",
    "encapsulation bioactive compound",
    "Maillard reaction protein",
    "food protein functionality",
    "quercetin protein interaction",
    "curcumin delivery system",
    "whey protein beta-lactoglobulin",
    "machine learning molecular property",
    "knowledge graph biomedical literature",
]
TOPICS = {
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
}
LICENSE_ALLOW = ("cc by", "cc-by", "cc0", "cc by-nc", "cc-by-nc", "cc by-nc-nd", "cc-by-nc-nd")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(value: str, limit: int = 80) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value or "").strip("-").lower()
    return (text[:limit].strip("-") or "untitled")


def safe_name(value: str, limit: int = 120) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:limit].strip() or "untitled").replace("#", "")


def year_of(record: dict[str, Any]) -> int | None:
    try:
        return int(str(record.get("pubYear") or "")[:4])
    except ValueError:
        return None


def authors_of(record: dict[str, Any]) -> list[str]:
    raw = clean_text(record.get("authorString"))
    names = [part.strip().rstrip(".") for part in raw.split(",")]
    return [name for name in names if name and name.lower() not in {"et al", "et al."}][:30]


def topic_matches(text: str) -> list[str]:
    low = text.lower()
    found = []
    for topic, needles in TOPICS.items():
        if any(needle in low for needle in needles):
            found.append(topic)
    return found


def _named_items(raw: Any) -> list[str]:
    items = raw or []
    if isinstance(items, dict):
        items = items.get("meshHeading") or items.get("keyword") or items.get("chemical") or []
    out = []
    for item in items if isinstance(items, list) else [items]:
        if isinstance(item, dict):
            value = (
                item.get("descriptorName") or item.get("name")
                or item.get("keyword") or item.get("chemicalName") or ""
            )
            if isinstance(value, dict):
                value = value.get("name") or ""
        else:
            value = item
        value = clean_text(value)
        if value and value not in out:
            out.append(value)
    return out[:24]


def mesh_of(record: dict[str, Any]) -> list[str]:
    return _named_items(record.get("meshHeadingList"))


def keywords_of(record: dict[str, Any]) -> list[str]:
    return _named_items(record.get("keywordList"))


def chemicals_of(record: dict[str, Any]) -> list[str]:
    return _named_items(record.get("chemicalList"))


def license_ok(value: str) -> bool:
    low = (value or "").strip().lower()
    return any(low.startswith(prefix) for prefix in LICENSE_ALLOW)


def pdf_url_for(record: dict[str, Any]) -> str | None:
    license_value = clean_text(record.get("license"))
    if not license_ok(license_value):
        return None
    for item in (record.get("fullTextUrlList") or {}).get("fullTextUrl", []) or []:
        if item.get("documentStyle") in {"pdf", "PDF"} and item.get("availabilityCode") == "OA":
            url = item.get("url")
            if url:
                return url
    return None


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "bioforge_literature.db"
        self.pdf_dir = root / "pdf"
        self.xml_dir = root / "xml"
        self.fulltext_dir = root / "fulltext"
        self.obsidian_dir = root / "obsidian"
        for path in (self.pdf_dir, self.xml_dir, self.fulltext_dir, self.obsidian_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._schema()

    def _schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_id TEXT,
            doi TEXT UNIQUE,
            pmid TEXT,
            pmcid TEXT,
            title TEXT NOT NULL,
            abstract TEXT,
            authors TEXT,
            journal TEXT,
            year INTEGER,
            license TEXT,
            is_oa INTEGER DEFAULT 0,
            pdf_url TEXT,
            landing_url TEXT,
            category TEXT,
            tags TEXT,
            retrieved_at TEXT NOT NULL,
            content_hash TEXT,
            pdf_path TEXT,
            fulltext_path TEXT,
            fulltext_status TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
        CREATE INDEX IF NOT EXISTS idx_papers_category ON papers(category);
        CREATE INDEX IF NOT EXISTS idx_papers_pmcid ON papers(pmcid);
        CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
            title, abstract, authors, tags, content='papers', content_rowid='rowid'
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_paper ON chunks(paper_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text, content='chunks', content_rowid='rowid'
        );
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            label TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
            src TEXT NOT NULL,
            predicate TEXT NOT NULL,
            dst TEXT NOT NULL,
            weight REAL DEFAULT 1,
            evidence TEXT,
            PRIMARY KEY(src, predicate, dst)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(papers)").fetchall()}
        for column in ("mesh", "keywords", "chemicals"):
            if column not in columns:
                self.conn.execute(f"ALTER TABLE papers ADD COLUMN {column} TEXT")
        self.conn.commit()

    def existing_doi(self, doi: str | None) -> bool:
        if not doi:
            return False
        row = self.conn.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,)).fetchone()
        return row is not None

    def add_paper(self, record: dict[str, Any], enrich: bool = False) -> bool:
        title = clean_text(record.get("title"))
        if not title:
            return False
        doi = clean_text(record.get("doi")) or None
        if self.existing_doi(doi):
            if enrich:
                self._enrich_tags(record)
            return False
        pmid = clean_text(record.get("pmid")) or None
        pmcid = clean_text(record.get("pmcid")) or None
        key = pmid or pmcid or doi or title
        paper_id = "epmc-" + (pmid or pmcid or hashlib.sha1(key.encode("utf-8")).hexdigest()[:16])
        abstract = clean_text(record.get("abstractText"))
        authors = authors_of(record)
        journal = clean_text(record.get("journalTitle") or (record.get("journalInfo") or {}).get("journal", {}).get("title"))
        license_value = clean_text(record.get("license"))
        tags = sorted(set(topic_matches(title + " " + abstract)))
        mesh = mesh_of(record)
        keywords = keywords_of(record)
        chemicals = chemicals_of(record)
        body_hash = hashlib.sha256((title + "\n" + abstract).encode("utf-8")).hexdigest()
        landing = f"https://europepmc.org/article/MED/{pmid}" if pmid else (f"https://doi.org/{doi}" if doi else None)
        row = (
            paper_id, "Europe PMC", pmid or pmcid or doi, doi, pmid, pmcid, title, abstract,
            json.dumps(authors, ensure_ascii=False), journal, year_of(record), license_value,
            1 if clean_text(record.get("isOpenAccess")).upper() == "Y" else 0,
            pdf_url_for(record), landing, tags[0] if tags else "general",
            json.dumps(tags, ensure_ascii=False), now(), body_hash, None, None, None,
            json.dumps(mesh, ensure_ascii=False), json.dumps(keywords, ensure_ascii=False),
            json.dumps(chemicals, ensure_ascii=False),
        )
        try:
            cur = self.conn.execute("""
            INSERT OR IGNORE INTO papers (
                id, source, source_id, doi, pmid, pmcid, title, abstract, authors, journal,
                year, license, is_oa, pdf_url, landing_url, category, tags, retrieved_at,
                content_hash, pdf_path, fulltext_path, fulltext_status, mesh, keywords, chemicals
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, row)
        except sqlite3.IntegrityError:
            return False
        if cur.rowcount == 0:
            return False
        db_row = self.conn.execute("SELECT rowid FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if db_row:
            searchable = " ".join(tags + mesh + keywords + chemicals)
            self.conn.execute("INSERT INTO papers_fts(rowid,title,abstract,authors,tags) VALUES (?,?,?,?,?)",
                              (db_row["rowid"], title, abstract, " ".join(authors), searchable))
            self._index_chunks(paper_id, title, abstract)
            self._index_graph(paper_id, title, authors, journal, tags)
        return True

    def _enrich_tags(self, record: dict[str, Any]) -> None:
        pmid = clean_text(record.get("pmid")) or None
        doi = clean_text(record.get("doi")) or None
        row = None
        if pmid:
            row = self.conn.execute("SELECT * FROM papers WHERE pmid=?", (pmid,)).fetchone()
        if row is None and doi:
            row = self.conn.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone()
        if row is None:
            return
        title = row["title"] or clean_text(record.get("title"))
        abstract = row["abstract"] or clean_text(record.get("abstractText"))
        tags = sorted(set(topic_matches(title + " " + abstract)))
        mesh = mesh_of(record)
        keywords = keywords_of(record)
        chemicals = chemicals_of(record)
        self.conn.execute(
            "UPDATE papers SET tags=?, category=?, mesh=?, keywords=?, chemicals=? WHERE id=?",
            (json.dumps(tags, ensure_ascii=False), tags[0] if tags else "general",
             json.dumps(mesh, ensure_ascii=False), json.dumps(keywords, ensure_ascii=False),
             json.dumps(chemicals, ensure_ascii=False), row["id"]),
        )

    def _chunk(self, text: str, size: int = 1000, overlap: int = 150) -> Iterable[str]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            chunk = text[start:start + size].strip()
            if chunk:
                chunks.append(chunk)
            start += size - overlap
        return chunks

    def _index_chunks(self, paper_id: str, title: str, abstract: str) -> None:
        for ordinal, chunk in enumerate(self._chunk(title + "\n" + abstract)):
            cur = self.conn.execute("INSERT INTO chunks(paper_id,ordinal,text) VALUES (?,?,?)", (paper_id, ordinal, chunk))
            self.conn.execute("INSERT INTO chunks_fts(rowid,text) VALUES (?,?)", (cur.lastrowid, chunk))

    def _entity(self, entity_id: str, kind: str, label: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO entities(id,kind,label) VALUES (?,?,?)", (entity_id, kind, label))

    def _edge(self, src: str, predicate: str, dst: str, weight: float = 1.0, evidence: str | None = None) -> None:
        self.conn.execute("INSERT OR IGNORE INTO edges(src,predicate,dst,weight,evidence) VALUES (?,?,?,?,?)",
                          (src, predicate, dst, weight, evidence))

    def _index_graph(self, paper_id: str, title: str, authors: list[str], journal: str, tags: list[str]) -> None:
        node = "paper:" + paper_id
        self._entity(node, "paper", title[:180])
        for topic in tags:
            target = "concept:" + slug(topic)
            self._entity(target, "concept", topic.replace("-", " "))
            self._edge(node, "mentions", target, 1.0, "title/abstract keyword")
        for author in authors[:8]:
            target = "author:" + slug(author, 120)
            self._entity(target, "author", author)
            self._edge(node, "authored_by", target, 1.0, "Europe PMC authorString")
        if journal:
            target = "journal:" + slug(journal, 120)
            self._entity(target, "journal", journal)
            self._edge(node, "published_in", target, 1.0, "Europe PMC journalTitle")

    def commit(self) -> None:
        self.conn.commit()

    def _xml_to_markdown(self, payload: bytes) -> str:
        root = ET.fromstring(payload)
        pieces: list[str] = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag not in {"title", "p", "caption"}:
                continue
            text = clean_text("".join(elem.itertext()))
            if len(text) < 2:
                continue
            if tag == "title":
                pieces.append("\n## " + text + "\n")
            else:
                pieces.append(text + "\n")
        return "\n".join(pieces).strip()

    def _store_fulltext(self, paper_id: str, text: str, xml: bytes | None = None) -> bool:
        if len(text.strip()) < 200:
            return False
        target = self.fulltext_dir / f"{paper_id}.md"
        target.write_text(text + "\n", encoding="utf-8")
        if xml:
            (self.xml_dir / f"{paper_id}.xml").write_bytes(xml)
        self.conn.execute("UPDATE papers SET fulltext_path = ?, fulltext_status = 'markdown' WHERE id = ?",
                          (str(target.relative_to(self.root)), paper_id))
        row = self.conn.execute("SELECT title, abstract FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if row:
            for ordinal, chunk in enumerate(self._chunk(clean_text(row["title"]) + "\n" + text)):
                cur = self.conn.execute("INSERT INTO chunks(paper_id,ordinal,text) VALUES (?,?,?)", (paper_id, 1000 + ordinal, chunk))
                self.conn.execute("INSERT INTO chunks_fts(rowid,text) VALUES (?,?)", (cur.lastrowid, chunk))
        self.conn.commit()
        return True

    def download_pdfs(self, limit: int, delay: float = 1.0) -> int:
        if limit <= 0:
            return 0
        rows = self.conn.execute("""
            SELECT id, pmcid, pdf_url, license FROM papers
            WHERE is_oa = 1 AND fulltext_path IS NULL AND (pdf_url IS NOT NULL OR pmcid IS NOT NULL)
            ORDER BY year DESC LIMIT ?
        """, (limit,)).fetchall()
        completed = 0
        with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            for row in rows:
                if not license_ok(row["license"] or ""):
                    continue
                got = False
                if row["pdf_url"]:
                    target = self.pdf_dir / f"{row['id']}.pdf"
                    try:
                        with client.stream("GET", row["pdf_url"]) as response:
                            response.raise_for_status()
                            total = 0
                            tmp = target.with_suffix(".part")
                            with tmp.open("wb") as handle:
                                for chunk in response.iter_bytes(65536):
                                    total += len(chunk)
                                    if total > 40 * 1024 * 1024:
                                        raise RuntimeError("PDF exceeds 40 MB")
                                    handle.write(chunk)
                            if total >= 1000 and tmp.read_bytes()[:4] == b"%PDF":
                                tmp.replace(target)
                                self.conn.execute("UPDATE papers SET pdf_path = ?, fulltext_status = 'pdf' WHERE id = ?",
                                                  (str(target.relative_to(self.root)), row["id"]))
                                self.conn.commit()
                                try:
                                    result = subprocess.run(["pdftotext", "-layout", str(target), "-"], capture_output=True, text=True, timeout=120)
                                    if result.returncode == 0 and self._store_fulltext(row["id"], result.stdout):
                                        got = True
                                except Exception:
                                    pass
                            else:
                                tmp.unlink(missing_ok=True)
                    except Exception as exc:
                        self.conn.execute("UPDATE papers SET fulltext_status = ? WHERE id = ?", (f"pdf_error:{str(exc)[:120]}", row["id"]))
                        self.conn.commit()
                if not got and row["pmcid"]:
                    try:
                        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{row['pmcid']}/fullTextXML"
                        response = client.get(url)
                        response.raise_for_status()
                        xml = response.content
                        text = self._xml_to_markdown(xml)
                        if self._store_fulltext(row["id"], text, xml):
                            got = True
                    except Exception as exc:
                        self.conn.execute("UPDATE papers SET fulltext_status = ? WHERE id = ?", (f"xml_error:{str(exc)[:120]}", row["id"]))
                        self.conn.commit()
                if got:
                    completed += 1
                time.sleep(delay)
        return completed

    def export_obsidian(self) -> int:
        rows = self.conn.execute("SELECT * FROM papers ORDER BY year DESC, title").fetchall()
        count = 0
        for row in rows:
            year = row["year"] or "unknown"
            folder = self.obsidian_dir / str(year)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{safe_name(row['title'], 110)} -- {row['id']}.md"
            tags = json.loads(row["tags"] or "[]")
            mesh = json.loads(row["mesh"] or "[]") if "mesh" in row.keys() else []
            keywords = json.loads(row["keywords"] or "[]") if "keywords" in row.keys() else []
            chemicals = json.loads(row["chemicals"] or "[]") if "chemicals" in row.keys() else []
            authors = json.loads(row["authors"] or "[]")
            all_tags = tags + [f"mesh/{slug(item)}" for item in mesh] + \
                [f"keyword/{slug(item)}" for item in keywords] + \
                [f"chemical/{slug(item)}" for item in chemicals]
            front = [
                "---",
                f"title: {json.dumps(row['title'], ensure_ascii=False)}",
                f"doi: {json.dumps(row['doi'] or '', ensure_ascii=False)}",
                f"pmid: {row['pmid'] or ''}",
                f"pmcid: {row['pmcid'] or ''}",
                f"year: {row['year'] or ''}",
                f"journal: {json.dumps(row['journal'] or '', ensure_ascii=False)}",
                f"license: {json.dumps(row['license'] or '', ensure_ascii=False)}",
                f"source: {json.dumps(row['source'], ensure_ascii=False)}",
                f"url: {json.dumps(row['landing_url'] or '', ensure_ascii=False)}",
                "tags:",
                "  - literature",
                "  - open-access" if row["is_oa"] else "  - metadata-only",
            ]
            front += [f"  - topic/{tag}" for tag in tags[:12]]
            front += [f"  - {tag}" for tag in all_tags[len(tags):][:24]]
            front.append("---")
            body = [
                "",
                f"# {row['title']}",
                "",
                f"- 作者：{', '.join(authors[:12]) or '—'}",
                f"- 期刊：{row['journal'] or '—'}",
                f"- 年份：{row['year'] or '—'}",
                f"- DOI：{row['doi'] or '—'}",
                f"- 许可：{row['license'] or '未标注'}",
                f"- 来源：{row['landing_url'] or '—'}",
                "",
                "## 摘要",
                "",
                row["abstract"] or "无摘要。",
                "",
                "## 分类",
                "",
                ", ".join(f"`{tag}`" for tag in tags) or "`general`",
            ]
            if mesh or keywords or chemicals:
                body += ["", "## 主题词与关键词", ""]
                if mesh:
                    body += ["- MeSH：" + "; ".join(mesh)]
                if keywords:
                    body += ["- 作者关键词：" + "; ".join(keywords)]
                if chemicals:
                    body += ["- 化合物：" + "; ".join(chemicals)]
            if row["fulltext_path"]:
                body += ["", "## 全文", "", f"转换文本：`{row['fulltext_path']}`"]
            path.write_text("\n".join(front + body) + "\n", encoding="utf-8")
            count += 1
        return count

    def stats(self) -> dict[str, Any]:
        one = lambda sql: self.conn.execute(sql).fetchone()[0]
        concepts = self.conn.execute("SELECT label, COUNT(*) AS n FROM edges e JOIN entities en ON en.id=e.dst WHERE e.predicate='mentions' GROUP BY e.dst ORDER BY n DESC LIMIT 10").fetchall()
        return {
            "papers": one("SELECT COUNT(*) FROM papers"),
            "open_access": one("SELECT COUNT(*) FROM papers WHERE is_oa=1"),
            "with_pdf": one("SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL"),
            "with_fulltext_md": one("SELECT COUNT(*) FROM papers WHERE fulltext_path IS NOT NULL"),
            "chunks": one("SELECT COUNT(*) FROM chunks"),
            "entities": one("SELECT COUNT(*) FROM entities"),
            "edges": one("SELECT COUNT(*) FROM edges"),
            "top_concepts": [{"concept": row[0], "papers": row[1]} for row in concepts],
            "db": str(self.db_path),
        }

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        words = [word for word in re.findall(r"[\w\-]+", query) if len(word) > 1][:12]
        if not words:
            return []
        fts_query = " OR ".join(f'"{word}"' for word in words)
        try:
            rows = self.conn.execute("""
                SELECT p.id, p.title, p.year, p.doi, p.license, p.category,
                       snippet(chunks_fts, 0, '<mark>', '</mark>', '…', 18) AS snippet
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                JOIN papers p ON p.id = c.paper_id
                WHERE chunks_fts MATCH ?
                ORDER BY bm25(chunks_fts)
                LIMIT ?
            """, (fts_query, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


def harvest(store: Store, queries: list[str], target: int, page_size: int = 1000, delay: float = 0.4,
            max_pages_per_query: int = 20) -> int:
    added = 0
    with httpx.Client(timeout=45, headers={"User-Agent": USER_AGENT}) as client:
        for query in queries:
            if added >= target:
                break
            cursor = "*"
            pages = 0
            while added < target and pages < max_pages_per_query:
                params = {
                    "query": f"({query}) AND OPEN_ACCESS:Y",
                    "format": "json",
                    "resultType": "core",
                    "pageSize": str(min(1000, page_size)),
                    "cursorMark": cursor,
                }
                try:
                    response = client.get(EPMC, params=params)
                    response.raise_for_status()
                    payload = response.json()
                except Exception as exc:
                    print(f"[warn] {query}: {exc}", file=sys.stderr)
                    break
                records = (payload.get("resultList") or {}).get("result") or []
                if not records:
                    break
                before = added
                for record in records:
                    if store.add_paper(record):
                        added += 1
                        if added % 100 == 0:
                            store.commit()
                            print(f"[harvest] {added}/{target} papers")
                    if added >= target:
                        break
                store.commit()
                pages += 1
                next_cursor = payload.get("nextCursorMark")
                print(f"[page] query={query!r} page={pages} fetched={len(records)} new={added - before} total={added}")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
                time.sleep(delay)
                if added - before == 0 and pages >= 2:
                    break
    return added


def enrich_metadata(store: Store, limit: int = 0) -> int:
    rows = store.conn.execute(
        "SELECT id, pmid, doi FROM papers WHERE mesh IS NULL OR keywords IS NULL "
        "ORDER BY year DESC LIMIT ?", (limit or 100000,)
    ).fetchall()
    targets = [row for row in rows if row["pmid"]]
    updated = 0
    with httpx.Client(timeout=45, headers={"User-Agent": USER_AGENT}) as client:
        for start in range(0, len(targets), 50):
            batch = targets[start:start + 50]
            query = " OR ".join(f"EXT_ID:{row['pmid']}" for row in batch)
            try:
                response = client.get(EPMC, params={
                    "query": query, "format": "json", "resultType": "core", "pageSize": "100",
                })
                response.raise_for_status()
                records = (response.json().get("resultList") or {}).get("result") or []
            except Exception as exc:
                print(f"[warn] enrich batch {start}: {exc}", file=sys.stderr)
                continue
            for record in records:
                store._enrich_tags(record)
                updated += 1
            store.commit()
            print(f"[enrich] {min(start + 50, len(targets))}/{len(targets)} records={updated}")
            time.sleep(0.35)
    return updated


def build_index(store: Store) -> None:
    rows = store.conn.execute("SELECT * FROM papers").fetchall()
    store.conn.execute("DELETE FROM papers_fts")
    store.conn.execute("DELETE FROM chunks")
    store.conn.execute("DELETE FROM chunks_fts")
    store.conn.execute("DELETE FROM entities")
    store.conn.execute("DELETE FROM edges")
    for row in rows:
        db_row = store.conn.execute("SELECT rowid FROM papers WHERE id=?", (row["id"],)).fetchone()
        tags = json.loads(row["tags"] or "[]")
        authors = json.loads(row["authors"] or "[]")
        mesh = json.loads(row["mesh"] or "[]") if "mesh" in row.keys() else []
        keywords = json.loads(row["keywords"] or "[]") if "keywords" in row.keys() else []
        chemicals = json.loads(row["chemicals"] or "[]") if "chemicals" in row.keys() else []
        searchable = " ".join(tags + mesh + keywords + chemicals)
        if db_row:
            store.conn.execute("INSERT INTO papers_fts(rowid,title,abstract,authors,tags) VALUES (?,?,?,?,?)",
                               (db_row["rowid"], row["title"], row["abstract"] or "", " ".join(authors), searchable))
            store._index_chunks(row["id"], row["title"], row["abstract"] or "")
            store._index_graph(row["id"], row["title"], authors, row["journal"] or "", tags)
    store.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="BioForge OA literature -> Obsidian -> RAG -> knowledge graph")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("harvest")
    p.add_argument("--query", action="append", help="Europe PMC query; repeatable")
    p.add_argument("--target", type=int, default=10000)
    p.add_argument("--pdf-limit", type=int, default=0)
    p.add_argument("--no-export", action="store_true")
    p.add_argument("--build", action="store_true")

    p = sub.add_parser("build")
    p.add_argument("--export", action="store_true")

    p = sub.add_parser("enrich")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-export", action="store_true")

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)

    sub.add_parser("stats")

    args = parser.parse_args()
    store = Store(args.root)
    try:
        if args.command == "harvest":
            queries = args.query or DEFAULT_QUERIES
            added = harvest(store, queries, args.target)
            if args.build:
                build_index(store)
            if args.pdf_limit:
                print(f"[pdf] downloaded={store.download_pdfs(args.pdf_limit)}")
            if not args.no_export:
                print(f"[obsidian] notes={store.export_obsidian()}")
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        elif args.command == "build":
            build_index(store)
            if args.export:
                print(f"[obsidian] notes={store.export_obsidian()}")
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        elif args.command == "enrich":
            updated = enrich_metadata(store, args.limit)
            build_index(store)
            if not args.no_export:
                print(f"[obsidian] notes={store.export_obsidian()}")
            print(json.dumps({"enriched": updated, **store.stats()}, ensure_ascii=False, indent=2))
        elif args.command == "search":
            print(json.dumps(store.search(args.query, args.limit), ensure_ascii=False, indent=2))
        elif args.command == "stats":
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
