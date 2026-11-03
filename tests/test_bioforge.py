from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ["BIOFORGE_TOKEN"] = "test-token-for-pytest"
os.environ["BIOFORGE_REQUIRE_AUTH"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import app as app_module  # noqa: E402
from backend import data, engine, mcp_server, training, validation  # noqa: E402

HEADERS = {"Authorization": "Bearer test-token-for-pytest"}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


@pytest.fixture()
def isolated_training(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "DB_PATH", tmp_path / "feedback.db")
    monkeypatch.setattr(training, "MODEL_PATH", tmp_path / "models" / "active.pkl")
    monkeypatch.setattr(training, "CARD_PATH", tmp_path / "models" / "model_card.json")
    monkeypatch.setattr(data, "MODELS_DIR", tmp_path / "models")
    (tmp_path / "models").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_dataset_manifest():
    manifest = data.dataset_manifest()
    assert manifest["proteins.json"]["items"] >= 10
    assert manifest["protectants.json"]["items"] >= 10
    assert manifest["compounds.json"]["items"] >= 8
    assert manifest["spectra.json"]["items"] >= 10


def test_parse_food_brief():
    brief = engine.parse_brief("设计一个在 72°C、pH 4.0 饮料中基本不变的绿色荧光食品配方，总保留率 ≥ 80%")
    assert brief["food_safe_required"] is True
    assert brief["target_kind"] == "food_beverage"
    assert brief["conditions"]["process_temp_c"] == 72
    assert brief["conditions"]["ph"] == 4.0
    assert brief["spectral"]["desired_em_nm"] == 520
    assert brief["spectral"]["target_retention"] >= 0.8
    assert brief["spectral"]["invariance"] is True


def test_food_design_prefers_food_safe_candidate():
    result = engine.design("绿色荧光食品饮料，72°C，pH 4.0，基本不变", None, False)
    assert result["brief"]["food_safe_required"] is True
    selected = result["selected"]
    assert selected["kind"] == "compound"
    assert selected["id"] in {"quercetin", "riboflavin", "curcumin", "chlorophyllin"}
    assert selected["metrics"]["overall_retention"] >= 0
    assert result["warnings"]
    assert result["formulation"]["ingredients"]
    assert any("food" in (item.get("note") or "").lower() or item.get("food_safe") for item in result["formulation"]["ingredients"])


def test_protein_design_and_virtual_experiment():
    result = engine.design("Find a green fluorescent protein stable at 85C and pH 5 with high brightness", None, False)
    assert result["selected"]["kind"] == "protein"
    assert result["selected"]["id"] in {"mNeonGreen", "mClover3", "mCitrine", "sfGFP", "EGFP"}
    ve = result["virtual_experiment"]
    assert len(ve["temperature"]["x"]) == len(ve["temperature"]["optimized"])
    assert len(ve["ph"]["x"]) == len(ve["ph"]["optimized"])
    assert ve["monte_carlo"]["n"] >= 100
    assert 0 <= ve["monte_carlo"]["prob_meet_target"] <= 1
    assert ve["sensitivity"]
    spec = result["spectra"]["fluorescence"]
    assert len(spec["wavelength_nm"]) == len(spec["emission_reference"]) == len(spec["emission_stressed"])
    assert len(spec["uvvis_wavelength_nm"]) == len(spec["uvvis_reference"])
    assert result["logic_chain"]["nodes"] and result["logic_chain"]["edges"]


def test_small_molecule_design():
    result = engine.design("small molecule fluorescent probe emitting at 520 nm in water", None, False)
    assert result["selected"]["kind"] == "compound"
    assert result["selected"]["metrics"]["spectral_fit"] > 0.5


def test_spectra_match():
    result = engine.match_spectra([[370, 1.0], [255, 0.6]], "UV-Vis")
    assert result["matches"]
    assert result["matches"][0]["compound_id"] == "quercetin"
    assert result["matches"][0]["score"] > 0.5


def test_quick_validation_rdkit():
    result = validation.quick_mm("C1=CC(=C(C=C1C2=C(C(=O)C3=C(C=C(C=C3O2)O)O)O)O)O")
    assert result["available"] is True
    assert result["engine"] in {"MMFF94s", "UFF"}
    assert result["atoms_with_h"] > 10


def test_report_artifacts(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(data, "JOBS_DIR", jobs_dir)
    result = engine.design("绿色荧光食品饮料 72C pH4", None, True)
    artifacts = result.get("artifacts") or {}
    assert artifacts
    job_dir = jobs_dir / result["job_id"]
    for name in ("report.html", "report.pdf", "protocol.md", "dataset.csv", "package.zip", "animation.gif", "result.json"):
        path = job_dir / name
        assert path.exists(), name
        assert path.stat().st_size > 0
    html = (job_dir / "report.html").read_text(encoding="utf-8")
    assert "BioForge" in html
    assert (job_dir / "charts").exists()
    assert (job_dir / "tables").exists()


def test_api_auth_and_design(client):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/parse", json={"query": "green protein"}).status_code == 401
    parsed = client.post("/api/parse", headers=HEADERS, json={"query": "72C pH4 green food beverage"})
    assert parsed.status_code == 200
    assert parsed.json()["food_safe_required"] is True
    design = client.post("/api/design", headers=HEADERS, json={"query": "小分子荧光探针 520 nm"})
    assert design.status_code == 200
    payload = design.json()
    assert payload["job_id"]
    job = client.get(f"/api/jobs/{payload['job_id']}", headers=HEADERS)
    assert job.status_code == 200
    assert client.get(f"/api/jobs/{payload['job_id']}/download", headers=HEADERS).status_code == 200
    assert client.get("/api/jobs/../../etc/passwd", headers=HEADERS).status_code in {404, 422}


def test_api_spectra_and_cors(client):
    response = client.post("/api/spectra/match", headers=HEADERS, json={"peaks": [[370, 1.0], [255, 0.6]], "type": "UV-Vis"})
    assert response.status_code == 200
    assert response.json()["matches"][0]["compound_id"] == "quercetin"
    preflight = client.options("/api/model/feedback", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"})
    assert preflight.status_code == 200
    assert "DELETE" in preflight.headers.get("access-control-allow-methods", "")


def test_feedback_and_training(client, isolated_training):
    for index in range(6):
        payload = {
            "candidate_id": "quercetin",
            "kind": "compound",
            "measured_retention": 0.62 + index * 0.02,
            "process_temp_c": 70 + index,
            "ph": 4.0,
            "predicted_retention": 0.58 + index * 0.02,
            "n_replicates": 3,
            "source": "real",
        }
        response = client.post("/api/feedback", headers=HEADERS, json=payload)
        assert response.status_code == 200, response.text
    card = client.get("/api/model/card", headers=HEADERS).json()
    assert card["stats"]["total"] == 6
    trained = client.post("/api/model/train", headers=HEADERS, json={"include_synthetic": False})
    assert trained.status_code == 200, trained.text
    model = trained.json()
    assert model["trained"] is True
    assert model["card"]["n_samples"] >= 5
    exported = client.get("/api/model/feedback", headers=HEADERS)
    assert exported.status_code == 200
    assert "candidate_id" in exported.text
    deleted = client.delete("/api/model/feedback?confirm=yes-delete-all", headers=HEADERS)
    assert deleted.status_code == 200
    assert client.get("/api/model/card", headers=HEADERS).json()["stats"]["total"] == 0


def test_mcp_handshake_and_tools():
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION
    tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert {"bioforge_design", "bioforge_parse", "bioforge_spectra_match"} <= names
    parsed = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "bioforge_parse", "arguments": {"query": "72C pH4 green beverage"}}})
    payload = json.loads(parsed["result"]["content"][0]["text"])
    assert payload["food_safe_required"] is True
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_stdio_roundtrip():
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )
    try:
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response["id"] == 1
        assert len(response["result"]["tools"]) >= 5
    finally:
        process.stdin.close()
        process.terminate()
        process.wait(timeout=10)
