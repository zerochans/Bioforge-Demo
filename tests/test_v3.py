from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import auth, data, lab  # noqa: E402


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
    monkeypatch.setattr(lab, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(lab, "ARTIFACT_DIR", tmp_path / "models")
    from backend import app_v3
    with TestClient(app_v3.app) as test_client:
        yield test_client


def login(client):
    response = client.post("/api/auth/login", json={"username": "tester", "password": "testpass123"})
    assert response.status_code == 200, response.text


def import_demo(client):
    response = client.post("/api/v3/lab/datasets/demo")
    assert response.status_code == 200, response.text
    return response.json()


def train_demo(client, dataset_id, **overrides):
    payload = {
        "dataset_id": dataset_id,
        "target": "stability_days",
        "algorithm": "random_forest",
        "include_synthetic": True,
        "cv_folds": 5,
    }
    payload.update(overrides)
    response = client.post("/api/v3/lab/train", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_v3_health_static_and_auth_gate(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["version"] == "3.2.2"
    assert body["lab_version"] == "3.2.2"
    assert body["mode"] == "food+biologic+lab"
    assert client.get("/api/v3/lab/overview").status_code == 401
    shell = client.get("/")
    assert shell.status_code == 200
    assert "BioForge Studio 3.2" in shell.text
    assert "模型实验室" in shell.text
    script = client.get("/lab.js")
    assert script.status_code == 200
    assert "Bayesian" in script.text or "贝叶斯" in script.text


def test_v3_demo_train_and_leakage_guard(client):
    login(client)
    dataset = import_demo(client)
    assert dataset["row_count"] == 180
    assert dataset["source_type"] == "synthetic"
    assert dataset["training"]["needs_synthetic_opt_in"] is True
    targets = set(dataset["target_candidates"])
    features = set(dataset["feature_candidates"])
    assert "stability_days" in targets
    for outcome in ("particle_size_nm", "viscosity_mpas", "sensory_score"):
        assert outcome in targets
        assert outcome not in features

    blocked = client.post("/api/v3/lab/train", json={
        "dataset_id": dataset["id"],
        "target": "stability_days",
        "algorithm": "random_forest",
        "include_synthetic": False,
    })
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "synthetic_opt_in_required"

    result = train_demo(client, dataset["id"])
    model = result["model"]
    assert model["target"] == "stability_days"
    assert model["dataset"]["hash"] == dataset["hash"]
    assert model["metrics"]["r2"] > 0.5
    assert model["metrics"]["n"] == 180
    assert len(model["features"]) == 11
    assert "stability_days" not in model["features"]
    assert "particle_size_nm" not in model["features"]
    assert model["parity"] and model["feature_importance"] and model["fold_metrics"]
    assert client.get(f"/api/v3/lab/models/{model['model_id']}").status_code == 200


def test_v3_optimize_feedback_predict_and_export(client):
    login(client)
    dataset = import_demo(client)
    model = train_demo(client, dataset["id"])["model"]
    optimized = client.post("/api/v3/lab/optimize", json={
        "model_id": model["model_id"],
        "direction": "maximize",
        "n_candidates": 3,
        "search_size": 512,
        "space": {"system": {"values": ["yogurt"]}, "ph": {"min": 4.2, "max": 4.6}},
        "seed": 7,
    })
    assert optimized.status_code == 200, optimized.text
    run = optimized.json()
    assert len(run["candidates"]) == 3
    for candidate in run["candidates"]:
        assert candidate["features"]["system"] == "yogurt"
        assert 4.2 <= candidate["features"]["ph"] <= 4.6
        assert candidate["lower_95"] < candidate["predicted"] < candidate["upper_95"]
        assert candidate["confidence"] in {"high", "medium", "low"}
    assert client.get(f"/api/v3/lab/runs/{run['run_id']}").status_code == 200
    run_csv = client.get(f"/api/v3/lab/runs/{run['run_id']}/csv")
    assert run_csv.status_code == 200
    assert "candidate_id" in run_csv.text

    candidate = run["candidates"][0]
    predicted = client.post("/api/v3/lab/predict", json={
        "model_id": model["model_id"],
        "records": [candidate["features"]],
    })
    assert predicted.status_code == 200, predicted.text
    assert predicted.json()["predictions"][0]["prediction"] is not None

    feedback = client.post("/api/v3/lab/feedback", json={
        "model_id": model["model_id"],
        "features": candidate["features"],
        "measured": {"stability_days": 88.0},
        "notes": "pytest wet-lab feedback",
        "retrain": True,
    })
    assert feedback.status_code == 200, feedback.text
    closed = feedback.json()
    assert closed["row_count"] == 181
    assert closed["append"]["rows"] == 1
    assert closed["feedback"]["measured"] == 88.0
    assert closed["retrain"]["model"]["model_id"] != model["model_id"]
    assert closed["retrain"]["model"]["metrics"]["n"] == 181

    csv_response = client.get(f"/api/v3/lab/datasets/{dataset['id']}/csv")
    assert csv_response.status_code == 200
    assert "stability_days" in csv_response.text

    delete = client.delete(f"/api/v3/lab/datasets/{dataset['id']}?confirm=yes-delete-dataset")
    assert delete.status_code == 200
    assert delete.json()["models_deleted"] >= 1
    assert client.get(f"/api/v3/lab/datasets/{dataset['id']}").status_code == 404


def test_v3_custom_import_default_features_and_validation(client):
    login(client)
    rows = ["batch,run_id,system,protein_pct,ph,stability_days,particle_size_nm"]
    for index in range(12):
        rows.append(f"B{index // 3},{100 + index},{['yogurt', 'beverage', 'sauce'][index % 3]},{3 + index * 0.2:.1f},{4.0 + index * 0.05:.2f},{40 + index * 2},{100 + index * 3}")
    response = client.post("/api/v3/lab/datasets", json={
        "name": "pytest measured formulation",
        "content": "\n".join(rows),
        "source_type": "measured",
        "format": "csv",
        "dedupe": True,
    })
    assert response.status_code == 200, response.text
    dataset = response.json()
    assert dataset["row_count"] == 12
    assert dataset["training"]["needs_synthetic_opt_in"] is False
    assert "stability_days" not in dataset["feature_candidates"]
    assert "particle_size_nm" not in dataset["feature_candidates"]
    assert "batch" not in dataset["feature_candidates"]
    assert "run_id" not in dataset["feature_candidates"]
    run_col = next(column for column in dataset["schema"]["columns"] if column["name"] == "run_id")
    assert run_col["role"] == "identifier"
    assert run_col["type"] == "numeric"

    result = client.post("/api/v3/lab/train", json={
        "dataset_id": dataset["id"],
        "target": "stability_days",
        "algorithm": "ridge",
        "cv_folds": 4,
    })
    assert result.status_code == 200, result.text
    model = result.json()["model"]
    assert set(model["features"]) == {"system", "protein_pct", "ph"}
    assert "stability_days" not in model["features"]

    leaky = client.post("/api/v3/lab/train", json={
        "dataset_id": dataset["id"],
        "target": "stability_days",
        "features": ["system", "protein_pct", "particle_size_nm"],
        "algorithm": "ridge",
    })
    assert leaky.status_code == 200, leaky.text
    leaky_model = leaky.json()["model"]
    assert "particle_size_nm" in leaky_model["leakage_risk_features"]
    assert any("泄漏" in warning for warning in leaky_model["warnings"])

    text_feature = client.post("/api/v3/lab/train", json={
        "dataset_id": dataset["id"],
        "target": "stability_days",
        "features": ["batch"],
        "algorithm": "ridge",
    })
    assert text_feature.status_code == 422
    assert text_feature.json()["code"] == "text_feature"

    id_feature = client.post("/api/v3/lab/train", json={
        "dataset_id": dataset["id"],
        "target": "stability_days",
        "features": ["run_id"],
        "algorithm": "ridge",
    })
    assert id_feature.status_code == 422
    assert id_feature.json()["code"] == "identifier_feature"


def test_v3_compute_parameters_and_local_tool_settings(client):
    login(client)
    from backend import compute

    config = compute._normalize_options({
        "md_steps": 999999,
        "em_steps": 1,
        "threads": 999,
        "dt_ps": 0.002,
        "temperature_k": 300,
        "docking_seed": -8,
    })
    assert config["md_steps"] == 100000
    assert config["em_steps"] == 50
    assert config["threads"] == 64
    assert config["docking_seed"] == 0

    capabilities = compute.capabilities()
    ids = {tool["id"] for tool in capabilities["tools"]}
    assert {"vina", "gromacs", "cp2k", "haddock", "obabel"} <= ids
    assert capabilities["paths"]["haddock"]

    tools = client.get("/api/v3/tools")
    assert tools.status_code == 200
    body = tools.json()
    assert "haddock" in body["paths"]
    assert "haddock" in body["available"]

    bad = client.put("/api/v3/tools", json={"paths": {"gromacs": "/definitely/not/here"}})
    assert bad.status_code == 422
    assert "gromacs" in bad.json()["detail"]

    invalid_pdb = client.get("/api/v3/structure/not-a-pdb")
    assert invalid_pdb.status_code == 422


def test_v3_biologic_design_id_and_graph(client):
    login(client)
    response = client.post("/api/v2/design", json={
        "query": "设计一个耐热绿色荧光蛋白，75度30分钟，pH 7.4",
        "options": {"mode": "biologic"},
    })
    assert response.status_code == 200, response.text
    design = response.json()
    assert design["design_id"]
    assert design["job_id"]
    assert design["mode"] == "biologic"
    assert design["selected"]["kind"] in {"protein", "compound"}
    saved = client.get(f"/api/v2/designs/{design['design_id']}")
    assert saved.status_code == 200, saved.text
    graph = client.post("/api/v2/graph", json={"design_id": design["design_id"]})
    assert graph.status_code == 200, graph.text
    body = graph.json()
    kinds = {node["kind"] for node in body["nodes"]}
    assert "design" in kinds
    assert kinds & {"protein", "compound", "biologic_target"}
    assert any(node["kind"] == "excipient" for node in body["nodes"])
    assert body["summary"]["logic_steps"] >= 5


def test_v3_literature_search(client):
    from backend import literature
    if not literature.DB_PATH.exists():
        pytest.skip("literature database not built")
    login(client)
    stats = client.get("/api/v3/literature/stats")
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["available"] is True
    assert body["papers"] >= 1
    found = client.get("/api/v3/literature/search", params={"q": "quercetin protein interaction", "limit": 3})
    assert found.status_code == 200, found.text
    payload = found.json()
    assert payload["count"] >= 1
    assert payload["items"][0]["url"].startswith("https://")
