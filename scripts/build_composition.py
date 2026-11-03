"""Build a per-ingredient nutrient snapshot.

Primary source: USDA FoodData Central SR Legacy (public domain), downloaded as
the official JSON archive. Every mapped record keeps its fdcId, description,
match type and source URL. Ingredients without a defensible match keep a
curated screening estimate and are explicitly labelled as such.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import data  # noqa: E402
from backend import food as legacy_food  # noqa: E402

SR_URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip"

# Ingredient -> FDC record selected by exact description. These are direct
# matches to the ingredient form used by the formulation engine, except where
# match is marked as a proxy.
FDC_MAP: dict[str, tuple[int, str, str]] = {
    "water": (173647, "exact", "Beverages, water, tap, drinking"),
    "sucrose": (169655, "exact", "Sugars, granulated"),
    "fructose": (169896, "exact", "Sweeteners, tabletop, fructose, dry, powder"),
    "glucose_syrup": (168837, "exact", "Syrups, corn, light"),
    "gelatin": (169599, "exact", "Gelatins, dry powder, unsweetened"),
    "wheat_flour": (168894, "exact", "Wheat flour, white, all-purpose, enriched, bleached"),
    "oat_flour": (169741, "exact", "Oat flour, partially debranned"),
    "rice_flour": (169714, "exact", "Rice flour, white, unenriched"),
    "corn_flour": (169748, "exact", "Corn flour, whole-grain, white"),
    "corn_starch": (169698, "exact", "Cornstarch"),
    "wheat_gluten": (168147, "exact", "Vital wheat gluten"),
    "soy_protein": (174276, "exact", "Soy protein isolate"),
    "milk_powder": (170876, "exact", "Milk, dry, whole, with added vitamin D"),
    "cream": (170859, "exact", "Cream, fluid, heavy whipping"),
    "egg_white": (172183, "exact", "Egg, white, raw, fresh"),
    "egg_yolk": (172184, "exact", "Egg, yolk, raw, fresh"),
    "pork_lean": (168230, "exact", "Pork, fresh, loin, whole, separable lean only, raw"),
    "beef_lean": (171757, "exact", "Beef, round, top round steak, boneless, separable lean only, trimmed to 0\" fat, all grades, raw"),
    "chicken_breast": (171077, "exact", "Chicken, broiler or fryers, breast, skinless, boneless, meat only, raw"),
    "pork_fat": (167813, "exact", "Pork, fresh, separable fat, raw"),
    "sunflower_oil": (172338, "exact", "Oil, sunflower, high oleic (70% and over)"),
    "canola_oil": (172336, "exact", "Oil, canola"),
    "cocoa_butter": (171421, "exact", "Oil, cocoa butter"),
    "coconut_oil": (171412, "exact", "Oil, coconut"),
    "lecithin": (171426, "exact", "Oil, soybean lecithin"),
    "vinegar": (172237, "exact", "Vinegar, distilled"),
    "sodium_chloride": (173468, "exact", "Salt, table"),
    "baking_soda": (175040, "exact", "Leavening agents, baking soda"),
    "vanilla": (173471, "exact", "Vanilla extract"),
    "cocoa_powder": (169593, "exact", "Cocoa, dry powder, unsweetened"),
    "tomato_paste": (170459, "exact", "Tomato products, canned, paste, without salt added"),
    "cabbage": (169975, "exact", "Cabbage, raw"),
    "oats": (169705, "exact", "Oats (Includes foods for USDA's Food Distribution Program)"),
    "orange_juice_concentrate": (169923, "exact", "Orange juice, frozen concentrate, unsweetened, undiluted"),
    "molasses": (168820, "exact", "Molasses"),
    "onion_powder": (170002, "proxy", "Onions, dehydrated flakes (proxy for powder)"),
}

NUTRIENT_MAP = {
    "203": "protein_g",
    "204": "fat_g",
    "205": "carb_g",
    "269": "sugar_g",
    "291": "fiber_g",
    "307": "sodium_mg",
    "208": "energy_kcal",
}


def _download(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SR_URL, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_sr(path: Path) -> dict[int, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["fdcId"]): item for item in payload["SRLegacyFoods"]}


def _values(record: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for nutrient in record.get("foodNutrients", []):
        number = str(nutrient.get("nutrient", {}).get("number", ""))
        key = NUTRIENT_MAP.get(number)
        if key and nutrient.get("amount") is not None:
            values[key] = round(float(nutrient["amount"]), 3)
    return values


def build(sr_json: Path, output: Path) -> dict:
    sr = _load_sr(sr_json)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    for item in data.ingredients():
        fallback = legacy_food._nutrient(item["id"])
        nutrient = {
            "protein_g": round(float(fallback.get("protein", 0.0)), 3),
            "fat_g": round(float(fallback.get("fat", 0.0)), 3),
            "sugar_g": round(float(fallback.get("sugar", 0.0)), 3),
            "fiber_g": round(float(fallback.get("fiber", 0.0)), 3),
            "sodium_mg": round(float(fallback.get("sodium_mg", 0.0)), 3),
        }
        record = {
            "ingredient_id": item["id"],
            "name": item["name"],
            "cn_name": item["cn_name"],
            "nutrients": nutrient,
            "source_type": "curated_estimate",
            "confidence": "low",
            "match": "none",
            "fdc_id": None,
            "fdc_description": None,
            "source_url": None,
            "note": "No defensible USDA SR Legacy match; retained as a screening estimate. Do not use as a label value.",
        }
        if item["id"] in FDC_MAP:
            fdc_id, match, expected = FDC_MAP[item["id"]]
            source = sr.get(fdc_id)
            if source and expected.lower() in source["description"].lower():
                values = _values(source)
                if values:
                    nutrient.update({key: value for key, value in values.items() if key in nutrient})
                    record.update({
                        "nutrients": nutrient,
                        "source_type": "usda_fdc_sr_legacy",
                        "confidence": "medium",
                        "match": match,
                        "fdc_id": fdc_id,
                        "fdc_description": source["description"],
                        "source_url": f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
                        "note": "USDA SR Legacy food composition, per 100 g. SR Legacy is a compiled reference dataset, not a measurement of this supplier lot.",
                    })
        records.append(record)
    manifest = {
        "schema_version": "2.1",
        "source_type": "usda_fdc_sr_legacy + curated_estimate",
        "generated_utc": generated,
        "basis": "per 100 g edible portion",
        "primary_source": {
            "id": "usda_fdc_sr_legacy",
            "name": "USDA FoodData Central SR Legacy",
            "url": SR_URL,
            "license": "US public domain (CC0)",
            "sha256": _sha256(sr_json),
            "published": "2018-04 (download)",
        },
        "methods": [
            "For mapped ingredients, nutrient amounts are copied from the selected SR Legacy record.",
            "Unmapped ingredients retain the v2 curated screening estimate and are labelled curated_estimate/low.",
            "No supplier lot, brand or measured product data are implied.",
        ],
        "counts": {
            "ingredients": len(records),
            "fdc_mapped": sum(1 for row in records if row["source_type"] == "usda_fdc_sr_legacy"),
            "curated_estimates": sum(1 for row in records if row["source_type"] == "curated_estimate"),
        },
        "items": records,
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest["counts"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sr-json", type=Path, default=Path("/tmp/opencode/fdc/FoodData_Central_sr_legacy_food_json_2018-04.json"))
    parser.add_argument("--download", type=Path, default=Path("/tmp/opencode/fdc/sr.zip"))
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "ingredient_composition.json")
    args = parser.parse_args()
    if not args.sr_json.exists():
        _download(args.download)
        with zipfile.ZipFile(args.download) as archive:
            archive.extractall(args.sr_json.parent)
    counts = build(args.sr_json, args.output)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
