from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from . import composition, data, processing

ENGINE_VERSION = "2.1.0-food"

CATEGORY_WORDS = {
    "beverage_generic": ("饮料", "饮品", "汽水", "苏打", "beverage", "drink", "soda"),
    "juice": ("果汁", "橙汁", "苹果汁", "juice"),
    "dairy_milk": ("乳饮", "牛奶", "牛乳", "milk", "乳饮料", "灭菌乳", "超高温灭菌"),
    "dairy_yogurt": ("酸奶", "发酵乳", "yogurt", "yoghurt"),
    "plant_milk": ("植物奶", "豆奶", "燕麦奶", "杏仁奶", "plant milk", "soy milk", "oat milk"),
    "bakery_bread": ("面包", "吐司", "馒头", "bread", "toast", "bun"),
    "bakery_cake": ("蛋糕", "戚风", "海绵", "cake", "muffin"),
    "meat_sausage": ("香肠", "火腿", "肉肠", "sausage", "ham"),
    "plant_meat": ("植物肉", "素肉", "植物基肉", "肉饼", "plant-based meat", "vegan patty", "burger"),
    "sauce_emulsion": ("蛋黄酱", "沙拉酱", "乳化酱", "mayonnaise", "mayo", "dressing"),
    "sauce_acid": ("番茄酱", "ketchup", "辣椒酱", "酸性酱", "sauce"),
    "confectionery_gummy": ("软糖", "糖果", "gummy", "candy", "gelatin candy"),
    "confectionery_chocolate": ("巧克力", "chocolate", "cocoa"),
    "snack_extruded": ("膨化", "薯片", "零食", "snack", "chip", "extruded"),
    "cereal_bar": ("谷物棒", "能量棒", "燕麦棒", "cereal bar", "granola bar", "protein bar"),
    "frozen_dessert": ("冰淇淋", "雪糕", "冰激凌", "ice cream", "frozen dessert"),
    "fermented_vegetable": ("泡菜", "酸菜", "发酵蔬菜", "kimchi", "sauerkraut", "fermented vegetable"),
    "edible_film": ("可食膜", "可食用膜", "可食性", "海藻酸钠膜", "涂层", "edible film", "coating"),
    "powder_drink": ("固体饮料", "冲剂", "粉剂", "powder drink", "drink mix"),
    "jelly": ("果冻", "jelly", "gel dessert"),
}

_MEAT_IDS = {"pork_lean", "beef_lean", "chicken_breast", "pork_fat", "fish_oil"}
_COLORANT_IDS = {"anthocyanin", "beta_carotene", "riboflavin", "phycocyanin", "beet_extract"}

ROLE_CN = {
    "continuous_phase": "连续相", "sweetener": "甜味剂", "bulking": "填充/载体",
    "acidulant": "酸度调节剂", "buffer": "缓冲剂", "colorant": "着色剂",
    "preservative": "防腐剂", "antioxidant": "抗氧化剂", "emulsifier": "乳化剂",
    "stabilizer": "稳定剂", "thickener": "增稠剂", "gelling": "胶凝剂",
    "protein": "蛋白质", "fat": "脂肪", "fiber": "膳食纤维", "salt": "食盐",
    "flavor": "风味", "structure": "结构主体", "leavening": "膨松/发酵",
    "calcium": "钙源", "crosslinker": "交联剂", "plasticizer": "增塑剂",
    "binder": "黏结剂", "fortification": "营养强化", "solids": "固形物",
    "dairy_solids": "乳固体", "substrate": "发酵基质", "cocoa": "可可固形物",
    "juice_solids": "果汁固形物", "anticaking": "抗结剂", "film_former": "成膜基质",
    "acid": "酸度", "umami": "鲜味", "sweetness": "甜味",
    "thermoprotectant": "热保护剂", "chelator": "螯合剂", "color_protectant": "护色剂",
}

_VARIANT_CATEGORIES = {
    "hydrocolloid", "acidulant", "fiber", "colorant", "salt", "emulsifier",
    "antioxidant", "preservative", "buffer", "leavening", "vegetable",
}

STRATEGY_EN = {
    "balanced": "Balanced",
    "clean_label": "Clean label",
    "cost": "Cost priority",
    "stability": "Stability priority",
    "sensory": "Sensory priority",
    "high_protein": "High protein",
    "low_sugar": "Low sugar",
    "low_sodium": "Low sodium",
    "plant_based": "Plant based",
    "fiber": "High fibre",
}

STRATEGIES = [
    ("balanced", "均衡型", "在基础模板上补齐关键功能角色，兼顾稳定、感官与成本。"),
    ("clean_label", "清洁标签", "优先天然配料，减少或替换合成添加剂和 E 编号成分。"),
    ("cost", "成本优先", "用低成本的成熟原料替代高价原料，同时保留关键工艺控制。"),
    ("stability", "稳定性优先", "强化抗氧化/抑菌/水分活度和热保护，适合长货架期。"),
    ("sensory", "感官优先", "强化脂肪、甜味、鲜味和质构，追求更接近目标产品的口感和风味。"),
    ("high_protein", "高蛋白", "增加优质蛋白来源并用水分/胶体平衡质构。"),
    ("low_sugar", "低糖", "降低可发酵糖和总糖，使用高倍甜味剂/纤维/水分复配。"),
    ("low_sodium", "低钠", "部分替代 NaCl，使用酸、鲜味、香辛料和钾盐补足风味。"),
    ("plant_based", "植物基", "去除动物源配料，使用植物蛋白、植物油脂和亲水胶体。"),
    ("fiber", "高纤", "增加可溶性/不溶性膳食纤维，兼顾质构和水分。"),
]


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12], 16)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _has(text: str, *words: str) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


_INGREDIENT_ALIASES = {
    "caffeine": ("咖啡因", "caffeine"),
    "tea_extract": ("茶提取物", "茶叶提取物", "绿茶提取物", "绿茶", "红茶", "tea extract", "green tea", "black tea"),
    "coffee_extract": ("咖啡提取物", "咖啡饮料", "coffee extract", "coffee"),
    "quercetin": ("槲皮素", "quercetin"),
    "whey_protein": ("乳清蛋白", "乳清分离蛋白", "whey protein", "whey"),
    "ascorbic_acid": ("维生素c", "维c", "抗坏血酸", "vitamin c", "ascorbic acid"),
    "phycocyanin": ("藻蓝蛋白", "藻蓝素", "phycocyanin"),
    "beta_carotene": ("β-胡萝卜素", "beta-carotene", "beta carotene"),
    "riboflavin": ("核黄素", "维生素b2", "riboflavin", "vitamin b2"),
    "anthocyanin": ("花青素", "anthocyanin", "anthocyanins"),
    "beet_extract": ("甜菜红", "甜菜根红", "beet extract", "beetroot red"),
    "cocoa_powder": ("可可粉", "cocoa powder"),
    "oats": ("燕麦", "oats", "oat"),
}


def _negated_ingredient(text: str, word: str) -> bool:
    lower = text.lower()
    needle = word.lower()
    for prefix in ("不含", "不加", "无", "without", "no ", "free of", "exclude "):
        start = 0
        while True:
            index = lower.find(prefix, start)
            if index < 0:
                break
            tail = lower[index:index + len(prefix) + len(needle) + 8]
            if needle in tail:
                return True
            start = index + len(prefix)
    return False


def _requested_ingredients(text: str) -> list[str]:
    lower = text.lower()
    found: list[tuple[int, str]] = []
    for item in data.ingredients():
        names = [item.get("id"), item.get("name"), item.get("cn_name")]
        names.extend(_INGREDIENT_ALIASES.get(str(item.get("id")), ()))
        best = 0
        for name in names:
            if not name or len(str(name)) < 2:
                continue
            needle = str(name).lower()
            if needle in lower and not _negated_ingredient(text, str(name)):
                best = max(best, len(needle))
        if best:
            found.append((best, str(item["id"])))
    found.sort(key=lambda pair: (-pair[0], pair[1]))
    return [item_id for _length, item_id in found[:4]]


def _quantity_near(text: str, keywords: tuple[str, ...]) -> tuple[float, str, str] | None:
    for keyword in keywords:
        patterns = (
            rf"([<>≤≥]=?)?\s*(\d+(?:\.\d+)?)\s*(%|mg|毫克|g|克)?\s*(?:of\s+)?{re.escape(keyword)}",
            rf"{re.escape(keyword)}\s*(?:content|level|含量|水平)?\s*(?:[：:=]|为|是)?\s*([<>≤≥]=?)?\s*(\d+(?:\.\d+)?)\s*(%|mg|毫克|g|克)?",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and (match.group(1) or match.group(3)):
                return float(match.group(2)), (match.group(3) or "").lower(), keyword
    return None


def _percent_value(value: float, unit: str) -> float:
    return value / 1000.0 if unit in {"mg", "毫克"} else value


def _sodium_mg(value: float, unit: str, keyword: str) -> float:
    if keyword == "盐":
        if unit in {"mg", "毫克"}:
            return value * 0.4
        if unit == "%":
            return value * 4000.0
        return value * 400.0
    if unit in {"mg", "毫克"}:
        return value
    if unit in {"g", "克"}:
        return value * 1000.0
    if unit == "%":
        return value * 1000.0
    return value * 1000.0 if value <= 5 else value


def detect_system(text: str, options: dict[str, Any] | None = None) -> str:
    options = options or {}
    if options.get("system_id"):
        return str(options["system_id"])
    best = (0, 0, "beverage_generic")
    lower = text.lower()
    for system_id, words in CATEGORY_WORDS.items():
        matched = [word for word in words if word.lower() in lower]
        hits = len(matched)
        specificity = sum(len(word) for word in matched)
        if (hits, specificity) > (best[0], best[1]):
            best = (hits, specificity, system_id)
    return best[2]


def parse_food_brief(query: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = dict(options or {})
    text = re.sub(r"\s+", " ", (query or "").strip())[:6000]
    system_id = detect_system(text, options)
    system = data.get_food_system(system_id)
    targets: dict[str, Any] = {
        "low_sugar": _has(text, "低糖", "减糖", "无糖", "低卡", "low sugar", "sugar reduced", "no sugar"),
        "high_protein": _has(text, "高蛋白", "蛋白质", "protein rich", "high protein"),
        "low_sodium": _has(text, "低钠", "减盐", "低盐", "low sodium", "reduced salt"),
        "low_fat": _has(text, "低脂", "减脂", "low fat"),
        "high_fiber": _has(text, "高纤", "纤维", "fiber", "fibre"),
        "clean_label": _has(text, "清洁标签", "无添加", "天然", "clean label", "no additives"),
        "gluten_free": _has(text, "无麸质", "gluten free", "gluten-free"),
        "soy_free": _has(text, "无大豆", "无豆", "soy free", "soy-free"),
        "dairy_free": _has(text, "无乳", "无奶", "乳糖不耐", "dairy free", "dairy-free", "non-dairy"),
        "vegan": _has(text, "纯素", "植物基", "vegan", "plant based", "plant-based"),
        "natural_color": _has(text, "天然色素", "无合成色素", "natural color", "natural colour"),
        "no_allergen": _has(text, "无过敏原", "过敏原", "allergen free", "allergen-free"),
        "long_shelf": _has(text, "长保质期", "长货架", "12 个月", "12个月", "18 个月", "long shelf"),
        "stability": _has(text, "稳定", "货架", "保质", "shelf life", "stability"),
        "cost_sensitive": _has(text, "低成本", "便宜", "成本", "low cost", "cheap"),
        "sensory_first": _has(text, "好吃", "口感", "风味", "sensory", "taste"),
        "juicy": _has(text, "多汁", "juicy"),
        "crisp": _has(text, "脆", "crisp", "crunchy"),
        "natural": _has(text, "天然", "natural"),
    }
    sugar = _quantity_near(text, ("糖", "sugar", "蔗糖"))
    sugar_reduction = None
    for pattern in (
        r"(?:糖|sugar)[^。；;\n]{0,12}?(?:降低|减少|减|lower|reduce|reduction)[^。；;\n]{0,12}?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:less|reduced|reduction|lower)\s+(?:sugar|糖)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            sugar_reduction = float(match.group(1))
            break
    protein = _quantity_near(text, ("蛋白质", "蛋白", "protein"))
    sodium = _quantity_near(text, ("钠", "sodium", "盐"))
    fiber = _quantity_near(text, ("膳食纤维", "纤维", "dietary fibre", "dietary fiber", "fiber", "fibre"))
    if sugar is not None:
        targets["sugar_max_pct"] = _percent_value(sugar[0], sugar[1])
        targets["low_sugar"] = True
    if protein is not None:
        targets["protein_min_pct"] = _percent_value(protein[0], protein[1])
        targets["high_protein"] = True
    if sodium is not None:
        targets["sodium_max_mg"] = _sodium_mg(*sodium)
        targets["low_sodium"] = True
    if fiber is not None:
        targets["fiber_min_pct"] = _percent_value(fiber[0], fiber[1])
        targets["high_fiber"] = True
    if sugar_reduction is not None:
        targets["sugar_reduction_pct"] = sugar_reduction
        targets["low_sugar"] = True
    if sugar is None and targets.get("sugar_reduction_pct"):
        targets["sugar_max_pct"] = 100.0
    else:
        targets["sugar_max_pct"] = float(options.get("sugar_max_pct", targets.get("sugar_max_pct", 5.0 if targets["low_sugar"] else 25.0)))
    targets["protein_min_pct"] = float(options.get("protein_min_pct", targets.get("protein_min_pct", 10.0 if targets["high_protein"] else 0.0)))
    targets["sodium_max_mg"] = float(options.get("sodium_max_mg", targets.get("sodium_max_mg", 400.0 if targets["low_sodium"] else 1200.0)))
    targets["fiber_min_pct"] = float(options.get("fiber_min_pct", targets.get("fiber_min_pct", 3.0 if targets["high_fiber"] else 0.0)))
    targets["shelf_days"] = int(options.get("shelf_days", 365 if targets["long_shelf"] else system["shelf_days"]))
    ph_match = re.search(r"pH\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    ph_range_match = re.search(r"pH\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[–—~-]|到|至)\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    temp_match = re.search(r"(\d+(?:\.\d+)?)\s*[°℃]\s*C", text, re.IGNORECASE)
    time_match = re.search(r"(\d+(?:\.\d+)?)\s*(秒|s|min|分钟)", text, re.IGNORECASE)
    targets["process_temp_c"] = float(options.get("process_temp_c", float(temp_match.group(1)) if temp_match else system["process_temp_c"]))
    if options.get("process_time_min") is not None:
        targets["process_time_min"] = float(options["process_time_min"])
    elif time_match:
        value = float(time_match.group(1))
        targets["process_time_min"] = value / 60.0 if time_match.group(2).lower() in {"秒", "s"} else value
    else:
        targets["process_time_min"] = float(system["process_time_min"])
    if ph_range_match:
        ph_low, ph_high = sorted((float(ph_range_match.group(1)), float(ph_range_match.group(2))))
        targets["ph_range"] = [ph_low, ph_high]
        targets["ph"] = float(options.get("ph", (ph_low + ph_high) / 2.0))
    else:
        targets["ph"] = float(options.get("ph", float(ph_match.group(1)) if ph_match else system["ph_target"]))
    reduce_match = re.search(r"(?:钠|盐)[^。；;\n]{0,10}?(?:降低|减少|减)\s*(\d+(?:\.\d+)?)\s*%", text)
    if reduce_match:
        targets["sodium_reduction_pct"] = float(reduce_match.group(1))
        base_sodium = sum(float(_nutrient(item_id).get("sodium_mg", 0.0)) * float(pct) / 100.0 for item_id, pct, _role in system["base_recipe"])
        targets["low_sodium"] = True
        targets["sodium_max_mg"] = round(base_sodium * (1.0 - float(reduce_match.group(1)) / 100.0), 1)
    color_words = {
        "藻蓝蛋白": "phycocyanin", "phycocyanin": "phycocyanin",
        "β-胡萝卜素": "beta_carotene", "胡萝卜素": "beta_carotene", "beta-carotene": "beta_carotene", "beta carotene": "beta_carotene",
        "花青素": "anthocyanin", "anthocyanin": "anthocyanin", "anthocyanins": "anthocyanin",
        "甜菜红": "beet_extract", "beetroot red": "beet_extract", "beet red": "beet_extract", "beet extract": "beet_extract",
        "核黄素": "riboflavin", "riboflavin": "riboflavin",
    }
    lower_text = text.lower()
    for word, item_id in color_words.items():
        if word.lower() in lower_text and not _negated_ingredient(text, word):
            targets["colorant_id"] = item_id
            targets["natural_color"] = True
            break
    targets["requested_ingredients"] = _requested_ingredients(text)
    retention_match = re.search(r"(?:保留率|保留|retention)[^。；;\n]{0,14}?(?:≥|>=|不低于|至少|at least)?\s*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    if not retention_match:
        retention_match = re.search(r"(\d+(?:\.\d+)?)\s*%[^。；;\n]{0,12}?(?:保留率|保留|retention)", text, re.IGNORECASE)
    if targets.get("colorant_id") and retention_match:
        targets["color_retention_min_pct"] = min(100.0, max(50.0, float(retention_match.group(1))))
    if "槲皮素" in text:
        targets["bioactive_id"] = "quercetin"
    if "燕麦" in text:
        targets["oat_base"] = True
    targets["cost_sensitive"] = bool(options.get("cost_sensitive", targets["cost_sensitive"]))
    targets["clean_label"] = bool(options.get("clean_label", targets["clean_label"]))
    targets["vegan"] = bool(options.get("vegan", targets["vegan"]))
    targets["dairy_free"] = bool(options.get("dairy_free", targets["dairy_free"]))
    targets["gluten_free"] = bool(options.get("gluten_free", targets["gluten_free"]))
    targets["soy_free"] = bool(options.get("soy_free", targets["soy_free"]))
    targets["no_allergen"] = bool(options.get("no_allergen", targets["no_allergen"]))
    targets["natural_color"] = bool(options.get("natural_color", targets["natural_color"]))
    priorities = {
        "stability": 0.30, "sensory": 0.20, "cost": 0.15, "nutrition": 0.20, "clean_label": 0.10, "process_fit": 0.05,
    }
    if targets["cost_sensitive"]:
        priorities["cost"] += 0.15
        priorities["sensory"] -= 0.05
    if targets["clean_label"] or targets["natural_color"]:
        priorities["clean_label"] += 0.20
        priorities["cost"] -= 0.05
    if targets["high_protein"] or targets["low_sugar"] or targets["low_sodium"]:
        priorities["nutrition"] += 0.10
        priorities["sensory"] -= 0.03
    if targets.get("stability"):
        priorities["stability"] += 0.10
    total = sum(max(0.0, value) for value in priorities.values())
    priorities = {key: max(0.0, value) / total for key, value in priorities.items()}
    warnings = []
    if targets["vegan"]:
        targets["dairy_free"] = True
    if system_id in {"meat_sausage", "dairy_milk", "dairy_yogurt", "bakery_bread", "bakery_cake"} and targets["vegan"]:
        warnings.append("植物基改造会显著改变质构、风味和工艺；基础模板中的动物源配料需要系统性替换。")
    if system_id == "fermented_vegetable":
        warnings.append("发酵蔬菜的微生物安全依赖盐度、厌氧和酸化曲线；本模型仅做配方筛选，不替代发酵验证。")
    if system_id == "meat_sausage":
        warnings.append("肉制品涉及致病菌、亚硝酸盐、冷链和热加工验证；本结果不是 HACCP 或法规批准。")
    if system_id == "powder_drink":
        warnings.append("固体饮料的剂量均匀度、溶解性和维生素降解需要中试验证。")
    if targets["natural_color"] and system_id in {"confectionery_gummy", "beverage_generic", "jelly"}:
        warnings.append("天然色素对 pH、热、光和氧敏感，需做加速褪色实验并选择避光包装。")
    if targets.get("color_retention_min_pct"):
        warnings.append(f"查询要求色素保留率 ≥ {targets['color_retention_min_pct']:g}%；本引擎仅做筛选级启发式估算，必须用加速褪色或货架期实测确认。")
    warnings.append("配方为数字原型；配料合法性、最大使用量、过敏原、标签和微生物安全必须按销售地法规与中试验证。")
    brief = {
        "query": text,
        "mode": "food_formulation",
        "language": "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en",
        "system_id": system_id,
        "system": system,
        "targets": targets,
        "priorities": priorities,
        "warnings": warnings,
        "assumptions": [
            f"产品体系识别为「{system['cn_name']}」；若识别错误，可在选项中指定 system_id。",
            "营养、pH、水分活度、稳定性和货架期为模板/组分先验估算，不是实测值。",
            "所有配料用量均为筛选起点；实际最大使用量以销售地现行法规为准。",
        ],
        "outputs": ["portfolio", "formulation", "interaction_graph", "process", "qc", "evidence", "compute_plan"],
    }
    return brief


def _ingredient_map() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in data.ingredients()}


def _role(item: dict[str, Any]) -> str:
    funcs = item.get("functions", [])
    return funcs[0] if funcs else item.get("category", "ingredient")


def _role_cn(role: str) -> str:
    return ROLE_CN.get(role, role)


def _is_animal(item: dict[str, Any]) -> bool:
    return item.get("id") in {
        "whey_protein", "casein", "milk_powder", "cream", "egg_white", "egg_yolk",
        "pork_lean", "beef_lean", "chicken_breast", "pork_fat", "gelatin", "fish_oil",
    }


def _allowed(item: dict[str, Any], targets: dict[str, Any]) -> bool:
    if targets.get("vegan") and _is_animal(item):
        return False
    if targets.get("dairy_free") and item.get("category") == "dairy":
        return False
    if targets.get("dairy_free") and item.get("id") in {"whey_protein", "casein", "milk_powder", "cream", "gelatin"}:
        return False
    if targets.get("gluten_free") and item.get("id") in {"wheat_flour", "wheat_gluten", "sourdough"}:
        return False
    if targets.get("soy_free") and item.get("id") in {"soy_protein", "lecithin"}:
        return False
    if targets.get("no_allergen") and item.get("allergen"):
        return False
    if targets.get("clean_label") and item.get("food_additive") and not item.get("clean_label"):
        return False
    return True


_SYSTEM_ALLOW = {
    "dairy": {"dairy", "protein", "sweetener", "hydrocolloid", "acidulant", "buffer", "preservative", "antioxidant", "colorant", "fiber", "stabilizer", "fruit", "flavor", "fat", "micronutrient"},
    "bakery": {"protein_carb", "protein", "dairy", "sweetener", "fat", "hydrocolloid", "fiber", "leavening", "microbial", "flavor", "colorant", "fruit", "enzyme", "antioxidant", "preservative"},
    "beverage": {"base", "sweetener", "acidulant", "buffer", "preservative", "antioxidant", "colorant", "flavor", "hydrocolloid", "protein", "fiber", "fruit", "botanical", "micronutrient", "dairy", "fat"},
    "confectionery": {"sweetener", "hydrocolloid", "acidulant", "colorant", "flavor", "fat", "protein", "dairy", "fiber", "emulsifier", "humectant", "bulking", "antioxidant"},
    "meat": {"meat", "fat", "protein", "hydrocolloid", "salt", "flavor", "acidulant", "preservative", "enzyme", "fiber", "micronutrient", "bulking"},
    "sauce": {"sweetener", "hydrocolloid", "acidulant", "salt", "flavor", "fat", "protein", "fiber", "colorant", "preservative", "emulsifier", "vegetable", "micronutrient"},
    "snack": {"protein_carb", "protein", "fat", "sweetener", "hydrocolloid", "fiber", "flavor", "salt", "colorant", "leavening", "dairy"},
    "frozen": {"dairy", "protein", "sweetener", "fat", "hydrocolloid", "emulsifier", "flavor", "colorant", "fruit", "fiber", "acidulant"},
    "powder": {"sweetener", "protein", "dairy", "hydrocolloid", "acidulant", "flavor", "colorant", "fiber", "micronutrient", "antioxidant", "fat"},
    "packaging": {"hydrocolloid", "protein", "fat", "fiber", "bulking"},
    "fermented": {"vegetable", "salt", "acidulant", "flavor", "microbial", "fiber", "hydrocolloid"},
}


def _system_allows(item: dict[str, Any], system: dict[str, Any] | None) -> bool:
    if not system:
        return True
    if item["id"] in _MEAT_IDS and system.get("category") != "meat":
        return False
    if item["id"] in {"mustard", "vinegar", "onion_powder", "garlic_powder"} and system.get("category") not in {"sauce", "meat", "snack"}:
        return False
    if item["id"] in {"cocoa_mass", "cocoa_butter", "cocoa_powder"} and system["id"] in {"confectionery_gummy", "jelly"}:
        return False
    if system["id"] == "plant_meat" and item["id"] in {"cocoa_mass", "cocoa_butter", "cocoa_powder", "honey"}:
        return False
    allowed = _SYSTEM_ALLOW.get(system.get("category"))
    return not allowed or item.get("category") in allowed


def _fit_score(item: dict[str, Any], role_words: tuple[str, ...], targets: dict[str, Any], system: dict[str, Any] | None = None) -> float:
    """Deterministic, inspectable ingredient ranking.

    The score is a screening preference, not a probability or a measurement.
    Hard legality/safety constraints are applied before this function.
    """
    funcs = set(item.get("functions", []))
    roles = set(role_words)
    score = 8.0 * len(roles & funcs)
    composition_row = composition.get(item["id"])
    nutrients = composition_row.get("nutrients", {})
    if targets.get("clean_label"):
        score += 3.0 if item.get("clean_label") and not item.get("food_additive") else -5.0
    if targets.get("cost_sensitive"):
        score += (6.0 - float(item.get("cost_index", 3))) * 0.7
    if targets.get("high_protein"):
        score += min(5.0, float(nutrients.get("protein_g", 0.0)) / 20.0)
    if targets.get("low_sugar"):
        score -= min(6.0, float(nutrients.get("sugar_g", 0.0)) / 20.0)
    if targets.get("low_sodium"):
        score -= min(6.0, float(nutrients.get("sodium_mg", 0.0)) / 8000.0)
    if targets.get("high_fiber"):
        score += min(3.0, float(nutrients.get("fiber_g", 0.0)) / 25.0)
    if targets.get("natural_color") and "colorant" in funcs:
        score += 1.0 if not item.get("food_additive") else -1.0
    ph = float(targets.get("ph", 7.0))
    if float(item.get("ph_min", 2.0)) <= ph <= float(item.get("ph_max", 9.0)):
        score += 0.7
    else:
        score -= 4.0
    temp = float(targets.get("process_temp_c", (system or {}).get("process_temp_c", 25.0)))
    if temp > float(item.get("max_process_temp_c", 250.0)):
        score -= 6.0
    if targets.get("no_allergen") and item.get("allergen"):
        score -= 20.0
    score += {"high": 1.5, "medium": 0.7, "low": 0.0}.get(composition_row.get("confidence", "low"), 0.0)
    if composition_row.get("source_type") == "usda_fdc_sr_legacy":
        score += 0.8
    return round(score, 4)


def _pick(pool: list[dict[str, Any]], role_words: tuple[str, ...], targets: dict[str, Any], rng: Any = None, exclude: set[str] | None = None, system: dict[str, Any] | None = None) -> dict[str, Any] | None:
    exclude = exclude or set()
    roles = set(role_words)
    candidates = []
    for item in pool:
        if item["id"] in exclude or not _allowed(item, targets) or not _system_allows(item, system):
            continue
        if roles & set(item.get("functions", [])):
            candidates.append((_fit_score(item, role_words, targets, system), item["id"], item))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return candidates[0][2] if candidates else None


def _choose(ids: list[str], targets: dict[str, Any], rng: Any = None, system: dict[str, Any] | None = None, exclude: set[str] | None = None) -> dict[str, Any] | None:
    exclude = exclude or set()
    candidates = []
    for item_id in ids:
        item = _ingredient_map().get(item_id)
        if not item or item_id in exclude:
            continue
        if _allowed(item, targets) and _system_allows(item, system):
            candidates.append((_fit_score(item, tuple(item.get("functions", [])), targets, system), item["id"], item))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return candidates[0][2] if candidates else None


def _protein_pick(system: dict[str, Any], targets: dict[str, Any], rng: Any = None, exclude: set[str] | None = None) -> dict[str, Any] | None:
    category = system.get("category")
    if category == "dairy":
        ids = ["whey_protein", "casein", "soy_protein", "pea_protein"]
    elif category == "bakery":
        ids = ["wheat_gluten", "soy_protein", "pea_protein", "egg_white", "whey_protein"]
    elif system.get("id") == "plant_meat":
        ids = ["pea_protein", "soy_protein", "wheat_gluten"]
    elif category in {"beverage", "confectionery", "frozen"}:
        ids = ["whey_protein", "soy_protein", "pea_protein"]
    else:
        ids = ["soy_protein", "pea_protein", "whey_protein", "casein", "egg_white", "wheat_gluten"]
    return _choose(ids, targets, rng, system, exclude)


_PLANT_ALT = {
    "milk_powder": ["soy_protein", "pea_protein"],
    "whey_protein": ["soy_protein", "pea_protein"],
    "casein": ["soy_protein", "pea_protein"],
    "cream": ["coconut_oil", "sunflower_oil"],
    "egg_white": ["soy_protein", "pea_protein"],
    "egg_yolk": ["soy_protein", "sunflower_oil"],
    "gelatin": ["pectin_lm", "agar"],
    "pork_lean": ["pea_protein", "soy_protein"],
    "beef_lean": ["pea_protein", "soy_protein"],
    "chicken_breast": ["pea_protein", "soy_protein"],
    "pork_fat": ["sunflower_oil", "coconut_oil"],
    "fish_oil": ["sunflower_oil", "canola_oil"],
}


def _plant_alt(item_id: str, targets: dict[str, Any], rng: Any = None, system: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return _choose(_PLANT_ALT.get(item_id, ["soy_protein", "pea_protein"]), targets, rng, system, {item_id})


def _adapt_base(system: dict[str, Any], targets: dict[str, Any], rng: Any = None) -> list[dict[str, Any]]:
    imap = _ingredient_map()
    recipe = []
    for item_id, pct, role in system["base_recipe"]:
        item = imap[item_id]
        if not _allowed(item, targets):
            if system.get("category") == "bakery" and targets.get("gluten_free"):
                if item_id == "wheat_flour":
                    recipe.append({"id": "rice_flour", "pct": round(float(pct) * 0.65, 3), "role": "structure"})
                    recipe.append({"id": "corn_starch", "pct": round(min(15.0, float(pct) * 0.15), 3), "role": "structure"})
                    recipe.append({"id": "pea_protein", "pct": round(float(pct) * 0.20, 3), "role": "protein"})
                    continue
                if item_id == "wheat_gluten":
                    recipe.append({"id": "pea_protein", "pct": round(float(pct), 3), "role": "protein"})
                    continue
                if item_id == "sourdough":
                    recipe.append({"id": "yeast", "pct": round(float(pct), 3), "role": "leavening"})
                    continue
            if item_id in {"wheat_flour", "wheat_gluten", "sourdough"}:
                replacement = _pick(data.ingredients(), ("structure", "bulking"), targets, rng, {"wheat_flour", "wheat_gluten", "sourdough"}, system)
                if replacement:
                    recipe.append({"id": replacement["id"], "pct": round(float(pct), 3), "role": "structure", "replaced": item_id})
                    continue
            if item_id in {"milk_powder", "cream", "whey_protein", "casein"}:
                if targets.get("oat_base") and system["id"] == "frozen_dessert":
                    if item_id == "cream":
                        recipe.append({"id": "coconut_oil", "pct": round(float(pct), 3), "role": "fat", "replaced": item_id})
                    else:
                        recipe.append({"id": "oats", "pct": round(float(pct), 3), "role": "solids", "replaced": item_id})
                    continue
                replacement = _protein_pick(system, targets, rng, {"milk_powder", "cream", "whey_protein", "casein"})
                if replacement:
                    recipe.append({"id": replacement["id"], "pct": round(float(pct), 3), "role": "protein", "replaced": item_id})
                    continue
            if item_id == "gelatin":
                replacement = _choose(["pectin_lm", "agar", "pectin_hm"], targets, rng, system, {"gelatin"})
                if replacement:
                    recipe.append({"id": replacement["id"], "pct": round(float(pct), 3), "role": "gelling", "replaced": item_id})
                    continue
            if item_id in {"soy_protein", "lecithin"}:
                replacement = _choose(["pea_protein", "soy_protein", "mono_diglyceride"], targets, rng, system, {"soy_protein", "lecithin"})
                if replacement:
                    recipe.append({"id": replacement["id"], "pct": round(float(pct), 3), "role": "protein", "replaced": item_id})
                    continue
            if item_id in {"pork_lean", "beef_lean", "chicken_breast", "pork_fat"}:
                replacement = _choose(["pea_protein", "soy_protein", "sunflower_oil"], targets, rng, system, {"pork_lean", "beef_lean", "chicken_breast", "pork_fat"})
                if replacement:
                    recipe.append({"id": replacement["id"], "pct": round(float(pct), 3), "role": "protein", "replaced": item_id})
                    continue
        recipe.append({"id": item_id, "pct": round(float(pct), 3), "role": role})
    if system.get("category") == "bakery" and targets.get("gluten_free") and system["id"] == "bakery_bread":
        recipe.append({"id": "xanthan", "pct": 0.4, "role": "hydrocolloid"})
    return _normalize(recipe)


def _normalize(recipe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in recipe:
        if item["pct"] <= 0:
            continue
        if item["id"] in merged:
            merged[item["id"]]["pct"] += item["pct"]
        else:
            merged[item["id"]] = {"id": item["id"], "pct": float(item["pct"]), "role": item.get("role", "ingredient")}
    total = sum(item["pct"] for item in merged.values())
    if total <= 0:
        return [{"id": "water", "pct": 100.0, "role": "continuous_phase"}]
    for item in merged.values():
        item["pct"] = round(item["pct"] * 100.0 / total, 3)
    return sorted(merged.values(), key=lambda item: -item["pct"])


def _add(recipe: list[dict[str, Any]], item: dict[str, Any], pct: float, targets: dict[str, Any], role: str | None = None) -> None:
    if not _allowed(item, targets):
        return
    existing = next((row for row in recipe if row["id"] == item["id"]), None)
    if existing is not None:
        existing["pct"] = round(existing["pct"] + pct, 3)
    else:
        recipe.append({"id": item["id"], "pct": round(max(0.001, pct), 3), "role": role or _role(item)})
    if item["id"] == "water":
        return
    water = next((row for row in recipe if row["id"] == "water"), None)
    if water is not None and water["id"] != item["id"]:
        water["pct"] = round(max(0.0, water["pct"] - pct), 3)
    else:
        donor = max((row for row in recipe if row["id"] != item["id"]), key=lambda row: row["pct"], default=None)
        if donor is not None:
            donor["pct"] = round(max(0.0, donor["pct"] - pct), 3)


def _reduce(recipe: list[dict[str, Any]], ids: set[str], factor: float) -> None:
    for row in recipe:
        if row["id"] in ids:
            row["pct"] = round(row["pct"] * factor, 3)


def _shift(recipe: list[dict[str, Any]], old: str, new_id: str, pct: float, targets: dict[str, Any]) -> None:
    row = next((item for item in recipe if item["id"] == old), None)
    replacement = _ingredient_map().get(new_id)
    if not row or not replacement or not _allowed(replacement, targets):
        return
    amount = min(float(pct), float(row["pct"]))
    if amount <= 0:
        return
    row["pct"] = round(float(row["pct"]) - amount, 3)
    _add(recipe, replacement, amount, targets, row.get("role"))
    if row["pct"] <= 0.001:
        recipe.remove(row)


def _replace(recipe: list[dict[str, Any]], old: str, new_id: str, targets: dict[str, Any]) -> None:
    item = next((row for row in recipe if row["id"] == old), None)
    if not item:
        return
    replacement = _ingredient_map().get(new_id)
    if not replacement or not _allowed(replacement, targets):
        return
    _add(recipe, replacement, item["pct"], targets, item.get("role"))
    recipe.remove(item)


def _fiber_pct(recipe: list[dict[str, Any]]) -> float:
    total = sum(float(row.get("pct", 0.0)) for row in recipe)
    if total <= 0:
        return 0.0
    fiber = sum(float(_nutrient(row["id"]).get("fiber", 0.0)) * float(row.get("pct", 0.0)) / 100.0 for row in recipe)
    return fiber * 100.0 / total


def _sugar_pct(recipe: list[dict[str, Any]]) -> float:
    total = sum(float(row.get("pct", 0.0)) for row in recipe)
    if total <= 0:
        return 0.0
    sugar = sum(float(_nutrient(row["id"]).get("sugar", 0.0)) * float(row.get("pct", 0.0)) / 100.0 for row in recipe)
    return sugar * 100.0 / total


def _strategy_recipe(system: dict[str, Any], targets: dict[str, Any], strategy: str, rng: Any = None) -> list[dict[str, Any]]:
    recipe = _adapt_base(system, targets, rng)
    pool = data.ingredients()
    imap = _ingredient_map()
    for requested_id in targets.get("requested_ingredients") or []:
        item = imap.get(str(requested_id))
        if not item or not _allowed(item, targets):
            continue
        typical = item.get("typical_pct") or [0.01, 0.1]
        upper = float(typical[1]) if isinstance(typical, (list, tuple)) and len(typical) > 1 else 0.1
        if requested_id == "whey_protein":
            upper = max(3.0, min(12.0, upper))
        elif requested_id == "tea_extract":
            upper = max(0.5, min(2.0, upper))
        elif requested_id == "caffeine":
            upper = max(0.03, min(0.1, upper))
        _add(recipe, item, upper, targets, _role(item))
    if strategy == "clean_label" or targets.get("clean_label"):
        for row in list(recipe):
            item = _ingredient_map()[row["id"]]
            if item.get("food_additive") and not item.get("clean_label"):
                alt = _pick(pool, tuple(item.get("functions", [])), {**targets, "clean_label": True}, rng, system=system)
                if alt and alt["id"] != item["id"]:
                    _replace(recipe, item["id"], alt["id"], targets)
    if strategy == "cost" or targets.get("cost_sensitive"):
        for old, new in (("trehalose", "sucrose"), ("whey_protein", "soy_protein"), ("vanilla", "flavor"), ("cocoa_butter", "sunflower_oil")):
            if any(row["id"] == old for row in recipe) and new not in {row["id"] for row in recipe}:
                _replace(recipe, old, new, targets)
    if strategy == "stability":
        for role, pct in (("antioxidant", 0.03), ("preservative", 0.05), ("humectant", 0.8)):
            exclude = set(_COLORANT_IDS) if targets.get("colorant_id") else set()
            if targets.get("colorant_id") == "phycocyanin":
                exclude.add("ascorbic_acid")
            item = _pick(pool, (role,), targets, rng, exclude=exclude or None, system=system)
            if item:
                _add(recipe, item, pct, targets, role)
    if strategy == "sensory" or targets.get("sensory_first"):
        sensory_roles = [("flavor", 0.12), ("fat", 0.8), ("sweetener", 0.5)]
        if system.get("category") == "beverage":
            sensory_roles = [("flavor", 0.12), ("sweetener", 0.5)]
        for role, pct in sensory_roles:
            exclude = {"cocoa_powder", "cocoa_mass"} if system.get("category") == "beverage" else None
            item = _pick(pool, (role,), targets, rng, exclude=exclude, system=system)
            if item:
                _add(recipe, item, pct, targets, role)
    if targets.get("high_protein") or strategy == "high_protein":
        need = targets.get("protein_min_pct", 10.0)
        item = _protein_pick(system, targets, rng)
        if item:
            current = _metrics(recipe, system, targets, {"priorities": {"stability": 1, "sensory": 0, "cost": 0, "nutrition": 0, "clean_label": 0, "process_fit": 0}})["protein_pct"]
            protein_density = max(20.0, float(_nutrient(item["id"]).get("protein", 50.0)))
            add = min(18.0, max(1.0, (need - current) / protein_density * 100.0))
            _add(recipe, item, add, targets, "protein")
    if targets.get("low_sugar") or strategy == "low_sugar":
        _reduce(recipe, {"sucrose", "glucose", "fructose", "glucose_syrup", "honey", "molasses"}, 0.45)
        milk = next((row for row in recipe if row["id"] == "milk_powder"), None)
        if milk and system["id"] in {"dairy_yogurt", "dairy_drink", "ice_cream"}:
            _shift(recipe, "milk_powder", "whey_protein", float(milk["pct"]) * 0.75, targets)
        for sweetener in ("reb_a", "erythritol", "inulin"):
            item = _ingredient_map().get(sweetener)
            if item and _allowed(item, targets):
                _add(recipe, item, 1.2 if sweetener != "reb_a" else 0.03, targets, "sweetener")
        if system["id"] == "powder_drink":
            for old, new, factor in (("sucrose", "erythritol", 0.9), ("maltodextrin", "inulin", 0.7)):
                row = next((entry for entry in recipe if entry["id"] == old), None)
                if row:
                    _shift(recipe, old, new, float(row["pct"]) * factor, targets)
            _add(recipe, _ingredient_map().get("reb_a"), 0.05, targets, "high_intensity_sweetener")
        sugar_target = float(targets.get("sugar_max_pct", 0.0) or 0.0)
        sugar_ids = {"sucrose", "glucose", "fructose", "glucose_syrup", "honey", "molasses"}
        if sugar_target > 0 and sugar_target < 100:
            for _ in range(40):
                if _sugar_pct(recipe) <= sugar_target - 0.05:
                    break
                row = max((entry for entry in recipe if entry["id"] in sugar_ids), key=lambda entry: float(entry["pct"]), default=None)
                if row is None or float(row["pct"]) <= 0.1:
                    break
                row["pct"] = round(float(row["pct"]) - 0.1, 3)
    if targets.get("low_sodium") or strategy == "low_sodium":
        _reduce(recipe, {"sodium_chloride"}, 0.6)
        salt_replacer = _ingredient_map().get("potassium_chloride")
        if salt_replacer and _allowed(salt_replacer, targets):
            _add(recipe, salt_replacer, 0.35, targets, "salt")
        for flavor_id in ("onion_powder", "garlic_powder", "vinegar", "citric_acid"):
            if flavor_id == "vinegar" and system.get("category") in {"bakery", "dairy", "frozen", "confectionery"}:
                continue
            if flavor_id.endswith("powder") and system.get("category") not in {"sauce", "meat", "snack"}:
                continue
            item = _ingredient_map().get(flavor_id)
            if item and _allowed(item, targets):
                _add(recipe, item, 0.12 if flavor_id.endswith("powder") else 0.2, targets, "flavor")
    if targets.get("high_fiber") or strategy == "fiber":
        item = _pick(pool, ("fiber", "prebiotic"), targets, rng, system=system)
        if item:
            target_fiber = float(targets.get("fiber_min_pct", 0.0) or 0.0)
            if target_fiber > 0:
                for _ in range(24):
                    if _fiber_pct(recipe) >= target_fiber + 0.02:
                        break
                    _add(recipe, item, 0.5, targets, "fiber")
            else:
                _add(recipe, item, 2.5, targets, "fiber")
    if targets.get("vegan") or strategy == "plant_based":
        for row in list(recipe):
            item = _ingredient_map()[row["id"]]
            if _is_animal(item):
                alt = _plant_alt(item["id"], targets, rng, system)
                if alt:
                    _replace(recipe, item["id"], alt["id"], targets)
    if targets.get("natural_color") or (strategy == "clean_label" and system["id"] in {"confectionery_gummy", "beverage_generic", "jelly"}):
        for row in list(recipe):
            item = _ingredient_map()[row["id"]]
            if item.get("id") in {"riboflavin", "sucralose"}:
                alt = _ingredient_map().get("beta_carotene") if item.get("id") == "riboflavin" else _ingredient_map().get("reb_a")
                if alt and _allowed(alt, targets):
                    _replace(recipe, item["id"], alt["id"], targets)
    colorant_id = targets.get("colorant_id")
    if colorant_id:
        item = _ingredient_map().get(colorant_id)
        if item and _allowed(item, targets):
            _add(recipe, item, 0.15 if system.get("category") == "beverage" else 0.25, targets, "color")
            if colorant_id == "phycocyanin":
                trehalose = _ingredient_map().get("trehalose")
                citrate = _ingredient_map().get("sodium_citrate")
                if trehalose and _allowed(trehalose, targets):
                    _add(recipe, trehalose, 3.0 if strategy == "stability" else 2.0, targets, "thermoprotectant")
                if citrate and _allowed(citrate, targets):
                    _add(recipe, citrate, 0.15, targets, "chelator")
    elif targets.get("natural_color") and system.get("category") in {"confectionery", "beverage"}:
        item = _ingredient_map().get("beet_extract" if system.get("category") == "confectionery" else "anthocyanin")
        if item and _allowed(item, targets):
            _add(recipe, item, 0.2, targets, "color")
    if targets.get("bioactive_id"):
        item = _ingredient_map().get(targets["bioactive_id"])
        if item and _allowed(item, targets):
            _add(recipe, item, 0.05, targets, "bioactive")
    if targets.get("oat_base") and system["id"] in {"dairy_milk", "frozen_dessert"}:
        item = _ingredient_map().get("oats")
        if item and _allowed(item, targets):
            _add(recipe, item, 5.0, targets, "base")
    if system["id"] in {"bakery_bread", "bakery_cake"} and strategy in {"stability", "sensory", "balanced"}:
        item = _pick(pool, ("humectant", "fat"), targets, rng, system=system)
        if item:
            _add(recipe, item, 0.6, targets, "humectant")
    if system["id"] in {"plant_meat", "meat_sausage"} and strategy in {"sensory", "stability", "balanced"}:
        item = _pick(pool, ("binder", "protein_crosslink"), targets, rng, system=system)
        if item:
            _add(recipe, item, 0.6, targets, "binder")
    return _normalize(recipe)


def _nutrient(item_id: str) -> dict[str, float]:
    from . import composition
    return composition.nutrients(item_id)


def _legacy_nutrient_values(item_id: str) -> dict[str, float]:
    values = {
        "soy_protein": {"protein": 90, "fat": 4, "sugar": 0, "fiber": 1},
        "pea_protein": {"protein": 82, "fat": 2, "sugar": 0, "fiber": 2},
        "whey_protein": {"protein": 90, "fat": 1, "sugar": 1, "fiber": 0},
        "casein": {"protein": 80, "fat": 1, "sugar": 0, "fiber": 0},
        "milk_powder": {"protein": 34, "fat": 27, "sugar": 38, "fiber": 0},
        "cream": {"protein": 2, "fat": 35, "sugar": 3, "fiber": 0},
        "egg_white": {"protein": 85, "fat": 0, "sugar": 1, "fiber": 0},
        "egg_yolk": {"protein": 16, "fat": 30, "sugar": 3, "fiber": 0},
        "pork_lean": {"protein": 21, "fat": 8, "sugar": 0, "fiber": 0},
        "beef_lean": {"protein": 22, "fat": 7, "sugar": 0, "fiber": 0},
        "chicken_breast": {"protein": 23, "fat": 2, "sugar": 0, "fiber": 0},
        "pork_fat": {"protein": 5, "fat": 90, "sugar": 0, "fiber": 0},
        "gelatin": {"protein": 85, "fat": 0, "sugar": 0, "fiber": 0},
        "wheat_flour": {"protein": 12, "fat": 2, "sugar": 1, "fiber": 3},
        "oat_flour": {"protein": 13, "fat": 7, "sugar": 1, "fiber": 10},
        "rice_flour": {"protein": 7, "fat": 1, "sugar": 0, "fiber": 2},
        "corn_flour": {"protein": 7, "fat": 3, "sugar": 1, "fiber": 3},
        "oats": {"protein": 13, "fat": 7, "sugar": 1, "fiber": 10},
        "wheat_gluten": {"protein": 75, "fat": 2, "sugar": 1, "fiber": 1},
        "sucrose": {"protein": 0, "fat": 0, "sugar": 100, "fiber": 0},
        "glucose": {"protein": 0, "fat": 0, "sugar": 100, "fiber": 0},
        "fructose": {"protein": 0, "fat": 0, "sugar": 100, "fiber": 0},
        "glucose_syrup": {"protein": 0, "fat": 0, "sugar": 80, "fiber": 0},
        "honey": {"protein": 0, "fat": 0, "sugar": 80, "fiber": 0},
        "maltodextrin": {"protein": 0, "fat": 0, "sugar": 5, "fiber": 0},
        "inulin": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 90},
        "pectin_hm": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 85},
        "pectin_lm": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 85},
        "xanthan": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 80},
        "guar": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 80},
        "carrageenan": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 80},
        "agar": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 80},
        "sodium_chloride": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 39000},
        "potassium_chloride": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 0},
        "sodium_citrate": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 23000},
        "sodium_benzoate": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 16000},
        "baking_soda": {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 27000},
        "cocoa_mass": {"protein": 13, "fat": 52, "sugar": 0, "fiber": 12},
        "cocoa_powder": {"protein": 20, "fat": 13, "sugar": 0, "fiber": 30},
        "cocoa_butter": {"protein": 0, "fat": 100, "sugar": 0, "fiber": 0},
    }
    return values.get(item_id, {"protein": 0, "fat": 0, "sugar": 0, "fiber": 0, "sodium_mg": 0})


def _color_retention(recipe: list[dict[str, Any]], system: dict[str, Any], targets: dict[str, Any]) -> tuple[float | None, str | None]:
    by_id = {row["id"]: float(row["pct"]) for row in recipe}
    colorant_id = targets.get("colorant_id")
    if not colorant_id:
        colorant_id = next((item_id for item_id in _COLORANT_IDS if item_id in by_id), None)
    if not colorant_id:
        return None, None
    ph = float(targets.get("ph", system["ph_target"]))
    temp = float(targets.get("process_temp_c", system["process_temp_c"]))
    minutes = float(targets.get("process_time_min", system["process_time_min"]))
    trehalose = by_id.get("trehalose", 0.0)
    citrate = by_id.get("sodium_citrate", 0.0)
    tocopherol = by_id.get("tocopherol", 0.0)
    if colorant_id == "phycocyanin":
        retention = 96.0
        retention -= max(0.0, 5.0 - ph) * 9.0
        retention -= max(0.0, temp - 65.0) * 0.9
        retention -= max(0.0, minutes - 1.0) * 0.8
        retention -= 4.0 if "citric_acid" in by_id else 0.0
        retention -= 4.0
        retention += min(9.0, trehalose * 3.0)
        retention += min(2.0, citrate * 4.0)
        basis = "筛选级启发式：pH、巴氏温度/时间、柠檬酸、光照/氧，以及海藻糖/柠檬酸盐保护上限"
    elif colorant_id == "anthocyanin":
        retention = 94.0 - max(0.0, ph - 4.0) * 6.0 - max(0.0, temp - 90.0) * 0.5 - 3.0
        retention += min(4.0, trehalose * 2.0) + min(2.0, citrate * 4.0)
        basis = "筛选级启发式：pH、温度、光照/氧，以及海藻糖/柠檬酸盐保护上限"
    elif colorant_id == "beta_carotene":
        retention = 94.0 - max(0.0, temp - 95.0) * 0.35 - 5.0 + min(3.0, tocopherol * 10.0) + min(2.0, trehalose * 1.5)
        basis = "筛选级启发式：温度、光照/氧和生育酚保护上限"
    elif colorant_id == "beet_extract":
        retention = 93.0 - max(0.0, temp - 80.0) * 0.6 - 3.0 + min(4.0, trehalose * 2.0)
        basis = "筛选级启发式：温度、光照/氧和海藻糖保护上限"
    else:
        retention = 95.0 - (8.0 if "clear" in str(system.get("packaging", "")).lower() else 3.0)
        basis = "筛选级启发式：包装透光和维生素光敏性"
    return round(max(0.0, min(100.0, retention)), 1), basis


def _metrics(recipe: list[dict[str, Any]], system: dict[str, Any], targets: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    imap = _ingredient_map()
    nutrients = {"protein": 0.0, "fat": 0.0, "sugar": 0.0, "fiber": 0.0, "sodium_mg": 0.0}
    for row in recipe:
        n = _nutrient(row["id"])
        factor = float(row["pct"]) / 100.0
        nutrients["protein"] += n.get("protein", 0.0) * factor
        nutrients["fat"] += n.get("fat", 0.0) * factor
        nutrients["sugar"] += n.get("sugar", 0.0) * factor
        nutrients["fiber"] += n.get("fiber", 0.0) * factor
        nutrients["sodium_mg"] += n.get("sodium_mg", 0.0) * factor
    aw_mid = (float(system["water_activity"][0]) + float(system["water_activity"][1])) / 2.0
    aw = aw_mid
    for row in recipe:
        item = imap[row["id"]]
        aw -= float(item.get("aw_effect", 0.0)) * min(1.0, float(row["pct"]) / max(1.0, float(item.get("max_pct", 30.0))))
    aw = _clamp(aw, 0.20, 0.995)
    acid_strength = {
        "citric_acid": 0.16, "malic_acid": 0.14, "lactic_acid": 0.10, "acetic_acid": 0.13,
        "vinegar": 0.10, "tomato_paste": 0.03, "orange_juice_concentrate": 0.03, "sourdough": 0.03,
    }
    buffer_strength = {"sodium_citrate": 0.05, "calcium_lactate": 0.02, "baking_soda": 0.08}
    acid_load = sum(acid_strength.get(row["id"], 0.0) * float(row["pct"]) for row in recipe)
    buffer_load = sum(buffer_strength.get(row["id"], 0.0) * float(row["pct"]) for row in recipe)
    base_acid = sum(acid_strength.get(item_id, 0.0) * float(pct) for item_id, pct, _role in system["base_recipe"])
    base_buffer = sum(buffer_strength.get(item_id, 0.0) * float(pct) for item_id, pct, _role in system["base_recipe"])
    target_ph = float(targets.get("ph", system["ph_target"]))
    ph = target_ph - (acid_load - base_acid) * 0.06 + (buffer_load - base_buffer) * 0.04
    ph = _clamp(ph, max(2.0, float(system["ph_range"][0]) - 0.3), min(9.0, float(system["ph_range"][1]) + 0.3))
    heat_sensitive = []
    for row in recipe:
        item = imap[row["id"]]
        if item["id"] in {"yeast", "sourdough", "transglutaminase"}:
            continue
        if float(targets.get("process_temp_c", system["process_temp_c"])) > float(item.get("max_process_temp_c", 250.0)):
            heat_sensitive.append(item["cn_name"])
    ph_mismatch = []
    for row in recipe:
        item = imap[row["id"]]
        if ph < float(item.get("ph_min", 2.0)) - 0.25 or ph > float(item.get("ph_max", 9.0)) + 0.25:
            ph_mismatch.append(item["cn_name"])
    positive = []
    negative = []
    interactions = data.food_interactions()
    by_id = {row["id"]: row for row in recipe}
    for ix in interactions:
        if ix["a"] in by_id and ix["b"] in by_id:
            scale = min(1.0, (float(by_id[ix["a"]]["pct"]) + float(by_id[ix["b"]]["pct"])) / 8.0)
            record = {
                "id": ix["id"], "a": ix["a"], "b": ix["b"], "a_cn": imap[ix["a"]]["cn_name"], "b_cn": imap[ix["b"]]["cn_name"],
                "type": ix["type"], "effect": round(float(ix["effect"]) * max(0.15, scale), 4),
                "mechanism_cn": ix["mechanism_cn"], "evidence": ix.get("evidence", ""), "confidence": ix.get("confidence", "medium"),
            }
            if record["effect"] >= 0:
                positive.append(record)
            else:
                negative.append(record)
    interaction_score = _clamp(0.55 + sum(x["effect"] for x in positive) * 1.2 + sum(x["effect"] for x in negative) * 1.6)
    colorants = [row["id"] for row in recipe if row["id"] in {"anthocyanin", "beta_carotene", "riboflavin", "phycocyanin", "beet_extract"}]
    color_risk = 0.0
    if "anthocyanin" in colorants:
        color_risk += max(0.0, ph - 4.0) * 0.08 + (0.10 if system["storage_temp_c"] > 20 else 0.0)
    if "phycocyanin" in colorants:
        color_risk += max(0.0, 5.0 - ph) * 0.08 + max(0.0, float(targets.get("process_temp_c", system["process_temp_c"])) - 70.0) * 0.006
    if "riboflavin" in colorants:
        color_risk += 0.06 if "clear" in str(system.get("packaging", "")).lower() else 0.02
    color_retention_pct, color_retention_basis = _color_retention(recipe, system, targets)
    preservatives = sum(1 for row in recipe if "preservative" in imap[row["id"]].get("functions", []))
    antioxidants = sum(1 for row in recipe if "antioxidant" in imap[row["id"]].get("functions", []))
    microbial_risk = 0.0
    if aw > 0.90 and ph > 4.6:
        microbial_risk += 0.18
    if aw > 0.90 and ph > 4.6 and preservatives == 0:
        microbial_risk += 0.20
    if system["category"] in {"meat", "dairy"} and targets.get("process_temp_c", system["process_temp_c"]) < 90:
        microbial_risk += 0.12
    if system["category"] == "fermented":
        microbial_risk += 0.10
    thermal_risk = 0.18 * len(heat_sensitive) + max(0.0, float(targets.get("process_temp_c", system["process_temp_c"])) - 100.0) * 0.002
    stability = _clamp(0.92 - thermal_risk - color_risk - microbial_risk + interaction_score * 0.12 - len(ph_mismatch) * 0.02)
    allergen_count = sum(1 for row in recipe if imap[row["id"]].get("allergen"))
    additive_count = sum(1 for row in recipe if imap[row["id"]].get("food_additive"))
    clean_fraction = sum(1 for row in recipe if imap[row["id"]].get("clean_label")) / max(1, len(recipe))
    nutrition = 0.55
    if targets.get("high_protein"):
        nutrition = _clamp(0.35 + nutrients["protein"] / max(1.0, targets.get("protein_min_pct", 10.0)) * 0.65)
    if targets.get("low_sugar"):
        nutrition = min(nutrition, _clamp(0.9 - max(0.0, nutrients["sugar"] - targets.get("sugar_max_pct", 5.0)) * 0.04))
    if targets.get("low_sodium"):
        nutrition = min(nutrition, _clamp(0.9 - max(0.0, nutrients["sodium_mg"] - targets.get("sodium_max_mg", 400.0)) / 1200.0))
    if targets.get("high_fiber"):
        nutrition = min(1.0, nutrition + nutrients["fiber"] * 0.015)
    if targets.get("no_allergen") and allergen_count:
        nutrition *= 0.55
    sensory = 0.62
    sensory += min(0.12, nutrients["fat"] * 0.006)
    sensory += min(0.10, nutrients["sugar"] * 0.004)
    if targets.get("low_sugar"):
        sensory -= max(0.0, nutrients["sugar"] - 8.0) * 0.004
    if targets.get("low_sodium"):
        sensory -= max(0.0, nutrients["sodium_mg"] - 500.0) / 5000.0
    if "flavor" in {_role(imap[row["id"]]) for row in recipe}:
        sensory += 0.05
    if any("gelling" in imap[row["id"]].get("functions", []) for row in recipe):
        sensory += 0.03
    sensory = _clamp(sensory)
    cost_values = [float(imap[row["id"]].get("cost_index", 3)) * float(row["pct"]) / 100.0 for row in recipe]
    cost = _clamp(1.0 - sum(cost_values) / 5.0 * 1.25)
    process_fit = _clamp(1.0 - 0.16 * len(heat_sensitive) - 0.08 * len(ph_mismatch))
    weights = brief["priorities"]
    overall = (
        weights["stability"] * stability + weights["sensory"] * sensory + weights["cost"] * cost
        + weights["nutrition"] * nutrition + weights["clean_label"] * clean_fraction + weights["process_fit"] * process_fit
    )
    if targets.get("clean_label"):
        overall *= 0.75 + 0.25 * clean_fraction
    if targets.get("no_allergen") and allergen_count:
        overall *= 0.6
    if targets.get("high_protein") and nutrients["protein"] < targets.get("protein_min_pct", 0):
        overall *= 0.7
    if targets.get("low_sugar") and nutrients["sugar"] > targets.get("sugar_max_pct", 100):
        overall *= 0.75
    if targets.get("low_sodium") and nutrients["sodium_mg"] > targets.get("sodium_max_mg", 99999):
        overall *= 0.75
    return {
        "overall_score": round(_clamp(overall), 4),
        "stability": round(stability, 4), "sensory": round(sensory, 4), "cost": round(cost, 4),
        "nutrition": round(nutrition, 4), "clean_label": round(clean_fraction, 4), "process_fit": round(process_fit, 4),
        "interaction": round(interaction_score, 4),
        "ph": round(ph, 2), "aw": round(aw, 3),
        "protein_pct": round(nutrients["protein"], 2), "fat_pct": round(nutrients["fat"], 2),
        "sugar_pct": round(nutrients["sugar"], 2), "fiber_pct": round(nutrients["fiber"], 2),
        "sodium_mg": round(nutrients["sodium_mg"], 1),
        "allergens": sorted({imap[row["id"]].get("name") for row in recipe if imap[row["id"]].get("allergen")}),
        "additives": sorted({imap[row["id"]].get("e_number") or imap[row["id"]].get("name") for row in recipe if imap[row["id"]].get("food_additive")}),
        "heat_sensitive": heat_sensitive, "ph_mismatch": ph_mismatch,
        "positive_interactions": sorted(positive, key=lambda x: x["effect"], reverse=True)[:8],
        "negative_interactions": sorted(negative, key=lambda x: x["effect"])[:8],
        "interaction_net": round(sum(x["effect"] for x in positive) + sum(x["effect"] for x in negative), 4),
        "color_risk": round(color_risk, 4), "microbial_risk": round(microbial_risk, 4), "thermal_risk": round(thermal_risk, 4),
        "color_retention_pct": color_retention_pct, "color_retention_basis": color_retention_basis,
        "preservative_count": preservatives, "antioxidant_count": antioxidants,
    }


def _intervals(metrics: dict[str, Any], comp_summary: dict[str, Any]) -> dict[str, Any]:
    mapped = float(comp_summary.get("mapped_mass_pct", 0.0))
    comp_rel = 0.08 if mapped >= 70 else 0.15
    def rel(value: float, fraction: float) -> list[float]:
        return [round(value * (1.0 - fraction), 3), round(value * (1.0 + fraction), 3)]
    return {
        "protein_pct": rel(metrics["protein_pct"], comp_rel),
        "fat_pct": rel(metrics["fat_pct"], comp_rel),
        "sugar_pct": rel(metrics["sugar_pct"], comp_rel),
        "fiber_pct": rel(metrics["fiber_pct"], min(0.25, comp_rel + 0.05)),
        "sodium_mg": rel(metrics["sodium_mg"], comp_rel),
        "ph": [round(max(2.0, metrics["ph"] - 0.30), 2), round(min(9.0, metrics["ph"] + 0.30), 2)],
        "aw": [round(max(0.20, metrics["aw"] - 0.03), 3), round(min(0.995, metrics["aw"] + 0.03), 3)],
        "color_retention_pct": [round(max(0.0, float(metrics.get("color_retention_pct") or 0.0) - 8.0), 1), round(min(100.0, float(metrics.get("color_retention_pct") or 0.0) + 8.0), 1)] if metrics.get("color_retention_pct") is not None else None,
        "stability": [round(max(0.0, metrics["stability"] - 0.15), 3), round(min(1.0, metrics["stability"] + 0.15), 3)],
        "basis": "Assumed screening uncertainty, not a confidence interval from experiments.",
        "composition_relative_uncertainty": comp_rel,
        "mapped_mass_pct": mapped,
    }


def _constraint_report(system: dict[str, Any], targets: dict[str, Any], metrics: dict[str, Any], intervals: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    def add(identifier: str, label: str, value: Any, limit: Any, unit: str, kind: str, interval: list[float] | None = None) -> None:
        status = "pass"
        if kind == "min":
            if value < limit:
                status = "fail"
            elif interval and interval[0] < limit:
                status = "at_risk"
        elif kind == "max":
            if value > limit:
                status = "fail"
            elif interval and interval[1] > limit:
                status = "at_risk"
        elif kind == "range":
            low, high = limit
            if value < low or value > high:
                status = "fail"
            elif interval and (interval[0] < low or interval[1] > high):
                status = "at_risk"
        rows.append({
            "id": identifier, "label": label, "value": value, "limit": limit,
            "unit": unit, "kind": kind, "status": status, "interval": interval,
            "basis": "point estimate and assumed screening interval",
        })
    if targets.get("high_protein"):
        add("protein_min", "蛋白质下限", metrics["protein_pct"], float(targets.get("protein_min_pct", 10.0)), "%", "min", intervals["protein_pct"])
    if targets.get("low_sugar") and float(targets.get("sugar_max_pct", 100.0)) < 100:
        add("sugar_max", "糖上限", metrics["sugar_pct"], float(targets.get("sugar_max_pct", 5.0)), "%", "max", intervals["sugar_pct"])
    if targets.get("low_sodium"):
        add("sodium_max", "钠上限", metrics["sodium_mg"], float(targets.get("sodium_max_mg", 400.0)), "mg/100g", "max", intervals["sodium_mg"])
    if targets.get("fiber_min_pct"):
        add("fiber_min", "膳食纤维下限", metrics["fiber_pct"], float(targets.get("fiber_min_pct", 3.0)), "%", "min", intervals["fiber_pct"])
    if targets.get("color_retention_min_pct") is not None and metrics.get("color_retention_pct") is not None:
        add("color_retention_min", "色素保留率", metrics["color_retention_pct"], float(targets["color_retention_min_pct"]), "%", "min", intervals["color_retention_pct"])
    add("ph_window", "体系 pH 窗口", metrics["ph"], list(system["ph_range"]), "", "range", intervals["ph"])
    if targets.get("ph_range"):
        add("ph_target", "目标 pH 窗口", metrics["ph"], list(targets["ph_range"]), "", "range", intervals["ph"])
    if targets.get("no_allergen"):
        rows.append({"id": "allergen_free", "label": "无过敏原", "value": metrics["allergens"], "limit": [], "unit": "", "kind": "boolean", "status": "pass" if not metrics["allergens"] else "fail", "interval": None, "basis": "ingredient allergen flags"})
    if targets.get("gluten_free"):
        rows.append({"id": "gluten_free", "label": "无麸质", "value": True, "limit": True, "unit": "", "kind": "boolean", "status": "pass", "interval": None, "basis": "ingredient allow-list; cross-contact not assessed"})
    if targets.get("soy_free"):
        rows.append({"id": "soy_free", "label": "无大豆", "value": True, "limit": True, "unit": "", "kind": "boolean", "status": "pass", "interval": None, "basis": "ingredient allow-list"})
    if targets.get("dairy_free"):
        rows.append({"id": "dairy_free", "label": "无乳", "value": True, "limit": True, "unit": "", "kind": "boolean", "status": "pass", "interval": None, "basis": "ingredient allow-list"})
    return rows


def _metric_provenance(comp_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "metric": "蛋白质/脂肪/糖/纤维/钠",
            "method": "质量加权求和：Σ(配料占比_i/100 × 每 100 g 配料营养素_i)",
            "source": f"配方质量的 {comp_summary.get('mapped_mass_pct', 0)}% 来自 USDA FDC SR Legacy，其余为 curated estimate",
            "evidence_tier": "B/C",
            "confidence": "medium" if comp_summary.get("mapped_mass_pct", 0) >= 70 else "low",
            "note": "参考组成数据，不是供应商批次检测。",
        },
        {
            "metric": "pH",
            "method": "目标 pH 锚点 + 线性酸/缓冲负荷指数，并夹到体系范围内",
            "source": "食品体系模板 + 配料酸/缓冲先验",
            "evidence_tier": "D",
            "confidence": "very low",
            "note": "这是情景指数，不是实测 pH；必须用校准 pH 计和滴定验证。",
        },
        {
            "metric": "水分活度 aw",
            "method": "模板 aw 中点减去按比例缩放的保湿剂/糖/盐效应",
            "source": "配料 aw curated 先验",
            "evidence_tier": "D",
            "confidence": "very low",
            "note": "不是水活度模型；必须在 25°C 实测 aw。",
        },
        {
            "metric": "稳定性/货架期",
            "method": "由热处理、pH、aw、防腐剂、抗氧化剂和相互作用标志计算的稳定性启发式；货架期 = 模板 × 修正因子",
            "source": "curated 食品化学规则",
            "evidence_tier": "E",
            "confidence": "very low",
            "note": "规划情景，不是动力学或微生物模型；必须做加速和实时试验。",
        },
        {
            "metric": "综合评分",
            "method": "六个子分数的加权和，叠加硬约束惩罚",
            "source": "用户目标/查询优先级 + curated 规则",
            "evidence_tier": "E",
            "confidence": "very low",
            "note": "用于候选比较的决策指数，不是成功概率。",
        },
    ]


def _recipe_changes(base: list[dict[str, Any]], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    b = {row["id"]: float(row["pct"]) for row in base}
    c = {row["id"]: float(row["pct"]) for row in selected}
    rows = []
    for item_id in sorted(set(c) - set(b)):
        rows.append({"action": "add", "ingredient": item_id, "because": "策略添加：补足目标功能角色或约束"})
    for item_id in sorted(set(b) - set(c)):
        rows.append({"action": "remove", "ingredient": item_id, "because": "被替代、禁用或归一化移除"})
    for item_id in sorted(set(b) & set(c)):
        if abs(c[item_id] - b[item_id]) >= 0.1:
            rows.append({"action": "adjust", "ingredient": item_id, "from_pct": round(b[item_id], 3), "to_pct": round(c[item_id], 3), "because": "满足目标/工艺/质构平衡"})
    return rows[:30]


def _expanded(recipe: list[dict[str, Any]], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    imap = _ingredient_map()
    rows = []
    for row in recipe:
        item = imap[row["id"]]
        role = row.get("role") or _role(item)
        comp = composition.get(item["id"])
        rows.append({
            "id": item["id"], "name": item["name"], "cn_name": item["cn_name"],
            "pct": round(float(row["pct"]), 3), "role": role, "role_cn": _role_cn(role),
            "category": item.get("category"), "functions": item.get("functions", []),
            "typical_range": item.get("typical_pct"), "max_pct": item.get("max_pct"),
            "allergen": item.get("allergen", False), "food_additive": item.get("food_additive", False),
            "e_number": item.get("e_number"), "clean_label": item.get("clean_label", True),
            "cost_index": item.get("cost_index", 3), "notes_cn": item.get("notes_cn", ""),
            "evidence": item.get("evidence", []), "source_type": comp.get("source_type", "curated_estimate"),
            "confidence": comp.get("confidence", "low"),
            "composition": comp.get("nutrients", {}),
            "composition_source": comp.get("source_type"),
            "composition_match": comp.get("match"),
            "fdc_id": comp.get("fdc_id"),
            "fdc_description": comp.get("fdc_description"),
            "composition_note": comp.get("note"),
        })
    return rows


def _process(system: dict[str, Any], recipe: list[dict[str, Any]], targets: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    imap = _ingredient_map()
    has_gum = any(any(x in imap[row["id"]].get("functions", []) for x in ("thickener", "gelling", "stabilizer")) for row in recipe)
    has_protein = any("protein" in imap[row["id"]].get("functions", []) or imap[row["id"]].get("category") == "protein" for row in recipe)
    temp = float(targets.get("process_temp_c", system["process_temp_c"]))
    time_min = float(targets.get("process_time_min", system["process_time_min"]))
    category = system["category"]
    steps = [
        {"step": 1, "title": "原料验收与称量", "detail": "核对配料表、过敏原、法规状态和批次；按 100 kg 中试批次称量，微量成分先做预混。"},
        {"step": 2, "title": "预处理", "detail": ("蛋白/胶体先水合分散，避免结块；" if has_gum or has_protein else "") + "油脂/固体原料按工艺要求预热或粉碎；记录实际水分和温度。"},
        {"step": 3, "title": "混合/乳化/成型", "detail": f"{system['cn_name']}基础单元操作：按模板顺序混合，控制剪切、时间和温度；关键功能成分最后加入。"},
    ]
    if category == "bakery":
        steps[2]["detail"] = "和面/打发至目标面筋或泡沫状态；控制面团/面糊温度和比重。"
        steps.append({"step": 4, "title": "发酵/烘焙", "detail": f"按 {temp:g}°C / {time_min:g} min 的模板工艺进行发酵和烘焙；记录中心温度、体积和水分损失。"})
    elif category == "meat":
        steps[2]["detail"] = "斩拌/乳化至蛋白溶出、脂肪颗粒细化；控制终温不超过 12°C，避免破乳。"
        steps.append({"step": 4, "title": "热加工", "detail": f"按 {temp:g}°C / {time_min:g} min 达到目标中心温度；验证致病菌灭活和冷链。"})
    elif category in {"dairy", "plant_based"} and system["id"] == "dairy_yogurt":
        steps[2]["detail"] = "乳固体水合、均质；接种发酵剂，按模板温度发酵至 pH 4.5 左右。"
        steps.append({"step": 4, "title": "发酵/冷却", "detail": f"发酵至 pH {metrics['ph']:g} 附近，破乳/搅拌，快速冷却到 4°C；记录活菌数和乳清析出。"})
    elif category == "frozen":
        steps.append({"step": 4, "title": "杀菌/均质/老化", "detail": f"按 {temp:g}°C / {time_min:g} min 杀菌，均质后老化 ≥4 h；控制脂肪结晶和冰晶。"})
        steps.append({"step": 5, "title": "凝冻/硬化", "detail": "凝冻至目标 overrun，迅速硬化到 -18°C 或更低；避免热冲击。"})
    elif category == "sauce":
        steps.append({"step": 4, "title": "乳化/热处理", "detail": f"按 {temp:g}°C / {time_min:g} min 热处理；控制加油速度和均质压力，防止破乳。"})
    elif category == "confectionery":
        steps.append({"step": 4, "title": "熬糖/调温/成型", "detail": f"按 {temp:g}°C / {time_min:g} min 的模板工艺控制糖浆浓度、调温或凝胶；快速成型。"})
    elif category == "snack":
        steps.append({"step": 4, "title": "挤压/烘焙/干燥", "detail": f"按 {temp:g}°C / {time_min:g} min 的模板工艺控制水分、剪切和膨胀；干燥到目标 aw。"})
    elif category == "fermented":
        steps.append({"step": 4, "title": "盐渍/发酵", "detail": f"按模板盐度和温度发酵；监测 pH、盐度、亚硝酸盐和厌氧条件。"})
    elif category == "powder":
        steps.append({"step": 4, "title": "干混/造粒/包装", "detail": "控制环境湿度；先做微量成分预混，再与大宗粉体混合；检测均匀度。"})
    elif category == "packaging":
        steps.append({"step": 4, "title": "成膜/干燥/交联", "detail": f"按 {temp:g}°C / {time_min:g} min 干燥成膜；控制厚度、交联和水分。"})
    else:
        steps.append({"step": 4, "title": "热处理/灌装", "detail": f"按 {temp:g}°C / {time_min:g} min 的等效热处理；热灌装/无菌灌装并快速冷却。"})
    steps.append({"step": len(steps) + 1, "title": "冷却/包装/储存", "detail": f"{system['packaging']}；按 {system['storage_temp_c']:g}°C 储存，记录批号、时间和温度。"})
    return steps


def _qc(system: dict[str, Any], targets: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    tests = [
        {"test": "pH", "method": "校准 pH 计，25°C", "acceptance": f"{metrics['ph']:g} ± 0.1（目标范围 {system['ph_range'][0]:g}-{system['ph_range'][1]:g}）", "stage": "每批"},
        {"test": "水分活度 aw", "method": "水分活度仪，25°C", "acceptance": f"{metrics['aw']:.2f} ± 0.02（按产品标准）", "stage": "每批/稳定性"},
        {"test": "可溶性固形物/Brix", "method": "折光仪，20°C", "acceptance": "按产品标准和模板目标", "stage": "每批"},
        {"test": "蛋白质", "method": "Kjeldahl / Dumas / 近红外（按矩阵验证）", "acceptance": f"≥ {targets.get('protein_min_pct', 0):g}%（如适用）", "stage": "每批"},
        {"test": "糖/钠", "method": "HPLC / ICP-OES / 离子色谱", "acceptance": f"糖 ≤ {targets.get('sugar_max_pct', 100):g}%；钠 ≤ {targets.get('sodium_max_mg', 99999):g} mg/100g（如适用）", "stage": "每批/型式检验"},
        {"test": "微生物", "method": "按产品类别执行菌落总数、霉菌酵母、致病菌检测", "acceptance": "符合销售地法规和产品标准", "stage": "每批/稳定性"},
        {"test": "感官", "method": "训练小组，盲样，标准描述词和 9 点标度", "acceptance": "与目标产品差异在预设范围内", "stage": "中试/货架期"},
        {"test": "色差", "method": "分光测色仪，CIELAB，标准光源", "acceptance": "ΔE 在预设范围内；天然色素需加速褪色", "stage": "每批/稳定性"},
    ]
    for extra in system.get("qc", []):
        if extra not in {item["test"] for item in tests}:
            tests.append({"test": extra, "method": "按产品标准/文献方法", "acceptance": "按法规或内控标准", "stage": "中试/稳定性"})
    return tests


def _shelf_life(system: dict[str, Any], metrics: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    base = int(targets.get("shelf_days", system["shelf_days"]))
    factor = 0.55 + 0.45 * metrics["stability"]
    if metrics["aw"] < 0.6:
        factor += 0.10
    if metrics["ph"] < 4.5:
        factor += 0.08
    if metrics["preservative_count"]:
        factor += 0.06
    if metrics["negative_interactions"]:
        factor -= min(0.15, abs(metrics["interaction_net"]) * 0.6)
    predicted = max(3, min(base * 1.3, int(base * factor)))
    return {
        "target_days": base,
        "predicted_days": predicted,
        "storage_temp_c": system["storage_temp_c"],
        "basis": "模板货架期 × 稳定性/aw/pH/防腐/相互作用修正；必须做真实加速和长期试验。",
        "accelerated": "建议 40°C/75% RH（或产品对应条件）加速 4-12 周，并与 4/25°C 实时数据桥接。",
    }


def _regulatory(system: dict[str, Any], recipe: list[dict[str, Any]], metrics: dict[str, Any], targets: dict[str, Any]) -> list[str]:
    imap = _ingredient_map()
    notes = [
        "配料表、过敏原、营养标签、最大使用量和食品类别必须按销售地现行法规核验；本工具不提供法规批准。",
        "所有食品添加剂（E 编号）必须确认在该食品类别中的允许使用量和携带原则。",
    ]
    if metrics["allergens"]:
        notes.append("含过敏原：" + "、".join(metrics["allergens"]) + "；需评估交叉污染和标签声明。")
    if targets.get("no_allergen"):
        notes.append("已按“无过敏原”目标过滤，但生产线交叉污染仍需验证。")
    if system["id"] == "meat_sausage":
        notes.append("肉制品需 HACCP、致病菌控制、亚硝酸盐（如使用）和中心温度验证；不得把本配方直接用于生产。")
    if system["category"] == "fermented":
        notes.append("发酵食品需验证酸化曲线、盐度、亚硝酸盐和厌氧条件；不得仅依赖模型判断安全。")
    if system["category"] == "powder":
        notes.append("固体饮料需验证冲调后的 pH、剂量均匀度和微生物指标。")
    if any(imap[row["id"]].get("food_additive") and not imap[row["id"]].get("clean_label") for row in recipe):
        notes.append("配方含合成/非清洁标签添加剂；清洁标签或特定市场版本需替换并重新验证。")
    return notes


def _candidate(
    system: dict[str, Any],
    brief: dict[str, Any],
    strategy: tuple[str, str, str],
    rng: Any = None,
    recipe_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    targets = brief["targets"]
    recipe = [dict(row) for row in recipe_override] if recipe_override is not None else _strategy_recipe(system, targets, strategy[0], rng)
    metrics = _metrics(recipe, system, targets, brief)
    comp_summary = composition.summary(recipe)
    intervals = _intervals(metrics, comp_summary)
    constraint_report = _constraint_report(system, targets, metrics, intervals)
    constraint_status = "fail" if any(row["status"] == "fail" for row in constraint_report) else ("at_risk" if any(row["status"] == "at_risk" for row in constraint_report) else "pass")
    expanded = _expanded(recipe, metrics)
    shelf = _shelf_life(system, metrics, targets)
    process_steps = _process(system, recipe, targets, metrics)
    processing_effects = processing.evaluate(system, recipe, targets, metrics)
    warnings = []
    if metrics["heat_sensitive"]:
        warnings.append("工艺温度超过以下配料建议上限：" + "、".join(metrics["heat_sensitive"][:5]))
    if metrics["ph_mismatch"]:
        warnings.append("pH 可能超出以下配料的稳定范围：" + "、".join(metrics["ph_mismatch"][:5]))
    if metrics["negative_interactions"]:
        warnings.append("检测到负向相互作用：" + "；".join(f"{x['a_cn']}+{x['b_cn']}" for x in metrics["negative_interactions"][:3]))
    if targets.get("high_protein") and metrics["protein_pct"] < targets.get("protein_min_pct", 0):
        warnings.append(f"估算蛋白质 {metrics['protein_pct']:.1f}% 低于目标 {targets['protein_min_pct']:.1f}%；需提高蛋白或调整基准。")
    if targets.get("low_sugar") and targets.get("sugar_max_pct", 100) < 100 and metrics["sugar_pct"] > targets.get("sugar_max_pct", 100):
        warnings.append(f"估算糖 {metrics['sugar_pct']:.1f}% 高于目标 {targets['sugar_max_pct']:.1f}%；需进一步减糖。")
    if targets.get("low_sodium") and metrics["sodium_mg"] > targets.get("sodium_max_mg", 99999):
        warnings.append(f"估算钠 {metrics['sodium_mg']:.0f} mg/100g 高于目标 {targets['sodium_max_mg']:.0f} mg/100g；需调整盐/钾盐。")
    if targets.get("high_fiber") and metrics["fiber_pct"] < targets.get("fiber_min_pct", 0):
        warnings.append(f"估算膳食纤维 {metrics['fiber_pct']:.1f}% 低于目标 {targets['fiber_min_pct']:.1f}%；需增加纤维或调整基准。")
    if targets.get("bioactive_id"):
        warnings.append("功能成分（如槲皮素）的溶解度、降解、苦味和有效剂量需实测；本配方仅用于机制研究。")
    if metrics["color_risk"] > 0.08:
        warnings.append("色素稳定性风险较高：需避光、控氧、控制 pH/热处理并做加速褪色实验。")
    color_target = targets.get("color_retention_min_pct")
    color_est = metrics.get("color_retention_pct")
    if color_target is not None and color_est is not None:
        if color_est < float(color_target):
            warnings.append(f"色素保留率筛选估算 {color_est:.1f}% 低于目标 {float(color_target):.0f}%；需调整 pH/热处理或保护剂，并以实测为准。")
        else:
            warnings.append(f"色素保留率筛选估算 {color_est:.1f}%（目标 {float(color_target):.0f}%）；接近阈值，必须做加速褪色实测。")
    rationale = [
        f"综合评分 {metrics['overall_score']:.3f}；稳定性 {metrics['stability']:.2f}、感官 {metrics['sensory']:.2f}、成本 {metrics['cost']:.2f}、营养 {metrics['nutrition']:.2f}、清洁标签 {metrics['clean_label']:.2f}。",
        f"估算 pH {metrics['ph']:g}、aw {metrics['aw']:.2f}、蛋白质 {metrics['protein_pct']:.1f}%、糖 {metrics['sugar_pct']:.1f}%、钠 {metrics['sodium_mg']:.0f} mg/100g。",
        *([f"色素保留率筛选估算 {metrics['color_retention_pct']:.1f}%（{metrics.get('color_retention_basis')}）；不是实测。"] if metrics.get("color_retention_pct") is not None else []),
        f"正向相互作用 {len(metrics['positive_interactions'])} 条，负向 {len(metrics['negative_interactions'])} 条；净效应 {metrics['interaction_net']:+.3f}。",
    ]
    constraint_met = True
    if targets.get("high_protein") and metrics["protein_pct"] < targets.get("protein_min_pct", 0) * 0.95:
        constraint_met = False
    if targets.get("low_sugar") and targets.get("sugar_max_pct", 100) < 100 and metrics["sugar_pct"] > targets.get("sugar_max_pct", 100) * 1.05:
        constraint_met = False
    if targets.get("low_sodium") and metrics["sodium_mg"] > targets.get("sodium_max_mg", 99999) * 1.05:
        constraint_met = False
    if targets.get("high_fiber") and metrics["fiber_pct"] < targets.get("fiber_min_pct", 0) * 0.95:
        constraint_met = False
    if targets.get("no_allergen") and metrics["allergens"]:
        constraint_met = False
    if targets.get("color_retention_min_pct") is not None and metrics.get("color_retention_pct") is not None:
        if metrics["color_retention_pct"] < float(targets["color_retention_min_pct"]):
            constraint_met = False
    if targets.get("gluten_free") and any(row["id"] in {"wheat_flour", "wheat_gluten", "sourdough"} for row in recipe):
        constraint_met = False
    if targets.get("soy_free") and any(row["id"] in {"soy_protein", "lecithin"} for row in recipe):
        constraint_met = False
    if targets.get("dairy_free") and any(row["id"] in {"milk_powder", "cream", "whey_protein", "casein"} for row in recipe):
        constraint_met = False
    return {
        "id": f"{system['id']}-{strategy[0]}",
        "constraint_met": constraint_met,
        "constraint_status": constraint_status,
        "constraint_report": constraint_report,
        "strategy": strategy[0], "strategy_cn": strategy[1], "strategy_note": strategy[2],
        "strategy_en": STRATEGY_EN.get(strategy[0], strategy[0].replace("_", " ").title()),
        "system_id": system["id"], "system_cn": system["cn_name"],
        "score": metrics["overall_score"], "metrics": metrics,
        "intervals": intervals, "composition": comp_summary,
        "ingredients": expanded, "process": process_steps,
        "processing_effects": processing_effects,
        "qc": _qc(system, targets, metrics), "shelf_life": shelf,
        "regulatory": _regulatory(system, recipe, metrics, targets),
        "warnings": warnings, "rationale": rationale,
        "interactions": {"positive": metrics["positive_interactions"], "negative": metrics["negative_interactions"]},
        "metric_provenance": _metric_provenance(comp_summary),
        "evidence_grade": "C" if comp_summary.get("mapped_mass_pct", 0) >= 70 else "D",
        "recipe": recipe,
    }


def _diversity(candidates: list[dict[str, Any]], limit: int = 8, threshold: float = 0.88) -> list[dict[str, Any]]:
    chosen = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        ids = {row["id"] for row in candidate["recipe"]}
        if all(len(ids & {row["id"] for row in prior["recipe"]}) / max(1, len(ids | {row["id"] for row in prior["recipe"]})) < threshold for prior in chosen):
            chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return chosen


def _recipe_key(candidate: dict[str, Any]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(row["id"]), round(float(row["pct"]), 3)) for row in candidate.get("recipe", [])))


def _unique_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    keys: set[tuple[tuple[str, float], ...]] = set()
    for candidate in sorted(candidates, key=lambda item: float(item["score"]), reverse=True):
        key = _recipe_key(candidate)
        if key and key not in keys:
            chosen.append(candidate)
            keys.add(key)
    return chosen


def _fill_variants(
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    system: dict[str, Any],
    brief: dict[str, Any],
    limit: int = 8,
) -> list[dict[str, Any]]:
    chosen = list(selected)
    keys = {_recipe_key(candidate) for candidate in chosen}
    sources = list(chosen) + [candidate for candidate in candidates if candidate.get("id") not in {item.get("id") for item in chosen}]
    pool = data.ingredients()
    for base in sources:
        if len(chosen) >= limit:
            break
        ids = {row["id"] for row in base.get("recipe", [])}
        for row in sorted(base.get("recipe", []), key=lambda item: float(item["pct"])):
            if len(chosen) >= limit:
                break
            if row["id"] == "water" or float(row["pct"]) > 8.0:
                continue
            original = _ingredient_map().get(row["id"])
            if not original or original.get("category") not in _VARIANT_CATEGORIES:
                continue
            exclude = set(ids)
            for _ in range(4):
                alt = _pick(pool, tuple(original.get("functions", [])), brief["targets"], exclude=exclude, system=system)
                if not alt:
                    break
                exclude.add(alt["id"])
                if alt["id"] in ids or float(alt.get("max_pct", 100.0)) < float(row["pct"]):
                    continue
                if alt.get("category") != original.get("category"):
                    continue
                if _is_animal(alt) and not _is_animal(original):
                    continue
                recipe = [dict(item) for item in base.get("recipe", [])]
                for item in recipe:
                    if item["id"] == row["id"]:
                        item["id"] = alt["id"]
                        break
                if len({item["id"] for item in recipe}) != len(recipe):
                    continue
                index = len(chosen)
                strategy = (
                    f"{base['strategy']}_alt{index}",
                    f"{base['strategy_cn']} · 变体（{original['cn_name']}→{alt['cn_name']}）",
                    f"以{base['strategy_cn']}为基准，用{alt['cn_name']}替代{original['cn_name']}；用于比较原料选择对指标和约束的影响。",
                )
                candidate = _candidate(system, brief, strategy, recipe_override=recipe)
                key = _recipe_key(candidate)
                if key in keys or candidate["constraint_status"] == "fail":
                    continue
                base_en = base.get("strategy_en") or STRATEGY_EN.get(base["strategy"], base["strategy"])
                candidate["strategy_en"] = f"{base_en} · variant ({alt.get('name') or alt['cn_name']} for {original.get('name') or original['cn_name']})"
                candidate["strategy_note_en"] = f"Replaces {original.get('name') or original['cn_name']} with {alt.get('name') or alt['cn_name']} in the {base_en} recipe."
                candidate["variant_of"] = base["id"]
                candidate["substitution"] = {"from": row["id"], "to": alt["id"], "pct": row["pct"]}
                chosen.append(candidate)
                keys.add(key)
                break
    return chosen


def design_food(query: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = dict(options or {})
    brief = parse_food_brief(query, options)
    system = brief["system"]
    candidates = [_candidate(system, brief, strategy, None) for strategy in STRATEGIES]
    baseline = _candidate(system, brief, ("balanced", "均衡型", "基础模板"), None)
    candidates.append(baseline)
    unique = _unique_candidates(candidates)
    passing = [candidate for candidate in unique if candidate.get("constraint_met")]
    pool = passing if len(passing) >= 3 else unique
    selected_portfolio = _fill_variants(_diversity(pool, 8, 1.01), unique, system, brief, 8)
    if len(selected_portfolio) < 8:
        seen = {candidate["id"] for candidate in selected_portfolio}
        selected_portfolio += [candidate for candidate in unique if candidate["id"] not in seen][: 8 - len(selected_portfolio)]
    if not selected_portfolio:
        raise ValueError("no food formulation candidates available")
    selected = selected_portfolio[0]
    selected["recipe_changes"] = _recipe_changes(baseline["recipe"], selected["recipe"])
    baseline_metrics = baseline["metrics"]
    decision = [
        f"识别产品体系：{system['cn_name']}；生成 {len(selected_portfolio)} 个可比较配方，而不是单一答案。",
        f"推荐策略「{selected['strategy_cn']}」：综合评分 {selected['score']:.3f}；{selected['strategy_note']}",
        f"关键估算：pH {selected['metrics']['ph']:g}、aw {selected['metrics']['aw']:.2f}、蛋白质 {selected['metrics']['protein_pct']:.1f}%、糖 {selected['metrics']['sugar_pct']:.1f}%、钠 {selected['metrics']['sodium_mg']:.0f} mg/100g。",
        *([f"色素保留率筛选估算 {selected['metrics']['color_retention_pct']:.1f}%，目标 {float(brief['targets'].get('color_retention_min_pct', 0)):g}%；必须实测。"] if selected['metrics'].get("color_retention_pct") is not None and brief["targets"].get("color_retention_min_pct") is not None else []),
        f"相对基础模板：评分变化 {selected['score'] - baseline_metrics['overall_score']:+.3f}；稳定性 {selected['metrics']['stability'] - baseline_metrics['stability']:+.2f}；成本 {selected['metrics']['cost'] - baseline_metrics['cost']:+.2f}。",
        f"相互作用：{len(selected['interactions']['positive'])} 条正向、{len(selected['interactions']['negative'])} 条负向；负向作用已进入警告和评分惩罚。",
        f"货架期模型估计 {selected['shelf_life']['predicted_days']} 天（目标 {selected['shelf_life']['target_days']} 天），必须实测。",
    ]
    warnings = list(brief["warnings"]) + selected["warnings"]
    if selected["metrics"]["negative_interactions"]:
        warnings.append("配方存在需要实验验证的负向相互作用；不要只看综合评分。")
    evidence = {
        "local": [
            {"source": "data/food_systems.json", "type": "curated template", "confidence": system.get("confidence", "medium"), "note": system.get("regulatory_note", "")},
            {"source": "data/ingredients.json", "type": "curated ingredient priors", "confidence": "medium", "note": "法规状态和最大使用量需逐项核验。"},
            {"source": "data/interactions.json", "type": "curated literature prior", "confidence": "medium", "note": "相互作用是方向性先验，不是实测。"},
        ],
        "citations": sorted({ref for row in selected["ingredients"] for ref in row.get("evidence", [])})[:24],
        "online": [],
        "spectra_note": "本地光谱为近似参考谱；若需实验谱，请在“数据库证据”中查询 PubChem/MassBank，报告会标注检索时间和记录号。",
    }
    provenance = {
        "engine_version": ENGINE_VERSION,
        "package_version": "2.1.0",
        "created_utc": _now(),
        "mode": "food_formulation",
        "datasets": data.dataset_manifest(),
        "parameter_provenance": [
            {"parameter": "pH", "basis": "template target + acid/buffer load", "source": "curated system + ingredient priors", "confidence": "low-medium"},
            {"parameter": "water activity", "basis": "template aw + humectant/sugar/salt priors", "source": "curated ingredient priors", "confidence": "low-medium"},
            {"parameter": "protein/sugar/fat/fiber/sodium", "basis": "ingredient composition priors", "source": "USDA-style composition priors", "confidence": "low-medium"},
            {"parameter": "stability", "basis": "thermal/pH/aw/antioxidant/preservative/interaction heuristic", "source": "curated food chemistry", "confidence": "low"},
            {"parameter": "shelf life", "basis": "template shelf life × stability modifier", "source": "model estimate", "confidence": "low"},
        ],
        "citations": evidence["citations"],
        "limitations": [
            "配方与指标是筛选先验，不是实测、法规批准或食品安全结论。",
            "配料最大使用量、过敏原、标签和食品类别必须按销售地法规逐项核验。",
            "相互作用为方向性文献先验；实际矩阵 pH、离子强度、温度和加工历史会改变结果。",
            "货架期、微生物安全和感官必须通过中试、加速试验和长期试验验证。",
            "在线数据库结果需保留检索时间、记录号和原始链接；数据库可能有错误或缺失。",
        ],
    }
    return {
        "design_id": f"F{_seed(query, system['id'], _now()):012x}",
        "job_id": None,
        "created_utc": _now(),
        "engine_version": ENGINE_VERSION,
        "package_version": "2.1.0",
        "mode": "food_formulation",
        "brief": brief,
        "system": system,
        "selected": selected,
        "portfolio": selected_portfolio,
        "candidates": selected_portfolio,
        "baseline": baseline,
        "decision_summary": decision,
        "reasoning": {
            "entity": {"kind": "food_formulation", "system_id": system["id"], "system_cn": system["cn_name"]},
            "facts": [
                {"statement": f"已识别产品体系为 {system['cn_name']}。", "source": "data/food_systems.json", "tier": "database"},
                {"statement": f"候选来自 {len(data.ingredients())} 个配料和 {len(data.food_interactions())} 条相互作用记录。", "source": "data/ingredients.json + data/interactions.json", "tier": "database"},
                {"statement": f"组成计算覆盖 {selected['composition']['mapped_mass_pct']}% 的配方质量来自 USDA FDC SR Legacy，其余为 curated estimate。", "source": "data/ingredient_composition.json", "tier": "B/C"},
            ],
            "rules": [
                {"statement": "配料先过硬性过滤：体系允许、pH/工艺上限、过敏原/禁用项、最大添加量。", "tier": "explicit rule"},
                {"statement": "在合法配料内用确定性评分选择：功能匹配、清洁标签、成本、营养、pH/温度兼容、组成置信度。", "tier": "explicit rule"},
                {"statement": "配方百分数归一化后计算质量加权营养和方向性相互作用。", "tier": "explicit rule"},
            ],
            "assumptions": [
                {"statement": "pH 是基于模板与酸/缓冲负荷的筛选指数，不是实测 pH。", "tier": "D"},
                {"statement": "aw 和货架期是模板/规则外推，不是微生物或动力学模型。", "tier": "E"},
                {"statement": "FDC 组成是参考数据，不代表实际供应商批次。", "tier": "B/C"},
                {"statement": "相互作用效应是方向性文献先验，不是该矩阵的实测值。", "tier": "D"},
            ],
            "uncertainty": {
                "composition": selected["intervals"],
                "score_note": "综合分是候选排序指数，不是成功概率；区间仅用于筛选，不是统计置信区间。",
            },
            "validation_required": [
                "实测 pH、aw、Brix、水分、蛋白质、糖、钠和脂肪。",
                "中试核对工艺收率、质构、色泽、风味和微生物。",
                "加速试验 + 实时货架期试验；不得把模型天数当保质期。",
                "按销售地法规核验配料表、过敏原、添加剂最大使用量和营养标签。",
            ],
        },
        "warnings": warnings,
        "evidence": evidence,
        "provenance": provenance,
        "processing": selected.get("processing_effects") or {},
        "formulation": {
            "name": f"{system['cn_name']}·{selected['strategy_cn']}原型",
            "serving_basis": "100 g / 100 mL",
            "ingredients": selected["ingredients"],
            "process": selected["process"],
            "qc": selected["qc"],
            "controls": [{"parameter": item, "target": "按模板/内控", "why": "影响稳定性、安全或感官"} for item in system["critical_controls"]],
            "storage": f"{selected['shelf_life']['predicted_days']} 天模型估计；{system['storage_temp_c']:g}°C；{system['packaging']}",
            "packaging": system["packaging"],
            "regulatory": selected["regulatory"],
            "warnings": selected["warnings"],
            "cost_note": "成本为相对指数，不含采购、损耗、法规检测和中试费用。",
        },
        "logic_chain": {
            "nodes": [
                {"id": "query", "label": "自然语言需求", "detail": query[:160], "status": "computed"},
                {"id": "system", "label": "产品体系", "detail": system["cn_name"], "status": "computed"},
                {"id": "constraints", "label": "目标解析", "detail": json.dumps(brief["targets"], ensure_ascii=False)[:180], "status": "computed"},
                {"id": "ingredients", "label": "配料知识库", "detail": f"{len(data.ingredients())} 个配料，{len(data.food_interactions())} 条相互作用", "status": "computed"},
                {"id": "portfolio", "label": "多策略配方组合", "detail": f"{len(selected_portfolio)} 个候选，推荐 {selected['strategy_cn']}", "status": "computed"},
                {"id": "interactions", "label": "相互作用", "detail": f"正向 {len(selected['interactions']['positive'])} / 负向 {len(selected['interactions']['negative'])}", "status": "computed"},
                {"id": "metrics", "label": "指标估算", "detail": f"pH {selected['metrics']['ph']:g}; aw {selected['metrics']['aw']:.2f}; 蛋白 {selected['metrics']['protein_pct']:.1f}%", "status": "computed"},
                {"id": "process", "label": "工艺与 QC", "detail": system["process_temp_c"], "status": "computed"},
                {"id": "docking", "label": "机制计算", "detail": "可对关键蛋白-配体运行 Vina/OpenMM/GROMACS/CP2K", "status": "available"},
                {"id": "lab", "label": "中试与法规", "detail": "必须做真实样品、加速试验和法规核验", "status": "planned"},
            ],
            "edges": [{"from": "query", "to": "system"}, {"from": "system", "to": "constraints"}, {"from": "constraints", "to": "ingredients"}, {"from": "ingredients", "to": "portfolio"}, {"from": "portfolio", "to": "interactions"}, {"from": "interactions", "to": "metrics"}, {"from": "metrics", "to": "process"}, {"from": "process", "to": "docking"}, {"from": "process", "to": "lab"}, {"from": "docking", "to": "lab"}],
        },
    }
