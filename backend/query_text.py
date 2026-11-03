from __future__ import annotations

import re
from typing import Any

ALIASES = {
    "乳清蛋白": "whey protein",
    "β-乳球蛋白": "beta-lactoglobulin",
    "β乳球蛋白": "beta-lactoglobulin",
    "牛血清白蛋白": "bovine serum albumin",
    "大豆分离蛋白": "soy protein isolate",
    "豌豆蛋白": "pea protein",
    "藻蓝蛋白": "phycocyanin",
    "绿色荧光蛋白": "green fluorescent protein",
    "酪蛋白": "casein",
    "胶原蛋白": "collagen",
    "明胶": "gelatin",
    "大豆蛋白": "soy protein",
    "乳铁蛋白": "lactoferrin",
    "溶菌酶": "lysozyme",
    "胰岛素": "insulin",
    "抗体": "antibody",
    "多肽": "peptide",
    "蛋白": "protein",
    "多糖": "polysaccharide",
    "寡糖": "oligosaccharide",
    "低聚糖": "oligosaccharide",
    "脂质": "lipid",
    "淀粉": "starch",
    "纤维素": "cellulose",
    "果胶": "pectin",
    "卡拉胶": "carrageenan",
    "海藻酸钠": "sodium alginate",
    "黄原胶": "xanthan gum",
    "瓜尔胶": "guar gum",
    "菊粉": "inulin",
    "麦芽糊精": "maltodextrin",
    "海藻糖": "trehalose",
    "蔗糖": "sucrose",
    "葡萄糖": "glucose",
    "果糖": "fructose",
    "乳糖": "lactose",
    "山梨醇": "sorbitol",
    "甘油": "glycerol",
    "槲皮素": "quercetin",
    "姜黄素": "curcumin",
    "白藜芦醇": "resveratrol",
    "儿茶素": "catechin",
    "表没食子儿茶素没食子酸酯": "epigallocatechin gallate",
    "花青素": "anthocyanin",
    "咖啡因": "caffeine",
    "芦丁": "rutin",
    "芹菜素": "apigenin",
    "木犀草素": "luteolin",
    "番茄红素": "lycopene",
    "叶黄素": "lutein",
    "β-胡萝卜素": "beta-carotene",
    "β胡萝卜素": "beta-carotene",
    "维生素C": "ascorbic acid",
    "维生素c": "ascorbic acid",
    "抗坏血酸": "ascorbic acid",
    "维生素E": "tocopherol",
    "生育酚": "tocopherol",
    "维生素B12": "vitamin B12",
    "叶酸": "folic acid",
    "钙": "calcium",
    "铁": "iron",
    "锌": "zinc",
    "钠": "sodium",
    "钾": "potassium",
    "镁": "magnesium",
    "番茄": "tomato",
    "燕麦": "oat",
    "牛奶": "milk",
    "酸奶": "yogurt",
    "奶酪": "cheese",
    "面包": "bread",
    "冰淇淋": "ice cream",
    "巧克力": "chocolate",
    "软糖": "gummy candy",
    "大豆": "soybean",
    "花生": "peanut",
    "坚果": "nut",
    "肉": "meat",
    "鱼": "fish",
    "蛋": "egg",
    "盐": "salt",
    "糖": "sugar",
    "脂肪": "fat",
    "能量": "energy",
    "风味": "flavor",
    "质构": "texture",
    "色泽": "color",
    "货架期": "shelf life",
    "水分活度": "water activity",
    "美拉德反应": "maillard reaction",
    "美拉德": "maillard",
    "焦糖化": "caramelization",
    "氧化": "oxidation",
    "水解": "hydrolysis",
    "发酵": "fermentation",
    "酶解": "enzymatic hydrolysis",
    "糖基化": "glycosylation",
    "磷酸化": "phosphorylation",
    "交联": "crosslinking",
    "凝胶": "gelation",
    "乳化": "emulsification",
    "起泡": "foaming",
    "结晶": "crystallization",
    "玻璃化转变": "glass transition",
    "淀粉糊化": "starch gelatinization",
    "糊化": "gelatinization",
    "回生": "retrogradation",
    "蛋白质变性": "protein denaturation",
    "变性": "denaturation",
    "聚集": "aggregation",
    "降解": "degradation",
    "异构化": "isomerization",
    "环化": "cyclization",
    "脂质氧化": "lipid oxidation",
    "维生素降解": "vitamin degradation",
    "巴氏杀菌": "pasteurization",
    "灭菌": "sterilization",
    "均质": "homogenization",
    "喷雾干燥": "spray drying",
    "冷冻干燥": "freeze drying",
    "真空干燥": "vacuum drying",
    "挤压": "extrusion",
    "烘焙": "baking",
    "油炸": "frying",
    "蒸煮": "cooking",
    "腌制": "curing",
    "烟熏": "smoking",
    "辐照": "irradiation",
    "高压处理": "high pressure processing",
    "超声": "ultrasound",
    "微波": "microwave",
    "冷等离子体": "cold plasma",
    "脉冲电场": "pulsed electric field",
    "结合": "binding",
    "抑制": "inhibition",
    "激活": "activation",
    "机制": "mechanism",
    "结构": "structure",
    "稳定性": "stability",
    "溶解度": "solubility",
    "生物利用度": "bioavailability",
    "毒性": "toxicity",
    "过敏原": "allergen",
    "相互作用": "interaction",
}

EN_ALIASES = {
    "egcg": "epigallocatechin gallate",
    "vit c": "ascorbic acid",
    "vitamin c": "ascorbic acid",
    "vit e": "tocopherol",
    "bsa": "bovine serum albumin",
    "md": "molecular dynamics",
    "hpp": "high pressure processing",
    "pef": "pulsed electric field",
    "scco2": "supercritical carbon dioxide",
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was", "were",
    "has", "have", "had", "not", "but", "its", "their", "our", "you", "all", "can",
    "how", "what", "why", "when", "where", "which", "who", "will", "would", "should",
    "effect", "effects", "using", "used", "based", "between", "under", "over", "about",
    "与", "和", "的", "在", "对", "及", "或", "中", "内", "后", "前", "下",
}


def _normalize(text: str) -> str:
    text = (text or "").replace("\u3000", " ").replace("－", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def expand_query(query: str) -> dict[str, Any]:
    original = _normalize(query)
    text = original
    matched: list[dict[str, str]] = []
    for zh, en in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if zh and zh in text:
            text = text.replace(zh, f" {en} ")
            matched.append({"term": zh, "english": en})
    for en, canonical in sorted(EN_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(en)}(?![a-z0-9])", text, re.I):
            text = re.sub(rf"(?<![a-z0-9]){re.escape(en)}(?![a-z0-9])", f" {canonical} ", text, flags=re.I)
            matched.append({"term": en, "english": canonical})
    expanded = re.sub(r"\s+", " ", text).strip()
    if re.search(r"[\u3400-\u9fff]", expanded):
        for connector in ("与", "和", "的", "及", "或", "在", "对"):
            expanded = expanded.replace(connector, " ")
        expanded = re.sub(r"\s+", " ", expanded).strip()
    expanded = re.sub(r"\b([A-Za-z][A-Za-z0-9-]*)(?:\s+\1\b)+", r"\1", expanded, flags=re.I)
    has_cjk = bool(re.search(r"[\u3400-\u9fff]", original))
    return {
        "original": original,
        "expanded": expanded,
        "matched": matched,
        "language": "zh" if has_cjk and not re.search(r"[a-zA-Z]{3,}", original) else ("mixed" if has_cjk else "en"),
    }


def terms(query: str) -> list[str]:
    expansion = expand_query(query)
    text = expansion["expanded"].lower()
    words = re.findall(r"[a-z][a-z0-9\-]{1,}|[\u3400-\u9fff]{2,}", text)
    output: list[str] = []
    for word in words:
        word = word.strip("-")
        if len(word) < 2 or word in STOPWORDS or word in output:
            continue
        output.append(word)
    return output[:18]


def relevance(query: str, text: str) -> tuple[float, list[str]]:
    expansion = expand_query(query)
    query_terms = terms(query)
    if not query_terms:
        return 0.0, []
    haystack = (text or "").lower()
    matched = [term for term in query_terms if term in haystack]
    phrase = expansion["expanded"].lower()
    phrase_hit = bool(phrase and len(phrase) >= 3 and phrase in haystack)
    coverage = len(matched) / max(1, min(len(query_terms), 6))
    score = min(1.0, 0.58 * coverage + (0.32 if phrase_hit else 0.0) + (0.10 if matched else 0.0))
    return round(score, 3), matched


def strength(score: float | None) -> str:
    value = float(score or 0)
    if value >= 0.72:
        return "high"
    if value >= 0.40:
        return "medium"
    return "low"
