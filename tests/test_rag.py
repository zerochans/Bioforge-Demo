from __future__ import annotations

import asyncio

import pytest

from backend import knowledge_agent as rag
from backend import literature, rag_store


def _row(paper_id: str, title: str, relevance: float = 0.68) -> dict:
    return {
        "id": paper_id,
        "title": title,
        "year": 2025,
        "doi": f"10.0000/{paper_id}",
        "pmcid": f"PMC{paper_id}",
        "url": f"https://example.org/{paper_id}",
        "snippet": "Whey protein and quercetin interaction was measured in a food matrix.",
        "abstract": "Whey protein and quercetin interaction was measured in a food matrix with limited mechanistic detail.",
        "relevance": relevance,
        "strength": "medium" if relevance >= 0.4 else "low",
        "match_terms": ["whey", "protein", "quercetin", "interaction"],
        "license": "cc by",
    }


@pytest.fixture()
def rag_env(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_store, "DB_PATH", tmp_path / "rag.sqlite3")
    monkeypatch.setattr(rag, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(rag, "_llm_enabled", lambda: False)
    monkeypatch.setattr(rag, "_external_enabled", lambda: False)
    monkeypatch.setattr(literature, "stats", lambda: {"available": True, "papers": 10000})
    monkeypatch.setattr(
        rag,
        "_graph_expand",
        lambda evidence: {
            "available": True,
            "backend": "test-graph",
            "notice": "test graph",
            "nodes": [{"id": "query:current", "type": "query", "label": "q"}],
            "edges": [
                {"source": "local:epmc-1", "target": "concept:whey", "predicate": "mentions", "label": "提及", "weight": 1.0},
                {"source": "local:epmc-2", "target": "concept:quercetin", "predicate": "mentions", "label": "提及", "weight": 1.0},
            ],
            "concepts": [
                {"id": "concept:whey", "label": "whey", "papers": 2, "weight": 1.0},
                {"id": "concept:quercetin", "label": "quercetin", "papers": 2, "weight": 1.0},
            ],
        },
    )
    monkeypatch.setattr(rag, "_add_external_graph", lambda graph, evidence: graph)
    rag_store.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rag_store.init()
    return tmp_path


def test_rag_local_answer_then_review_feedback_rollback(rag_env, monkeypatch):
    monkeypatch.setattr(
        rag,
        "_local_retrieve",
        lambda question: [
            rag._local_item(_row("epmc-1", "Whey protein quercetin encapsulation study")),
            rag._local_item(_row("epmc-2", "Quercetin binding to whey protein")),
        ],
    )
    record = asyncio.run(rag.ask("whey protein quercetin interaction", max_iterations=1))
    assert record["status"] == "pending_review"
    assert record["quality"]["score"] >= 0.45
    assert len(record["evidence"]) == 2
    assert "[E1]" in record["answer"]
    assert record["citations"]
    assert record["verification"]["status"] == "verified"
    assert record["route"][0]["node"] == "plan"
    assert any(item["node"] == "draft" for item in record["route"])
    assert rag_store.get_run(record["id"]) is not None

    reviewed = rag.review(record["id"], "approve", "tester", "checked")
    assert reviewed["status"] == "approved"
    assert reviewed["record"]["human_review"]["reviewer"] == "tester"
    assert rag_store.reviews(record["id"])[0]["action"] == "approve"

    feedback = rag.add_feedback(record["id"], 0.5, "evidence_quality", "useful")
    assert feedback["feedback"]["reward"] == 0.5
    assert feedback["weights"]

    rolled = asyncio.run(rag.rollback(record["id"], "tester", "recheck", "mechanism"))
    assert rolled["rolled_back_run_id"] == record["id"]
    assert rolled["new_run"]["prior_run_id"] == record["id"]
    assert rolled["new_run"]["status"] == "pending_review"
    assert rag_store.get_run(record["id"])["status"] == "rolled_back"


def test_rag_external_fallback_marks_weak(rag_env, monkeypatch):
    monkeypatch.setattr(rag, "_local_retrieve", lambda question: [])
    monkeypatch.setattr(rag, "_external_enabled", lambda: True)

    async def fake_external(question):
        return {
            "items": [{
                "id": "external:test:1",
                "source": "Europe PMC OA",
                "source_type": "paper",
                "title": "A remote open-access paper about quercetin and whey",
                "year": 2024,
                "doi": "10.0000/external",
                "pmcid": "PMC999",
                "url": "https://example.org/external",
                "snippet": "External metadata only; full text not checked.",
                "abstract": "External metadata only; full text not checked.",
                "relevance": 0.52,
                "strength": "medium",
                "license": "cc by",
                "oa": True,
                "fulltext": False,
                "match_terms": [],
                "provenance": "public_api_test",
                "retrieved_at": "2026-11-03T00:00:00+00:00",
            }],
            "errors": [],
            "sources": ["Europe PMC OA"],
        }

    monkeypatch.setattr(rag, "_external_retrieve", fake_external)
    record = asyncio.run(rag.ask("quercetin whey interaction", max_iterations=1))
    assert any(item["node"] == "external_retrieve" for item in record["route"])
    assert record["quality"]["external_used"] is True
    assert record["quality"]["label"] in {"weak", "insufficient"}
    assert any("外部" in warning or "偏弱" in warning for warning in record["warnings"])
    assert record["status"] == "pending_review"


def test_rag_no_evidence_is_explicitly_insufficient(rag_env, monkeypatch):
    monkeypatch.setattr(rag, "_local_retrieve", lambda question: [])
    record = asyncio.run(rag.ask("zzzz-no-such-evidence-987", max_iterations=2))
    assert record["quality"]["label"] == "insufficient"
    assert record["verification"]["status"] == "insufficient"
    assert "没有足够" in record["answer"] or "not enough" in record["answer"]
    assert any("不足" in warning for warning in record["warnings"])


def test_rag_engine_uses_langgraph():
    status = rag.engine_status()
    assert status["langgraph_installed"] is True
    assert status["orchestrator"] == "langgraph"
    assert status["deepagents_note"]


def test_rag_api_ask_and_review(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import auth, data
    from backend import app_v3

    monkeypatch.setenv("BIOFORGE_ADMIN_USER", "tester")
    monkeypatch.setenv("BIOFORGE_ADMIN_PASSWORD", "testpass123")
    monkeypatch.setattr(auth, "AUTH_PATH", tmp_path / "auth.json")
    monkeypatch.setattr(auth, "SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(auth, "LOGIN_PATH", tmp_path / "login.txt")
    monkeypatch.setattr(data, "DESIGNS_DIR", tmp_path / "designs")
    (tmp_path / "designs").mkdir()
    monkeypatch.setattr(rag_store, "DB_PATH", tmp_path / "api-rag.sqlite3")
    monkeypatch.setattr(rag, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(rag, "_llm_enabled", lambda: False)
    monkeypatch.setattr(rag, "_external_enabled", lambda: False)
    monkeypatch.setattr(literature, "stats", lambda: {"available": True, "papers": 10000})
    monkeypatch.setattr(
        rag,
        "_local_retrieve",
        lambda question: [
            rag._local_item(_row("epmc-1", "Whey protein quercetin encapsulation study")),
            rag._local_item(_row("epmc-2", "Quercetin binding to whey protein")),
        ],
    )
    monkeypatch.setattr(
        rag,
        "_graph_expand",
        lambda evidence: {"available": True, "backend": "test", "notice": "test", "nodes": [], "edges": [], "concepts": []},
    )
    monkeypatch.setattr(rag, "_add_external_graph", lambda graph, evidence: graph)
    rag_store.init()
    with TestClient(app_v3.app) as client:
        login = client.post("/api/auth/login", json={"username": "tester", "password": "testpass123"})
        assert login.status_code == 200, login.text
        response = client.post("/api/v3/rag/ask", json={"question": "whey quercetin", "max_iterations": 1, "external": False})
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["status"] == "pending_review"
        assert record["citations"]
        run_id = record["id"]
        assert client.get(f"/api/v3/rag/runs/{run_id}").status_code == 200
        reviewed = client.post(f"/api/v3/rag/runs/{run_id}/review", json={"action": "approve", "reviewer": "tester", "note": "ok"})
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "approved"
        queue = client.get("/api/v3/rag/reviews?status=pending_review")
        assert queue.status_code == 200
        assert all(item["id"] != run_id for item in queue.json()["items"])
