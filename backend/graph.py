from __future__ import annotations

from typing import Any

from . import data

NODE_TYPES = {
    "design": "当前设计任务本身；它连接目标、约束、候选和证据。",
    "food_system": "要解决的食品体系，例如面包、酸奶或饮料；不是某个配料。",
    "protein": "蛋白/多肽靶点或体系组分；结构靶点不等于已验证功能。",
    "compound": "小分子、活性成分或候选物。",
    "biologic_target": "生物制剂设计中的目标蛋白或分子。",
    "candidate": "设计候选；连接配料/保护剂与推理链。",
    "strategy": "配方或设计策略；是决策路径，不是实验证据。",
    "ingredient": "食品配料；其功能与证据来自本地策展数据。",
    "excipient": "生物制剂保护剂/辅料；不是活性成分。",
    "target": "必须满足的约束或验收目标。",
    "process": "推理链步骤；表示计算/决策顺序，不等于因果证明。",
    "processing": "具体单元操作步骤；由当前配方模板生成，仍需中试验证。",
    "processing_effect": "加工引起的成分/分子变化预测；来源和置信度逐条保留。",
    "mechanism": "机制说明节点；用于连接原因与结果，不能替代实测。",
    "literature": "策展文献或证据节点；没有公开链接时会明确标注。",
    "data_source": "本地已登记的数据来源及其许可/认证状态。",
    "online_source": "本次在线检索实际返回的数据源。",
    "online_record": "在线数据库返回的单条记录；保留原始链接、时间和匹配依据。",
    "constraint": "设计约束。",
}

EDGE_TYPES = {
    "targets_system": ("靶向体系", "设计对象指向要解决的食品体系或生物靶点；不是分子结合证据。", "workflow"),
    "selects_candidate": ("选择候选", "设计任务选择该候选；表示决策结果。", "workflow"),
    "selects_strategy": ("选择策略", "设计任务采用该配方/设计策略。", "workflow"),
    "uses": ("使用配料", "候选配方使用该配料；边的权重是配方占比。", "curated"),
    "formulates_with": ("配伍", "候选与保护剂/辅料配伍；边的权重是配方占比。", "curated"),
    "interaction": ("配料相互作用", "两条配料之间的方向性相互作用；证据字符串来自策展规则/文献先验，不是本配方实测。", "curated"),
    "supported_by": ("由证据支持", "配料功能或声明指向一条策展证据。", "curated"),
    "mechanism_note": ("机制说明", "候选的机制说明；不是独立实验。", "curated"),
    "constraint": ("约束", "设计约束或验收目标。", "workflow"),
    "starts": ("推理起点", "推理链从设计进入第一步。", "workflow"),
    "next": ("下一步", "推理链顺序；只表示步骤先后，不自动证明因果。", "workflow"),
    "completes": ("返回设计", "推理链完成并回到设计对象。", "workflow"),
    "mentions": ("提及", "文本/实体提及关系。", "curated"),
    "authored_by": ("作者", "文献作者关系。", "curated"),
    "published_in": ("发表于", "文献发表来源关系。", "curated"),
    "contains": ("包含记录", "在线数据源包含该记录。", "online"),
    "candidate_evidence": ("候选证据", "在线记录可作为候选的外部证据线索；需核对原始记录，不等于已验证。", "online"),
    "exact_inchikey": ("精确结构映射", "由 UniChem 按 InChIKey 验证的同一化合物映射。", "verified"),
    "uniprot_pdb_xref": ("UniProt→PDB", "UniProt 记录中的 PDB 交叉引用。", "verified"),
    "spectrum_reference": ("谱图参考", "记录中标注的谱图/数据库参考；不是结构身份验证。", "reference"),
    "starts_process": ("开始工艺", "从推理/设计进入具体单元操作。", "workflow"),
    "next_process": ("下一步工艺", "单元操作的先后顺序；不代表因果或充分性。", "workflow"),
    "predicts_change": ("预测成分变化", "规则/文献先验给出的加工变化预测；必须用实测验证。", "model"),
}

PROVENANCE_BASIS = {
    "workflow": "流程/决策关系；只表示软件步骤或选择顺序，不是实验证据。",
    "curated": "本地策展条目、配料先验或文献摘录；需回到原始研究核对条件。",
    "verified": "标识符级交叉验证；证明记录指向同一实体，不等于功能或结合验证。",
    "online": "本次在线检索实际返回的记录；可点击原始链接核对，但未做实验复现。",
    "reference": "数据库参考记录；不是同条件实测，不能单独作为结论依据。",
    "model": "规则/文献先验的计算预测；必须用实测数据验证。",
    "unknown": "来源状态未知；不应作为证据使用。",
}

EDGE_ALIASES = {
    "targets_system": "targets_system",
    "selects_candidate": "selects_candidate",
    "selects_strategy": "selects_strategy",
    "uses": "uses",
    "formulates_with": "formulates_with",
    "interaction": "interaction",
    "supported_by": "supported_by",
    "mechanism_note": "mechanism_note",
    "constraint": "constraint",
    "starts": "starts",
    "next": "next",
    "completes": "completes",
}


def _citation(label: str, source: str, **extra: Any) -> dict[str, Any]:
    return {"label": label, "source": source, **extra}


def _citations_from(values: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(values, str):
        values = [values]
    return [_citation(str(value), source) for value in (values or []) if value]


def _node(node_id: str, label: str, kind: str, **extra: Any) -> dict[str, Any]:
    meaning = extra.pop("meaning", None) or NODE_TYPES.get(kind, "图谱节点。")
    return {"id": node_id, "label": label, "kind": kind, "meaning": meaning, **extra}


def build_design_graph(design: dict[str, Any], online: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = design.get("selected") or {}
    design_id = design.get("design_id") or design.get("job_id")
    system = design.get("system") or {}
    is_food = bool(system)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_node(node: dict[str, Any]) -> None:
        if node["id"] not in {item["id"] for item in nodes}:
            nodes.append(node)

    def add_edge(source: str, target: str, edge_type: str, **extra: Any) -> None:
        label, meaning, default_status = EDGE_TYPES.get(edge_type, (edge_type, "关系边。", "unknown"))
        status = extra.pop("evidence_status", extra.pop("confidence", default_status))
        if status not in PROVENANCE_BASIS:
            status = "unknown"
        raw_citations = extra.pop("citations", [])
        if isinstance(raw_citations, str):
            raw_citations = [raw_citations]
        citations = []
        for item in raw_citations or []:
            if isinstance(item, dict):
                citation = {key: value for key, value in item.items() if value not in (None, "")}
                if citation.get("label") or citation.get("source"):
                    citations.append(citation)
            elif item:
                citations.append(_citation(str(item), "curated prior"))
        basis = extra.pop("basis", PROVENANCE_BASIS[status])
        if status != "workflow" and not citations:
            extra.setdefault("caveat", "当前边没有公开引用；这是规则/流程关系，不能当作实验证据。")
        edge = {
            "from": source,
            "to": target,
            "type": edge_type,
            "label": extra.pop("label", label),
            "meaning": extra.pop("meaning", meaning),
            "confidence": status,
            "evidence_status": status,
            "basis": basis,
            "citations": citations,
            **extra,
        }
        if not any({key: value for key, value in item.items() if key != "id"} == edge for item in edges):
            edge["id"] = f"edge:{len(edges) + 1}"
            edges.append(edge)

    add_node(_node(
        f"design:{design_id}", "设计", "design", mode=design.get("mode"), design_id=design_id,
        detail=(design.get("brief") or {}).get("query", ""), confidence="workflow",
    ))
    if is_food:
        system_id = f"system:{system.get('id')}"
        system_label = system.get("cn_name") or system.get("name", "system")
        system_kind = "food_system"
    else:
        system_id = f"biologic:{selected.get('id') or 'target'}"
        system_label = "生物靶点"
        system_kind = "protein" if selected.get("kind") == "protein" else "compound"
    add_node(_node(
        system_id, system_label, system_kind, name=selected.get("cn_name") or selected.get("name"),
        category=system.get("category"), source="selected candidate", confidence="workflow",
        detail=(system.get("description") or system.get("category") or ""),
    ))
    add_edge(f"design:{design_id}", system_id, "targets_system")

    strategy = selected.get("strategy")
    if strategy:
        strategy_id = f"strategy:{strategy}"
        add_node(_node(
            strategy_id, selected.get("strategy_cn") or strategy, "strategy", score=selected.get("score"),
            note=selected.get("strategy_note"), confidence="workflow",
        ))
        add_edge(f"design:{design_id}", strategy_id, "selects_strategy")
    else:
        strategy_id = f"candidate:{selected.get('id')}"
        add_node(_node(
            strategy_id, "候选", "candidate", name=selected.get("cn_name") or selected.get("name"),
            score=selected.get("score"), meets_spec=selected.get("meets_spec"), confidence="workflow",
            detail=(selected.get("rationale") or [""])[0],
        ))
        add_edge(f"design:{design_id}", strategy_id, "selects_candidate")

    imap = {item["id"]: item for item in data.ingredients()}
    ingredient_count = 0
    formulation = design.get("formulation") or {}
    formulation_rows = formulation.get("ingredients") or selected.get("ingredients") or []
    if is_food:
        for row in selected.get("ingredients", []):
            item = imap.get(row["id"], {})
            ingredient_count += 1
            node_id = f"ingredient:{row['id']}"
            add_node(_node(
                node_id, row.get("cn_name") or item.get("cn_name") or row["id"], "ingredient",
                pct=row.get("pct"), role=row.get("role_cn") or item.get("category"),
                functions=item.get("functions", []), evidence=item.get("evidence", []),
                citations=_citations_from(item.get("evidence", []), "curated ingredient prior"),
                confidence=item.get("confidence") or "medium",
            ))
            add_edge(strategy_id, node_id, "uses", weight=row.get("pct"), citations=_citations_from(item.get("evidence", []), "curated ingredient prior"))
        recipe_ids = {row["id"] for row in selected.get("ingredients", [])}
        metrics = selected.get("metrics") or {}
        for ix in metrics.get("positive_interactions", []) + metrics.get("negative_interactions", []):
            if ix["a"] in recipe_ids and ix["b"] in recipe_ids:
                add_edge(
                    f"ingredient:{ix['a']}", f"ingredient:{ix['b']}", "interaction",
                    effect=ix.get("effect"), sign="positive" if ix.get("effect", 0) >= 0 else "negative",
                    mechanism=ix.get("mechanism_cn"), evidence=ix.get("evidence"),
                    citations=_citations_from(ix.get("evidence"), "curated interaction prior"),
                    confidence=ix.get("confidence") or "medium",
                )
    else:
        for row in formulation_rows:
            ingredient_count += 1
            name = row.get("name") or row.get("id") or "ingredient"
            node_id = f"ingredient:{row.get('id') or name}"
            is_target = str(row.get("name", "")).lower() == str(selected.get("name", "")).lower() or row.get("id") == selected.get("id")
            add_node(_node(
                node_id, row.get("cn_name") or name, "biologic_target" if is_target else "excipient",
                pct=row.get("pct"), role=row.get("role_cn") or row.get("role"),
                food_safe=row.get("food_safe"), note=row.get("note"),
            ))
            add_edge(strategy_id, node_id, "formulates_with", weight=row.get("pct"), citations=[_citation(row.get("note"), "curated formulation prior")] if row.get("note") else [])
            item = imap.get(row.get("id", ""), {})
            for label in item.get("evidence", [])[:2]:
                evidence_id = f"evidence:{len(nodes)}"
                add_node(_node(evidence_id, label, "literature", source="curated prior", confidence="medium"))
                add_edge(node_id, evidence_id, "supported_by", citations=[_citation(label, "curated prior")])
        for blend in selected.get("blend", []):
            for label in (blend.get("notes_cn"), blend.get("notes")):
                if label:
                    evidence_id = f"mechanism:{len(nodes)}"
                    add_node(_node(evidence_id, label, "mechanism", source="curated prior", confidence="low"))
                    add_edge(f"ingredient:{blend.get('id')}", evidence_id, "mechanism_note", citations=[_citation(label, "curated prior")])
                    break

    for target_key, target_value in (design.get("targets") or {}).items():
        if target_value in (True, False) and target_value:
            node_id = f"target:{target_key}"
            add_node(_node(node_id, target_key, "target", value=str(target_value), confidence="workflow"))
            add_edge(f"design:{design_id}", node_id, "constraint")

    for step in (design.get("logic_chain") or {}).get("nodes", []):
        step_id = f"step:{step.get('id')}"
        add_node(_node(
            step_id, step.get("label") or step.get("id"), "process",
            detail=step.get("detail"), status=step.get("status"), confidence="workflow",
        ))
    for edge in (design.get("logic_chain") or {}).get("edges", []):
        add_edge(
            f"step:{edge.get('from')}", f"step:{edge.get('to')}", "next",
            confidence="workflow",
            note="这是推理链顺序，不是因果证明；每一步的输入/输出需在详情中核对。",
        )
    steps = (design.get("logic_chain") or {}).get("nodes", [])
    if steps:
        add_edge(f"design:{design_id}", f"step:{steps[0].get('id')}", "starts")
        add_edge(f"step:{steps[-1].get('id')}", f"design:{design_id}", "completes")

    process_steps = formulation.get("process") or selected.get("process") or []
    processing_effects = selected.get("processing_effects") or design.get("processing") or {}
    process_anchor = f"step:process" if any(node["id"] == "step:process" for node in nodes) else strategy_id
    for index, step in enumerate(process_steps, 1):
        process_node = f"processing:{index}"
        add_node(_node(
            process_node, f"{step.get('step', index)}. {step.get('title', '工艺步骤')}", "processing",
            detail=step.get("detail"), step=step.get("step", index), confidence="workflow",
            evidence_note="该节点是当前配方的单元操作模板，不是外部实验证据。",
        ))
        add_edge(
            process_anchor, process_node, "starts_process" if index == 1 else "next_process",
            label="开始工艺" if index == 1 else "下一步工艺",
            confidence="workflow",
        )
        process_anchor = process_node
    for effect in (processing_effects.get("effects") or [])[:10]:
        effect_node = f"effect:{effect.get('id')}"
        add_node(_node(
            effect_node, f"{effect.get('component', '组分')}：{effect.get('change', '变化')}", "processing_effect",
            detail=effect.get("mechanism"), macro=effect.get("macro"), level=effect.get("level"),
            confidence=effect.get("confidence", "low"), validation=effect.get("validation"),
            citations=effect.get("evidence", []),
        ))
        add_edge(
            process_anchor, effect_node, "predicts_change",
            label="预测变化",
            confidence=effect.get("confidence", "low"),
            citations=effect.get("evidence", []),
            caveat=processing_effects.get("boundary"),
        )

    source_ids = set()
    for item in data.sources():
        source_id = f"source:{item['id']}"
        add_node(_node(
            source_id, item.get("name", item["id"]), "data_source",
            url=item.get("url"), license=item.get("license"), auth=item.get("auth"),
            description=item.get("description"), verified=item.get("verified"),
            confidence="registry",
            citations=[_citation(f"{item.get('name', item['id'])} 来源登记", "data/sources.json", url=item.get("url"))],
        ))
        source_ids.add(item["id"])
    if online:
        for source, result in (online.get("sources") or {}).items():
            if result.get("status") != "ok":
                continue
            source_node = f"source:{source}"
            add_node(_node(
                source_node, result.get("source_name") or source, "online_source",
                query=online.get("query"), retrieved_at=result.get("retrieved_at"),
            ))
            for record in result.get("records", [])[:3]:
                record_node = f"online:{source}:{record.get('id')}"
                add_node(_node(
                    record_node, record.get("title", record.get("id")), "online_record",
                    url=record.get("url"), license=record.get("license"),
                    relevance=record.get("relevance"), strength=record.get("strength"),
                    match_basis=record.get("match_basis"), retrieved_at=record.get("retrieved_at"),
                    citations=[_citation(
                        record.get("title", record.get("id")), record.get("source_name") or source,
                        url=record.get("url"), license=record.get("license"),
                        retrieved_at=record.get("retrieved_at"), match_basis=record.get("match_basis"),
                    )],
                ))
                add_edge(source_node, record_node, "contains")
                if source in {"pubchem", "chebi", "fdc", "openfoodfacts", "chembl", "massbank", "kegg", "zinc", "genbank"}:
                    add_edge(f"design:{design_id}", record_node, "candidate_evidence")
        for link in online.get("cross_links", []):
            add_edge(
                f"online:{link['from']}", f"online:{link['to']}", link["type"],
                note=link.get("note"), verified_by=link.get("verified_by"),
            )

    return {
        "design_id": design_id,
        "mode": design.get("mode", "food" if is_food else "biologic"),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "ingredients": ingredient_count,
            "interactions": sum(1 for edge in edges if edge["type"] == "interaction"),
            "logic_steps": len((design.get("logic_chain") or {}).get("nodes", [])),
            "processing_steps": len(process_steps),
            "processing_effects": sum(1 for edge in edges if edge["type"] == "predicts_change"),
            "online_records": sum(1 for node in nodes if node["kind"] == "online_record"),
            "curated_sources": len(source_ids),
            "edges_with_citations": sum(1 for edge in edges if edge.get("citations")),
            "edges_without_citations": sum(1 for edge in edges if not edge.get("citations")),
        },
        "semantics": {
            "node": "节点是设计对象、配料、约束、工艺步骤、预测变化或证据记录；颜色表示类型，大小表示连接度。",
            "edge": "边表示关系；边的中文标签说明语义，点击边可查看其含义、来源、置信度和原始链接。",
            "rule": "工作流边只表示决策/步骤顺序；curated 边是本地文献/规则先验；verified 边是标识符级交叉验证；model 边是机理规则预测，必须实测。",
            "provenance": "每条边都有 evidence_status、basis 和 citations。workflow 只是流程；没有 citations 的非工作流边会显示 caveat。",
            "provenance_levels": PROVENANCE_BASIS,
            "node_types": NODE_TYPES,
            "edge_types": {
                key: {"label": value[0], "meaning": value[1], "confidence": value[2]}
                for key, value in EDGE_TYPES.items()
            },
        },
    }


def evidence_table(design: dict[str, Any], online: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = []
    imap = {item["id"]: item for item in data.ingredients()}
    selected = design.get("selected") or {}
    formulation_rows = (design.get("formulation") or {}).get("ingredients") or selected.get("ingredients") or []
    for row in formulation_rows:
        item = imap.get(row.get("id", ""), {})
        evidence = item.get("evidence") or ([row.get("note")] if row.get("note") else [])
        for label in evidence[:3]:
            rows.append({
                "ingredient": row.get("cn_name") or item.get("cn_name") or row.get("name") or row.get("id"),
                "claim": f"{row.get('role_cn') or item.get('category') or row.get('role')}: {label}",
                "source_type": "curated_prior",
                "source": label,
                "retrieved_at": None,
                "url": None,
                "confidence": item.get("confidence", "medium"),
            })
    processing = selected.get("processing_effects") or design.get("processing") or {}
    for effect in (processing.get("effects") or []):
        for ref in effect.get("evidence", []):
            rows.append({
                "ingredient": effect.get("component"),
                "claim": f"{effect.get('change')}: {effect.get('mechanism')}",
                "source_type": "processing_mechanism",
                "source": ref.get("label"),
                "retrieved_at": None,
                "url": ref.get("url"),
                "confidence": effect.get("confidence", "low"),
                "validation": effect.get("validation"),
            })
    if online:
        for record in online.get("records", [])[:60]:
            rows.append({
                "ingredient": (design.get("brief") or {}).get("query", "")[:80],
                "claim": record.get("title"),
                "source_type": "online_database",
                "source": record.get("source_name") or record.get("source"),
                "retrieved_at": record.get("retrieved_at"),
                "url": record.get("url"),
                "license": record.get("license"),
                "confidence": "record-level; verify primary source",
            })
    return rows
