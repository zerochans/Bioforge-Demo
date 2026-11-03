from backend import datasources, food, graph, processing, query_text


def test_query_expansion_maps_chinese_terms():
    result = query_text.expand_query("乳清蛋白与槲皮素结合")
    assert "whey protein" in result["expanded"]
    assert "quercetin" in result["expanded"]
    assert "binding" in result["expanded"]
    assert result["language"] == "zh"
    matched = {item["term"]: item["english"] for item in result["matched"]}
    assert matched["乳清蛋白"] == "whey protein"
    terms = query_text.terms("乳清蛋白与槲皮素结合")
    assert "whey" in terms and "quercetin" in terms
    assert len(terms) == len(set(terms))


def test_query_routing_separates_compound_and_protein():
    assert datasources.route_queries("乳清蛋白与槲皮素结合") == ("whey protein", "quercetin")
    assert datasources.route_queries("槲皮素 稳定性")[1] == "quercetin"
    assert datasources.route_queries("whey protein quercetin binding")[1] == "quercetin"


def test_query_relevance_and_language():
    score, matched = query_text.relevance("quercetin stability", "Quercetin stability in beverages at pH 3.5")
    assert score >= 0.7 and "quercetin" in matched
    assert query_text.strength(score) == "high"
    assert query_text.expand_query("EGCG 稳定性")["language"] == "mixed"
    assert query_text.strength(0.1) == "low" and query_text.strength(0.5) == "medium"


def test_processing_effects_are_evidence_backed():
    result = food.design_food("设计一款高蛋白软面包，蛋白质 ≥ 12%，无麸质，保质期 7 天")
    block = result["selected"]["processing_effects"]
    assert block["version"] == processing.VERSION
    assert block["effects"], "expected at least one processing effect"
    for effect in block["effects"]:
        assert effect["evidence"], effect["id"]
        assert effect["mechanism"] and effect["validation"]
        assert effect["level"] in {"low", "medium", "high"}
    assert "方向性" in block["boundary"]


def test_case_specific_processing_and_system_detection():
    assert food.detect_system("益生菌固体饮料，活菌 ≥ 10^8 CFU/g") == "powder_drink"
    powder = food.design_food("益生菌固体饮料，活菌 ≥ 10^8 CFU/g，低糖，冲调后 pH 4.5，货架期 12 个月")
    assert powder["system"]["id"] == "powder_drink"
    assert powder["selected"]["constraint_met"] is True
    extruded = food.design_food("高纤挤压膨化玉米零食，膳食纤维 ≥ 8%，钠 ≤ 500 mg/100g，酥脆，水分活度 ≤ 0.35")
    assert "starch_gelatinization" in {item["id"] for item in extruded["selected"]["processing_effects"]["effects"]}
    kimchi = food.design_food("低盐泡菜，钠 ≤ 500 mg/100g，pH 4.2，发酵 7 天")
    assert "fermentation" in {item["id"] for item in kimchi["selected"]["processing_effects"]["effects"]}


def test_graph_semantics_and_processing_nodes():
    result = food.design_food("低钠番茄酱，钠 ≤ 120 mg/100g，pH 3.8，货架期 12 个月")
    built = graph.build_design_graph(result)
    assert built["summary"]["processing_steps"] >= 1
    assert built["summary"]["processing_effects"] >= 1
    kinds = {node["kind"] for node in built["nodes"]}
    assert {"processing", "processing_effect"} <= kinds
    for node in built["nodes"]:
        assert node["id"] and node["kind"] in graph.NODE_TYPES
        assert node["meaning"] and node["confidence"]
    edge_ids = [edge["id"] for edge in built["edges"]]
    assert len(edge_ids) == len(set(edge_ids))
    assert built["semantics"]["node_types"] and built["semantics"]["edge_types"]
    for edge in built["edges"]:
        assert edge["type"] in graph.EDGE_TYPES
        assert edge["label"] and edge["meaning"] and edge["confidence"]
