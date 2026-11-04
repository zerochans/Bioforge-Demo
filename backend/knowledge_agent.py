from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import httpx

from . import data, literature, query_text, rag_store

try:
    from langchain_core.documents import Document
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    Document = None  # type: ignore[assignment]
    StrOutputParser = None  # type: ignore[assignment]
    ChatPromptTemplate = None  # type: ignore[assignment]
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]
    LANGGRAPH_AVAILABLE = False

try:
    from langchain_ollama import ChatOllama

    LANGCHAIN_OLLAMA_AVAILABLE = True
except Exception:
    ChatOllama = None  # type: ignore[assignment]
    LANGCHAIN_OLLAMA_AVAILABLE = False


RAG_DIR = data.RUNTIME_DIR / "rag"
CACHE_DIR = RAG_DIR / "cache"
OLLAMA_URL = os.environ.get("BIOFORGE_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("BIOFORGE_OLLAMA_MODEL", "qwen3.8:27b")
LLM_MODE = os.environ.get("BIOFORGE_RAG_LLM", "auto").strip().lower()
EXTERNAL_MODE = os.environ.get("BIOFORGE_RAG_EXTERNAL", "1").strip().lower()
HTTP_TIMEOUT = float(os.environ.get("BIOFORGE_RAG_TIMEOUT", "18"))
MAX_EVIDENCE = 12
MAX_ITERATIONS = 2
CACHE_TTL = 24 * 3600
QUALITY_STRONG = 0.72
QUALITY_MODERATE = 0.45
QUALITY_WEAK = 0.25


class RAGState(TypedDict, total=False):
    question: str
    run_id: str
    iteration: int
    max_iterations: int
    external_requested: bool
    external_done: bool
    prior_run_id: str
    original_question: str
    query_plan: dict[str, Any]
    evidence: list[dict[str, Any]]
    graph: dict[str, Any]
    quality: dict[str, Any]
    draft: str
    citations: list[dict[str, Any]]
    verification: dict[str, Any]
    warnings: list[str]
    route: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    external_errors: list[str]
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"R{stamp}-{uuid.uuid4().hex[:8]}"


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _external_enabled() -> bool:
    return _env_bool("BIOFORGE_RAG_EXTERNAL", external_default())


def external_default() -> bool:
    return EXTERNAL_MODE not in {"0", "false", "no", "off"}


def _llm_enabled() -> bool:
    return LLM_MODE not in {"0", "false", "no", "off", "none"}


def engine_status() -> dict[str, Any]:
    return {
        "engine": "bioforge-rag",
        "version": "3.3",
        "orchestrator": "langgraph" if LANGGRAPH_AVAILABLE else "sequential-fallback",
        "langgraph_installed": LANGGRAPH_AVAILABLE,
        "langchain_ollama_installed": LANGCHAIN_OLLAMA_AVAILABLE,
        "deepagents_note": "DeepAgent needs Python >=3.11; optional worker only. Active path is LangGraph.",
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "llm_enabled": _llm_enabled(),
        "external_enabled": _external_enabled(),
        "local_literature": literature.stats(),
        "store": rag_store.stats(),
        "limits": {"max_evidence": MAX_EVIDENCE, "max_iterations": MAX_ITERATIONS},
    }


def _source_key(item: dict[str, Any]) -> str:
    doi = (item.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return "title:" + re.sub(r"\W+", "", (item.get("title") or "").lower())[:180]


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        key = _source_key(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _assign_citations(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, item in enumerate(evidence, start=1):
        item["evidence_id"] = f"E{index}"
    return evidence


def _local_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"local:{row.get('id')}",
        "paper_id": row.get("id"),
        "source": "Local SQLite BM25",
        "source_type": "paper",
        "title": row.get("title") or "",
        "year": row.get("year"),
        "doi": row.get("doi") or "",
        "pmcid": row.get("pmcid") or "",
        "url": row.get("url") or "",
        "snippet": re.sub(r"</?mark>", "", row.get("snippet") or ""),
        "abstract": row.get("abstract") or "",
        "relevance": float(row.get("relevance") or 0),
        "strength": row.get("strength") or "low",
        "license": row.get("license") or "",
        "oa": True,
        "fulltext": False,
        "match_terms": row.get("match_terms") or [],
        "provenance": "local-bm25",
        "retrieved_at": _now(),
    }


def _local_retrieve(question: str) -> list[dict[str, Any]]:
    rows = literature.search(question, limit=10)
    return [_local_item(row) for row in rows]


def _graph_expand(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    paper_ids = [str(item.get("paper_id")) for item in evidence if item.get("source_type") == "paper" and item.get("paper_id")]
    nodes: list[dict[str, Any]] = [{"id": "query:current", "type": "query", "label": "当前问题", "status": "verified_by_user_input"}]
    edges: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    paper_titles = {
        str(item.get("paper_id")): item.get("title") or str(item.get("paper_id"))
        for item in evidence if item.get("paper_id")
    }
    for paper_id in paper_ids[:8]:
        nodes.append({"id": f"local:{paper_id}", "type": "local_paper", "label": paper_titles.get(paper_id, paper_id)[:160], "status": "local_oa_metadata"})
        edges.append({
            "source": "query:current",
            "target": f"local:{paper_id}",
            "predicate": "retrieves",
            "label": "本地检索命中",
            "provenance": "local_bm25",
            "status": "retrieved",
            "weight": 1.0,
        })
    if not paper_ids:
        return {"nodes": nodes, "edges": edges, "concepts": concepts, "available": False, "notice": "没有本地论文节点可扩展。"}
    graph_path = Path(literature.DB_PATH)
    if not graph_path.exists():
        return {"nodes": nodes, "edges": edges, "concepts": concepts, "available": False, "notice": "本地知识图谱不可用。"}
    conn = sqlite3.connect(f"file:{graph_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        ids = [f"paper:{paper_id}" for paper_id in paper_ids[:8]]
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT e.src, e.predicate, e.dst, e.weight, en.label, en.kind
            FROM edges e JOIN entities en ON en.id = e.dst
            WHERE e.src IN ({placeholders}) AND e.predicate = 'mentions'
            ORDER BY e.weight DESC, en.label LIMIT 30
            """,
            ids,
        ).fetchall()
        concept_counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            cid = row["dst"]
            if cid not in concept_counts:
                concept_counts[cid] = {
                    "id": cid,
                    "type": "concept",
                    "label": row["label"],
                    "kind": row["kind"],
                    "papers": 0,
                    "weight": 0.0,
                    "status": "derived_from_metadata",
                }
                nodes.append(concept_counts[cid])
            concept_counts[cid]["papers"] += 1
            concept_counts[cid]["weight"] = round(max(concept_counts[cid]["weight"], float(row["weight"] or 1)), 3)
            edges.append({
                "source": row["src"].replace("paper:", "local:"),
                "target": cid,
                "predicate": "mentions",
                "label": "提及",
                "provenance": "metadata_keyword",
                "status": "derived_from_metadata",
                "weight": round(float(row["weight"] or 1), 3),
            })
        groups = conn.execute(
            f"""
            SELECT a.dst AS left_id, b.dst AS right_id, COUNT(*) AS n
            FROM edges a JOIN edges b ON a.src = b.src
            WHERE a.src IN ({placeholders}) AND b.src IN ({placeholders})
              AND a.predicate = 'mentions' AND b.predicate = 'mentions'
              AND a.dst < b.dst
            GROUP BY a.dst, b.dst ORDER BY n DESC LIMIT 12
            """,
            ids + ids,
        ).fetchall()
        for group in groups:
            label = "共现"
            edges.append({
                "source": group["left_id"],
                "target": group["right_id"],
                "predicate": "co_occurs_with",
                "label": label,
                "provenance": "metadata_keyword",
                "status": "hypothesis_needs_validation",
                "weight": round(min(1.0, 0.35 + float(group["n"]) * 0.12), 3),
            })
        concepts = sorted(concept_counts.values(), key=lambda item: (item["papers"], item["weight"]), reverse=True)[:12]
        return {
            "nodes": nodes[:80],
            "edges": edges[:80],
            "concepts": concepts,
            "available": True,
            "backend": "sqlite-literature-graph",
            "notice": "标签来自标题/摘要关键词与作者关键词；共现关系不是因果或机制证明。",
        }
    except sqlite3.Error as exc:
        return {"nodes": nodes, "edges": edges, "concepts": concepts, "available": False, "notice": f"图谱读取失败：{exc}"}
    finally:
        conn.close()


def _add_external_graph(graph: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    output = {
        "nodes": list(graph.get("nodes") or []),
        "edges": list(graph.get("edges") or []),
        "concepts": list(graph.get("concepts") or []),
        "available": bool(graph.get("available")),
        "backend": graph.get("backend", "sqlite-literature-graph"),
        "notice": graph.get("notice", ""),
    }
    seen = {node.get("id") for node in output["nodes"]}
    for item in evidence:
        if item.get("source_type") != "paper" or str(item.get("source", "")).startswith("Local"):
            continue
        node_id = f"external:{hashlib.sha1(_source_key(item).encode()).hexdigest()[:14]}"
        if node_id in seen:
            continue
        seen.add(node_id)
        output["nodes"].append({
            "id": node_id,
            "type": "external_paper",
            "label": item.get("title", "")[:160],
            "status": "external_oa_metadata",
        })
        output["edges"].append({
            "source": "query:current",
            "target": node_id,
            "predicate": "routes_to_external",
            "label": "外部检索",
            "provenance": "public_api_metadata",
            "status": "external_needs_review",
            "weight": 0.6,
        })
    return output


def _quality(evidence: list[dict[str, Any]], graph: dict[str, Any], external_done: bool) -> dict[str, Any]:
    local = [item for item in evidence if str(item.get("source", "")).startswith("Local")]
    external = [item for item in evidence if item not in local]
    top = sorted((float(item.get("relevance") or 0) for item in local), reverse=True)
    avg_top = sum(top[:3]) / max(1, len(top[:3]))
    concepts = graph.get("concepts") or []
    fulltext = sum(1 for item in local if item.get("fulltext"))
    coverage = min(1.0, len(set(term for item in local for term in item.get("match_terms") or [])) / 4.0)
    score = (
        0.44 * avg_top
        + 0.20 * min(1.0, len(local) / 4.0)
        + 0.16 * min(1.0, len(concepts) / 6.0)
        + 0.12 * coverage
        + 0.08 * min(1.0, fulltext / 2.0)
    )
    if external:
        score = min(1.0, score + 0.14)
    if not local and not external:
        score = 0.03
    elif not local:
        score = min(score, 0.38)
    score = round(score, 3)
    if score >= QUALITY_STRONG and avg_top >= 0.55 and len(local) >= 3:
        label = "strong"
    elif score >= QUALITY_MODERATE:
        label = "moderate"
    elif score >= QUALITY_WEAK:
        label = "weak"
    else:
        label = "insufficient"
    reasons: list[str] = []
    if not local:
        reasons.append("本地 10,000 篇 OA 库没有命中直接证据")
    if local and avg_top < 0.45:
        reasons.append("本地命中相关性偏低")
    if len(local) < 2:
        reasons.append("本地独立证据少于 2 条")
    if not concepts:
        reasons.append("缺少可扩展的概念/关系节点")
    if fulltext < 2:
        reasons.append("多数命中只有题录/摘要，不是全文")
    if external:
        reasons.append("已使用外部 OA 公共 API，仍需人工核对原文与许可")
    return {
        "score": score,
        "label": label,
        "label_zh": {"strong": "较强", "moderate": "中等", "weak": "偏弱", "insufficient": "不足"}[label],
        "avg_top_relevance": round(avg_top, 3),
        "local_count": len(local),
        "external_count": len(external),
        "concept_count": len(concepts),
        "fulltext_count": fulltext,
        "reasons": reasons,
        "thresholds": {"strong": QUALITY_STRONG, "moderate": QUALITY_MODERATE, "weak": QUALITY_WEAK},
        "external_used": external_done or bool(external),
    }


def _query_plan(question: str, prior_run_id: str = "") -> dict[str, Any]:
    expansion = query_text.expand_query(question)
    terms = query_text.terms(question)
    return {
        "original": question,
        "expanded": expansion.get("expanded", question),
        "matched_aliases": expansion.get("matched", []),
        "terms": terms,
        "language": expansion.get("language", "mixed"),
        "prior_run_id": prior_run_id,
        "intent": "literature_grounded_answer",
    }


def _cache_path(source: str, question: str) -> Path:
    digest = hashlib.sha256(f"{source}|{question}".encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{source}-{digest}.json"


def _cache_read(source: str, question: str) -> list[dict[str, Any]] | None:
    path = _cache_path(source, question)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("saved_at", 0)) > CACHE_TTL:
            return None
        return list(payload.get("items") or [])
    except (OSError, ValueError):
        return None


def _cache_write(source: str, question: str, items: list[dict[str, Any]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(source, question)
    try:
        path.write_text(json.dumps({"saved_at": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _query_for_api(question: str) -> str:
    terms = [term for term in query_text.terms(question) if re.search(r"[a-z0-9]", term)][:6]
    if not terms:
        terms = ["food", "protein"]
    return " OR ".join(f'"{term}"' for term in terms)


async def _europe_pmc(question: str) -> list[dict[str, Any]]:
    cached = _cache_read("europepmc", question)
    if cached is not None:
        return cached
    params = {
        "query": f"({_query_for_api(question)}) AND OPEN_ACCESS:Y",
        "format": "json",
        "pageSize": 6,
        "resultType": "core",
        "synonym": "true",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params=params)
        response.raise_for_status()
        payload = response.json()
    items = []
    for row in (payload.get("resultList") or {}).get("result") or []:
        title = row.get("title") or ""
        if not title:
            continue
        items.append({
            "id": f"external:europepmc:{row.get('id') or row.get('pmid') or title[:40]}",
            "source": "Europe PMC OA",
            "source_type": "paper",
            "title": title,
            "year": row.get("pubYear"),
            "doi": row.get("doi") or "",
            "pmcid": row.get("pmcid") or "",
            "url": f"https://europepmc.org/article/MED/{row.get('pmid')}" if row.get("pmid") else "https://europepmc.org/",
            "snippet": (row.get("abstractText") or "")[:420],
            "abstract": (row.get("abstractText") or "")[:1200],
            "relevance": 0.58,
            "strength": "medium",
            "license": row.get("license") or "metadata_only",
            "oa": True,
            "fulltext": bool(row.get("pmcid")),
            "match_terms": [],
            "provenance": "public_api_europepmc",
            "retrieved_at": _now(),
        })
    _cache_write("europepmc", question, items)
    return items


def _rebuild_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, places in index.items():
        for place in places:
            positions.append((int(place), word))
    return " ".join(word for _, word in sorted(positions)[:220])


async def _openalex(question: str) -> list[dict[str, Any]]:
    cached = _cache_read("openalex", question)
    if cached is not None:
        return cached
    params = {
        "search": question[:240],
        "filter": "is_oa:true",
        "per-page": 5,
        "select": "id,doi,title,publication_year,primary_location,open_access,cited_by_count,abstract_inverted_index,type",
    }
    headers = {"User-Agent": "BioForgeStudio/3.3 (local research; contact: local-user)"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get("https://api.openalex.org/works", params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    items = []
    for row in payload.get("results") or []:
        title = row.get("title") or ""
        if not title:
            continue
        location = row.get("primary_location") or {}
        source_name = ((location.get("source") or {}).get("display_name") or "OpenAlex")
        urls = [row.get("doi"), location.get("landing_page_url"), (row.get("open_access") or {}).get("oa_url")]
        url = next((str(value) for value in urls if value), "https://openalex.org/")
        items.append({
            "id": f"external:openalex:{row.get('id') or title[:40]}",
            "source": f"OpenAlex / {source_name}",
            "source_type": "paper",
            "title": title,
            "year": row.get("publication_year"),
            "doi": (row.get("doi") or "").replace("https://doi.org/", ""),
            "pmcid": "",
            "url": url,
            "snippet": _rebuild_abstract(row.get("abstract_inverted_index"))[:420],
            "abstract": _rebuild_abstract(row.get("abstract_inverted_index"))[:1200],
            "relevance": 0.52,
            "strength": "medium",
            "license": "open_access_metadata",
            "oa": True,
            "fulltext": False,
            "match_terms": [],
            "provenance": "public_api_openalex",
            "retrieved_at": _now(),
        })
    _cache_write("openalex", question, items)
    return items


async def _external_retrieve(question: str) -> dict[str, Any]:
    tasks = [
        _europe_pmc(question),
        _openalex(question),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for result in results:
        if isinstance(result, Exception):
            errors.append(f"{type(result).__name__}: {str(result)[:180]}")
            continue
        items.extend(result)
    return {"items": _dedupe(items), "errors": errors, "sources": ["Europe PMC OA", "OpenAlex"]}


def _prompt_messages() -> Any:
    if ChatPromptTemplate is None:
        return None
    system = (
        "You are BioForge Studio's evidence-grounded food science assistant. "
        "Use ONLY the supplied evidence. Never invent papers, authors, DOIs, numerical results, or conclusions. "
        "Cite each factual sentence with [E1], [E2], etc. If evidence is weak or indirect, say so explicitly. "
        "Separate local-library evidence from external OA metadata. Do not treat keyword co-occurrence as causal proof. "
        "Do not provide clinical, medical, regulatory, or safety clearance claims. Answer in the user's language."
    )
    human = (
        "Question:\n{question}\n\nEvidence quality: {quality}\n\nRetrieval route: {route}\n\n"
        "Evidence:\n{evidence}\n\nWrite a concise, auditable answer. End with a short Limitations section."
    )
    return ChatPromptTemplate.from_messages([("system", system), ("human", human)])


async def _llm_answer(question: str, evidence: list[dict[str, Any]], quality: dict[str, Any], route: list[dict[str, Any]]) -> str | None:
    if not _llm_enabled() or ChatOllama is None or ChatPromptTemplate is None:
        return None
    evidence_text = "\n\n".join(
        f"[{item.get('evidence_id')}] {item.get('title')} ({item.get('year') or 'n.d.'}); "
        f"source={item.get('source')}; relevance={item.get('relevance')}; "
        f"license={item.get('license')}; url={item.get('url')}\n{(item.get('abstract') or item.get('snippet') or '')[:900]}"
        for item in evidence[:8]
    )
    if not evidence_text:
        evidence_text = "(none)"
    try:
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
            temperature=0,
            num_ctx=16384,
            timeout=90,
        )
        chain = _prompt_messages() | llm | StrOutputParser()
        result = await chain.ainvoke({
            "question": question,
            "evidence": evidence_text,
            "quality": json.dumps(quality, ensure_ascii=False),
            "route": " -> ".join(item.get("node", "") for item in route),
        })
        text = str(result).strip()
        return text or None
    except Exception:
        return None


def _deterministic_answer(question: str, evidence: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    chinese = bool(re.search(r"[\u3400-\u9fff]", question))
    if not evidence:
        if chinese:
            return (
                "当前没有足够的本地或外部证据回答这个问题。\n\n"
                "系统已检索本地 10,000 篇 OA 文献库与外部 OA 公共文献 API，但没有获得可直接引用的结果。"
                "请不要把本回答当作结论；建议补充更具体的蛋白/化合物/食品体系与实验条件后重试。\n\n"
                "局限：检索失败或证据不足不等于“没有相关研究”。"
            )
        return (
            "There is not enough local or external evidence to answer this question.\n\n"
            "The local 10,000-paper OA library and external OA APIs returned no directly citable results. "
            "Do not treat this as a conclusion; add a specific protein/compound/food system and conditions, then retry.\n\n"
            "Limitation: absence of retrieved evidence is not proof that no research exists."
        )
    lines = []
    if chinese:
        prefix = "以下是基于可核对证据的受限结论，不代表临床、法规或安全性结论。" if quality.get("label") in {"strong", "moderate"} else "当前证据偏弱，以下只能作为待验证的研究线索。"
        lines.append(prefix)
        for item in evidence[:5]:
            lines.append(f"- [{item.get('evidence_id')}] 《{item.get('title')}》({item.get('year') or 'n.d.'})：{item.get('snippet') or item.get('abstract') or '仅有题录信息。'}")
        lines.append("\n局限：本地库多数记录只有题录/摘要；关键词共现不是机制证明；外部条目需回原文核对许可和实验条件。")
    else:
        prefix = "Limited evidence-grounded findings; not a clinical, regulatory, or safety conclusion." if quality.get("label") in {"strong", "moderate"} else "Evidence is weak; treat the following as hypotheses requiring validation."
        lines.append(prefix)
        for item in evidence[:5]:
            lines.append(f"- [{item.get('evidence_id')}] {item.get('title')} ({item.get('year') or 'n.d.'}): {item.get('snippet') or item.get('abstract') or 'Metadata only.'}")
        lines.append("\nLimitations: most local records are metadata/abstract only; keyword co-occurrence is not mechanistic proof; verify external full text and licensing.")
    return "\n".join(lines)


def _extract_citations(answer: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = {str(item.get("evidence_id")): item for item in evidence}
    used = []
    for match in re.finditer(r"\[(E\d+)\]", answer or ""):
        eid = match.group(1)
        if eid in valid and eid not in {item.get("evidence_id") for item in used}:
            item = valid[eid]
            used.append({
                "evidence_id": eid,
                "title": item.get("title"),
                "source": item.get("source"),
                "url": item.get("url"),
                "license": item.get("license"),
                "year": item.get("year"),
            })
    return used


def _claim_sentences(answer: str) -> list[str]:
    skip = re.compile(
        r"^(局限|限制|注意|声明|引用|参考文献|limitations?|notes?|disclaimer|references?|sources?)\b"
        r"|不代表|不能作为|不构成|not a clinical|not a regulatory|not medical|not proof|证据不足|"
        r"当前没有足够|there is not enough|treat the following|以下.*(线索|结论)|回答仅",
        re.I,
    )
    units: list[str] = []
    for raw_line in (answer or "").splitlines():
        line = raw_line.strip(" -•\t")
        if len(line) < 18 or skip.search(line):
            continue
        if raw_line.strip().startswith(("-", "•", "*")) or re.search(r"\[E\d+\]", line):
            units.append(line)
            continue
        for part in re.split(r"(?<=[。！？.!?])\s+", line):
            part = part.strip(" -•")
            if len(part) >= 18 and not skip.search(part):
                units.append(part)
    return units[:12]


def _verify_answer(answer: str, evidence: list[dict[str, Any]], quality: dict[str, Any]) -> dict[str, Any]:
    ids = {str(item.get("evidence_id")) for item in evidence}
    claims = []
    supported = 0
    for sentence in _claim_sentences(answer):
        cited = [eid for eid in ids if f"[{eid}]" in sentence]
        terms = set(query_text.terms(sentence))
        support_text = " ".join(
            f"{item.get('title')} {item.get('snippet')} {item.get('abstract')}"
            for item in evidence if str(item.get("evidence_id")) in cited
        ).lower()
        overlap = len([term for term in terms if term in support_text]) / max(1, min(len(terms), 8))
        ok = bool(cited) and (overlap >= 0.12 or quality.get("label") in {"strong", "moderate"})
        if ok:
            supported += 1
        claims.append({
            "claim": sentence[:280],
            "citations": cited,
            "support_overlap": round(overlap, 3),
            "status": "supported" if ok else "needs_review",
        })
    issues = [
        claim["claim"][:160]
        for claim in claims
        if claim["status"] != "supported"
    ]
    if not evidence:
        issues = []
    rate = supported / max(1, len(claims)) if claims else (1.0 if not evidence else 0.0)
    if not evidence:
        status = "insufficient"
    elif rate >= 0.75:
        status = "verified"
    else:
        status = "needs_revision"
    return {
        "claims": claims,
        "supported": supported,
        "total": len(claims),
        "support_rate": round(rate, 3),
        "issues": issues[:8],
        "status": status,
        "rule": "每个事实句必须带有效 [E#] 引用，并与被引证据有词项重叠；该规则只能发现部分无依据表述。",
    }


def _route_entry(node: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"node": node, "detail": detail, "at": _now(), **extra}


def _node_plan(state: RAGState) -> dict[str, Any]:
    question = state.get("question", "").strip()
    plan = _query_plan(question, state.get("prior_run_id", ""))
    return {
        "query_plan": plan,
        "warnings": list(state.get("warnings") or []),
        "route": list(state.get("route") or []) + [
            _route_entry("plan", f"解析问题并扩展术语：{', '.join(plan['terms'][:6]) or '无术语'}", intent=plan["intent"])
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("plan", "LangGraph 入口")],
    }


def _node_local(state: RAGState) -> dict[str, Any]:
    question = state.get("question", "")
    items = _local_retrieve(question)
    existing = list(state.get("evidence") or [])
    merged = _dedupe(existing + items)[:MAX_EVIDENCE]
    merged = _assign_citations(merged)
    return {
        "evidence": merged,
        "route": list(state.get("route") or []) + [
            _route_entry("local_retrieve", f"本地 SQLite BM25 命中 {len(items)} 条", count=len(items))
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("local_retrieve", "FTS/BM25")],
    }


def _node_graph(state: RAGState) -> dict[str, Any]:
    graph = _graph_expand(list(state.get("evidence") or []))
    graph = _add_external_graph(graph, list(state.get("evidence") or []))
    return {
        "graph": graph,
        "route": list(state.get("route") or []) + [
            _route_entry("graph_expand", f"扩展 {len(graph.get('concepts') or [])} 个概念节点", concepts=len(graph.get("concepts") or []))
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("graph_expand", graph.get("notice", ""))],
    }


def _node_assess(state: RAGState) -> dict[str, Any]:
    evidence = list(state.get("evidence") or [])
    graph = dict(state.get("graph") or {})
    quality = _quality(evidence, graph, bool(state.get("external_done")))
    needed = quality["score"] < 0.62 or quality["local_count"] < 2
    warnings = list(state.get("warnings") or [])
    if needed and not state.get("external_done"):
        warnings.append("本地证据强度不足，准备路由到外部 OA 公共 API。")
    if quality["label"] in {"weak", "insufficient"}:
        warnings.append("当前逻辑性/证据强度偏弱，不能把答案当作确定结论。")
    if int(quality.get("fulltext_count") or 0) < 2 and evidence:
        warnings.append("多数命中只有题录/摘要而非全文；机制与数值必须回原文核对。")
    if quality.get("external_count"):
        warnings.append("已调用外部 OA 公共 API；外部元数据与摘要是待审核材料，不是同行评审结论。")
    return {
        "quality": quality,
        "warnings": list(dict.fromkeys(warnings)),
        "route": list(state.get("route") or []) + [
            _route_entry("assess_quality", f"证据评分 {quality['score']}（{quality['label_zh']}），外部需求={needed}", score=quality["score"], label=quality["label"])
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("assess_quality", "质量门控")],
    }


def _after_assess(state: RAGState) -> str:
    quality = state.get("quality") or {}
    if state.get("external_requested") and not state.get("external_done") and _external_enabled():
        return "external"
    return "draft"


async def _node_external(state: RAGState) -> dict[str, Any]:
    question = state.get("question", "")
    route = list(state.get("route") or [])
    if not _external_enabled():
        return {
            "external_done": True,
            "external_requested": False,
            "warnings": list(state.get("warnings") or []) + ["外部检索已禁用；只能使用本地库。"],
            "route": route + [_route_entry("external_retrieve", "外部检索被配置禁用")],
        }
    result = await _external_retrieve(question)
    evidence = _dedupe(list(state.get("evidence") or []) + result["items"])[:MAX_EVIDENCE]
    evidence = _assign_citations(evidence)
    graph = _add_external_graph(dict(state.get("graph") or {}), evidence)
    warnings = list(state.get("warnings") or [])
    if result["errors"]:
        warnings.append("外部检索部分失败：" + "；".join(result["errors"])[:360])
    return {
        "evidence": evidence,
        "graph": graph,
        "external_done": True,
        "external_errors": result["errors"],
        "warnings": warnings,
        "route": route + [
            _route_entry("external_retrieve", f"外部 OA 命中 {len(result['items'])} 条", sources=result["sources"], errors=len(result["errors"]))
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("external_retrieve", "Europe PMC + OpenAlex")],
    }


async def _node_draft(state: RAGState) -> dict[str, Any]:
    evidence = list(state.get("evidence") or [])
    quality = dict(state.get("quality") or _quality(evidence, dict(state.get("graph") or {}), bool(state.get("external_done"))))
    answer = await _llm_answer(state.get("question", ""), evidence, quality, list(state.get("route") or []))
    model = f"{OLLAMA_MODEL} via LangChain" if answer else "deterministic-evidence-template"
    if not answer:
        answer = _deterministic_answer(state.get("question", ""), evidence, quality)
    citations = _extract_citations(answer, evidence)
    if evidence and not citations:
        answer += "\n\n引用：" + "；".join(f"[{item.get('evidence_id')}] {item.get('title')}" for item in evidence[:5])
        citations = _extract_citations(answer, evidence)
    return {
        "draft": answer,
        "citations": citations,
        "route": list(state.get("route") or []) + [
            _route_entry("draft", f"生成答案（{model}）", model=model, citation_count=len(citations))
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("draft", model)],
    }


def _node_verify(state: RAGState) -> dict[str, Any]:
    evidence = list(state.get("evidence") or [])
    quality = dict(state.get("quality") or {})
    verification = _verify_answer(state.get("draft", ""), evidence, quality)
    route = list(state.get("route") or []) + [
        _route_entry("verify", f"核验 {verification['total']} 个事实句，支持率 {verification['support_rate']}", status=verification["status"])
    ]
    return {
        "verification": verification,
        "route": route,
        "trace": list(state.get("trace") or []) + [_route_entry("verify", verification["rule"])],
    }


def _after_verify(state: RAGState) -> str:
    verification = state.get("verification") or {}
    quality = state.get("quality") or {}
    if verification.get("status") == "needs_revision" and int(state.get("iteration") or 0) < int(state.get("max_iterations") or MAX_ITERATIONS) and quality.get("label") not in {"insufficient"}:
        return "revise"
    return "finalize"


def _node_revise(state: RAGState) -> dict[str, Any]:
    plan = dict(state.get("query_plan") or {})
    concepts = [item.get("label") for item in (state.get("graph") or {}).get("concepts", [])][:4]
    base = state.get("question", "")
    revised = (base + " " + " ".join(str(concept) for concept in concepts if concept)).strip()
    if revised == base:
        revised = base + " mechanism evidence"
    return {
        "question": revised,
        "original_question": state.get("original_question") or base,
        "iteration": int(state.get("iteration") or 0) + 1,
        "query_plan": {**plan, "revision": revised, "terms": query_text.terms(revised)},
        "route": list(state.get("route") or []) + [
            _route_entry("revise", f"第 {int(state.get('iteration') or 0) + 1} 轮改写并回查：{revised[:180]}", iteration=int(state.get("iteration") or 0) + 1)
        ],
        "trace": list(state.get("trace") or []) + [_route_entry("revise", "verification-driven loop")],
    }


def _compiled_graph() -> Any:
    if not LANGGRAPH_AVAILABLE or StateGraph is None:
        return None
    workflow = StateGraph(RAGState)
    workflow.add_node("plan", _node_plan)
    workflow.add_node("local_retrieve", _node_local)
    workflow.add_node("graph_expand", _node_graph)
    workflow.add_node("assess_quality", _node_assess)
    workflow.add_node("external_retrieve", _node_external)
    workflow.add_node("generate", _node_draft)
    workflow.add_node("verify", _node_verify)
    workflow.add_node("revise", _node_revise)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "local_retrieve")
    workflow.add_edge("local_retrieve", "graph_expand")
    workflow.add_edge("graph_expand", "assess_quality")
    workflow.add_conditional_edges("assess_quality", _after_assess, {"external": "external_retrieve", "draft": "generate"})
    workflow.add_edge("external_retrieve", "assess_quality")
    workflow.add_edge("generate", "verify")
    workflow.add_conditional_edges("verify", _after_verify, {"revise": "revise", "finalize": END})
    workflow.add_edge("revise", "local_retrieve")
    return workflow.compile()


async def _run_sequential(state: RAGState) -> RAGState:
    for node in (_node_plan, _node_local, _node_graph, _node_assess):
        state.update(await _maybe_await(node(state)))
    if _after_assess(state) == "external":
        state.update(await _maybe_await(_node_external(state)))
        state.update(await _maybe_await(_node_assess(state)))
    state.update(await _maybe_await(_node_draft(state)))
    state.update(await _maybe_await(_node_verify(state)))
    if _after_verify(state) == "revise":
        state.update(await _maybe_await(_node_revise(state)))
        state.update(await _maybe_await(_node_local(state)))
        state.update(await _maybe_await(_node_graph(state)))
        state.update(await _maybe_await(_node_assess(state)))
        state.update(await _maybe_await(_node_draft(state)))
        state.update(await _maybe_await(_node_verify(state)))
    return state


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _finalize(state: RAGState) -> dict[str, Any]:
    evidence = list(state.get("evidence") or [])
    graph = dict(state.get("graph") or {})
    quality = dict(state.get("quality") or {})
    verification = dict(state.get("verification") or {})
    citations = list(state.get("citations") or [])
    warnings = list(dict.fromkeys(state.get("warnings") or []))
    if quality.get("label") == "insufficient":
        warnings.append("未获得足够证据；答案仅说明检索状态，不应作为科学结论。")
    status = "pending_review"
    return {
        "id": state.get("run_id") or _new_run_id(),
        "created_at": _now(),
        "updated_at": _now(),
        "question": state.get("original_question") or state.get("question", ""),
        "effective_question": state.get("question", ""),
        "answer": state.get("draft", ""),
        "status": status,
        "quality": quality,
        "verification": verification,
        "evidence": evidence,
        "citations": citations,
        "graph": {
            "available": graph.get("available", False),
            "backend": graph.get("backend", ""),
            "notice": graph.get("notice", ""),
            "concepts": graph.get("concepts", [])[:12],
            "nodes": graph.get("nodes", [])[:40],
            "edges": graph.get("edges", [])[:40],
        },
        "route": state.get("route", []),
        "trace": state.get("trace", []),
        "warnings": warnings,
        "query_plan": state.get("query_plan", {}),
        "engine": "langgraph" if LANGGRAPH_AVAILABLE else "sequential-fallback",
        "deepagent": {"status": "optional_not_active", "reason": "deepagents requires Python >=3.11; active orchestrator is LangGraph"},
        "prior_run_id": state.get("prior_run_id", ""),
        "human_review": {
            "required": True,
            "status": "pending",
            "note": "人工审核后才能作为已审核记录；回答本身不构成同行评审或监管批准。",
        },
        "limits": {
            "local_library": literature.stats(),
            "external_sources": ["Europe PMC OA", "OpenAlex"],
            "max_iterations": int(state.get("max_iterations") or MAX_ITERATIONS),
        },
    }


async def ask(
    question: str,
    max_iterations: int = MAX_ITERATIONS,
    prior_run_id: str = "",
    force_external: bool | None = None,
) -> dict[str, Any]:
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")
    run_id = _new_run_id()
    state: RAGState = {
        "question": question,
        "original_question": question,
        "run_id": run_id,
        "iteration": 0,
        "max_iterations": max(1, min(3, int(max_iterations))),
        "external_requested": True if force_external is None else force_external,
        "external_done": False,
        "prior_run_id": prior_run_id,
        "evidence": [],
        "graph": {},
        "warnings": [],
        "route": [],
        "trace": [],
    }
    if LANGGRAPH_AVAILABLE:
        compiled = _compiled_graph()
        result = await compiled.ainvoke(state)
    else:
        result = await _run_sequential(state)
    record = _finalize(result)
    rag_store.save_run(record)
    return record


def _reviewer_name(reviewer: str | None) -> str:
    return (reviewer or os.environ.get("BIOFORGE_REVIEWER", "local-human-reviewer")).strip()[:120]


def review(run_id: str, action: str, reviewer: str = "", note: str = "", corrected_answer: str = "") -> dict[str, Any]:
    record = rag_store.get_run(run_id)
    if record is None:
        raise KeyError(run_id)
    action = (action or "").strip().lower()
    if action not in {"approve", "reject"}:
        raise ValueError("action must be approve or reject")
    reviewer = _reviewer_name(reviewer)
    review_row = rag_store.add_review(run_id, action, reviewer, note, corrected_answer)
    status = "approved" if action == "approve" else "rejected"
    rag_store.set_status(run_id, status)
    record["status"] = status
    record["human_review"] = {
        "required": True,
        "status": status,
        "reviewer": reviewer,
        "note": note,
        "corrected_answer": corrected_answer,
        "reviewed_at": _now(),
    }
    rag_store.save_run(record)
    reward = 1.0 if action == "approve" else -1.0
    rag_store.add_feedback(run_id, reward, "human_review", note)
    _learn_from_record(record, reward)
    review_row["status"] = status
    return {"run_id": run_id, "status": status, "review": review_row, "record": rag_store.get_run(run_id)}


def add_feedback(run_id: str, reward: float, dimension: str = "overall", note: str = "") -> dict[str, Any]:
    record = rag_store.get_run(run_id)
    if record is None:
        raise KeyError(run_id)
    row = rag_store.add_feedback(run_id, reward, dimension, note)
    _learn_from_record(record, float(reward))
    return {"run_id": run_id, "feedback": row, "weights": rag_store.weights(12)}


def _learn_from_record(record: dict[str, Any], reward: float) -> None:
    graph = record.get("graph") or {}
    edges = graph.get("edges") or []
    keys = []
    for edge in edges[:12]:
        if edge.get("predicate") in {"mentions", "co_occurs_with", "routes_to_external"}:
            keys.append(f"{edge.get('predicate')}:{edge.get('source')}->{edge.get('target')}")
    for evidence in (record.get("evidence") or [])[:6]:
        if evidence.get("provenance"):
            keys.append(f"source:{evidence.get('provenance')}")
    for key in dict.fromkeys(keys):
        rag_store.update_relation_weight(key, reward)


async def rollback(run_id: str, reviewer: str = "", note: str = "", extra_query: str = "") -> dict[str, Any]:
    record = rag_store.get_run(run_id)
    if record is None:
        raise KeyError(run_id)
    reviewer = _reviewer_name(reviewer)
    question = record.get("question", "")
    if extra_query.strip():
        question = f"{question} {extra_query.strip()}"
    rag_store.set_status(run_id, "rolled_back")
    prior = dict(record)
    prior["status"] = "rolled_back"
    rag_store.save_run(prior)
    rag_store.add_review(run_id, "rollback", reviewer, note, "")
    new_record = await ask(question, max_iterations=MAX_ITERATIONS, prior_run_id=run_id)
    new_record["route"].insert(0, _route_entry("human_rollback", f"人工回滚自 {run_id}，重新检索/生成", reviewer=reviewer, note=note))
    new_record["trace"].insert(0, _route_entry("human_rollback", "rollback requested by human reviewer"))
    new_record["human_review"]["rollback_from"] = run_id
    rag_store.save_run(new_record)
    return {"rolled_back_run_id": run_id, "new_run": new_record, "reviewer": reviewer}


async def deepagent_review(run_id: str) -> dict[str, Any]:
    record = rag_store.get_run(run_id)
    if record is None:
        raise KeyError(run_id)
    worker_python = os.environ.get("BIOFORGE_DEEPAGENT_PYTHON", "").strip()
    if not worker_python:
        return {
            "run_id": run_id,
            "available": False,
            "engine": "deepagents",
            "reason": "BIOFORGE_DEEPAGENT_PYTHON is not configured; active orchestrator is LangGraph.",
        }
    worker = Path(worker_python)
    if not worker.exists():
        return {"run_id": run_id, "available": False, "engine": "deepagents", "reason": f"worker python not found: {worker_python}"}
    script = data.ROOT / "rag_worker" / "deep_review.py"
    if not script.exists():
        return {"run_id": run_id, "available": False, "engine": "deepagents", "reason": "rag_worker/deep_review.py is missing"}
    payload = {
        "question": record.get("question", ""),
        "answer": record.get("answer", ""),
        "quality": record.get("quality", {}),
        "verification": record.get("verification", {}),
        "evidence": (record.get("evidence") or [])[:8],
    }
    try:
        process = await asyncio.create_subprocess_exec(
            str(worker),
            str(script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(data.ROOT),
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            timeout=150,
        )
    except asyncio.TimeoutError:
        return {"run_id": run_id, "available": False, "engine": "deepagents", "reason": "deepagent worker timed out"}
    except OSError as exc:
        return {"run_id": run_id, "available": False, "engine": "deepagents", "reason": f"worker failed to start: {exc}"}
    if process.returncode != 0:
        return {
            "run_id": run_id,
            "available": False,
            "engine": "deepagents",
            "reason": f"worker exit {process.returncode}",
            "stderr": stderr.decode("utf-8", errors="ignore")[:600],
        }
    try:
        result = json.loads(stdout.decode("utf-8", errors="ignore"))
    except ValueError:
        return {"run_id": run_id, "available": False, "engine": "deepagents", "reason": "worker returned non-JSON output"}
    return {"run_id": run_id, "available": True, **result}


def pending_reviews(limit: int = 25) -> list[dict[str, Any]]:
    return [
        {
            "id": record.get("id"),
            "created_at": record.get("created_at"),
            "question": record.get("question"),
            "status": record.get("status"),
            "quality": record.get("quality", {}),
            "warnings": record.get("warnings", [])[:3],
        }
        for record in rag_store.list_runs(status="pending_review", limit=limit)
    ]


def health() -> dict[str, Any]:
    status = engine_status()
    status["pending_reviews"] = len(pending_reviews(100))
    return status
