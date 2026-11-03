from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from . import composition, data, query_text

UA = "BioForgeStudio/2.1 (local research; contact: local-user)"
CACHE_TTL = 24 * 3600
TIMEOUT = 18.0

_SPECS = {
    "pubchem": {"name": "PubChem", "license": "public domain (NCBI)", "url": "https://pubchem.ncbi.nlm.nih.gov/"},
    "chebi": {"name": "ChEBI", "license": "CC BY 4.0", "url": "https://www.ebi.ac.uk/chebi/"},
    "unichem": {"name": "UniChem", "license": "CC BY 4.0", "url": "https://www.ebi.ac.uk/unichem/"},
    "uniprot": {"name": "UniProt", "license": "CC BY 4.0", "url": "https://www.uniprot.org/"},
    "pdb": {"name": "RCSB PDB", "license": "CC0 1.0", "url": "https://www.rcsb.org/"},
    "alphafold": {"name": "AlphaFold DB", "license": "CC BY 4.0", "url": "https://alphafold.ebi.ac.uk/"},
    "europepmc": {"name": "Europe PMC", "license": "metadata CC BY 4.0; abstracts per publisher", "url": "https://europepmc.org/"},
    "fdc": {"name": "USDA FoodData Central", "license": "US public domain", "url": "https://fdc.nal.usda.gov/"},
    "openfoodfacts": {"name": "Open Food Facts", "license": "ODbL 1.0", "url": "https://world.openfoodfacts.org/"},
    "chembl": {"name": "ChEMBL", "license": "CC BY-SA 4.0", "url": "https://www.ebi.ac.uk/chembl/"},
    "string": {"name": "STRING", "license": "CC BY 4.0", "url": "https://string-db.org/"},
    "massbank": {"name": "MassBank", "license": "record-specific", "url": "https://massbank.eu/MassBank/"},
    "genbank": {"name": "NCBI GenBank / Protein", "license": "US public domain (NCBI)", "url": "https://www.ncbi.nlm.nih.gov/genbank/"},
    "kegg": {"name": "KEGG", "license": "academic use; redistribution restricted", "url": "https://www.kegg.jp/"},
    "zinc": {"name": "ZINC", "license": "free for research; browser verification required", "url": "https://zinc.docking.org/"},
}

LICENSED_SOURCES = [
    {"id": "drugbank", "name": "DrugBank", "status": "license_required", "url": "https://go.drugbank.com/", "note": "需要商业/学术许可和 API key；未配置时不查询，也不复制其数据。"},
    {"id": "ccdc", "name": "CCDC / Cambridge Structural Database", "status": "license_required", "url": "https://www.ccdc.cam.ac.uk/", "note": "晶体结构数据库需机构订阅；本机未配置授权。"},
    {"id": "chembook", "name": "ChemBook / 化学专业数据库", "status": "credentials_required", "url": "", "note": "需用户提供有权的机构入口；未提供前不接入。"},
    {"id": "nmrshiftdb2", "name": "NMRShiftDB2", "status": "public_reference", "url": "https://nmrshiftdb.nmr.uni-koeln.de/", "note": "可作为公开 NMR 参考入口；批量/自动查询需遵守站点条款。"},
    {"id": "lipidmaps", "name": "LIPID MAPS", "status": "public_reference", "url": "https://www.lipidmaps.org/", "note": "脂质分类与结构参考；自动查询需按接口条款配置。"},
    {"id": "glytoucan", "name": "GlyTouCan", "status": "public_reference", "url": "https://glytoucan.org/", "note": "聚糖 accession 参考；糖链身份需用 accession 精确检索。"},
    {"id": "university_library", "name": "高校图书馆电子资源", "status": "credentials_required", "url": "", "note": "需机构 IP/代理、账号和许可；不能绕过付费墙或批量下载。"},
]

PROTEIN_HINTS = (
    "protein", "peptide", "enzyme", "receptor", "kinase", "antibody", "target",
    "lactoglobulin", "casein", "albumin", "collagen", "gluten", "lysozyme",
    "蛋白", "多肽", "酶", "受体", "激酶", "抗体", "靶点", "靶标",
)
FOOD_HINTS = (
    "food", "formulation", "beverage", "drink", "juice", "bread", "yogurt", "sauce",
    "gummy", "ice cream", "chocolate", "meat", "dairy", "snack", "candy", "powder",
    "食品", "饮料", "配方", "面包", "酸奶", "酱", "软糖", "冰淇淋", "巧克力", "肉",
    "乳", "汁", "粉", "零食", "糖果",
)
INTERACTION_HINTS = (
    "binding", "bind", "dock", "docking", "complex", "interaction", "target",
    "对接", "结合", "复合物", "相互作用", "靶点", "抑制", "激动",
)
FOOD_QUERY_MAP = {
    "番茄酱": "tomato sauce",
    "橙汁": "orange juice",
    "面包": "bread",
    "酸奶": "yogurt",
    "冰淇淋": "ice cream",
    "巧克力": "chocolate",
    "软糖": "gummy candy",
    "肉": "meat",
    "豆奶": "soy milk",
    "燕麦": "oats",
}

ENTITY_SOURCES = {
    "compound": ["pubchem", "unichem", "chebi", "chembl", "kegg", "zinc", "europepmc", "massbank"],
    "protein": ["uniprot", "genbank", "pdb", "alphafold", "string", "europepmc"],
    "food": ["fdc", "openfoodfacts", "europepmc"],
    "complex": ["pubchem", "unichem", "chebi", "chembl", "kegg", "zinc", "uniprot", "genbank", "pdb", "alphafold", "string", "europepmc", "massbank"],
}
VALID_ENTITIES = set(ENTITY_SOURCES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cache_path(key: str) -> str:
    data.ensure_dirs()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return str(data.CACHE_DIR / f"db-{digest}.json")


def _cache_get(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL:
        return None
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return None


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    except OSError:
        pass


async def _get_json(url: str, key: str, params: dict[str, Any] | None = None) -> Any:
    cached = _cache_get(key)
    if cached is not None:
        return cached["payload"]
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    if len(response.content) > 8_000_000:
        raise ValueError("upstream response too large")
    payload = response.json()
    _cache_set(key, {"retrieved_at": _now(), "url": str(response.url), "payload": payload})
    return payload


async def _get_text(url: str, key: str, params: dict[str, Any] | None = None) -> str:
    cached = _cache_get(key)
    if cached is not None:
        return str(cached["payload"])
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    if len(response.content) > 8_000_000:
        raise ValueError("upstream response too large")
    payload = response.text
    _cache_set(key, {"retrieved_at": _now(), "url": str(response.url), "payload": payload})
    return payload


def _record(
    source: str,
    item_id: str,
    title: str,
    url: str,
    extra: dict[str, Any] | None = None,
    score: float | None = None,
    match_basis: str = "name_search",
    relevance: float | None = None,
) -> dict[str, Any]:
    spec = _SPECS.get(source, {"name": source, "license": "unknown", "url": ""})
    return {
        "source": source,
        "source_name": spec["name"],
        "id": str(item_id),
        "title": title,
        "url": url,
        "license": spec["license"],
        "retrieved_at": _now(),
        "score": score,
        "match_basis": match_basis,
        "relevance": relevance if relevance is not None else score,
        "data": extra or {},
    }


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())[:240]


def classify_query(query: str, entity: str | None = None) -> tuple[str, dict[str, Any]]:
    """Classify before selecting sources.

    Compound is the safe default for a bare molecule name; protein/food databases
    are only queried when the query or the user explicitly says so.
    """
    requested = (entity or "auto").strip().lower()
    text = (query or "").lower()
    protein_hit = next((word for word in PROTEIN_HINTS if word in text), None)
    food_hit = next((word for word in FOOD_HINTS if word in text), None)
    interaction_hit = next((word for word in INTERACTION_HINTS if word in text), None)
    if requested in VALID_ENTITIES:
        inferred = requested
        reason = f"用户指定实体类型：{requested}"
    elif protein_hit and interaction_hit:
        inferred = "complex"
        reason = f"检测到蛋白/靶点词「{protein_hit}」与相互作用词「{interaction_hit}」"
    elif protein_hit:
        inferred = "protein"
        reason = f"检测到蛋白/酶/靶点词「{protein_hit}」"
    elif food_hit:
        inferred = "food"
        reason = f"检测到食品/配方词「{food_hit}」"
    else:
        inferred = "compound"
        reason = "未检测到蛋白或食品语境；按小分子/化合物处理，避免调用无关的蛋白和食品库"
    plan = {
        "entity": inferred,
        "reason": reason,
        "signals": {"protein": protein_hit, "food": food_hit, "interaction": interaction_hit},
        "sources": ENTITY_SOURCES[inferred],
    }
    return inferred, plan


def _query_terms(query: str) -> list[str]:
    return query_text.terms(query)


def _text_relevance(query: str, text: str) -> float:
    return query_text.relevance(query, text)[0]


def _localize_food_query(query: str) -> str:
    for zh, en in FOOD_QUERY_MAP.items():
        if zh in query:
            query = query.replace(zh, en)
    query = re.sub(r"(?i)\b(low sodium|low sugar|low fat|high protein|high fiber|no sugar|无糖|低钠|低糖|低脂|高蛋白|高纤维)\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return _clean_query(query)


async def _pubchem(query: str) -> dict[str, Any]:
    cid_payload = await _get_json(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(query, safe='')}/cids/JSON",
        f"pubchem-cid:{query}",
    )
    cids = [int(x) for x in cid_payload.get("IdentifierList", {}).get("CID", [])[:3]]
    if not cids:
        return {"source": "pubchem", "status": "empty", "records": [], "query": query}
    cid = cids[0]
    prop = await _get_json(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,IUPACName,InChIKey,Title/JSON",
        f"pubchem-prop-v21b:{cid}",
    )
    props = (prop.get("PropertyTable", {}).get("Properties") or [{}])[0]
    spectra: list[dict[str, Any]] = []
    try:
        pv = await _get_json(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Mass+Spectrometry",
            f"pubchem-ms:{cid}",
        )
        spectra = _pubchem_spectra(pv, cid)
    except Exception:
        spectra = []
    title = props.get("Title") or props.get("IUPACName") or query
    return {
        "source": "pubchem",
        "status": "ok",
        "query": query,
        "records": [
            _record(
                "pubchem", cid, title,
                f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                {
                    "formula": props.get("MolecularFormula"),
                    "mw": props.get("MolecularWeight"),
                    "smiles": props.get("IsomericSMILES") or props.get("CanonicalSMILES") or props.get("SMILES"),
                    "iupac": props.get("IUPACName"),
                    "inchikey": props.get("InChIKey"),
                    "cid": cid,
                    "spectra": spectra[:6],
                    "spectra_note": "PubChem aggregates experimental spectra; verify the primary record and instrument conditions before use.",
                    "identity_note": "PubChem name lookup is the anchor; downstream database links use the InChIKey, not the query string.",
                },
                1.0,
                "pubchem_name_exact",
                1.0,
            )
        ],
    }


def _pubchem_spectra(payload: dict[str, Any], cid: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def children(node: dict[str, Any]) -> list[dict[str, Any]]:
        return list(node.get("Section", []) or [])

    def find(node: dict[str, Any], heading: str, depth: int = 0) -> list[dict[str, Any]]:
        if depth > 8:
            return []
        found = []
        if node.get("TOCHeading") == heading:
            found.append(node)
        for child in children(node):
            found.extend(find(child, heading, depth + 1))
        return found

    for root in payload.get("Record", {}).get("Section", []) or []:
        for ms in find(root, "Mass Spectrometry"):
            for spec in children(ms):
                if not spec.get("Information"):
                    continue
                info = spec["Information"]
                entry: dict[str, Any] = {"type": spec.get("TOCHeading"), "peaks": [], "source": "PubChem"}
                for item in info:
                    name = str(item.get("Name") or "")
                    value = item.get("Value") or {}
                    text = ""
                    if value.get("StringWithMarkup"):
                        text = "; ".join(str(x.get("String", "")) for x in value["StringWithMarkup"])
                    if name == "Spectra ID":
                        entry["spectra_id"] = text
                    elif name in {"Instrument", "Instrument Type", "Ionization Mode", "MS Level"}:
                        entry[name.lower().replace(" ", "_")] = text
                    elif name == "SPLASH":
                        entry["splash"] = text
                    elif name == "Accession ID":
                        entry["accession"] = text
                        entry["url"] = f"https://massbank.eu/MassBank/RecordDisplay?id={text}"
                    elif name == "Top 5 Peaks":
                        peaks = []
                        for row in value.get("StringWithMarkup", []) or []:
                            parts = str(row.get("String", "")).split()
                            if len(parts) >= 2:
                                try:
                                    peaks.append({"mz": float(parts[0]), "intensity": float(parts[1])})
                                except ValueError:
                                    pass
                        entry["peaks"] = peaks
                if entry.get("peaks"):
                    entry.setdefault("url", f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}#section=Mass-Spectrometry")
                    result.append(entry)
    return result


async def _unichem(inchikey: str) -> dict[str, Any]:
    if not inchikey:
        return {"source": "unichem", "status": "skipped", "reason": "没有 PubChem InChIKey，无法做结构标识符验证", "records": []}
    try:
        payload = await _get_json(
            f"https://www.ebi.ac.uk/unichem/rest/verbose_inchikey/{quote(inchikey, safe='')}",
            f"unichem:{inchikey}",
        )
    except Exception as exc:
        return {"source": "unichem", "status": "error", "error": str(exc)[:240], "records": [], "inchikey": inchikey}
    wanted = {"chebi", "chembl", "drugbank", "hmdb", "pubchem"}
    mappings: dict[str, list[str]] = {}
    records = []
    for row in payload if isinstance(payload, list) else []:
        name = str(row.get("name") or "").lower()
        if name not in wanted:
            continue
        ids = [str(value) for value in row.get("src_compound_id", []) if value]
        if not ids:
            continue
        mappings[name] = ids
        for item_id in ids[:4]:
            url = row.get("src_url") or row.get("base_id_url", "")
            if url and not str(url).startswith("http"):
                url = ""
            records.append(_record(
                "unichem", item_id, f"UniChem {name}: {item_id}", url or f"https://www.ebi.ac.uk/unichem/",
                {"mapping_db": name, "inchikey": inchikey, "source_ids": ids[:8]},
                1.0, "exact_inchikey", 1.0,
            ))
    return {"source": "unichem", "status": "ok" if records else "empty", "inchikey": inchikey, "mappings": mappings, "records": records}


async def _chebi_exact(chebi_id: str) -> dict[str, Any]:
    payload = await _get_json(
        f"https://www.ebi.ac.uk/chebi/backend/api/public/compound/{quote(chebi_id, safe=':')}/",
        f"chebi-exact:{chebi_id}",
    )
    accession = payload.get("chebi_accession") or chebi_id
    return {"source": "chebi", "status": "ok", "records": [_record(
        "chebi", accession, payload.get("name") or accession,
        f"https://www.ebi.ac.uk/chebi/searchId.do?chebiId={accession}",
        {"stars": payload.get("stars"), "formula": payload.get("formula"), "mass": payload.get("mass"), "definition": (payload.get("definition") or "")[:800]},
        1.0, "exact_inchikey", 1.0,
    )]}


async def _chebi_search(query: str) -> dict[str, Any]:
    payload = await _get_json(
        "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/",
        f"chebi-search-v21:{query}",
        {"term": query, "size": 5},
    )
    records = []
    for item in (payload.get("results") or [])[:5]:
        source = item.get("_source", {})
        chebi_id = source.get("chebi_accession")
        if not chebi_id:
            continue
        name = source.get("name") or query
        relevance = _text_relevance(query, name)
        records.append(_record(
            "chebi", chebi_id, name,
            f"https://www.ebi.ac.uk/chebi/searchId.do?chebiId={chebi_id}",
            {"stars": source.get("stars"), "formula": source.get("formula"), "mass": source.get("mass")},
            relevance, "name_search", relevance,
        ))
    return {"source": "chebi", "status": "ok" if records else "empty", "records": records, "note": "UniChem 未返回精确 ChEBI 映射时使用名称检索；这些记录不是结构验证结果。"}


async def _chembl_exact(chembl_id: str) -> dict[str, Any]:
    payload = await _get_json(
        f"https://www.ebi.ac.uk/chembl/api/data/molecule/{quote(chembl_id, safe='')}.json",
        f"chembl-exact:{chembl_id}",
    )
    props = payload.get("molecule_properties") or {}
    return {"source": "chembl", "status": "ok", "records": [_record(
        "chembl", chembl_id, payload.get("pref_name") or chembl_id,
        f"https://www.ebi.ac.uk/chembl/explore/compound/{chembl_id}",
        {"max_phase": payload.get("max_phase"), "formula": props.get("full_molformula"), "inchikey": payload.get("molecule_structures", {}).get("standard_inchi_key")},
        1.0, "exact_inchikey", 1.0,
    )]}


async def _chembl_search(query: str) -> dict[str, Any]:
    payload = await _get_json(
        "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
        f"chembl-search-v21:{query}",
        {"q": query, "limit": 5},
    )
    records = []
    for item in (payload.get("molecules") or [])[:5]:
        chembl_id = item.get("molecule_chembl_id")
        name = item.get("pref_name") or query
        relevance = _text_relevance(query, name)
        records.append(_record(
            "chembl", chembl_id, name,
            f"https://www.ebi.ac.uk/chembl/explore/compound/{chembl_id}",
            {"max_phase": item.get("max_phase"), "formula": item.get("molecule_properties", {}).get("full_molformula")},
            relevance, "name_search", relevance,
        ))
    return {"source": "chembl", "status": "ok" if records else "empty", "records": records, "note": "仅在没有 UniChem 精确映射时使用名称检索。"}


async def _uniprot(query: str) -> dict[str, Any]:
    payload = await _get_json(
        "https://rest.uniprot.org/uniprotkb/search",
        f"uniprot-v21:{query}",
        {"query": query, "format": "json", "size": 5},
    )
    records = []
    for entry in payload.get("results", [])[:5]:
        accession = entry.get("primaryAccession")
        protein = (((entry.get("proteinDescription") or {}).get("recommendedName") or {}).get("fullName") or {}).get("value")
        title = protein or query
        relevance = _text_relevance(query, title) or 0.5
        xrefs = [
            {"database": x.get("database"), "id": x.get("id")}
            for x in entry.get("uniProtKBCrossReferences", []) or []
            if x.get("database") in {"PDB", "AlphaFoldDB"}
        ]
        records.append(_record(
            "uniprot", accession, title,
            f"https://www.uniprot.org/uniprotkb/{accession}/entry",
            {
                "organism": (entry.get("organism") or {}).get("scientificName"),
                "taxon_id": (entry.get("organism") or {}).get("taxonId"),
                "length": (entry.get("sequence") or {}).get("length"),
                "reviewed": entry.get("entryType"),
                "keywords": [k.get("name") for k in entry.get("keywords", [])][:10],
                "xrefs": xrefs,
            },
            relevance, "uniprot_search", relevance,
        ))
    return {"source": "uniprot", "status": "ok" if records else "empty", "records": records}


async def _pdb_from_uniprot(uniprot_records: list[dict[str, Any]]) -> dict[str, Any]:
    ids: list[str] = []
    sources: dict[str, str] = {}
    for record in uniprot_records:
        for xref in record.get("data", {}).get("xrefs", []):
            if xref.get("database") == "PDB" and xref.get("id") and xref["id"] not in ids:
                ids.append(xref["id"])
                sources[xref["id"]] = record["id"]
    records = [
        _record(
            "pdb", pdb_id, f"PDB entry {pdb_id}",
            f"https://www.rcsb.org/structure/{pdb_id}",
            {"download": f"https://files.rcsb.org/download/{pdb_id}.pdb", "uniprot": sources[pdb_id], "xref_source": "UniProt uniProtKBCrossReferences"},
            1.0, "uniprot_pdb_xref", 1.0,
        )
        for pdb_id in ids[:8]
    ]
    return {
        "source": "pdb",
        "status": "ok" if records else "empty",
        "records": records,
        "note": "只列出 UniProt 记录中的 PDB 交叉引用；没有用全文检索猜结构。",
    }


async def _alphafold(uniprot_records: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for rec in uniprot_records[:3]:
        accession = rec["id"]
        payload = await _get_json(
            f"https://alphafold.ebi.ac.uk/api/prediction/{accession}",
            f"alphafold:{accession}",
        )
        for item in (payload or [])[:1]:
            records.append(_record(
                "alphafold", accession, f"AlphaFold model {accession}",
                f"https://alphafold.ebi.ac.uk/entry/{accession}",
                {"pdb": item.get("pdbUrl"), "cif": item.get("cifUrl"), "pae": item.get("paeImageUrl")},
                1.0, "uniprot_accession", 1.0,
            ))
    return {"source": "alphafold", "status": "ok" if records else "empty", "records": records}


async def _europepmc(query: str) -> dict[str, Any]:
    payload = await _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        f"epmc-v21:{query}",
        {"query": query, "format": "json", "pageSize": 6, "resultType": "core"},
    )
    records = []
    for item in (payload.get("resultList", {}).get("result") or [])[:6]:
        title = item.get("title") or query
        records.append(_record(
            "europepmc", item.get("id") or item.get("pmid") or item.get("doi"), title,
            f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}",
            {
                "authors": item.get("authorString"),
                "journal": (item.get("journalInfo") or {}).get("journal", {}).get("title"),
                "year": item.get("pubYear"),
                "doi": item.get("doi"),
                "abstract": (item.get("abstractText") or "")[:1200],
            },
            float(item.get("score", 0)) / 100.0 if item.get("score") else None,
            "literature_search",
            0.6,
        ))
    return {"source": "europepmc", "status": "ok" if records else "empty", "records": records, "note": "文献检索是语境证据，不是化合物/蛋白身份验证。"}


def _local_fdc(query: str, display_query: str, reason: str) -> dict[str, Any]:
    """Fallback to the versioned USDA SR Legacy snapshot when the live API fails."""
    terms = _query_terms(query)
    records = []
    for item in data.ingredients():
        comp = composition.get(item["id"])
        if not comp.get("fdc_id"):
            continue
        haystack = f"{item['id']} {item['name']} {item.get('cn_name', '')} {comp.get('fdc_description', '')}".lower()
        relevance = round(sum(1 for term in terms if term in haystack) / len(terms), 3) if terms else 0.0
        if relevance < 0.5:
            continue
        records.append(_record(
            "fdc", comp["fdc_id"], comp.get("fdc_description") or item["name"],
            comp.get("source_url") or f"https://fdc.nal.usda.gov/food-details/{comp['fdc_id']}/nutrients",
            {
                "data_type": "SR Legacy (local snapshot)",
                "nutrients": comp.get("nutrients"),
                "ingredient_id": item["id"],
                "snapshot": "FoodData_Central_sr_legacy_food_json_2018-04",
                "lookup_query": query,
                "fallback_reason": reason,
            },
            relevance, "local_fdc_snapshot", relevance,
        ))
        if len(records) >= 5:
            break
    return {
        "source": "fdc",
        "status": "degraded" if records else "empty",
        "records": records,
        "query": display_query,
        "lookup_query": query,
        "note": f"实时 FDC API 不可用（{reason}），已切换到本地 USDA SR Legacy 快照；快照是参考组成，不是当前产品批次。",
    }


async def _fdc(query: str, display_query: str) -> dict[str, Any]:
    lookup = _localize_food_query(query)
    try:
        payload = await _get_json(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            f"fdc-v21:{lookup}",
            {"query": lookup, "pageSize": 10, "api_key": os.environ.get("FDC_API_KEY", "DEMO_KEY")},
        )
    except Exception as exc:
        return _local_fdc(lookup, display_query, str(exc)[:160])
    records = []
    for item in (payload.get("foods") or [])[:10]:
        title = item.get("description") or lookup
        relevance = _text_relevance(lookup, title)
        if relevance < 0.5:
            continue
        nutrients = {}
        for nutrient in item.get("foodNutrients", [])[:30]:
            name = nutrient.get("nutrientName")
            if name:
                nutrients[name] = nutrient.get("value")
        records.append(_record(
            "fdc", item.get("fdcId"), title,
            f"https://fdc.nal.usda.gov/food-details/{item.get('fdcId')}/nutrients",
            {"data_type": item.get("dataType"), "brand": item.get("brandOwner"), "nutrients": nutrients, "lookup_query": lookup},
            relevance, "food_search", relevance,
        ))
        if len(records) >= 5:
            break
    return {"source": "fdc", "status": "ok" if records else "empty", "records": records, "query": display_query, "lookup_query": lookup, "note": "按查询词相关性过滤；FDC 是食品组成数据库，不是化合物身份库。"}


async def _openfoodfacts(query: str) -> dict[str, Any]:
    lookup = _localize_food_query(query)
    payload = await _get_json(
        "https://world.openfoodfacts.org/cgi/search.pl",
        f"off-cgi-v21:{lookup}",
        {"search_terms": lookup, "search_simple": 1, "action": "process", "json": 1, "page_size": 10},
    )
    records = []
    for item in (payload.get("products") or [])[:10]:
        code = item.get("code")
        if not code:
            continue
        title = item.get("product_name") or lookup
        relevance = _text_relevance(lookup, title + " " + str(item.get("categories") or ""))
        if relevance < 0.5:
            continue
        records.append(_record(
            "openfoodfacts", code, title,
            f"https://world.openfoodfacts.org/product/{code}",
            {"brands": item.get("brands"), "categories": item.get("categories"), "ingredients": item.get("ingredients_text"), "lookup_query": lookup},
            relevance, "food_search", relevance,
        ))
        if len(records) >= 5:
            break
    return {"source": "openfoodfacts", "status": "ok" if records else "empty", "records": records, "query": query, "lookup_query": lookup}


async def _genbank(query: str) -> dict[str, Any]:
    search = await _get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        f"genbank-search-v1:{query}",
        {"db": "protein", "term": query, "retmax": 5, "retmode": "json"},
    )
    ids = ((search.get("esearchresult") or {}).get("idlist") or [])[:5]
    if not ids:
        return {"source": "genbank", "status": "empty", "records": [], "query": query}
    summary = await _get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        f"genbank-summary-v1:{','.join(ids)}",
        {"db": "protein", "id": ",".join(ids), "retmode": "json"},
    )
    result = summary.get("result") or {}
    records = []
    for uid in ids:
        row = result.get(uid) or {}
        accession = row.get("accessionversion") or row.get("caption") or uid
        title = row.get("title") or f"GenBank protein {accession}"
        relevance = _text_relevance(query, title)
        records.append(_record(
            "genbank", accession, title,
            f"https://www.ncbi.nlm.nih.gov/protein/{quote(str(accession), safe='')}",
            {
                "organism": row.get("organism"),
                "length": row.get("slen"),
                "moltype": row.get("moltype"),
                "accession": accession,
                "uid": uid,
                "lookup_query": query,
            },
            relevance, "genbank_protein_search", relevance,
        ))
    return {"source": "genbank", "status": "ok" if records else "empty", "records": records, "query": query, "note": "NCBI protein records; accession is the stable link, not a functional validation."}


async def _kegg(query: str) -> dict[str, Any]:
    text = await _get_text(
        f"https://rest.kegg.jp/find/compound/{quote(query, safe='')}",
        f"kegg-compound-v2:{query}",
    )
    records = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not re.fullmatch(r"[A-Za-z]\d{5}", parts[0].strip()):
            continue
        compound_id = parts[0].strip()
        title = parts[1][:240]
        relevance = _text_relevance(query, title)
        records.append(_record(
            "kegg", compound_id, title,
            f"https://www.kegg.jp/entry/{quote(compound_id, safe='')}",
            {"lookup_query": query, "kegg_id": compound_id},
            relevance, "kegg_find_compound", relevance,
        ))
        if len(records) >= 5:
            break
    return {"source": "kegg", "status": "ok" if records else "empty", "records": records, "query": query, "note": "KEGG REST; academic use, redistribution restricted. Verify current KEGG terms before reuse."}


async def _zinc(query: str) -> dict[str, Any]:
    try:
        payload = await _get_json(
            "https://zinc20.docking.org/substances.json",
            f"zinc-substances-v2:{query}",
            {"name": query, "limit": 5},
        )
    except Exception:
        return {
            "source": "zinc",
            "status": "link_only",
            "records": [],
            "query": query,
            "url": f"https://zinc.docking.org/substances/?name={quote(query, safe='')}",
            "note": "ZINC 现在对自动化 JSON 请求启用验证码/跳转；未复制任何数据。请打开链接，或先用 PubChem/UniChem 确认身份。",
        }
    rows = payload if isinstance(payload, list) else (payload.get("substances") or [])
    records = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        zinc_id = row.get("zinc_id") or row.get("zincid") or row.get("id")
        if not zinc_id:
            continue
        title = row.get("name") or row.get("smiles") or zinc_id
        relevance = _text_relevance(query, str(title))
        records.append(_record(
            "zinc", zinc_id, str(title),
            f"https://zinc.docking.org/substance/{quote(str(zinc_id), safe='')}/",
            {"smiles": row.get("smiles"), "inchikey": row.get("inchikey"), "purchasable": row.get("purchasable"), "lookup_query": query},
            relevance, "zinc_name_search", relevance,
        ))
    return {"source": "zinc", "status": "ok" if records else "empty", "records": records, "query": query, "note": "ZINC name search; if the endpoint is unavailable, use PubChem/UniChem identity and ZINC website."}


async def _string(uniprot_records: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for rec in uniprot_records[:2]:
        accession = rec["id"]
        taxon = rec.get("data", {}).get("taxon_id") or 9606
        payload = await _get_json(
            "https://string-db.org/api/json/interaction_partners",
            f"string-partners-v21:{accession}:{taxon}",
            {"identifiers": accession, "species": taxon, "limit": 10, "required_score": 400},
        )
        partners = []
        if isinstance(payload, list):
            for edge in payload[:10]:
                if edge.get("preferredName_A") != edge.get("preferredName_B"):
                    partners.append({"a": edge.get("preferredName_A"), "b": edge.get("preferredName_B"), "score": edge.get("score")})
        if partners:
            records.append(_record(
                "string", accession, f"STRING partners for {accession}",
                f"https://string-db.org/network/{taxon}.{accession}",
                {"partners": partners, "ncbi_taxon": taxon},
                1.0, "uniprot_accession", 0.9,
            ))
    return {"source": "string", "status": "ok" if records else "empty", "records": records, "note": "STRING 只在蛋白实体上下文调用，并使用 UniProt accession + taxon 作为输入。"}


def _massbank_link() -> dict[str, Any]:
    return {
        "source": "massbank",
        "status": "link_only",
        "records": [],
        "note": "MassBank 公共端点返回 HTML SPA，不伪装成 JSON 检索；请通过 PubChem 谱图中的 MassBank accession 打开原始记录。",
    }


def _cross_links(results: dict[str, Any], identity: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    pubchem_id = identity.get("pubchem_cid")
    inchikey = identity.get("inchikey")
    if pubchem_id and inchikey:
        for mapping_db, ids in (identity.get("mappings") or {}).items():
            if mapping_db == "pubchem":
                continue
            source = "chebi" if mapping_db == "chebi" else ("chembl" if mapping_db == "chembl" else mapping_db)
            for item_id in ids[:2]:
                links.append({
                    "from": f"pubchem:{pubchem_id}", "to": f"{source}:{item_id}",
                    "type": "exact_inchikey", "inchikey": inchikey,
                    "verified_by": "UniChem",
                    "note": "同一 InChIKey 的精确交叉引用；不是名称匹配。",
                })
    for rec in (results.get("pdb") or {}).get("records", []):
        uniprot_id = rec.get("data", {}).get("uniprot")
        if uniprot_id:
            links.append({
                "from": f"uniprot:{uniprot_id}", "to": f"pdb:{rec['id']}",
                "type": "uniprot_pdb_xref", "verified_by": "UniProt",
                "note": "UniProt 记录中的 PDB 交叉引用。",
            })
    for rec in (results.get("pubchem") or {}).get("records", []):
        for spec in rec.get("data", {}).get("spectra", []):
            if spec.get("accession"):
                links.append({
                    "from": f"pubchem:{rec['id']}", "to": f"massbank:{spec['accession']}",
                    "type": "spectrum_reference", "note": "PubChem 谱图记录中标注的 MassBank accession；为参考链接，不是结构身份验证。",
                })
    return links


GENERIC_QUERY_TERMS = {
    "binding", "interaction", "inhibition", "activation", "mechanism", "structure",
    "stability", "solubility", "bioavailability", "toxicity",
}
PROTEIN_QUERY_WORDS = (
    "protein", "peptide", "enzyme", "receptor", "kinase", "antibody",
    "albumin", "casein", "collagen", "lysozyme",
)


def route_queries(query: str, expansion: dict[str, Any] | None = None) -> tuple[str, str]:
    expansion = expansion or query_text.expand_query(query)
    matched_english = [item["english"] for item in expansion.get("matched", []) if item.get("english")]
    protein_terms = [term for term in matched_english if any(word in term for word in PROTEIN_QUERY_WORDS)]
    compound_terms = [
        term for term in matched_english
        if term not in protein_terms and term.lower() not in GENERIC_QUERY_TERMS
    ]
    fallback_terms = [
        term for term in query_text.terms(query)
        if term.lower() not in GENERIC_QUERY_TERMS
        and not any(word in term for word in PROTEIN_QUERY_WORDS)
    ]
    protein_query = protein_terms[0] if protein_terms else query
    compound_query = compound_terms[0] if compound_terms else (fallback_terms[-1] if fallback_terms else query)
    return protein_query, compound_query


async def search_all(query: str, sources: list[str] | None = None, entity: str | None = None, context: str | None = None) -> dict[str, Any]:
    original_query = _clean_query(query)
    if not original_query:
        raise ValueError("empty query")
    expansion = query_text.expand_query(original_query)
    query = expansion["expanded"] or original_query
    entity_kind, plan = classify_query(original_query, entity)
    allowed = ENTITY_SOURCES[entity_kind]
    requested = [str(source) for source in (sources or []) if source in _SPECS]
    rejected = []
    if requested:
        chosen = []
        for source in requested:
            if source in allowed:
                chosen.append(source)
            else:
                rejected.append({"source": source, "reason": f"该来源与实体类型 {entity_kind} 不匹配，已拒绝执行以避免无关结果"})
        selected_sources = chosen
    else:
        selected_sources = list(allowed)
    if not selected_sources:
        raise ValueError("no compatible sources for this entity")

    output: dict[str, Any] = {}
    identity: dict[str, Any] = {}
    protein_query, compound_query = route_queries(query, expansion)
    protein_query = context or protein_query
    public_identifier = context or (_localize_food_query(query) if entity_kind == "food" else query)

    async def run(source: str, coro: Any) -> None:
        try:
            output[source] = await coro
        except Exception as exc:
            output[source] = {"source": source, "status": "error", "error": str(exc)[:240], "records": []}

    # Anchors run first: identity must be established before cross-database links.
    if entity_kind in {"compound", "complex"} and "pubchem" in selected_sources:
        await run("pubchem", _pubchem(compound_query))
        pubchem_records = output.get("pubchem", {}).get("records", [])
        if pubchem_records:
            anchor = pubchem_records[0]
            identity["pubchem_cid"] = anchor["id"]
            identity["inchikey"] = anchor.get("data", {}).get("inchikey")
    if entity_kind in {"protein", "complex"} and "uniprot" in selected_sources:
        await run("uniprot", _uniprot(protein_query))
    uniprot_records = output.get("uniprot", {}).get("records", [])
    if uniprot_records:
        identity["uniprot_ids"] = [row["id"] for row in uniprot_records]

    if entity_kind in {"compound", "complex"} and "unichem" in selected_sources:
        await run("unichem", _unichem(str(identity.get("inchikey") or "")))
        identity["mappings"] = output.get("unichem", {}).get("mappings", {})
        for db, ids in identity["mappings"].items():
            identity[f"{db}_ids"] = ids

    tasks = []
    if "chebi" in selected_sources:
        chebi_ids = (identity.get("mappings") or {}).get("chebi", [])
        tasks.append(("chebi", _chebi_exact(chebi_ids[0]) if chebi_ids else _chebi_search(compound_query)))
    if "chembl" in selected_sources:
        chembl_ids = (identity.get("mappings") or {}).get("chembl", [])
        tasks.append(("chembl", _chembl_exact(chembl_ids[0]) if chembl_ids else _chembl_search(compound_query)))
    if "pdb" in selected_sources:
        tasks.append(("pdb", _pdb_from_uniprot(uniprot_records)))
    if "alphafold" in selected_sources:
        tasks.append(("alphafold", _alphafold(uniprot_records)))
    if "string" in selected_sources:
        tasks.append(("string", _string(uniprot_records)))
    if "europepmc" in selected_sources:
        tasks.append(("europepmc", _europepmc(public_identifier)))
    if "fdc" in selected_sources:
        tasks.append(("fdc", _fdc(query, query)))
    if "openfoodfacts" in selected_sources:
        tasks.append(("openfoodfacts", _openfoodfacts(query)))
    if "massbank" in selected_sources:
        output["massbank"] = _massbank_link()
    if "kegg" in selected_sources:
        tasks.append(("kegg", _kegg(compound_query)))
    if "zinc" in selected_sources:
        tasks.append(("zinc", _zinc(compound_query)))
    if "genbank" in selected_sources:
        tasks.append(("genbank", _genbank(protein_query)))

    if tasks:
        results = await asyncio.gather(*(coro for _, coro in tasks), return_exceptions=True)
        for (source, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                output[source] = {"source": source, "status": "error", "error": str(result)[:240], "records": []}
            else:
                output[source] = result

    for source in selected_sources:
        if source not in output:
            output[source] = {"source": source, "status": "skipped", "records": [], "reason": "依赖锚点未返回可验证标识符"}

    records = [record for result in output.values() for record in result.get("records", [])]
    for record in records:
        if record.get("relevance") is None:
            record["relevance"] = _text_relevance(original_query, f"{record.get('title', '')} {record.get('data', {})}")
        record["strength"] = query_text.strength(record.get("relevance"))
    records.sort(key=lambda item: float(item.get("relevance") or 0), reverse=True)
    for index, record in enumerate(records, 1):
        record["rank"] = index
    links = _cross_links(output, identity)
    return {
        "query": original_query,
        "query_expansion": expansion,
        "retrieved_at": _now(),
        "entity": entity_kind,
        "plan": {
            **plan,
            "query_original": original_query,
            "query_expanded": query,
            "compound_query": compound_query,
            "protein_query": protein_query,
            "matched_terms": expansion["matched"],
            "query_language": expansion["language"],
            "selected_sources": selected_sources,
            "rejected_sources": rejected,
            "ranking": "结果按词面/短语相关度排序；strength 是高/中/低分级，不是统计显著性。",
            "rule": "先分类实体，再选择数据库；化合物不查 UniProt/PDB/STRING，食品不查蛋白库，蛋白结构只通过 UniProt xref 映射。",
        },
        "identity": identity,
        "sources": output,
        "records": records,
        "cross_links": links,
        "notice": "在线记录缓存 24 h。每条记录保留来源、检索时间、原始链接、匹配依据和相关性；跨库链接只使用 InChIKey 或 UniProt/PDB xref。",
    }


def status() -> dict[str, Any]:
    return {
        "catalog": LICENSED_SOURCES,
        "sources": [
            {
                "id": key,
                "name": value["name"],
                "license": value["license"],
                "url": value["url"],
                "transport": "HTTPS JSON" if key != "massbank" else "HTML/link-only",
                "auth": "DEMO_KEY" if key == "fdc" else "none",
                "cache_hours": 24,
                "searchable": key != "massbank",
            }
            for key, value in _SPECS.items()
        ],
        "entity_policies": ENTITY_SOURCES,
        "retrieved_at": _now(),
        "notes": [
            "KEGG academic REST is queried only on demand; verify its current terms before redistributing results.",
            "MassBank is link-only: its public endpoint returns an HTML SPA, not a stable JSON API.",
            "ZINC browser verification may force link-only; failures are reported per source and do not block other sources.",
            "DrugBank, CCDC, ChemBook and university library resources require credentials/licenses and are not scraped.",
            "USDA FDC DEMO_KEY is rate-limited; set FDC_API_KEY for heavier use.",
            "UniChem is used to verify compound cross-references by InChIKey.",
            "PDB structures are selected from UniProt uniProtKBCrossReferences, not full-text searches.",
        ],
    }
