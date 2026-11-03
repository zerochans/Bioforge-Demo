from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import app_v3, assistant, compute, engine, food, graph, notes


def test_multipair_resolution_and_limit():
    pairs = compute._resolve_pairs("whey quercetin", {"receptors": "1BEB, 1GFL", "ligands": "quercetin, curcumin"})
    assert len(pairs) == 4
    assert {pair["pdb_id"] for pair in pairs} == {"1BEB", "1GFL"}
    assert all(pair["ligand"] in {"quercetin", "curcumin"} for pair in pairs)
    with pytest.raises(ValueError):
        compute._resolve_pairs("x", {"receptors": "1BEB, 1GFL, 1LYZ, 1AO6", "ligands": "quercetin, curcumin, caffeine, rutin"})


def test_haddock_option_defaults_and_residue_parsing():
    config = compute._normalize_options({"haddock_enabled": True})
    assert config["haddock_workflow"] == "protein-protein"
    assert config["haddock_sampling"] == 20
    assert config["haddock_mdsteps_rigid"] == 500
    assert compute._parse_residues("1, 2 5-7;9") == [1, 2, 5, 6, 7, 9]
    assert compute._split_pdb_chain("1LMQ:B") == ("1LMQ", "B")
    assert compute._split_pdb_chain("1BEB") == ("1BEB", "")


def test_haddock_config_stages_and_ligand_clustering():
    config = compute._normalize_options({
        "haddock_enabled": True, "haddock_sampling": 4, "haddock_select_top": 2,
        "haddock_top_models": 1, "haddock_flexref": True, "haddock_emref": True,
        "haddock_cluster": True,
    })
    text = compute._haddock_config_text(config, has_ambig=False, workflow="protein-ligand")
    assert "autotoppar = true" in text
    assert "[flexref]" in text and "[emref]" in text and "[clustrmsd]" in text
    assert "inter_rigid" in text.split("[rigidbody]", 1)[1].split("[caprieval]", 1)[0]
    assert "inter_rigid" not in text.split("[flexref]", 1)[1].split("[caprieval]", 1)[0]
    assert "mdsteps_rigid = 500" in text and "mdsteps_cool1 = 500" in text
    assert "top_models = 1" in text


def test_haddock_config_requires_restraint_fallback():
    config = compute._normalize_options({"haddock_enabled": True, "haddock_cmrest": False, "haddock_ranair": False})
    try:
        compute._haddock_config_text(config, has_ambig=False, workflow="protein-protein")
    except ValueError as exc:
        assert "cmrest" in str(exc) and "ranair" in str(exc)
    else:
        raise AssertionError("expected a restraint fallback error")


def test_haddock_capri_parsing_filters_rejected_models(tmp_path):
    capri = tmp_path / "capri_ss.tsv"
    capri.write_text(
        "model\tscore\tcluster_id\tcluster_ranking\n"
        "good.pdb\t-20.5\t1\t1\n"
        "bad.pdb\t9999.7\t2\t2\n"
        "nan.pdb\tnan\t3\t3\n",
        encoding="utf-8",
    )
    rows = compute._parse_capri(capri)
    assert [row["model"] for row in rows] == ["good.pdb"]
    assert rows[0]["score"] == -20.5
    clt = tmp_path / "capri_clt.tsv"
    clt.write_text(
        "# comment\ncluster_rank\tcluster_id\tn\tscore\n1\t1\t4\t-20.5\n2\t2\t1\t9999.7\n",
        encoding="utf-8",
    )
    clusters = compute._read_capri_clusters(clt)
    assert clusters == [{"cluster_rank": 1, "cluster_id": 1, "population": 4, "score": -20.5}]


def test_compute_requires_explicit_targets_and_persists_rejections(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="未识别受体"):
        compute._resolve("x", {})
    pairs = compute._resolve_pairs("whey quercetin", {})
    assert len(pairs) == 1
    assert pairs[0]["pdb_id"] == "1BEB"
    monkeypatch.setattr(compute.data, "COMPUTE_DIR", tmp_path / "compute")
    rejected = compute.record_rejected({"design_id": "D1", "brief": {"query": "x"}}, {}, "bad receptor")
    saved = json.loads((tmp_path / "compute" / rejected["id"] / "job.json").read_text(encoding="utf-8"))
    assert saved["status"] == "error"
    assert saved["failed_validation"] is True
    assert "bad receptor" in saved["error"]


def test_unknown_biologic_target_is_rejected():
    with pytest.raises(ValueError, match="乳铁蛋白"):
        engine.design("设计乳铁蛋白口服液，保护剂组合并评估保留率", {"mode": "biologic"}, False)


def test_graph_edges_have_provenance():
    result = food.design_food("低糖苹果汁")
    built = graph.build_design_graph(result)
    assert built["edges"]
    for edge in built["edges"]:
        assert edge["evidence_status"] in graph.PROVENANCE_BASIS
        assert edge["basis"]
        assert isinstance(edge["citations"], list)
        if edge["evidence_status"] != "workflow" and not edge["citations"]:
            assert edge.get("caveat")
    assert built["summary"]["edges_with_citations"] >= 1


def test_notes_are_read_only_and_path_safe(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Title\n\nBody", encoding="utf-8")
    monkeypatch.setattr(notes, "OBSIDIAN_DIR", vault)
    assert notes.status()["count"] == 1
    assert notes.read_note("note.md")["title"] == "Title"
    with pytest.raises(ValueError):
        notes.read_note("../outside.md")
    with pytest.raises(ValueError):
        notes.read_note("note.txt")


def test_complex_pdb_contains_receptor_and_ligand(tmp_path):
    receptor = tmp_path / "receptor.pdb"
    receptor.write_text(
        "ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00 10.00           N\n",
        encoding="utf-8",
    )
    pose = tmp_path / "pose.pdb"
    pose.write_text(
        "MODEL        1\n"
        "ATOM      1  C1  LIG A   1      11.000  10.000  10.000  1.00  0.00           C\n"
        "ENDMDL\n",
        encoding="utf-8",
    )
    out = tmp_path / "complex.pdb"
    compute._complex_pdb(receptor, pose, out, {"pdb_id": "TEST"})
    text = out.read_text(encoding="utf-8")
    assert "ATOM" in text and "HETATM" in text
    assert " LIG L   1" in text


def test_assistant_history_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "ASSISTANT_DIR", tmp_path / "assistant")
    monkeypatch.setattr(assistant, "BACKUP_DIR", tmp_path / "assistant" / "backup")
    monkeypatch.setattr(assistant, "HISTORY_PATH", tmp_path / "assistant" / "history.jsonl")
    record = {
        "id": "A1", "ts": "2026-10-23T00:00:00+00:00", "question": "q", "answer": "a", "model": "test",
    }
    assistant._save(record)
    assert json.loads(assistant.HISTORY_PATH.read_text(encoding="utf-8").strip())["answer"] == "a"
    assert list((tmp_path / "assistant" / "backup").glob("*.jsonl"))
    assert assistant.recent(1)[0]["question"] == "q"
    assert assistant._count_history() == 1
    assert assistant.recent(10, query="zzz") == []


def test_compute_resolves_single_and_multi_partner_cardinalities():
    from backend import compute

    combos = [
        ({"receptors": "1BEB", "ligands": "quercetin"}, 1),
        ({"receptors": "1BEB,1GFL", "ligands": "quercetin"}, 2),
        ({"receptors": "1BEB", "ligands": "quercetin,curcumin"}, 2),
        ({"receptors": "1BEB,1GFL", "ligands": "quercetin,curcumin"}, 4),
    ]
    for options, expected in combos:
        pairs = compute._resolve_pairs("", options)
        assert len(pairs) == expected, options
        assert all(pair.get("pdb_id") and pair.get("ligand") and pair.get("smiles") for pair in pairs)


def test_compute_accepts_pdb_query_and_fields_only_payload():
    pairs = compute._resolve_pairs("分析 1BEB 与 quercetin 的结合", {})
    assert [(pair["pdb_id"], pair["ligand"]) for pair in pairs] == [("1BEB", "quercetin")]
    query = app_v3._manual_compute_query({"receptors": ["1BEB", "1LYZ"], "ligands": "quercetin, caffeine"})
    assert "1BEB" in query and "caffeine" in query
    assert len(compute._resolve_pairs(query, {"receptors": "1BEB,1LYZ", "ligands": "quercetin,caffeine"})) == 4


def test_design_honors_requested_ingredients_and_explicit_protein():
    caffeine = food.design_food("设计一个含咖啡因的能量饮料")
    tea = food.design_food("绿茶饮料")
    whey = food.design_food("乳清蛋白饮料")
    assert "caffeine" in {row["id"] for row in caffeine["selected"]["recipe"]}
    assert "tea_extract" in {row["id"] for row in tea["selected"]["recipe"]}
    assert "whey_protein" in {row["id"] for row in whey["selected"]["recipe"]}
    assert {row["id"] for row in caffeine["selected"]["recipe"]} != {row["id"] for row in tea["selected"]["recipe"]}
    neon = engine.design("mNeonGreen 在 pH 4 饮料中的稳定性", {"mode": "biologic"}, False)
    assert neon["selected"]["id"] == "mNeonGreen"
    assert neon["brief"]["requested_kind"] == "protein"
    assert all(candidate["id"] != "phycocyanin" for candidate in neon["candidates"])
    red = engine.design("Find a red fluorescent protein for pH 7", {"mode": "biologic"}, False)
    assert red["selected"]["id"] != "phycocyanin"


def test_case_library_routes_food_and_mechanism_queries():
    cases = json.loads(Path("data/cases.json").read_text(encoding="utf-8"))["items"]
    assert all(case.get("title_en") and case.get("query_en") and case.get("expected_en") for case in cases)
    for case in cases:
        assert app_v3._is_food_query(case["query_en"]) is (case["id"] != "case_polyphenol_dock"), case["id"]
    assert len(cases) == 21
    systems = json.loads(Path("data/food_systems.json").read_text(encoding="utf-8"))["items"]
    resource_groups = json.loads(Path("data/resources.json").read_text(encoding="utf-8"))["groups"]
    assert len(systems) == 20 and sum(len(group["items"]) for group in resource_groups) == 45
    expected_systems = {
        "case_bread_high_protein": "bakery_bread", "case_yogurt_low_sugar": "dairy_yogurt",
        "case_plant_meat": "plant_meat", "case_gummy_natural": "confectionery_gummy",
        "case_sauce_low_sodium": "sauce_acid", "case_ice_cream_plant": "frozen_dessert",
        "case_phycocyanin": "beverage_generic", "case_protein_bar_high_protein": "cereal_bar",
        "case_extruded_high_fiber": "snack_extruded", "case_kimchi_low_salt": "fermented_vegetable",
        "case_edible_film": "edible_film", "case_probiotic_powder": "powder_drink",
        "case_low_sugar_jelly": "jelly", "case_uht_milk": "dairy_milk",
        "case_low_fat_mayo": "sauce_emulsion", "case_reduced_sugar_chocolate": "confectionery_chocolate",
        "case_clear_apple_juice": "juice", "case_oat_milk_uht": "plant_milk",
        "case_low_sugar_sponge_cake": "bakery_cake", "case_low_salt_sausage": "meat_sausage",
    }
    for case in cases:
        expected = case["id"] != "case_polyphenol_dock"
        assert app_v3._is_food_query(case["query"]) is expected, case["id"]
        if expected:
            assert food.detect_system(case["query"]) == expected_systems[case["id"]], case["id"]
    assert app_v3._is_food_query("澄清苹果汁，糖 ≤ 8%") is True
    assert app_v3._is_food_query("分析乳清蛋白与槲皮素的结合机制，运行对接") is False


def test_phycocyanin_retention_target_and_protectants():
    result = food.design_food("藻蓝蛋白蓝色饮料，pH 4.2，72°C 15 秒巴氏，保留率 ≥ 80%")
    targets = result["brief"]["targets"]
    assert targets["colorant_id"] == "phycocyanin"
    assert targets["color_retention_min_pct"] == 80.0
    for candidate in result["candidates"]:
        recipe_ids = {row["id"] for row in candidate["recipe"]}
        assert "phycocyanin" in recipe_ids
        assert "trehalose" in recipe_ids
        assert "sodium_citrate" in recipe_ids
        assert "anthocyanin" not in recipe_ids
        assert "canola_oil" not in recipe_ids
        assert "cocoa_powder" not in recipe_ids
        retention = candidate["metrics"]["color_retention_pct"]
        assert 70.0 <= retention <= 95.0
        row = next(item for item in candidate["constraint_report"] if item["id"] == "color_retention_min")
        assert row["status"] in {"at_risk", "fail"}
    stability = next(candidate for candidate in result["candidates"] if candidate["strategy"] == "stability")
    assert "ascorbic_acid" not in {row["id"] for row in stability["recipe"]}
    assert stability["metrics"]["color_retention_pct"] >= result["baseline"]["metrics"]["color_retention_pct"]


def test_food_portfolios_are_unique_and_english_targets_match():
    jelly_cn = food.design_food("低糖高纤果冻，糖 ≤ 8%，膳食纤维 ≥ 6%，pH 3.8，常温 9 个月")
    jelly_en = food.design_food("Low-sugar high-fibre jelly with ≤8% sugar, ≥6% dietary fibre, pH 3.8 and 9 months at ambient")
    for result in (jelly_cn, jelly_en):
        targets = result["brief"]["targets"]
        assert targets["sugar_max_pct"] == 8.0
        assert targets["fiber_min_pct"] == 6.0
        assert len(result["portfolio"]) == 8
        assert len({food._recipe_key(candidate) for candidate in result["portfolio"]}) == 8
        assert result["selected"]["metrics"]["fiber_pct"] >= 6.0
        assert all(candidate["constraint_status"] != "fail" for candidate in result["portfolio"])

    chocolate = food.design_food("Reduced-sugar dark chocolate with ≤15% sugar, ≥70% cocoa solids, bloom control and 12-month shelf life")
    assert chocolate["brief"]["targets"]["sugar_max_pct"] == 15.0
    assert chocolate["selected"]["metrics"]["sugar_pct"] <= 15.0
    assert chocolate["selected"]["constraint_status"] != "fail"
    assert len({food._recipe_key(candidate) for candidate in chocolate["portfolio"]}) == 8

    extruded = food.design_food("High-fibre extruded snack with ≥8% dietary fibre")
    assert extruded["brief"]["targets"]["fiber_min_pct"] == 8.0
    assert extruded["selected"]["metrics"]["fiber_pct"] >= 8.0
    assert len({food._recipe_key(candidate) for candidate in extruded["portfolio"]}) == 8


def test_md_mode_and_complex_topology(tmp_path):
    assert compute._normalize_options({})["md_mode"] == "complex"
    assert compute._normalize_options({"md_mode": "protein"})["md_mode"] == "protein"
    protein = tmp_path / "protein.gro"
    protein.write_text(
        "Protein\n    1\n    1ALA      N    1   0.100   0.100   0.100\n   1.00000   1.00000   1.00000\n",
        encoding="utf-8",
    )
    ligand = tmp_path / "ligand.gro"
    ligand.write_text(
        "Ligand\n    1\n    1MOL     C1   1   0.500   0.500   0.500\n   1.00000   1.00000   1.00000\n",
        encoding="utf-8",
    )
    merged = tmp_path / "complex.gro"
    assert compute._merge_gro(protein, ligand, merged) == 2
    assert merged.read_text(encoding="utf-8").splitlines()[1].strip() == "2"
    topology = tmp_path / "topol.top"
    topology.write_text(
        '#include "amber99sb-ildn.ff/forcefield.itp"\n\n[ molecules ]\nProtein_chain_A     1\n',
        encoding="utf-8",
    )
    compute._add_complex_topology(topology)
    text = topology.read_text(encoding="utf-8")
    assert '#include "LIG.acpype/LIG_GMX.itp"' in text
    assert text.rstrip().endswith("LIG                 1")
    assert compute._potential_from_log("Potential Energy = -125.5") == -125.5
    assert compute._potential_from_log("Potential\n  1.0 2.0 3.0 4.0 -125.5\n") == -125.5
    assert compute._em_status("Maximum force = 3289.4 on atom 4589\nSteepest Descents did not converge to Fmax < 500 in 301 steps.") == {"em_fmax": 3289.4, "em_fmax_atom": 4589, "em_actual_steps": 301, "em_converged": False}


def test_assistant_docs_budget_is_bounded(tmp_path, monkeypatch):
    root = tmp_path / "root"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "USER_GUIDE.md").write_text("A" * 5000, encoding="utf-8")
    (docs / "LIMITATIONS.md").write_text("B" * 5000, encoding="utf-8")
    monkeypatch.setattr(assistant.data, "ROOT", root)
    assert len(assistant._read_docs_context(1000)) <= 1000
    assert len(assistant._read_docs_context(2400)) <= 2400
    assert assistant._read_docs_context(0) == ""


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("bad", request=httpx.Request("POST", "http://test"), response=self)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses, calls, **kwargs):
        self.responses = list(responses)
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json):
        self.calls.append(dict(json))
        return self.responses.pop(0)


def test_assistant_retries_with_compact_prompt_and_large_context(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "ASSISTANT_DIR", tmp_path / "assistant")
    monkeypatch.setattr(assistant, "BACKUP_DIR", tmp_path / "assistant" / "backup")
    monkeypatch.setattr(assistant, "HISTORY_PATH", tmp_path / "assistant" / "history.jsonl")
    monkeypatch.setattr(assistant, "_models", lambda: [{"name": assistant.OLLAMA_MODEL}])
    calls = []
    responses = [
        _FakeResponse({"message": {"content": ""}, "done_reason": "length"}),
        _FakeResponse({"message": {"content": "最终回答"}, "done_reason": "stop", "model": "test"}),
    ]
    client = _FakeClient(responses, calls)
    monkeypatch.setattr(assistant.httpx, "Client", lambda **kwargs: client)
    result = assistant.ask("如何排查空回答？")
    assert result["answer"] == "最终回答"
    assert len(calls) == 2
    assert calls[0]["options"]["num_ctx"] == assistant.OLLAMA_NUM_CTX
    assert calls[0]["options"]["num_predict"] == 1600
    assert calls[1]["options"]["num_predict"] == 2400
    assert calls[1]["options"]["temperature"] == 0.1
    assert len(calls[1]["messages"][0]["content"]) < len(calls[0]["messages"][0]["content"])
    assert json.loads(assistant.HISTORY_PATH.read_text(encoding="utf-8").strip())["answer"] == "最终回答"


def test_assistant_recovers_when_model_returns_only_hidden_thinking(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "ASSISTANT_DIR", tmp_path / "assistant")
    monkeypatch.setattr(assistant, "BACKUP_DIR", tmp_path / "assistant" / "backup")
    monkeypatch.setattr(assistant, "HISTORY_PATH", tmp_path / "assistant" / "history.jsonl")
    monkeypatch.setattr(assistant, "_models", lambda: [{"name": assistant.OLLAMA_MODEL}])
    calls = []
    responses = [
        _FakeResponse({"message": {"content": "", "thinking": "internal reasoning" * 20}, "done_reason": "length"}),
        _FakeResponse({"message": {"content": "可用回答"}, "done_reason": "stop"}),
    ]
    client = _FakeClient(responses, calls)
    monkeypatch.setattr(assistant.httpx, "Client", lambda **kwargs: client)
    result = assistant.ask("隐藏推理导致空回答怎么办？")
    assert result["answer"] == "可用回答"
    assert len(calls) == 2
    assert calls[1]["options"]["num_predict"] > calls[0]["options"]["num_predict"]


def test_assistant_retries_without_think_on_http_400(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "ASSISTANT_DIR", tmp_path / "assistant")
    monkeypatch.setattr(assistant, "BACKUP_DIR", tmp_path / "assistant" / "backup")
    monkeypatch.setattr(assistant, "HISTORY_PATH", tmp_path / "assistant" / "history.jsonl")
    monkeypatch.setattr(assistant, "_models", lambda: [{"name": assistant.OLLAMA_MODEL}])
    calls = []
    responses = [
        _FakeResponse({}, status_code=400, text="unknown field think"),
        _FakeResponse({"message": {"content": "兼容回答"}, "done_reason": "stop"}),
    ]
    client = _FakeClient(responses, calls)
    monkeypatch.setattr(assistant.httpx, "Client", lambda **kwargs: client)
    result = assistant.ask("测试")
    assert result["answer"] == "兼容回答"
    assert "think" in calls[0] and "think" not in calls[1]
    assert len(calls) == 2
