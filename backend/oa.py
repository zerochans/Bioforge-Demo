from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from . import data

EMAIL_KEYS = ("BIOFORGE_CONTACT_EMAIL", "OPENALEX_MAILTO", "UNPAYWALL_EMAIL")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
PMID_RE = re.compile(r"^\d{5,9}$")
TIMEOUT = httpx.Timeout(6.0, connect=3.5)


def _secret_env() -> dict[str, str]:
    path = data.RUNTIME_DIR / "secrets" / "contact.env"
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


def contact_email() -> str:
    for key in EMAIL_KEYS:
        if os.environ.get(key):
            return os.environ[key].strip()
    return _secret_env().get("BIOFORGE_CONTACT_EMAIL", "").strip()


def _headers() -> dict[str, str]:
    email = contact_email()
    agent = "BioForge-Studio/3.2"
    if email:
        agent += f" (mailto:{email})"
    return {"User-Agent": agent, "Accept": "application/json"}




async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(2):
        try:
            return await client.get(url, params=params, headers=_headers())
        except Exception as exc:
            last = exc
            if attempt == 0:
                await asyncio.sleep(0.25)
    assert last is not None
    raise last

def _doi_from(text: str) -> str | None:
    match = DOI_RE.search(text or "")
    return match.group(0).rstrip(".,;)") if match else None


def _identifier(text: str) -> tuple[str, str]:
    value = (text or "").strip()
    doi = _doi_from(value)
    if doi:
        return "doi", doi
    pmid = re.sub(r"^pmid[:\s]*", "", value, flags=re.I).strip()
    if PMID_RE.match(pmid):
        return "pmid", pmid
    raise ValueError("请输入 DOI（10.xxxx/...）或 PubMed PMID。")


def _ezproxy(url: str) -> str | None:
    prefix = os.environ.get("BIOFORGE_EZPROXY_PREFIX", "").strip()
    if not prefix:
        return None
    return f"{prefix.rstrip('/')}/login?url={quote(url, safe='')}"


def _links(doi: str | None, pmid: str | None, pmcid: str | None = None) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    if doi:
        doi_url = f"https://doi.org/{doi}"
        links.append({"label": "DOI 原文入口", "url": doi_url, "kind": "doi"})
        ez = _ezproxy(doi_url)
        if ez:
            links.append({"label": "通过机构 EZproxy", "url": ez, "kind": "institution"})
    if pmid:
        links.append({"label": "PubMed", "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "kind": "pubmed"})
    if pmcid:
        links.append({"label": "Europe PMC 全文", "url": f"https://europepmc.org/article/PMC/{pmcid}", "kind": "oa"})
    if doi:
        links.append({"label": "Unpaywall 合法 OA 查询", "url": f"https://unpaywall.org/{doi}", "kind": "oa"})
        links.append({"label": "OpenAlex 记录", "url": f"https://api.openalex.org/works/https://doi.org/{doi}", "kind": "metadata"})
    links.append({"label": "华南理工大学图书馆", "url": "https://www.lib.scut.edu.cn/", "kind": "institution"})
    links.append({"label": "CARSI 机构登录", "url": "https://www.carsi.edu.cn/", "kind": "institution"})
    return links


async def _crossref(client: httpx.AsyncClient, doi: str) -> dict[str, Any]:
    params = {}
    if contact_email():
        params["mailto"] = contact_email()
    response = await _get(client, f"https://api.crossref.org/works/{quote(doi, safe='/')}", params)
    if response.status_code != 200:
        return {}
    message = response.json().get("message", {})
    return {
        "title": (message.get("title") or [""])[0],
        "authors": [
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
            for author in message.get("author", [])
        ][:12],
        "journal": (message.get("container-title") or [""])[0],
        "year": (message.get("issued", {}).get("date-parts") or [[None]])[0][0],
        "publisher": message.get("publisher"),
        "type": message.get("type"),
        "url": message.get("URL"),
    }


async def _unpaywall(client: httpx.AsyncClient, doi: str) -> dict[str, Any]:
    email = contact_email()
    if not email:
        return {"status": "email_required", "locations": []}
    response = await _get(client, f"https://api.unpaywall.org/v2/{quote(doi, safe='/')}", {"email": email})
    if response.status_code != 200:
        return {"status": "unavailable", "locations": []}
    payload = response.json()
    locations = []
    for location in payload.get("oa_locations") or []:
        url = location.get("url_for_pdf") or location.get("url")
        if not url:
            continue
        locations.append({
            "url": url,
            "host": location.get("host_type"),
            "version": location.get("version"),
            "license": location.get("license"),
            "is_best": bool(location.get("is_best")),
        })
    locations.sort(key=lambda item: item["is_best"], reverse=True)
    return {
        "status": "oa" if payload.get("is_oa") else "closed",
        "is_oa": bool(payload.get("is_oa")),
        "title": payload.get("title"),
        "year": payload.get("year"),
        "journal": payload.get("journal_name"),
        "oa_status": payload.get("oa_status"),
        "journal": payload.get("journal_name"),
        "publisher": payload.get("publisher"),
        "locations": locations[:8],
    }


async def _europe_pmc(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    response = await _get(
        client,
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        {"query": query, "format": "json", "pageSize": 3, "resultType": "core"},
    )
    if response.status_code != 200:
        return {}
    results = response.json().get("resultList", {}).get("result", [])
    if not results:
        return {}
    item = results[0]
    return {
        "title": item.get("title"),
        "authors": item.get("authorString"),
        "journal": item.get("journalTitle"),
        "year": item.get("pubYear"),
        "doi": item.get("doi"),
        "pmid": item.get("pmid"),
        "pmcid": item.get("pmcid"),
        "is_oa": item.get("isOpenAccess") == "Y",
        "license": item.get("license"),
        "url": item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url"),
    }


async def resolve(identifier: str) -> dict[str, Any]:
    kind, value = _identifier(identifier)
    doi = value if kind == "doi" else None
    pmid = value if kind == "pmid" else None
    result: dict[str, Any] = {
        "identifier": value,
        "kind": kind,
        "doi": doi,
        "pmid": pmid,
        "title": None,
        "authors": [],
        "journal": None,
        "year": None,
        "unpaywall": {"status": "not_checked", "locations": []},
        "links": _links(doi, pmid),
        "policy": "仅解析公开元数据与合法 OA 位置；不绕过付费墙、不提供 Sci-Hub 链接，也不收集机构账号密码。",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        if doi:
            cross, unpay, epmc = await asyncio.gather(
                _crossref(client, doi),
                _unpaywall(client, doi),
                _europe_pmc(client, f'DOI:"{doi}"'),
                return_exceptions=True,
            )
            if isinstance(cross, Exception):
                result["crossref_error"] = str(cross)[:160]
            else:
                result.update({k: v for k, v in cross.items() if v})
            if isinstance(unpay, Exception):
                result["unpaywall"] = {"status": "error", "locations": [], "error": str(unpay)[:160]}
            else:
                result["unpaywall"] = unpay
                for key in ("title", "year", "journal", "publisher"):
                    if not result.get(key) and unpay.get(key):
                        result[key] = unpay[key]
            if isinstance(epmc, Exception):
                result["europepmc_error"] = str(epmc)[:160]
            elif epmc:
                for key, value in epmc.items():
                    if value and (key not in result or not result.get(key)):
                        result[key] = value
        elif pmid:
            epmc = await _europe_pmc(client, f"EXT_ID:{pmid} AND SRC:MED")
            if epmc:
                for key, value in epmc.items():
                    if value and (key not in result or not result.get(key)):
                        result[key] = value
                result["doi"] = result.get("doi")
                if result.get("doi"):
                    result["links"] = _links(result["doi"], pmid, result.get("pmcid"))
    if result.get("doi") and not any(link["kind"] == "doi" for link in result["links"]):
        result["links"] = _links(result["doi"], result.get("pmid"), result.get("pmcid"))
    result["access"] = "open" if result.get("unpaywall", {}).get("is_oa") or result.get("is_oa") else "institutional_or_publisher"
    return result
