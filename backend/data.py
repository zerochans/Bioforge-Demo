from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import __version__

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RUNTIME_DIR = ROOT / "runtime"
JOBS_DIR = RUNTIME_DIR / "jobs"
DESIGNS_DIR = RUNTIME_DIR / "designs"
EVIDENCE_DIR = RUNTIME_DIR / "evidence"
COMPUTE_DIR = RUNTIME_DIR / "compute"
MODELS_DIR = RUNTIME_DIR / "models"
CACHE_DIR = RUNTIME_DIR / "cache"
LOGS_DIR = ROOT / "logs"
WEB_DIR = ROOT / "web"

PACK_FILES = (
    "proteins.json", "protectants.json", "compounds.json", "matrices.json", "spectra.json",
    "food_systems.json", "ingredients.json", "interactions.json", "sources.json", "cases.json",
    "ingredient_composition.json",
)
_LOCK = threading.Lock()


def ensure_dirs() -> None:
    for path in (RUNTIME_DIR, JOBS_DIR, DESIGNS_DIR, EVIDENCE_DIR, COMPUTE_DIR, MODELS_DIR, CACHE_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=24)
def _load(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load(name: str) -> dict[str, Any]:
    if name not in PACK_FILES:
        raise KeyError(f"unknown dataset: {name}")
    return _load(name)


def proteins() -> list[dict[str, Any]]:
    return list(load("proteins.json")["items"])


def protectants() -> list[dict[str, Any]]:
    return list(load("protectants.json")["items"])


def protectant_interactions() -> dict[str, float]:
    return dict(load("protectants.json").get("interactions", {}))


def compounds() -> list[dict[str, Any]]:
    return list(load("compounds.json")["items"])


def matrices() -> list[dict[str, Any]]:
    return list(load("matrices.json")["items"])


def spectra() -> list[dict[str, Any]]:
    return list(load("spectra.json")["items"])


def food_systems() -> list[dict[str, Any]]:
    return list(load("food_systems.json")["items"])


def ingredients() -> list[dict[str, Any]]:
    return list(load("ingredients.json")["items"])


def food_interactions() -> list[dict[str, Any]]:
    return list(load("interactions.json")["items"])


def sources() -> list[dict[str, Any]]:
    return list(load("sources.json")["items"])


def cases() -> list[dict[str, Any]]:
    return list(load("cases.json")["items"])


def by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def get_protein(protein_id: str) -> dict[str, Any]:
    item = by_id(proteins(), protein_id)
    if item is None:
        raise KeyError(f"unknown protein: {protein_id}")
    return item


def get_compound(compound_id: str) -> dict[str, Any]:
    item = by_id(compounds(), compound_id)
    if item is None:
        raise KeyError(f"unknown compound: {compound_id}")
    return item


def get_matrix(matrix_id: str) -> dict[str, Any]:
    item = by_id(matrices(), matrix_id)
    if item is None:
        item = by_id(matrices(), "beverage_generic")
    assert item is not None
    return item


def get_protectant(protectant_id: str) -> dict[str, Any]:
    item = by_id(protectants(), protectant_id)
    if item is None:
        raise KeyError(f"unknown protectant: {protectant_id}")
    return item


def get_food_system(system_id: str) -> dict[str, Any]:
    item = by_id(food_systems(), system_id)
    if item is None:
        item = by_id(food_systems(), "beverage_generic")
    assert item is not None
    return item


def get_ingredient(ingredient_id: str) -> dict[str, Any]:
    item = by_id(ingredients(), ingredient_id)
    if item is None:
        raise KeyError(f"unknown ingredient: {ingredient_id}")
    return item


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", text.lower()).strip()


def search_proteins(query: str, limit: int = 8) -> list[dict[str, Any]]:
    needle = _norm(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in proteins():
        hay = " ".join(
            str(item.get(key, ""))
            for key in ("id", "name", "cn_name", "aliases", "tags", "source_organism", "uniprot", "food_status")
        )
        hay = _norm(hay)
        if not needle or needle in hay:
            score = 1.0
        else:
            tokens = [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", needle) if len(t) >= 2]
            hits = sum(1 for t in tokens if t in hay)
            score = hits / max(1, len(tokens))
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [item for _, item in scored[:limit]]


def search_compounds(query: str, limit: int = 10) -> list[dict[str, Any]]:
    needle = _norm(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in compounds():
        hay = " ".join(
            str(item.get(key, ""))
            for key in ("id", "name", "cn_name", "category", "formula", "tags", "food_status")
        )
        hay = _norm(hay)
        if not needle:
            score = 0.5
        elif needle in hay:
            score = 1.0
        else:
            tokens = [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", needle) if len(t) >= 2]
            hits = sum(1 for t in tokens if t in hay)
            score = hits / max(1, len(tokens))
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [item for _, item in scored[:limit]]


def search_spectra(query: str, limit: int = 20) -> list[dict[str, Any]]:
    needle = _norm(query)
    hits = []
    for item in spectra():
        hay = _norm(f"{item.get('id')} {item.get('compound_id')} {item.get('type')} {item.get('solvent')} {item.get('notes')}")
        if not needle or needle in hay:
            hits.append(item)
    return hits[:limit]


def search_ingredients(query: str, limit: int = 12) -> list[dict[str, Any]]:
    needle = _norm(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in ingredients():
        hay = _norm(" ".join(str(item.get(key, "")) for key in ("id", "name", "cn_name", "category", "functions")))
        if not needle:
            score = 0.5
        elif needle in hay:
            score = 1.0
        else:
            tokens = [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", needle) if len(t) >= 2]
            score = sum(1 for t in tokens if t in hay) / max(1, len(tokens))
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [item for _, item in scored[:limit]]


def dataset_manifest() -> dict[str, Any]:
    manifest = {}
    for name in PACK_FILES:
        path = DATA_DIR / name
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        payload = load(name)
        manifest[name] = {
            "sha256_16": digest,
            "bytes": path.stat().st_size,
            "items": len(payload.get("items", [])),
            "schema_version": payload.get("schema_version"),
            "source_type": payload.get("source_type", "curated"),
        }
    manifest["engine_version"] = __version__
    manifest["root"] = str(ROOT)
    return manifest


def compound_options(food_safe_only: bool = False) -> list[dict[str, Any]]:
    items = compounds()
    if food_safe_only:
        items = [item for item in items if item.get("food_safe")]
    return items


def fluorescent_candidates(food_safe_only: bool = False) -> list[dict[str, Any]]:
    result = []
    for item in proteins():
        if item.get("type") != "fluorescent_protein":
            continue
        if food_safe_only and not str(item.get("food_status", "")).startswith("food"):
            continue
        result.append({**item, "_kind": "protein"})
    for item in compounds():
        if not item.get("fluorescence"):
            continue
        if food_safe_only and not item.get("food_safe"):
            continue
        result.append({**item, "_kind": "compound"})
    return result


def clear_cache() -> None:
    with _LOCK:
        _load.cache_clear()
