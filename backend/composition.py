from __future__ import annotations

from functools import lru_cache
from typing import Any

from . import data

COMPOSITION_PATH = data.DATA_DIR / "ingredient_composition.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    import json
    return json.loads(COMPOSITION_PATH.read_text(encoding="utf-8"))


def _index() -> dict[str, dict[str, Any]]:
    return {row["ingredient_id"]: row for row in _load()["items"]}


def get(ingredient_id: str) -> dict[str, Any]:
    return _index().get(ingredient_id, {
        "ingredient_id": ingredient_id,
        "nutrients": {"protein_g": 0.0, "fat_g": 0.0, "sugar_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0},
        "source_type": "curated_estimate",
        "confidence": "low",
        "match": "none",
        "fdc_id": None,
        "note": "missing composition record",
    })


def nutrients(ingredient_id: str) -> dict[str, float]:
    n = get(ingredient_id)["nutrients"]
    return {
        "protein": float(n.get("protein_g", 0.0)),
        "fat": float(n.get("fat_g", 0.0)),
        "sugar": float(n.get("sugar_g", 0.0)),
        "fiber": float(n.get("fiber_g", 0.0)),
        "sodium_mg": float(n.get("sodium_mg", 0.0)),
    }


def manifest() -> dict[str, Any]:
    payload = _load()
    return {
        "schema_version": payload.get("schema_version"),
        "generated_utc": payload.get("generated_utc"),
        "basis": payload.get("basis"),
        "primary_source": payload.get("primary_source"),
        "counts": payload.get("counts"),
        "methods": payload.get("methods"),
    }


def summary(recipe: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [get(row["id"]) for row in recipe]
    mapped = [row for row in rows if row.get("source_type") == "usda_fdc_sr_legacy"]
    mass = sum(float(row.get("pct", 0.0)) for row in recipe)
    mapped_mass = sum(float(recipe[i].get("pct", 0.0)) for i, row in enumerate(rows) if row.get("source_type") == "usda_fdc_sr_legacy")
    return {
        "source": "USDA FoodData Central SR Legacy + curated estimates",
        "mapped_ingredients": len(mapped),
        "estimated_ingredients": len(rows) - len(mapped),
        "mapped_mass_pct": round(mapped_mass / mass * 100.0, 2) if mass else 0.0,
        "basis": "per 100 g ingredient; recipe values are mass-weighted",
        "note": "SR Legacy is a compiled reference dataset, not a measurement of the actual ingredient lot.",
    }
