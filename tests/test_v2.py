from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import auth, data, datasources, food, graph  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BIOFORGE_ADMIN_USER", "tester")
    monkeypatch.setenv("BIOFORGE_ADMIN_PASSWORD", "testpass123")
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "auth.json")
    monkeypatch.setattr(auth, "SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(auth, "LOGIN_PATH", tmp_path / "login.txt")
    monkeypatch.setattr(data, "DESIGNS_DIR", tmp_path / "designs")
    (tmp_path / "designs").mkdir()
    from backend import app_v2
    with TestClient(app_v2.app) as test_client:
        yield test_client


def test_v2_dataset_counts():
    assert len(data.food_systems()) >= 20
    assert len(data.ingredients()) >= 90
    assert len(data.food_interactions()) >= 40
    assert len(data.cases()) >= 8
    assert len(data.sources()) >= 12


def test_v2_all_cases_are_multi_answer_and_constrained():
    for case in data.cases():
        result = food.design_food(case["query"])
        assert result["design_id"].startswith("F")
        assert len(result["portfolio"]) >= 6
        assert result["selected"]["constraint_met"] is True
        assert result["formulation"]["ingredients"]
        assert "provenance" in result and result["provenance"]["datasets"]
        assert result["logic_chain"]
        assert abs(sum(x["pct"] for x in result["formulation"]["ingredients"]) - 100) < 0.05


def test_v2_graph_has_evidence_and_interactions():
    result = food.design_food("低钠番茄酱，钠降低 30%，pH 3.7")
    g = graph.build_design_graph(result)
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"design", "food_system", "strategy", "ingredient", "data_source"} <= kinds
    assert g["summary"]["ingredients"] >= 5
    assert any(e["type"] in {"interaction", "constraint", "supported_by"} for e in g["edges"])
    table = graph.evidence_table(result)
    assert table and table[0]["ingredient"] and table[0]["claim"]


def test_v2_datasource_registry():
    status = datasources.status()
    assert len(status["sources"]) >= 11
    assert all("license" in item for item in status["sources"])


def test_v2_login_design_graph_api(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/v2/cases").status_code == 401
    bad = client.post("/api/auth/login", json={"username": "tester", "password": "wrong"})
    assert bad.status_code == 401
    login = client.post("/api/auth/login", json={"username": "tester", "password": "testpass123"})
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "tester"
    assert client.get("/api/auth/me").status_code == 200
    cases = client.get("/api/v2/cases")
    assert cases.status_code == 200 and len(cases.json()["items"]) >= 8
    design = client.post("/api/v2/design", json={"query": "高蛋白无麸质面包，蛋白 ≥ 12%", "options": {"mode": "food"}})
    assert design.status_code == 200, design.text
    payload = design.json()
    assert payload["design_id"].startswith("F")
    assert len(payload["portfolio"]) == 8
    path = data.DESIGNS_DIR / f"{payload['design_id']}.json"
    assert path.exists()
    graph_resp = client.post("/api/v2/graph", json={"design_id": payload["design_id"]})
    assert graph_resp.status_code == 200
    assert graph_resp.json()["nodes"]
    caps = client.get("/api/v2/compute/capabilities")
    assert caps.status_code == 200
    assert any(t["id"] == "vina" for t in caps.json()["tools"])
    assert client.post("/api/auth/logout").status_code == 200


def test_v2_artifact_traversal_blocked(client):
    login = client.post("/api/auth/login", json={"username": "tester", "password": "testpass123"})
    assert login.status_code == 200
    assert client.get("/api/v2/compute/jobs/../../etc/passwd").status_code in {404, 422}
    assert client.get("/api/v2/designs/../../etc/passwd").status_code in {404, 422}


def test_v21_entity_planner_prevents_cross_domain_queries():
    compound, compound_plan = datasources.classify_query("quercetin")
    assert compound == "compound"
    assert "uniprot" not in compound_plan["sources"]
    assert "pdb" not in compound_plan["sources"]
    assert "string" not in compound_plan["sources"]
    assert "fdc" not in compound_plan["sources"]
    protein, protein_plan = datasources.classify_query("beta-lactoglobulin")
    assert protein == "protein"
    assert "uniprot" in protein_plan["sources"]
    assert "pubchem" not in protein_plan["sources"]
    food, food_plan = datasources.classify_query("低钠番茄酱")
    assert food == "food"
    assert "fdc" in food_plan["sources"]
    assert "uniprot" not in food_plan["sources"]


def test_v21_cross_links_only_use_verified_identity():
    fake = {
        "pdb": {"records": [{"id": "1B0O", "data": {"uniprot": "P02754"}}]},
        "pubchem": {"records": [{"id": "5280343", "data": {"spectra": []}}]},
        "chebi": {"records": [{"id": "CHEBI:16243"}]},
    }
    links = datasources._cross_links(fake, {})
    assert any(link["type"] == "uniprot_pdb_xref" for link in links)
    assert not any(link["type"] == "same_compound_candidate" for link in links)
    assert not any(link["type"] == "exact_inchikey" for link in links)
    verified = datasources._cross_links(fake, {"pubchem_cid": "5280343", "inchikey": "REFJWTPEDVJJIY-UHFFFAOYSA-N", "mappings": {"chebi": ["CHEBI:16243"]}})
    assert any(link["type"] == "exact_inchikey" and link["to"] == "chebi:CHEBI:16243" for link in verified)


def test_v21_composition_snapshot_is_versioned_and_labelled():
    comp = json.loads((data.DATA_DIR / "ingredient_composition.json").read_text(encoding="utf-8"))
    assert comp["counts"] == {"ingredients": 96, "fdc_mapped": 35, "curated_estimates": 61}
    assert comp["primary_source"]["license"] == "US public domain (CC0)"
    assert comp["primary_source"]["sha256"].startswith("70d4235a")
    assert all("source_type" in row and "confidence" in row for row in comp["items"])
    assert sum(1 for row in comp["items"] if row["source_type"] == "usda_fdc_sr_legacy") == 35


def test_v21_food_design_is_deterministic_and_auditable():
    first = food.design_food("低钠番茄酱，钠降低 30%，pH 3.7")
    second = food.design_food("低钠番茄酱，钠降低 30%，pH 3.7")
    assert first["selected"]["recipe"] == second["selected"]["recipe"]
    selected = first["selected"]
    assert selected["constraint_report"]
    assert selected["intervals"]["protein_pct"][0] <= selected["intervals"]["protein_pct"][1]
    assert selected["metric_provenance"]
    assert selected["composition"]["mapped_mass_pct"] > 0
    assert first["reasoning"]["validation_required"]
    assert first["package_version"] == "2.1.0"
    assert first["provenance"]["datasets"]["ingredient_composition.json"]["source_type"].startswith("usda_fdc_sr_legacy")


def test_v21_fdc_fallback_uses_local_snapshot():
    result = datasources._local_fdc("orange juice", "orange juice", "test 429")
    assert result["status"] in {"degraded", "empty"}
    if result["records"]:
        record = result["records"][0]
        assert record["match_basis"] == "local_fdc_snapshot"
        assert record["data"]["fallback_reason"] == "test 429"
        assert record["data"]["snapshot"].startswith("FoodData_Central_sr_legacy")


def test_v21_absolute_units_and_ph_range_are_parsed():
    brief = food.parse_food_brief("高蛋白无麸质面包，蛋白质 ≥ 12 g/100g，钠 < 300 mg/100g，pH 4.2–4.6")
    targets = brief["targets"]
    assert targets["protein_min_pct"] == 12.0
    assert targets["sodium_max_mg"] == 300.0
    assert targets["low_sodium"] is True
    assert targets["ph_range"] == [4.2, 4.6]
    assert targets["ph"] == pytest.approx(4.4)
    salt = food.parse_food_brief("盐 < 1 g/100g")
    assert salt["targets"]["sodium_max_mg"] == 400.0
    shelf = food.parse_food_brief("低糖，稳定 12 个月")
    assert shelf["targets"]["sugar_max_pct"] == 5.0
