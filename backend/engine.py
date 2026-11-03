from __future__ import annotations

import hashlib
import json
import math
import random
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__, data
from . import validation as validation_mod

ENGINE_VERSION = "1.0.0"
DEFAULT_WEIGHTS = {"stability": 0.45, "spectral": 0.25, "food_safety": 0.15, "brightness": 0.10, "cost": 0.05}

COLOR_TARGETS = {
    "紫": 420, "蓝": 470, "青": 490, "绿": 520, "黄": 550, "橙": 590, "红": 620,
    "远红": 670, "近红外": 680, "purple": 420, "blue": 470, "cyan": 490,
    "green": 520, "yellow": 550, "orange": 590, "red": 620, "far-red": 670,
}

ROLE_CN = {
    "functional fluorophore": "功能荧光成分",
    "thermoprotectant": "耐热保护剂",
    "aggregation_suppressor": "聚集抑制剂",
    "antioxidant": "抗氧化剂",
    "buffer": "缓冲剂",
    "buffer_stabilizer": "缓冲稳定剂",
    "bulking_stabilizer": "填充稳定剂",
    "preservative": "防腐剂",
    "stabilizer": "稳定剂",
    "surfactant": "表面活性剂",
    "acidulant": "酸度调节剂",
    "sweetener": "甜味剂",
    "q.s. to 100 %": "定容至 100%",
}

AA_MASS = {
    "A": 71.0788, "R": 156.1875, "N": 114.1038, "D": 115.0886, "C": 103.1388,
    "E": 129.1155, "Q": 128.1307, "G": 57.0519, "H": 137.1411, "I": 113.1594,
    "L": 113.1594, "K": 128.1741, "M": 131.1926, "F": 147.1766, "P": 97.1167,
    "S": 87.0782, "T": 101.1051, "W": 186.2132, "Y": 163.1760, "V": 99.1326,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def gaussian(x: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((x - center) / max(1e-9, width)) ** 2)


def stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _find_named(text: str, items: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any] | None:
    lower = text.lower()
    best: tuple[int, dict[str, Any]] | None = None
    for item in items:
        names: list[str] = []
        for key in keys:
            value = item.get(key)
            if isinstance(value, list):
                names.extend(str(v) for v in value)
            elif value:
                names.append(str(value))
        for name in names:
            if len(name) < 2:
                continue
            if name.lower() in lower:
                if best is None or len(name) > best[0]:
                    best = (len(name), item)
    return best[1] if best else None


def _temperature(text: str) -> float | None:
    patterns = [
        r"(-?\d+(?:\.\d+)?)\s*(?:°\s*c|℃|摄氏度|度c)",
        r"(\d{2,3}(?:\.\d+)?)\s*度(?!\s*(?:天|日|分钟|min))",
        r"(?:加热|耐受|耐热|保温|杀菌|巴氏|uht|煮沸|温度|thermal|heat)[^。；;\n]{0,16}?(\d{2,3}(?:\.\d+)?)\s*(?:度|℃|°c)",
        r"(?:at|to)\s+(\d{2,3}(?:\.\d+)?)\s*(?:c|°c|degrees?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            value = float(match.group(1))
            if -20 <= value <= 200:
                return value
    if "煮沸" in text or "boiling" in text:
        return 100.0
    if "巴氏" in text or "pasteur" in text:
        return 72.0
    if "uht" in text or "超高温" in text:
        return 135.0
    return None


def _ph(text: str) -> float | None:
    match = re.search(r"ph\s*[=:：]?\s*(\d(?:\.\d)?)", text.lower())
    if match:
        value = float(match.group(1))
        if 0 <= value <= 14:
            return value
    if "强酸" in text or "strong acid" in text:
        return 2.5
    if "酸" in text or "acid" in text:
        return 3.5
    if "中性" in text or "neutral" in text:
        return 7.0
    if "碱性" in text or "alkaline" in text:
        return 8.5
    return None


def _duration_min(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(分钟|分|min(?:ute)?s?|小时|h(?:our)?s?)", text.lower())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("小时") or unit.startswith("h"):
        value *= 60.0
    if 0 <= value <= 100000:
        return value
    return None


def _shelf_days(text: str) -> int | None:
    match = re.search(r"(?:保质期|货架期|shelf[ -]?life|储存|存储)[^。；;\n]{0,12}?(\d+)\s*(天|日|days?)", text.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*(天|日)\s*(?:保质期|货架期|储存|存储)", text.lower())
    if match:
        return int(match.group(1))
    return None


def _wavelengths(text: str) -> tuple[float | None, float | None]:
    color_text = text.replace("紫外", "UV").replace("红外", "IR")
    lower = color_text.lower()
    values = [int(x) for x in re.findall(r"(\d{3})\s*nm", lower)]
    ex = em = None
    for color in sorted(COLOR_TARGETS, key=len, reverse=True):
        center = COLOR_TARGETS[color]
        if color.isascii():
            matched = re.search(rf"\b{re.escape(color)}\b", lower) is not None
        else:
            matched = re.search(rf"{re.escape(color)}(?:色|光)", color_text) is not None
            matched = matched or re.search(rf"(?:发|呈|荧光|emit|fluoresc\w*)[^。；;\n]{{0,6}}{re.escape(color)}", lower) is not None
        if matched:
            em = float(center)
            break
    if values:
        if len(values) == 1:
            em = float(values[0])
        else:
            ex, em = float(values[0]), float(values[-1])
    return ex, em


def _matrix_from_text(text: str, food: bool) -> str:
    lower = text.lower()
    if any(word in lower for word in ("橙汁", "果汁", "juice")):
        return "orange_juice"
    if any(word in lower for word in ("牛奶", "乳", "milk", "dairy")):
        return "milk"
    if any(word in lower for word in ("碳酸", "汽水", "soda", "carbonat")):
        return "carbonated"
    if any(word in lower for word in ("运动", "sports", "electrolyte")):
        return "sports_drink"
    if any(word in lower for word in ("茶", "tea")):
        return "green_tea"
    if any(word in lower for word in ("植物蛋白", "豆奶", "plant protein", "soy")):
        return "plant_protein"
    if any(word in lower for word in ("酸奶", "yogurt", "yoghurt")):
        return "yogurt_drink"
    if any(word in lower for word in ("缓冲", "buffer", "pbs", "hepes")):
        return "lab_buffer"
    return "beverage_generic" if food else "lab_buffer"


def _wants(text: str, *words: str) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def parse_brief(query: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", (query or "").strip())[:6000]
    if not text:
        text = "设计一个在加热和酸性条件下荧光光谱基本不变的绿色发光蛋白，并给出配方和验证方案"
    options = dict(options or {})
    lower = text.lower()
    food = _wants(text, "饮料", "食品", "饮品", "口服", "食品级", "beverage", "drink", "food", "gras", "汁", "juice", "奶", "乳", "茶", "咖啡", "可乐")
    fluorescent = _wants(text, "荧光", "发光", "fluoresc", "luminesc", "gfp", "rfp", "发光蛋白")
    small_molecule = _wants(text, "小分子", "化合物", "small molecule", "compound", "配体", "ligand", "探针")
    wants_protein_word = _wants(text, "蛋白", "protein", "酶", "enzyme")
    protein = wants_protein_word or fluorescent
    spectral_terms = {
        "uv_vis": _wants(text, "紫外", "uv", "吸收光谱", "吸光", "absorb"),
        "fluorescence": fluorescent or _wants(text, "荧光光谱", "发射光谱", "emission"),
        "ir": _wants(text, "红外", "ir", "ftir"),
        "ms": _wants(text, "质谱", "mass spec", "lc-ms", "ms/ms"),
        "nmr": _wants(text, "核磁", "nmr", "1h-nmr", "13c-nmr"),
    }
    four_spectra = _wants(text, "四大谱", "四谱")
    if four_spectra:
        spectral_terms = {key: True for key in spectral_terms}
    invariance = _wants(text, "不变", "基本不变", "保持", "稳定", "unchanged", "invariant", "retain") and (
        spectral_terms["fluorescence"] or spectral_terms["uv_vis"]
    )
    if food and fluorescent:
        target_kind = "food_beverage"
    elif small_molecule:
        target_kind = "small_molecule"
    elif protein or fluorescent:
        target_kind = "fluorescent_protein"
    elif food:
        target_kind = "food_beverage"
    else:
        target_kind = "formulation"

    matrix_id = str(options.get("matrix_id") or _matrix_from_text(text, food))
    matrix = data.get_matrix(matrix_id)
    explicit_temp = _temperature(text)
    explicit_ph = _ph(text)
    explicit_time = _duration_min(text)
    storage_temp = float(matrix.get("storage_temp_c", 25.0))
    if _wants(text, "冷藏", "4度", "4°c", "4 ℃", "fridge", "cold storage"):
        storage_temp = 4.0
    if _wants(text, "冷冻", "freeze", "-20"):
        storage_temp = -20.0
    if _wants(text, "室温", "常温", "room temperature"):
        storage_temp = 25.0
    shelf_days = _shelf_days(text) or int(matrix.get("shelf_days", 30))
    ex_nm, em_nm = _wavelengths(text)
    color_text = text.replace("紫外", "UV").replace("红外", "IR")
    desired_color = None
    for color in sorted(COLOR_TARGETS, key=len, reverse=True):
        if color.isascii():
            matched = re.search(rf"\b{re.escape(color)}\b", color_text.lower()) is not None
        else:
            matched = re.search(rf"{re.escape(color)}(?:色|光)", color_text) is not None
            matched = matched or re.search(rf"(?:发|呈|荧光|emit|fluoresc\w*)[^。；;\n]{{0,6}}{re.escape(color)}", color_text.lower()) is not None
        if matched:
            desired_color = color
            break
    if desired_color and em_nm is None:
        em_nm = float(COLOR_TARGETS[desired_color])

    wants_gif = _wants(text, "gif", "动图")
    wants_video = _wants(text, "视频", "video", "mp4")
    wants_report = _wants(text, "报告", "report", "pdf", "分析")
    wants_protocol = _wants(text, "实验", "protocol", "方案", "步骤", "操作")
    wants_dataset = _wants(text, "数据", "dataset", "csv", "表格")
    wants_print = _wants(text, "打印", "3d打印", "print")
    outputs = ["report"]
    if wants_gif:
        outputs.append("gif")
    if wants_video:
        outputs.append("video")
    if wants_protocol or _wants(text, "配方", "formulation"):
        outputs.append("protocol")
    if wants_dataset:
        outputs.append("dataset")
    if wants_print:
        outputs.append("printable_labware")

    weights = dict(DEFAULT_WEIGHTS)
    if _wants(text, "亮", "bright"):
        weights["brightness"] += 0.10
        weights["stability"] -= 0.05
    if _wants(text, "便宜", "成本", "cost", "cheap"):
        weights["cost"] += 0.10
        weights["stability"] -= 0.05
    if food or _wants(text, "安全", "食品级", "gras"):
        weights["food_safety"] += 0.10
        weights["brightness"] -= 0.05
    total_w = sum(max(0.0, v) for v in weights.values())
    weights = {key: max(0.0, value) / total_w for key, value in weights.items()}

    explicit_protein = _find_named(text, data.proteins(), ("id", "name", "cn_name", "aliases"))
    explicit_compound = _find_named(text, data.compounds(), ("id", "name", "cn_name"))
    if options.get("protein_id"):
        explicit_protein = data.get_protein(str(options["protein_id"]))
    if options.get("compound_id"):
        explicit_compound = data.get_compound(str(options["compound_id"]))
    if explicit_protein and not explicit_compound:
        requested_kind = "protein"
        target_kind = "fluorescent_protein"

    unresolved_proteins: list[str] = []
    if wants_protein_word and not fluorescent and not explicit_protein:
        known_names: list[str] = []
        for item in data.proteins():
            for key in ("id", "name", "cn_name", "aliases"):
                value = item.get(key)
                if isinstance(value, list):
                    known_names.extend(str(v) for v in value)
                elif value:
                    known_names.append(str(value))
        generic = {
            "植物", "食品", "高", "低", "富含", "优质", "绿色荧光", "荧光", "耐热",
            "重组", "融合", "目标", "设计", "小分子", "功能", "蛋白",
        }
        for match in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9β-]{2,14})蛋白", text):
            label = match.group(1)
            token = label + "蛋白"
            if label in generic:
                continue
            if any(token.lower() in name.lower() for name in known_names):
                continue
            if token not in unresolved_proteins:
                unresolved_proteins.append(token)
        for match in re.finditer(r"\b(lactoferrin|transferrin|casein|collagen|whey|zein|gluten)\b", lower):
            token = match.group(1)
            if token not in unresolved_proteins:
                unresolved_proteins.append(token)

    target_retention = 0.80
    retention_match = re.search(r"(\d{2,3}(?:\.\d+)?)\s*%", text)
    if retention_match:
        target_retention = clamp(float(retention_match.group(1)) / 100.0, 0.5, 0.99)
    if "基本不变" in text or "unchanged" in lower:
        target_retention = max(target_retention, 0.90)
    if options.get("target_retention"):
        target_retention = clamp(float(options["target_retention"]), 0.5, 0.99)

    process_temp = float(options.get("process_temp_c", explicit_temp if explicit_temp is not None else matrix["process_temp_c"]))
    process_time = float(options.get("process_time_min", explicit_time if explicit_time is not None else matrix["process_time_min"]))
    ph = float(options.get("ph", explicit_ph if explicit_ph is not None else matrix["ph"]))
    storage_temp = float(options.get("storage_temp_c", storage_temp))
    shelf_days = int(options.get("shelf_days", shelf_days))
    protocol = str(options.get("mode", "research")).lower()
    food_required = bool(options.get("food_safe", food))
    if protocol == "food":
        food_required = True
    if protocol in {"research", "lab"} and options.get("food_safe") is None:
        food_required = food

    assumptions = []
    warnings = []
    assumptions.append(f"模型基质设为「{matrix['cn_name']}」，pH {ph:g}，工艺 {process_temp:g}°C / {process_time:g} min，储存 {storage_temp:g}°C / {shelf_days} 天。")
    assumptions.append("稳定性参数是文献趋势校准的数字孪生先验，不是本实验室实测值。")
    if explicit_temp is None:
        assumptions.append("未显式给出加热温度，采用基质默认工艺温度。")
    if explicit_ph is None:
        assumptions.append("未显式给出 pH，采用基质默认 pH。")
    if spectral_terms["ir"] or spectral_terms["ms"] or spectral_terms["nmr"]:
        warnings.append("IR/MS/NMR 在本流程中用于参考谱库匹配与实验方案生成；蛋白质的 IR/MS/NMR 不能由本模型从头预测。")
    if food and target_kind == "fluorescent_protein":
        warnings.append("常见荧光蛋白（GFP/mCherry 等）不是食品配料；食品/饮料场景应使用食品级荧光色素（如核黄素、藻蓝蛋白）或仅做研究展示。")
    if food:
        warnings.append("食品配方必须按销售地法规核验配料、最大使用量、标签和过敏原；本结果不是法规或食品安全批准。")
    if _wants(text, "医疗", "治疗", "diagnos", "clinical"):
        warnings.append("本工具不提供医疗诊断或治疗建议。")
    if wants_print:
        warnings.append("无法把分子或活体直接“打印”出来；可导出实验包、二维码标签和可 3D 打印的样品架/比色皿夹具。")
    if invariance:
        assumptions.append("“光谱基本不变”按荧光保留率、发射峰位移和谱形余弦相似度联合判定。")

    if explicit_protein and not explicit_compound:
        requested_kind = "protein"
    elif explicit_compound and not explicit_protein:
        requested_kind = "compound"
    else:
        requested_kind = "compound" if (small_molecule and not wants_protein_word) else ("protein" if wants_protein_word else None)
    brief = {
        "query": text,
        "requested_kind": requested_kind,
        "language": "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en",
        "goal": "heat_acid_spectral_invariance" if (invariance and (_wants(text, "热", "heat") or _wants(text, "酸", "acid"))) else "fluorescent_design",
        "target_kind": target_kind,
        "mode": "food" if food_required else "research",
        "food_context": food,
        "food_safe_required": food_required,
        "matrix_id": matrix["id"],
        "matrix": matrix,
        "conditions": {
            "process_temp_c": process_temp,
            "process_time_min": process_time,
            "ph": ph,
            "storage_temp_c": storage_temp,
            "shelf_days": shelf_days,
        },
        "spectral": {
            "invariance": invariance,
            **spectral_terms,
            "desired_ex_nm": ex_nm,
            "desired_em_nm": em_nm,
            "desired_color": desired_color,
            "target_retention": target_retention,
        },
        "outputs": sorted(set(outputs)),
        "priorities": weights,
        "explicit_protein_id": explicit_protein["id"] if explicit_protein else None,
        "explicit_compound_id": explicit_compound["id"] if explicit_compound else None,
        "unresolved_proteins": unresolved_proteins,
        "assumptions": assumptions,
        "warnings": warnings,
    }
    if food_required:
        brief["warnings"].append("已启用食品级模式：候选和保护剂会按食品安全标记过滤；研究级试剂会显示但不会进入最终食品配方。")
    return brief


def _record_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    kind = candidate.get("_kind") or ("protein" if candidate.get("type") == "fluorescent_protein" or candidate.get("type") == "food_colorant_protein" else "compound")
    return {**candidate, "_kind": kind}


def candidate_pool(brief: dict[str, Any]) -> list[dict[str, Any]]:
    explicit_protein = brief.get("explicit_protein_id")
    explicit_compound = brief.get("explicit_compound_id")
    food = bool(brief["food_safe_required"])
    pool: list[dict[str, Any]] = []
    if explicit_protein:
        record = data.get_protein(explicit_protein)
        pool.append({**record, "_kind": "protein"})
    if explicit_compound:
        record = data.get_compound(explicit_compound)
        pool.append({**record, "_kind": "compound"})
    if pool:
        return pool
    target_kind = brief.get("target_kind", "fluorescent_protein")
    requested = brief.get("requested_kind")
    include_proteins = target_kind in {"fluorescent_protein", "food_beverage", "formulation"}
    include_compounds = target_kind in {"small_molecule", "food_beverage", "formulation"}
    if requested == "protein" and not explicit_compound:
        include_compounds = False
    if requested == "compound" and not explicit_protein:
        include_proteins = False
    if target_kind == "fluorescent_protein" and not requested == "compound":
        include_compounds = False
    allowed_types = {"fluorescent_protein", "food_colorant_protein"} if food else {"fluorescent_protein"}
    for item in data.proteins():
        if not include_proteins:
            break
        if item.get("type") not in allowed_types:
            continue
        if food and not str(item.get("food_status", "")).startswith("food"):
            continue
        pool.append({**item, "_kind": "protein"})
    for item in data.compounds():
        if not include_compounds:
            break
        if not item.get("fluorescence"):
            continue
        if food and not item.get("food_safe"):
            continue
        pool.append({**item, "_kind": "compound"})
    if not pool:
        pool = [{**item, "_kind": "protein"} for item in data.proteins() if item.get("type") == "fluorescent_protein"]
    return pool


def _effective_properties(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], brief: dict[str, Any], matrix: dict[str, Any]) -> dict[str, float]:
    if kind == "protein":
        tm = float(record.get("tm_c", 75.0))
        acid = float(record.get("acid_ph50", 5.0))
        scale = 1.0
    else:
        tm = float(record.get("tm_c", 72.0))
        acid = float(record.get("acid_ph50", 4.5))
        scale = 0.45
    dtm = blend_dtm(blend, matrix) * scale
    ph = float(brief["conditions"]["ph"])
    process_temp = float(brief["conditions"]["process_temp_c"])
    acid_penalty = max(0.0, 6.5 - ph) * (1.2 if kind == "protein" else 0.55)
    matrix_penalty = max(0.0, float(matrix.get("matrix_factor", 1.0)) - 1.0) * 3.0
    tm_eff = tm + dtm - acid_penalty - matrix_penalty
    acid_eff = acid - 0.10 * dtm + 0.05 * (ph - 4.0)
    folded = sigmoid((tm_eff - process_temp) / 4.0) * sigmoid((ph - acid_eff) / 0.40)
    return {"tm": tm, "tm_eff": tm_eff, "dtm": dtm, "acid_ph50": acid, "acid_ph50_eff": acid_eff, "folded": folded}


def _blend_effect(item: dict[str, Any], pct: float) -> float:
    dtm10 = float(item.get("dtm10_c", 0.0))
    k = float(item.get("K_pct", 10.0))
    max_effect = dtm10 * (k + 10.0) / 10.0
    return max_effect * pct / (k + pct) if pct > 0 else 0.0


def blend_dtm(blend: list[dict[str, Any]], matrix: dict[str, Any]) -> float:
    if not blend:
        return 0.0
    base = sum(_blend_effect(item, float(item["pct"])) for item in blend)
    interactions = data.protectant_interactions()
    by_key = {item["id"]: item for item in blend}
    for pair, factor in interactions.items():
        left, _, right = pair.partition("|")
        if left in by_key and right in by_key:
            left_effect = _blend_effect(by_key[left], float(by_key[left]["pct"]))
            right_effect = _blend_effect(by_key[right], float(by_key[right]["pct"]))
            base += min(left_effect, right_effect) * (float(factor) - 1.0)
    protection_factor = 1.0 / (0.70 + 0.30 * float(matrix.get("matrix_factor", 1.0)))
    return max(0.0, base * protection_factor)


def _blend_penalty(blend: list[dict[str, Any]], brief: dict[str, Any], food: bool) -> float:
    penalty = 0.0
    for item in blend:
        pct = float(item["pct"])
        max_pct = max(0.001, float(item.get("max_pct", 1.0)))
        penalty += float(item.get("uv_interference", 0.0)) * (pct / max_pct) * (0.8 if brief["spectral"]["invariance"] or brief["spectral"]["uv_vis"] else 0.3)
        if item.get("allergen"):
            penalty += 3.0
        penalty += {"low": 0.02, "medium": 0.06, "high": 0.14}.get(str(item.get("cost", "medium")), 0.06)
    total = sum(float(item["pct"]) for item in blend)
    if total > 15.0:
        penalty += (total - 15.0) * (0.06 if food else 0.02)
    if food and any(item.get("food_safe") is False for item in blend):
        penalty += 50.0
    return penalty


def optimize_blend(record: dict[str, Any], kind: str, brief: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    food = bool(brief["food_safe_required"])
    ph = float(brief["conditions"]["ph"])
    protectants = []
    for item in data.protectants():
        if float(item.get("max_pct", 0.0)) <= 0:
            continue
        if food and not item.get("food_safe"):
            continue
        if ph < float(item.get("ph_min", 0.0)) - 0.6 or ph > float(item.get("ph_max", 14.0)) + 0.6:
            continue
        protectants.append(item)
    if not protectants:
        return {"items": [], "dtm_c": 0.0, "penalty": 0.0, "score": 0.0, "alternatives": [], "method": "none"}
    rng = random.Random(stable_seed(brief["query"], record["id"], str(brief["conditions"]), kind))
    candidates: list[tuple[float, list[dict[str, Any]]]] = []
    max_total = 22.0 if food and brief["target_kind"] == "food_beverage" else 35.0
    if kind == "compound":
        max_total = min(max_total, 18.0)

    def make_blend(selected: list[dict[str, Any]], weights: list[float], total_scale: float) -> list[dict[str, Any]]:
        blend = []
        weight_sum = max(1e-9, sum(weights))
        for item, weight in zip(selected, weights):
            typical = item.get("typical_pct", [1.0, 5.0])
            target = float(typical[1]) * (0.35 + 1.15 * weight / weight_sum) * total_scale
            pct = min(float(item.get("max_pct", 1.0)), max(float(typical[0]) * 0.5, target))
            blend.append({"id": item["id"], "pct": round(pct, 3)})
        total = sum(item["pct"] for item in blend)
        if total > max_total:
            factor = max_total / total
            for item in blend:
                item["pct"] = round(item["pct"] * factor, 3)
        return blend

    def score(blend_specs: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
        expanded = []
        for spec in blend_specs:
            source = next(item for item in protectants if item["id"] == spec["id"])
            expanded.append({**source, "pct": spec["pct"]})
        dtm = blend_dtm(expanded, matrix) * (1.0 if kind == "protein" else 0.45)
        penalty = _blend_penalty(expanded, brief, food)
        return dtm - penalty, expanded

    empty = score([])
    candidates.append(empty)
    singles = []
    for item in protectants:
        if float(item.get("typical_pct", [0, 1])[1]) <= 0:
            continue
        scale = 0.8 if item.get("role") == "preservative" else 1.0
        blend = make_blend([item], [1.0], scale)
        candidates.append(score(blend))
        singles.append(blend)
    for _ in range(900):
        size = rng.choice([2, 2, 2, 3, 3, 4, 5])
        size = min(size, len(protectants))
        selected = rng.sample(protectants, size)
        weights = [rng.random() ** 1.6 + 0.05 for _ in selected]
        total_scale = rng.uniform(0.7, 1.6)
        blend = make_blend(selected, weights, total_scale)
        candidates.append(score(blend))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_items = candidates[0]
    unique: list[list[dict[str, Any]]] = []
    seen = set()
    for _, items in candidates:
        key = tuple(sorted((item["id"], round(float(item["pct"]), 1)) for item in items))
        if key in seen:
            continue
        seen.add(key)
        unique.append(items)
        if len(unique) >= 4:
            break
    dtm_final = blend_dtm(best_items, matrix) * (1.0 if kind == "protein" else 0.45)
    return {
        "items": best_items,
        "dtm_c": dtm_final,
        "penalty": _blend_penalty(best_items, brief, food),
        "score": best_score,
        "alternatives": unique[1:4],
        "method": "seeded random search + mechanistic blend model",
        "seed": stable_seed(brief["query"], record["id"], str(brief["conditions"]), kind),
    }


def _kinetic_retention(record: dict[str, Any], kind: str, props: dict[str, float], brief: dict[str, Any], matrix: dict[str, Any], temp_c: float, time_min: float, storage: bool = False) -> float:
    if time_min <= 0:
        return 1.0
    ph = float(brief["conditions"]["ph"])
    if kind == "protein":
        k_ref = 1.0e-5
        thermal_q = 0.060
        acid_q = 0.15
        protection_scale = 2.5
        base = 8.0
    else:
        k_ref = 5.0e-6
        thermal_q = 0.050
        acid_q = 0.10
        protection_scale = 1.2
        base = 8.0
    thermal = 10.0 ** (thermal_q * (temp_c - 25.0))
    acid = 10.0 ** (acid_q * (7.0 - ph))
    matrix_factor = float(matrix.get("matrix_factor", 1.0))
    protection = 1.0 + max(0.0, props["dtm"]) / base * protection_scale
    k = k_ref * thermal * acid * matrix_factor / max(0.2, protection)
    if storage:
        light = str(matrix.get("light", "amber bottle")).lower()
        light_factor = 2.2 if "clear" in light or "透明" in light else 1.0
        photostability = float(record.get("photostability", 0.5))
        if record.get("fluorescence") and not record.get("photostability"):
            photostability = 0.35
        k *= 1.0 + (1.0 - photostability) * (light_factor - 1.0) * 0.8
        oxygen = str(matrix.get("oxygen", "moderate")).lower()
        oxygen_factor = {0.0: 1.0, "low": 0.8, "moderate": 1.0, "air": 1.2}.get(oxygen, 1.0)
        if record.get("o2_required") is False:
            oxygen_factor = min(oxygen_factor, 1.0)
        k *= oxygen_factor
    retention = math.exp(-k * time_min)
    folded_factor = 1.0 if kind == "compound" else 0.15 + 0.85 * props["folded"]
    return clamp(retention * folded_factor)


def _spectral_metrics(record: dict[str, Any], kind: str, retention: float, brief: dict[str, Any], ph: float) -> dict[str, Any]:
    acid = float(record.get("acid_ph50", 4.5))
    shift = 0.8 + 4.5 * (1.0 - retention) + max(0.0, acid - ph) * 0.7
    interference = 0.0
    if kind == "compound":
        interference = float(record.get("uv_interference", 0.0)) * 0.02
    cosine = clamp(0.999 - 0.025 * (1.0 - retention) - interference, 0.0, 1.0)
    return {
        "intensity_retention": round(retention, 4),
        "delta_em_nm": round(shift, 2),
        "shape_cosine": round(cosine, 4),
        "uv_vis_change_pct": round(100.0 * (1.0 - retention) * 0.65, 2),
    }


def evaluate_candidate(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], brief: dict[str, Any]) -> dict[str, Any]:
    matrix = data.get_matrix(brief["matrix_id"])
    cond = brief["conditions"]
    props = _effective_properties(record, kind, blend, brief, matrix)
    process_ret = _kinetic_retention(record, kind, props, brief, matrix, cond["process_temp_c"], cond["process_time_min"], storage=False)
    storage_brief = {**brief, "conditions": {**cond, "process_temp_c": cond["storage_temp_c"]}}
    storage_props = _effective_properties(record, kind, blend, storage_brief, matrix)
    storage_ret = _kinetic_retention(record, kind, storage_props, storage_brief, matrix, cond["storage_temp_c"], cond["shelf_days"] * 1440.0, storage=True)
    mechanistic = clamp(process_ret * storage_ret)
    learned = mechanistic
    try:
        from . import training
        learned = training.correct_retention(
            mechanistic, cond["process_temp_c"], cond["ph"], float(record.get("tm_c", props["tm"])),
            float(props["dtm"]), float(matrix.get("matrix_factor", 1.0)), kind == "protein",
        )
    except Exception:
        learned = mechanistic
    overall = clamp(learned)
    spectral = _spectral_metrics(record, kind, overall, brief, cond["ph"])
    target = float(brief["spectral"]["target_retention"])
    meets = (
        overall >= target
        and spectral["delta_em_nm"] <= 3.0
        and spectral["shape_cosine"] >= 0.98
    ) if brief["spectral"]["invariance"] else overall >= target
    desired_em = brief["spectral"].get("desired_em_nm")
    em = record.get("em_nm")
    if desired_em and em:
        spectral_fit = math.exp(-0.5 * ((float(em) - float(desired_em)) / 35.0) ** 2)
    elif desired_em and not em:
        spectral_fit = 0.2
    else:
        spectral_fit = 1.0
    brightness = float(record.get("brightness", 1.0 if kind == "compound" else 0.8))
    brightness_score = clamp(brightness / 1.6)
    food_score = 1.0 if (str(record.get("food_status", "")).startswith("food") or record.get("food_safe")) else 0.35
    cost_score = 1.0 if str(record.get("food_status", "")).startswith("food") else 0.65
    if kind == "protein":
        cost_score *= 0.9 if "E. coli" in record.get("expression_hosts", []) else 0.7
    blend_cost = {"low": 1.0, "medium": 0.8, "high": 0.55}
    if blend:
        cost_score *= sum(blend_cost.get(str(item.get("cost", "medium")), 0.8) for item in blend) / len(blend)
    weights = brief["priorities"]
    total = (
        weights["stability"] * overall
        + weights["spectral"] * (0.55 * spectral_fit + 0.45 * spectral["shape_cosine"])
        + weights["food_safety"] * food_score
        + weights["brightness"] * brightness_score
        + weights["cost"] * cost_score
    )
    if brief["food_safe_required"] and food_score < 0.9:
        total *= 0.25
    if desired_em:
        if spectral_fit < 0.35:
            total *= 0.5
        if spectral_fit < 0.10:
            total *= 0.5
    if not meets:
        total *= 0.35 + 0.35 * clamp(overall / max(1e-6, target))
    if overall < 0.05:
        total *= 0.5
    expanded = []
    for item in blend:
        source = data.get_protectant(item["id"])
        expanded.append({
            "id": source["id"], "name": source["name"], "cn_name": source["cn_name"],
            "pct": round(float(item["pct"]), 3), "role": source.get("role"), "role_cn": ROLE_CN.get(str(source.get("role", "")), source.get("role", "")), "category": source.get("category"),
            "mechanism": source.get("mechanism", []), "dtm_c": round(_blend_effect(source, float(item["pct"])), 2),
            "food_safe": source.get("food_safe"), "notes": source.get("notes", ""),
            "notes_cn": source.get("notes_cn", source.get("notes", "")),
        })
    rationale = []
    rationale.append(f"预测工艺保留率 {overall:.1%}（目标 {target:.0%}），Δλem {spectral['delta_em_nm']:.1f} nm，谱形余弦 {spectral['shape_cosine']:.3f}。")
    rationale.append(f"保护剂组合将有效 Tm 从 {props['tm']:.1f}°C 调整到 {props['tm_eff']:.1f}°C，有效 pH50 为 {props['acid_ph50_eff']:.2f}。")
    if not meets:
        rationale.append("未达到“基本不变”阈值，建议提高保护剂剂量、降低工艺温度/时间，或改用更耐热的候选。")
    return {
        "id": record["id"],
        "name": record["name"],
        "cn_name": record.get("cn_name", record["name"]),
        "kind": kind,
        "type": record.get("type", "compound"),
        "references": record.get("references") or [],
        "evidence_level": record.get("evidence_level") or "curated",
        "score": round(clamp(total, 0.0, 1.0), 4),
        "meets_spec": bool(meets),
        "metrics": {
            "tm_c": round(props["tm"], 2), "tm_eff_c": round(props["tm_eff"], 2), "dtm_c": round(props["dtm"], 2),
            "acid_ph50": round(props["acid_ph50"], 2), "acid_ph50_eff": round(props["acid_ph50_eff"], 2),
            "process_retention": round(process_ret, 4), "storage_retention": round(storage_ret, 4),
            "mechanistic_retention": round(mechanistic, 4), "overall_retention": round(overall, 4),
            "learned_correction": round(overall - mechanistic, 4), "target_retention": target,
            "brightness": brightness, "ex_nm": record.get("ex_nm"), "em_nm": record.get("em_nm"),
            "photostability": record.get("photostability"), "food_status": record.get("food_status"),
            "spectral": spectral, "spectral_fit": round(spectral_fit, 4),
        },
        "score_breakdown": {
            "stability": round(overall, 4), "spectral": round(0.55 * spectral_fit + 0.45 * spectral["shape_cosine"], 4),
            "food_safety": round(food_score, 4), "brightness": round(brightness_score, 4), "cost": round(cost_score, 4),
            "weights": weights,
        },
        "blend": expanded,
        "blend_method": "seeded random search",
        "rationale": rationale,
        "warnings": _candidate_warnings(record, kind, expanded, brief),
        "record": record,
    }


def _candidate_warnings(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], brief: dict[str, Any]) -> list[str]:
    warnings = []
    status = str(record.get("food_status", ""))
    if brief["food_safe_required"] and not (status.startswith("food") or record.get("food_safe")):
        warnings.append("该候选不是食品级配料，不能用于可食用产品。")
    if record.get("allergen"):
        warnings.append("候选或辅料有过敏原标记。")
    if kind == "protein" and record.get("o2_required"):
        warnings.append("该荧光蛋白依赖氧气成熟；需控制溶解氧和储存氧。")
    if record.get("cofactor"):
        warnings.append(f"需要辅因子 {record['cofactor']}；需评估其法规状态、成本和稳定性。")
    if any(item["id"] == "ascorbic_acid" for item in blend) and record.get("id") in {"riboflavin", "anthocyanin"}:
        warnings.append("抗坏血酸与核黄素/花青素可能发生光氧化或色泽互作，需做相容性实验。")
    if any(item["id"] == "sodium_azide" for item in blend):
        warnings.append("叠氮化钠有毒，仅限实验室，不可用于食品或饮料。")
    if str(record.get("food_status", "")).startswith("food_colorant"):
        warnings.append("天然色素的食品法规状态因地区而异，需核验纯度、溶剂残留和最大使用量。")
    return warnings


def _theoretical_mass(sequence: str | None) -> float | None:
    if not sequence:
        return None
    try:
        from Bio.SeqUtils import molecular_weight
        return round(float(molecular_weight(sequence, seq_type="protein")), 2)
    except Exception:
        mass = sum(AA_MASS.get(aa, 0.0) for aa in sequence) + 18.0153
        return round(mass, 2)


def _dose_mg_l(record: dict[str, Any], kind: str) -> float:
    if kind == "protein":
        if record.get("id") == "phycocyanin":
            return 300.0
        return 200.0
    typical = record.get("typical_mg_l") or [20, 100]
    return float(typical[0])


def build_formulation(selected: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    record = selected["record"]
    kind = selected["kind"]
    matrix = data.get_matrix(brief["matrix_id"])
    ph = float(brief["conditions"]["ph"])
    food = bool(brief["food_safe_required"])
    ingredients: list[dict[str, Any]] = []
    warnings: list[str] = []
    dose = _dose_mg_l(record, kind)
    ingredients.append({
        "name": record["name"], "cn_name": record.get("cn_name"), "pct": round(dose / 10000.0, 5),
        "dose_mg_l": dose, "role": "functional fluorophore", "range": f"{dose*0.5:.0f}-{dose*2:.0f} mg/L",
        "food_safe": bool(record.get("food_safe") or str(record.get("food_status", "")).startswith("food")),
        "note": "主功能成分；先用储备液加入，避免泡沫和局部过浓。",
    })
    for item in selected["blend"]:
        ingredients.append({
            "name": item["name"], "cn_name": item["cn_name"], "pct": item["pct"], "role": item["role"],
            "range": f"{max(0.01, item['pct']*0.6):.3g}-{item['pct']*1.4:.3g} %", "food_safe": item["food_safe"],
            "note": item.get("notes_cn") or item.get("notes", ""),
        })
    if ph <= 6.5:
        buffer_pct = 0.5
        ingredients.append({"name": "Sodium citrate", "cn_name": "柠檬酸钠", "pct": buffer_pct, "role": "buffer", "range": "0.2-1.0 %", "food_safe": True, "note": "将 pH 稳定在目标附近。"})
    else:
        ingredients.append({"name": "L-Histidine", "cn_name": "L-组氨酸", "pct": 0.2, "role": "buffer", "range": "0.1-0.5 %", "food_safe": True, "note": "近中性 pH 缓冲。"})
    acidulant = 0.0
    if ph < 5.0:
        acidulant = 0.15
        ingredients.append({"name": "Citric acid", "cn_name": "柠檬酸", "pct": acidulant, "role": "acidulant", "range": "按 pH 滴定", "food_safe": True, "note": "缓慢滴定到目标 pH，记录实际用量。"})
    if food and ph <= 4.5:
        ingredients.append({"name": "Sodium benzoate", "cn_name": "苯甲酸钠", "pct": 0.05, "role": "preservative", "range": "≤0.1 %（按法规）", "food_safe": True, "note": "酸性饮料防腐；不得超过销售地最大使用量。"})
    elif food and ph <= 6.0:
        ingredients.append({"name": "Potassium sorbate", "cn_name": "山梨酸钾", "pct": 0.10, "role": "preservative", "range": "≤0.2 %（按法规）", "food_safe": True, "note": "需确认当地允许使用量和标签。"})
    if food and brief["target_kind"] == "food_beverage":
        ingredients.append({"name": "Rebaudioside A", "cn_name": "莱鲍迪苷A", "pct": 0.02, "role": "sweetener", "range": "按甜度等量替换", "food_safe": True, "note": "可选；按甜度目标调整。"})
    if food and record["id"] not in {"riboflavin", "anthocyanin"} and not any(item["id"] == "ascorbic_acid" for item in selected["blend"]):
        ingredients.append({"name": "Ascorbic acid", "cn_name": "抗坏血酸", "pct": 0.05, "role": "antioxidant", "range": "0.02-0.2 %", "food_safe": True, "note": "抗氧化；与色素做相容性实验。"})
    used = sum(float(item["pct"]) for item in ingredients)
    if used >= 100.0:
        warnings.append("辅料总量超过 100%，已按比例压缩；请重新优化配方。")
        scale = 99.0 / used
        for item in ingredients:
            item["pct"] = round(float(item["pct"]) * scale, 5)
        used = sum(float(item["pct"]) for item in ingredients)
    water_pct = round(100.0 - used, 4)
    ingredients.append({"name": "Purified water", "cn_name": "纯化水", "pct": water_pct, "role": "q.s. to 100 %", "range": "balance", "food_safe": True, "note": "用纯化水/去离子水定容。"})
    for item in ingredients:
        item["role_cn"] = ROLE_CN.get(str(item.get("role", "")), item.get("role", ""))

    process = [
        {"step": 1, "title": "预溶保护剂", "detail": f"在 40-50°C 的纯化水中溶解保护剂（{', '.join(item['cn_name'] for item in selected['blend']) or '无'}），避免结块。"},
        {"step": 2, "title": "缓冲与 pH", "detail": f"加入缓冲盐，缓慢用柠檬酸/NaOH 调到 pH {ph:g}；记录实际 pH 和温度。"},
        {"step": 3, "title": "加入功能成分", "detail": f"加入 {record.get('cn_name', record['name'])} 储备液至 {dose:.0f} mg/L；避光、低速搅拌，避免泡沫。"},
        {"step": 4, "title": "除氧与防腐", "detail": "充氮或真空脱气 10-15 min；按法规加入防腐剂/抗氧化剂；检测溶解氧。"},
        {"step": 5, "title": "热处理", "detail": f"{matrix['cn_name']}工艺：{brief['conditions']['process_temp_c']:g}°C / {brief['conditions']['process_time_min']:g} min（或等效巴氏/UHT 验证）。"},
        {"step": 6, "title": "灌装与冷却", "detail": "热灌装或无菌灌装；避光包装；快速冷却到储存温度；检查密封和顶空氧。"},
    ]
    controls = [
        {"parameter": "pH", "target": f"{ph:g} ± 0.1", "why": "酸是主要失活变量；pH 漂移会放大光谱变化。"},
        {"parameter": "工艺温度/时间", "target": f"{brief['conditions']['process_temp_c']:g}°C / {brief['conditions']['process_time_min']:g} min", "why": "累积热负荷决定不可逆失活。"},
        {"parameter": "溶解氧", "target": "≤1 ppm（如可行）", "why": "降低氧化和光氧化；氧依赖型荧光蛋白需单独评估。"},
        {"parameter": "光照", "target": "琥珀色/避光包装，UV 阻隔", "why": "核黄素、藻蓝蛋白和多种荧光团对光敏感。"},
        {"parameter": "离子强度", "target": "按基质，避免高盐", "why": "高盐会削弱保护剂的优先排除效应。"},
        {"parameter": "水分活度/固形物", "target": "按产品标准", "why": "影响玻璃化、微生物稳定性和保护剂有效性。"},
        {"parameter": "剪切/均质", "target": "低剪切，避免过度起泡", "why": "界面吸附和泡沫会导致蛋白损失。"},
    ]
    qc = [
        {"test": "荧光发射光谱", "method": "荧光分光光度计，固定激发/狭缝/温度", "acceptance": f"保留率 ≥ {brief['spectral']['target_retention']:.0%}，Δλem ≤ 3 nm，谱形余弦 ≥ 0.98", "stage": "0 h / 加速 / 货架期"},
        {"test": "UV-Vis 吸收", "method": "1 cm 比色皿，基质空白", "acceptance": "特征峰位置不漂移；吸光度变化在预设范围内", "stage": "0 h / 加速 / 货架期"},
        {"test": "pH", "method": "校准 pH 计，25°C", "acceptance": f"{ph:g} ± 0.1", "stage": "每批"},
        {"test": "外观/颜色", "method": "比色卡或色差仪", "acceptance": "与标准样对比 ΔE 在预设范围", "stage": "每批"},
        {"test": "微生物", "method": "按产品标准（菌落总数、霉菌酵母、致病菌）", "acceptance": "符合销售地法规", "stage": "每批/稳定性"},
        {"test": "蛋白完整性（如适用）", "method": "SDS-PAGE / SEC-HPLC", "acceptance": "主峰比例和降解产物在预设范围", "stage": "工艺后/货架期"},
    ]
    storage_days = int(brief["conditions"]["shelf_days"])
    retention = selected["metrics"]["overall_retention"]
    shelf_note = (
        f"数字孪生预测 {storage_days} 天后保留率约 {retention:.0%}（{brief['conditions']['storage_temp_c']:g}°C）。"
        "必须用真实样品做 0、7、14、30、60 天实测，并用加速试验校核。"
    )
    return {
        "name": f"{record.get('cn_name', record['name'])}·{matrix['cn_name']}原型",
        "serving_basis": "1 L",
        "ingredients": ingredients,
        "process": process,
        "controls": controls,
        "qc": qc,
        "storage": shelf_note,
        "packaging": "避光玻璃/高阻隔 PET；如含氧敏感成分，考虑氧气清除剂和氮气顶空。",
        "regulatory": _regulatory_notes(record, kind, selected["blend"], food),
        "warnings": warnings + [
            "本配方是数字原型，不是食品安全生产许可；需由具备资质的食品科学家/法规团队复核并做中试。",
        ],
        "cost_note": "成本未含表达纯化、法规检测和中试损耗；请用本地供应商报价替换。",
    }


def _regulatory_notes(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], food: bool) -> list[str]:
    notes = []
    status = str(record.get("food_status", ""))
    if food:
        notes.append("所有配料必须出现在销售地允许使用的食品配料/添加剂名单内，并按最大使用量和标签要求执行。")
        if kind == "protein" and not status.startswith("food"):
            notes.append("该荧光蛋白不是已批准食品配料；不得直接用于可食用产品。")
        if status.startswith("food_colorant"):
            notes.append("天然色素的批准状态、纯度、溶剂残留和最大使用量因地区而异；需供应商提供合规文件。")
        if record.get("id") == "riboflavin":
            notes.append("核黄素可作为食品着色剂/维生素使用，但需确认当地最大使用量与标签；避免与抗坏血酸在强光下共存。")
        if record.get("id") == "caffeine":
            notes.append("咖啡因有地区性限量/警示标签要求。")
        for item in blend:
            if item.get("id") in {"sodium_benzoate", "potassium_sorbate"}:
                notes.append(f"{item['name']} 的使用量必须符合当地防腐剂法规。")
    else:
        notes.append("研究用途：不构成食品、药品或医疗器械合规声明。")
    notes.append("任何体内/临床/食品用途都需要伦理、法规和安全性评估。")
    return notes


def _mc_summary(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], brief: dict[str, Any], n: int = 400) -> dict[str, Any]:
    rng = np.random.default_rng(stable_seed(brief["query"], record["id"], "mc"))
    matrix = data.get_matrix(brief["matrix_id"])
    cond = brief["conditions"]
    retentions = []
    for _ in range(n):
        temp = cond["process_temp_c"] + rng.normal(0, 1.0)
        ph = cond["ph"] + rng.normal(0, 0.08)
        b = []
        for item in blend:
            source = data.get_protectant(item["id"])
            b.append({"id": item["id"], "pct": float(item["pct"]) * float(np.clip(rng.normal(1.0, 0.15), 0.5, 1.5))})
        local_brief = {**brief, "conditions": {**cond, "process_temp_c": temp, "ph": ph}}
        local_record = dict(record)
        if kind == "protein":
            local_record["tm_c"] = float(record.get("tm_c", 75.0)) + rng.normal(0, float(record.get("tm_sd", 2.5)))
            local_record["acid_ph50"] = float(record.get("acid_ph50", 5.0)) + rng.normal(0, float(record.get("acid_ph50_sd", 0.35)))
        props = _effective_properties(local_record, kind, b, local_brief, matrix)
        process = _kinetic_retention(local_record, kind, props, local_brief, matrix, temp, cond["process_time_min"])
        storage = _kinetic_retention(local_record, kind, props, local_brief, matrix, cond["storage_temp_c"], cond["shelf_days"] * 1440.0, storage=True)
        retentions.append(clamp(process * storage))
    arr = np.array(retentions)
    target = float(brief["spectral"]["target_retention"])
    return {
        "n": n,
        "mean": round(float(arr.mean()), 4),
        "p05": round(float(np.percentile(arr, 5)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p95": round(float(np.percentile(arr, 95)), 4),
        "prob_meet_target": round(float((arr >= target).mean()), 4),
        "samples": [round(float(x), 4) for x in arr[:80]],
    }


def _sensitivity(record: dict[str, Any], kind: str, blend: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
    matrix = data.get_matrix(brief["matrix_id"])
    cond = brief["conditions"]
    baseline_props = _effective_properties(record, kind, blend, brief, matrix)
    baseline = _kinetic_retention(record, kind, baseline_props, brief, matrix, cond["process_temp_c"], cond["process_time_min"])
    variables = []
    for name, delta in (("process_temp_c", 2.0), ("ph", 0.2), ("process_time_min", 0.2), ("tm_c", 2.0), ("dtm_c", 0.2)):
        local_brief = {**brief, "conditions": dict(cond)}
        local_record = dict(record)
        local_blend = [dict(item) for item in blend]
        if name in local_brief["conditions"]:
            value = float(local_brief["conditions"][name])
            local_brief["conditions"][name] = value * (1 + delta) if name != "ph" else value + delta
        elif name == "tm_c":
            local_record["tm_c"] = float(record.get("tm_c", 75.0)) + delta
        elif name == "dtm_c":
            for item in local_blend:
                item["pct"] = float(item["pct"]) * (1 + delta)
        props = _effective_properties(local_record, kind, local_blend, local_brief, matrix)
        value = _kinetic_retention(local_record, kind, props, local_brief, matrix, local_brief["conditions"]["process_temp_c"], local_brief["conditions"]["process_time_min"])
        variables.append({"variable": name, "change": f"+{delta:.0%}" if name != "ph" else f"+{delta}", "delta_retention": round(value - baseline, 4)})
    variables.sort(key=lambda item: abs(item["delta_retention"]), reverse=True)
    return variables


def simulate_virtual(selected: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    record = selected["record"]
    kind = selected["kind"]
    blend = [{"id": item["id"], "pct": float(item["pct"])} for item in selected["blend"]]
    matrix = data.get_matrix(brief["matrix_id"])
    cond = brief["conditions"]
    temp_grid = np.arange(20.0, 101.0, 2.0)
    ph_grid = np.arange(2.0, 9.01, 0.2)
    time_grid = np.arange(0.0, 61.0, 1.0)
    base_props = _effective_properties(record, kind, [], brief, matrix)
    opt_props = _effective_properties(record, kind, blend, brief, matrix)
    base_temp = []
    opt_temp = []
    for t in temp_grid:
        local = {**brief, "conditions": {**cond, "process_temp_c": float(t)}}
        base_temp.append(_kinetic_retention(record, kind, _effective_properties(record, kind, [], local, matrix), local, matrix, float(t), cond["process_time_min"]))
        opt_temp.append(_kinetic_retention(record, kind, _effective_properties(record, kind, blend, local, matrix), local, matrix, float(t), cond["process_time_min"]))
    base_ph = []
    opt_ph = []
    for p in ph_grid:
        local = {**brief, "conditions": {**cond, "ph": float(p)}}
        base_ph.append(_kinetic_retention(record, kind, _effective_properties(record, kind, [], local, matrix), local, matrix, cond["process_temp_c"], cond["process_time_min"]))
        opt_ph.append(_kinetic_retention(record, kind, _effective_properties(record, kind, blend, local, matrix), local, matrix, cond["process_temp_c"], cond["process_time_min"]))
    base_time = [_kinetic_retention(record, kind, base_props, brief, matrix, cond["process_temp_c"], float(t)) for t in time_grid]
    opt_time = [_kinetic_retention(record, kind, opt_props, brief, matrix, cond["process_temp_c"], float(t)) for t in time_grid]
    storage_brief = {**brief, "conditions": {**cond, "process_temp_c": cond["storage_temp_c"]}}
    storage_props = _effective_properties(record, kind, blend, storage_brief, matrix)
    storage_time = np.arange(0, int(cond["shelf_days"]) + 1, max(1, int(cond["shelf_days"]) // 30))
    storage_curve = []
    for day in storage_time:
        local = {**brief, "conditions": {**cond, "shelf_days": int(day)}}
        storage_curve.append(_kinetic_retention(record, kind, storage_props, local, matrix, cond["storage_temp_c"], float(day) * 1440.0, storage=True))
    mc = _mc_summary(record, kind, blend, brief)
    sens = _sensitivity(record, kind, blend, brief)
    total_pct = sum(float(item["pct"]) for item in blend)
    dose_grid = np.linspace(0.0, max(5.0, total_pct * 1.6), 24)
    dose_curve = []
    for total in dose_grid:
        scaled = []
        for item in blend:
            pct = float(item["pct"]) * (float(total) / max(1e-9, total_pct))
            scaled.append({"id": item["id"], "pct": pct})
        props = _effective_properties(record, kind, scaled, brief, matrix)
        dose_curve.append(_kinetic_retention(record, kind, props, brief, matrix, cond["process_temp_c"], cond["process_time_min"]))
    predicted_shelf = None
    for day in range(0, 366):
        local = {**brief, "conditions": {**cond, "shelf_days": day}}
        retention = _kinetic_retention(record, kind, storage_props, local, matrix, cond["storage_temp_c"], float(day) * 1440.0, storage=True)
        if retention < float(brief["spectral"]["target_retention"]):
            predicted_shelf = day
            break
    return {
        "temperature": {"x": [round(float(x), 1) for x in temp_grid], "base": [round(float(x), 4) for x in base_temp], "optimized": [round(float(x), 4) for x in opt_temp]},
        "ph": {"x": [round(float(x), 2) for x in ph_grid], "base": [round(float(x), 4) for x in base_ph], "optimized": [round(float(x), 4) for x in opt_ph]},
        "time": {"x": [round(float(x), 1) for x in time_grid], "base": [round(float(x), 4) for x in base_time], "optimized": [round(float(x), 4) for x in opt_time]},
        "storage": {"x": [int(x) for x in storage_time], "optimized": [round(float(x), 4) for x in storage_curve]},
        "dose_response": {"x": [round(float(x), 2) for x in dose_grid], "optimized": [round(float(x), 4) for x in dose_curve]},
        "monte_carlo": mc,
        "sensitivity": sens,
        "predicted_shelf_life_days": predicted_shelf,
        "process_retention": selected["metrics"]["process_retention"],
        "storage_retention": selected["metrics"]["storage_retention"],
        "overall_retention": selected["metrics"]["overall_retention"],
    }


def _spectrum_arrays(record: dict[str, Any], kind: str, retention: float, brief: dict[str, Any], blend: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    blend = blend or []
    em = record.get("em_nm") or 520.0
    ex_raw = record.get("ex_nm") or [470]
    ex = ex_raw if isinstance(ex_raw, list) else [ex_raw]
    em_values = em if isinstance(em, list) else [em]
    em_center = float(em_values[0])
    wave = np.arange(380.0, 751.0, 1.0)
    exc = np.zeros_like(wave)
    for center in ex:
        exc += gaussian(wave, float(center), 17.0)
    exc = exc / max(1e-9, exc.max())
    emission = gaussian(wave, em_center, 22.0)
    emission = emission / max(1e-9, emission.max())
    stressed = emission * retention
    uv_wave = np.arange(240.0, 701.0, 1.0)
    uv = np.zeros_like(uv_wave)
    if kind == "protein":
        uv += 0.55 * gaussian(uv_wave, 280.0, 12.0)
        for center in ex:
            uv += gaussian(uv_wave, float(center), 18.0) * 0.8
        uv += 0.05 * np.exp(-(uv_wave - 240.0) / 150.0)
    else:
        for center in ex:
            uv += gaussian(uv_wave, float(center), 20.0)
        for item in blend:
            source = data.get_protectant(item["id"])
            if source["id"] == "ascorbic_acid":
                uv += gaussian(uv_wave, 245.0, 12.0) * 0.5 * float(item["pct"]) / 0.5
            if source["id"] == "riboflavin":
                uv += gaussian(uv_wave, 445.0, 20.0) * 0.4 * float(item["pct"]) / 0.1
    uv = uv / max(1e-9, uv.max())
    uv_stressed = uv * (0.35 + 0.65 * retention)
    metrics = spectral_compare(emission, stressed, wave)
    return {
        "wavelength_nm": [round(float(x), 1) for x in wave],
        "excitation": [round(float(x), 5) for x in exc],
        "emission_reference": [round(float(x), 5) for x in emission],
        "emission_stressed": [round(float(x), 5) for x in stressed],
        "uvvis_wavelength_nm": [round(float(x), 1) for x in uv_wave],
        "uvvis_reference": [round(float(x), 5) for x in uv],
        "uvvis_stressed": [round(float(x), 5) for x in uv_stressed],
        "metrics": metrics,
        "theoretical_mass_da": _theoretical_mass(record.get("sequence")) if kind == "protein" else record.get("mw"),
    }


def spectral_compare(reference: np.ndarray, stressed: np.ndarray, wave: np.ndarray) -> dict[str, Any]:
    ref_norm = reference / max(1e-9, np.linalg.norm(reference))
    stressed_norm = stressed / max(1e-9, np.linalg.norm(stressed))
    cosine = float(np.dot(ref_norm, stressed_norm))
    ref_peak = float(wave[int(np.argmax(reference))])
    stressed_peak = float(wave[int(np.argmax(stressed))])
    return {
        "cosine": round(clamp(cosine), 4),
        "peak_shift_nm": round(stressed_peak - ref_peak, 2),
        "intensity_ratio": round(float(stressed.max() / max(1e-9, reference.max())), 4),
        "reference_peak_nm": round(ref_peak, 1),
        "stressed_peak_nm": round(stressed_peak, 1),
    }


def simulate_spectra(selected: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    record = selected["record"]
    kind = selected["kind"]
    retention = float(selected["metrics"]["overall_retention"])
    blend = [{"id": item["id"], "pct": float(item["pct"])} for item in selected["blend"]]
    arrays = _spectrum_arrays(record, kind, retention, brief, blend)
    library = []
    requested_types = []
    for key, label in (("uv_vis", "UV-Vis"), ("ir", "IR"), ("ms", "MS"), ("nmr", "1H-NMR")):
        if brief["spectral"].get(key):
            requested_types.append(label)
    for spec in data.spectra():
        if spec["compound_id"] == record["id"] and (not requested_types or spec["type"] in requested_types):
            library.append(spec)
    if not requested_types:
        library = [spec for spec in data.spectra() if spec["compound_id"] == record["id"]]
    return {
        "fluorescence": arrays,
        "reference_peaks": library,
        "requested_types": requested_types,
        "invariance": {
            "target_retention": brief["spectral"]["target_retention"],
            "intensity_retention": round(retention, 4),
            "delta_em_nm": selected["metrics"]["spectral"]["delta_em_nm"],
            "shape_cosine": selected["metrics"]["spectral"]["shape_cosine"],
            "meets_spec": selected["meets_spec"],
            "interpretation": "满足“基本不变”阈值" if selected["meets_spec"] else "未满足阈值，需要更强保护或更温和工艺",
        },
        "note": "荧光/UV-Vis 曲线由数字孪生生成；IR/MS/NMR 为参考峰库与匹配/实验方案，不是从头预测。",
    }


def match_spectra(query_peaks: list[list[float]] | list[float], spectrum_type: str, tolerance: float | None = None, top_k: int = 5) -> dict[str, Any]:
    if not query_peaks:
        return {"query": [], "matches": [], "note": "no query peaks"}
    normalized = []
    for peak in query_peaks:
        if isinstance(peak, (int, float)):
            normalized.append((float(peak), 1.0))
        elif len(peak) >= 2:
            normalized.append((float(peak[0]), float(peak[1])))
    defaults = {"UV-Vis": 10.0, "IR": 20.0, "MS": 0.5, "1H-NMR": 0.12}
    tol = float(tolerance if tolerance is not None else defaults.get(spectrum_type, 10.0))
    results = []
    for spec in data.spectra():
        if spec["type"] != spectrum_type:
            continue
        ref = [(float(p[0]), float(p[1])) for p in spec["peaks"]]
        score = 0.0
        coverage = 0
        for q_mz, q_int in normalized:
            nearest = min(ref, key=lambda item: abs(item[0] - q_mz))
            delta = abs(nearest[0] - q_mz)
            if delta <= tol:
                coverage += 1
                score += q_int * nearest[1] * math.exp(-0.5 * (delta / max(1e-9, tol / 2.0)) ** 2)
        score /= max(1, len(normalized))
        results.append({
            "spectrum_id": spec["id"], "compound_id": spec["compound_id"], "type": spec["type"],
            "solvent": spec.get("solvent"), "score": round(clamp(score), 4), "coverage": round(coverage / max(1, len(normalized)), 4),
            "matches": sum(1 for q, _ in normalized if min(abs(r[0] - q) for r in ref) <= tol),
            "reference_peaks": spec["peaks"], "notes": spec.get("notes"),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return {
        "query": [{"position": p, "intensity": i} for p, i in normalized],
        "type": spectrum_type, "tolerance": tol, "matches": results[:max(1, min(20, int(top_k)))],
        "note": "近似参考谱匹配，不能替代标准品和认证方法。",
    }


def _logic_chain(brief: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    nodes = [
        {"id": "query", "label": "自然语言需求", "detail": brief["query"][:160], "status": "computed"},
        {"id": "constraints", "label": "约束解析", "detail": f"pH {brief['conditions']['ph']:g}; {brief['conditions']['process_temp_c']:g}°C/{brief['conditions']['process_time_min']:g} min; 保留率 ≥ {brief['spectral']['target_retention']:.0%}", "status": "computed"},
        {"id": "db", "label": "策展数据库", "detail": f"{len(data.proteins())} 个荧光蛋白/色素，{len(data.compounds())} 个小分子，{len(data.protectants())} 个保护剂", "status": "computed"},
        {"id": "screen", "label": "候选筛选", "detail": f"选中 {selected['cn_name']}，评分 {selected['score']:.3f}", "status": "computed"},
        {"id": "blend", "label": "保护剂优化", "detail": "、".join(f"{x['cn_name']} {x['pct']:g}%" for x in selected["blend"]) or "未使用保护剂", "status": "computed"},
        {"id": "twin", "label": "数字孪生", "detail": f"有效 Tm {selected['metrics']['tm_eff_c']:.1f}°C；预测保留率 {selected['metrics']['overall_retention']:.1%}", "status": "computed"},
        {"id": "spectra", "label": "光谱模拟", "detail": f"Δλem {selected['metrics']['spectral']['delta_em_nm']:.1f} nm；余弦 {selected['metrics']['spectral']['shape_cosine']:.3f}", "status": "computed"},
        {"id": "md", "label": "MD 验证", "detail": "生成力场/溶剂/时长/分析协议；需 HPC 或本地 OpenMM/Amber 执行", "status": "planned"},
        {"id": "qm", "label": "QM 验证", "detail": "生成 TD-DFT/QM-MM 方案；轻量 MMFF 快速检查可在线执行", "status": "planned"},
        {"id": "formulation", "label": "配方与工艺", "detail": "配料表、热处理、pH/氧/光控制、QC 与货架期", "status": "computed"},
        {"id": "lab", "label": "线下实验包", "detail": "样品、仪器、对照、统计与验收阈值", "status": "planned"},
    ]
    edges = [
        ("query", "constraints"), ("constraints", "db"), ("db", "screen"), ("screen", "blend"),
        ("blend", "twin"), ("twin", "spectra"), ("spectra", "md"), ("md", "qm"),
        ("spectra", "formulation"), ("formulation", "lab"), ("qm", "lab"),
    ]
    return {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges]}


def _provenance(brief: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    datasets = data.dataset_manifest()
    return {
        "engine_version": ENGINE_VERSION,
        "package_version": __version__,
        "created_utc": utc_now(),
        "datasets": datasets,
        "model": {
            "type": "mechanistic two-state + first-order kinetic digital twin",
            "calibration": "literature-trend priors; feedback-corrected when experimental data is supplied",
            "uncertainty": "Monte Carlo over Tm, pH50, protectant efficacy, process temperature and pH",
            "not_validated_for": ["regulatory release", "clinical use", "food safety approval", "de novo protein structure prediction"],
        },
        "selected": selected["id"],
        "brief_assumptions": brief["assumptions"],
        "limitations": [
            "In-silico ranking only; no candidate in this report has been experimentally validated by BioForge.",
            "Fluorescent protein stability parameters are approximate literature priors; batch, buffer and protein construct effects can dominate.",
            "The digital twin does not predict atomistic photophysics, aggregation pathways or all matrix interactions.",
            "IR/MS/NMR entries are approximate reference peaks for method development, not certified spectra.",
            "MD/QM results require an external engine; the generated protocols are starting points, not completed calculations.",
            "Food/beverage use requires regulatory, safety, sensory and shelf-life validation by qualified teams.",
        ],
        "citations": [
            "UniProt REST (P42212) for avGFP sequence",
            "FPbase-curated photophysical trends (values approximated in this demo pack)",
            "Tsien 1998; Shaner 2004; Pedelacq 2006; Bajar 2016; Bindels 2017",
            "Carpenter & Crowe 1989; Arakawa 2001; Mensink 2017 (protein stabilization trends)",
        ],
    }


def design(query: str, options: dict[str, Any] | None = None, generate_artifacts: bool = True) -> dict[str, Any]:
    brief = parse_brief(query, options)
    if brief.get("unresolved_proteins"):
        names = "、".join(brief["unresolved_proteins"])
        raise ValueError(
            f"目标蛋白「{names}」不在本地策展数据库中，无法负责任地生成候选；"
            "不会用藻蓝蛋白或其他蛋白替代。请提供 UniProt/PDB 标识并先导入策展记录，"
            "或从已收录的荧光蛋白/食品蛋白中选择。"
        )
    pool = candidate_pool(brief)
    matrix = data.get_matrix(brief["matrix_id"])
    candidates = []
    for record in pool:
        kind = record["_kind"]
        blend_result = optimize_blend(record, kind, brief, matrix)
        blend_specs = blend_result["items"]
        evaluated = evaluate_candidate(record, kind, blend_specs, brief)
        evaluated["blend_alternatives"] = blend_result.get("alternatives", [])
        evaluated["blend_penalty"] = round(float(blend_result.get("penalty", 0.0)), 4)
        evaluated["blend_seed"] = blend_result.get("seed")
        candidates.append(evaluated)
    candidates.sort(key=lambda item: (-item["score"], -item["metrics"]["overall_retention"], item["id"]))
    if not candidates:
        raise ValueError("no candidates available for the requested constraints")
    selected = candidates[0]
    alternatives = []
    try:
        other_kind = "compound" if selected["kind"] == "protein" else "protein"
        other_pool = []
        for item in candidate_pool({**brief, "requested_kind": "compound" if other_kind == "compound" else "protein", "target_kind": brief["target_kind"], "explicit_protein_id": brief.get("explicit_protein_id"), "explicit_compound_id": brief.get("explicit_compound_id")}):
            if item["_kind"] == other_kind:
                other_pool.append(item)
        for record in other_pool[:6]:
            blend_result = optimize_blend(record, record["_kind"], brief, matrix)
            evaluated = evaluate_candidate(record, record["_kind"], blend_result["items"], brief)
            evaluated.pop("record", None)
            alternatives.append(evaluated)
        alternatives.sort(key=lambda item: (-item["score"], -item["metrics"]["overall_retention"]))
        alternatives = alternatives[:3]
    except Exception:
        alternatives = []
    formulation = build_formulation(selected, brief)
    virtual = simulate_virtual(selected, brief)
    spectra_result = simulate_spectra(selected, brief)
    validation_plan = validation_mod.build_validation_plan(selected, brief, formulation)
    logic_chain = _logic_chain(brief, selected)
    provenance = _provenance(brief, selected)
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    result = {
        "job_id": job_id,
        "created_utc": utc_now(),
        "engine_version": ENGINE_VERSION,
        "brief": brief,
        "candidates": candidates[:10],
        "alternative_candidates": alternatives,
        "selected": selected,
        "formulation": formulation,
        "virtual_experiment": virtual,
        "spectra": spectra_result,
        "validation": validation_plan,
        "logic_chain": logic_chain,
        "provenance": provenance,
        "warnings": brief["warnings"] + selected["warnings"] + _global_warnings(brief, selected, alternatives) + [
            "仅用于研究与设计决策支持；任何食品、临床或法规用途都必须经过有资质团队验证。",
        ],
        "assumptions": brief["assumptions"],
        "decision_summary": _decision_summary(brief, selected),
    }
    if generate_artifacts:
        from . import report
        result["artifacts"] = report.build_artifacts(result)
    result["brief"].pop("matrix", None)
    for candidate in result["candidates"]:
        candidate.pop("record", None)
    if generate_artifacts:
        from . import report
        report.save_job(result)
    return result


def _global_warnings(brief: dict[str, Any], selected: dict[str, Any], alternatives: list[dict[str, Any]]) -> list[str]:
    warnings = []
    desired = brief["spectral"].get("desired_em_nm")
    if desired and selected["metrics"].get("spectral_fit", 1.0) < 0.5:
        warnings.append(f"目标发射波长约 {desired:.0f} nm 在可用候选里没有高匹配项；当前最佳匹配度仅 {selected['metrics']['spectral_fit']:.2f}，需要换候选、做光谱工程或放宽颜色要求。")
    if brief["food_safe_required"] and brief.get("requested_kind") == "protein" and selected["kind"] == "protein":
        warnings.append("食品级模式下的蛋白质候选很少；若允许小分子食品色素，报告里给出了备选，但它们的“蛋白”属性不成立。")
    if not selected["meets_spec"]:
        warnings.append("当前约束下没有候选达到“基本不变”阈值；建议降低工艺温度/时间、提高保护剂剂量、改用封装/冻干形式，或接受更低的目标保留率。")
    return warnings


def _decision_summary(brief: dict[str, Any], selected: dict[str, Any]) -> list[str]:
    lines = []
    lines.append(f"推荐候选：{selected['cn_name']}（{selected['kind']}），综合评分 {selected['score']:.3f}。")
    if selected["blend"]:
        lines.append("保护剂组合：" + "、".join(f"{item['cn_name']} {item['pct']:g}%" for item in selected["blend"]) + "。")
    else:
        lines.append("在当前约束下没有找到净收益为正的保护剂组合，建议先降低热负荷或更换候选。")
    lines.append(f"数字孪生预测：工艺后 {selected['metrics']['process_retention']:.1%}，货架期后 {selected['metrics']['storage_retention']:.1%}，总保留 {selected['metrics']['overall_retention']:.1%}。")
    lines.append(f"光谱判定：Δλem {selected['metrics']['spectral']['delta_em_nm']:.1f} nm，谱形余弦 {selected['metrics']['spectral']['shape_cosine']:.3f}，{'达到' if selected['meets_spec'] else '未达到'}“基本不变”阈值。")
    if brief["food_safe_required"]:
        lines.append("食品级模式已启用；最终配方需按销售地法规复核，并用真实样品做加速/货架期实验。")
    else:
        lines.append("研究模式；若要做食品/饮料，请切换到食品级候选并完成法规评估。")
    return lines


def load_job(job_id: str) -> dict[str, Any]:
    path = data.JOBS_DIR / job_id / "result.json"
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))
