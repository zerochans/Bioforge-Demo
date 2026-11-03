from __future__ import annotations

from typing import Any

from . import data

VERSION = "1.0"

REFERENCES = {
    "hodge1953": {
        "label": "Hodge 1953, Chemistry of browning reactions in model systems",
        "url": "https://doi.org/10.1021/jf60015a004",
        "type": "primary literature",
    },
    "lund2017": {
        "label": "Lund & Ray 2017, Control of Maillard reactions in foods",
        "url": "https://doi.org/10.1021/acs.jafc.7b00865",
        "type": "review",
    },
    "patras2010": {
        "label": "Patras et al. 2010, Effect of thermal processing on anthocyanin stability",
        "url": "https://doi.org/10.1016/j.tifs.2009.07.004",
        "type": "review",
    },
    "castaneda2009": {
        "label": "Castañeda-Ovando et al. 2009, Chemical studies of anthocyanins",
        "url": "https://doi.org/10.1016/j.foodchem.2008.09.001",
        "type": "review",
    },
    "vanboekel2008": {
        "label": "van Boekel 2008, Kinetic modeling of food quality",
        "url": "https://doi.org/10.1111/j.1541-4337.2007.00036.x",
        "type": "review",
    },
    "frankel1980": {
        "label": "Frankel 1980, Lipid oxidation",
        "url": "https://doi.org/10.1016/0163-7827(80)90006-5",
        "type": "review",
    },
    "bala2015": {
        "label": "Balasubramaniam et al. 2015, High pressure-based food processing",
        "url": "https://doi.org/10.1146/annurev-food-022814-015539",
        "type": "review",
    },
    "chemat2011": {
        "label": "Chemat et al. 2011, Applications of ultrasound in food technology",
        "url": "https://doi.org/10.1016/j.ultsonch.2010.11.023",
        "type": "review",
    },
    "dewit1981": {
        "label": "de Wit 1981, Structure and functional behaviour of whey proteins",
        "url": None,
        "type": "primary literature",
    },
    "mcclements2015": {
        "label": "McClements 2015, Food Emulsions: Principles, Practices, and Techniques",
        "url": None,
        "type": "textbook",
    },
    "fellows2017": {
        "label": "Fellows 2017, Food Processing Technology, 4th edition",
        "url": None,
        "type": "textbook",
    },
}


def _refs(*keys: str) -> list[dict[str, Any]]:
    return [REFERENCES[key] for key in keys if key in REFERENCES]


def _has(recipe: list[dict[str, Any]], ids: set[str]) -> bool:
    return any(row.get("id") in ids for row in recipe)


def _functions(recipe: list[dict[str, Any]]) -> set[str]:
    imap = {item["id"]: item for item in data.ingredients()}
    out: set[str] = set()
    for row in recipe:
        out.update(imap.get(str(row.get("id")), {}).get("functions", []) or [])
    return out


def _level(value: float, low: float, high: float) -> str:
    if value >= high:
        return "high"
    if value >= low:
        return "medium"
    return "low"


def _effect(
    effect_id: str,
    component: str,
    change: str,
    level: str,
    mechanism: str,
    macro: str,
    refs: list[dict[str, Any]],
    confidence: str = "medium",
    validation: str = "需用目标基质、实际工艺和目标成分做验证。",
    direction: str = "increase",
) -> dict[str, Any]:
    return {
        "id": effect_id,
        "component": component,
        "change": change,
        "direction": direction,
        "level": level,
        "mechanism": mechanism,
        "macro": macro,
        "evidence": refs,
        "confidence": confidence,
        "validation": validation,
    }


def evaluate(
    system: dict[str, Any],
    recipe: list[dict[str, Any]],
    targets: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    temp = float(targets.get("process_temp_c", system.get("process_temp_c", 25.0)))
    time_min = float(targets.get("process_time_min", system.get("process_time_min", 0.0)))
    ph = float(metrics.get("ph", 7.0))
    aw = float(metrics.get("aw", 0.99))
    protein = float(metrics.get("protein_pct", 0.0))
    sugar = float(metrics.get("sugar_pct", 0.0))
    fat = float(metrics.get("fat_pct", 0.0))
    heat_load = temp * max(0.1, time_min)
    functions = _functions(recipe)
    effects: list[dict[str, Any]] = []

    has_whey = _has(recipe, {"whey_protein", "whey_powder", "milk_powder"})
    has_protein = protein >= 3.0 or "protein" in functions
    has_reducing_sugar = sugar >= 4.0 or _has(recipe, {"glucose", "fructose", "maltodextrin", "honey", "fruit_juice"})
    has_anthocyanin = _has(recipe, {"anthocyanin", "black_carrot", "strawberry", "blueberry", "grape", "hibiscus", "purple_sweet_potato", "red_cabbage"})
    has_ascorbic = _has(recipe, {"ascorbic_acid", "vitamin_c", "orange_juice", "lemon_juice", "tomato_paste", "tomato"})
    has_unsaturated_fat = fat >= 3.0 and _has(recipe, {"sunflower_oil", "canola_oil", "soybean_oil", "olive_oil", "flaxseed_oil", "walnut_oil", "fish_oil", "algae_oil"})
    has_starch = _has(recipe, {"starch", "wheat_flour", "rice_flour", "corn_flour", "corn_starch", "cornmeal", "potato_starch", "tapioca_starch", "maltodextrin", "oat_flour", "oats", "wheat", "potato", "sweet_potato", "cassava", "plantain"})
    has_sucrose = _has(recipe, {"sucrose", "sugar"})
    has_hydrocolloid = bool(functions & {"thickener", "gelling", "stabilizer"})
    has_gelatin = _has(recipe, {"gelatin"})
    has_enzyme = _has(recipe, {"protease", "papain", "bromelain", "ficin", "transglutaminase"})

    if temp >= 55 and has_protein:
        level = _level(heat_load, 3000, 12000)
        effects.append(_effect(
            "thermal_protein",
            "蛋白质",
            "变性/展开，随后可能聚集或凝胶",
            level,
            f"当前条件约 {temp:g} °C / {time_min:g} min；接近或超过乳清蛋白等球状蛋白的热变性区间，疏水基团暴露后可形成可逆或不可逆聚集。聚集程度取决于蛋白浓度、pH、离子强度和剪切。",
            "预期影响持水/持油、乳化、起泡、凝胶硬度和消化速率；高蛋白体系可能变稠、失稳或形成颗粒感。",
            _refs("dewit1981", "vanboekel2008"),
            "medium",
            "用目标蛋白浓度、pH、离子强度和实际升温曲线做 DSC、浊度、粒径、SDS-PAGE 与流变验证。",
        ))
    if temp >= 90 and has_reducing_sugar and has_protein and 0.2 <= aw <= 0.9:
        level = _level(heat_load, 5000, 20000)
        effects.append(_effect(
            "maillard",
            "还原糖 + 氨基化合物",
            "美拉德反应生成风味/色泽，并可能损失赖氨酸",
            level,
            f"当前 pH {ph:g}、aw {aw:.2f}、约 {temp:g} °C / {time_min:g} min；还原糖与游离氨基在热条件下缩合，经 Amadori 重排和后续裂解生成类黑精及挥发性风味。",
            "预期褐变、烘焙/烤香/焦香增强；过量时出现苦味、色泽过深和赖氨酸利用率下降。高水分、短时杀菌通常褐变较轻。",
            _refs("hodge1953", "lund2017"),
            "medium",
            "以 420 nm 吸光、色差、HMF/呋喃和赖氨酸损失做动力学验证；不能仅凭配方预测终产品褐变。",
        ))
    if has_anthocyanin and (temp >= 70 or ph > 4.0 or aw > 0.85 or (aw < 0.4 and system.get("category") == "powder")):
        level = _level(max(0.0, temp - 60) / 40 + max(0.0, ph - 3.0) / 4 + max(0.0, aw - 0.8), 0.25, 0.8)
        effects.append(_effect(
            "anthocyanin",
            "花青素",
            "热/ pH 依赖降解与色调漂移",
            level,
            f"花青素在 pH {ph:g}、约 {temp:g} °C 下可能发生开环、聚合或与抗坏血酸/糖裂解产物反应；pH 接近中性时以醌式/查尔酮形态为主，颜色变淡。",
            "预期红色/紫色减弱、褐变增加；抗坏血酸和金属离子可能加速降解。",
            _refs("castaneda2009", "patras2010"),
            "medium",
            "用 pH 梯度、加速贮存和 LC-MS/MS 测总花青素/单体回收率；色差 ΔE 不能替代化学定量。",
        ))
    if has_ascorbic and (temp >= 60 or aw > 0.8):
        level = _level(heat_load, 1500, 6000)
        effects.append(_effect(
            "ascorbic",
            "抗坏血酸",
            "氧化/热降解，营养保留下降",
            level,
            f"当前热负荷约 {heat_load:.0f} °C·min、aw {aw:.2f}；溶解氧、金属离子和光会促进抗坏血酸氧化，热处理同时影响酶失活与褐变。",
            "预期维生素 C 标签值下降，可能伴随色泽变化；缺氧和螯合金属可减缓损失。",
            _refs("vanboekel2008"),
            "medium",
            "用 HPLC 或滴定法测加工前后抗坏血酸/脱氢抗坏血酸，结合溶解氧和包装顶空验证。",
        ))
    if has_unsaturated_fat and (temp >= 80 or "homogenization" in functions):
        level = _level(heat_load, 3000, 12000)
        effects.append(_effect(
            "lipid_oxidation",
            "不饱和脂质",
            "氧化生成过氧化物、醛酮和异味",
            level,
            f"当前脂肪约 {fat:g}%、热负荷约 {heat_load:.0f} °C·min；不饱和脂肪酸在氧、光、热和金属离子存在下发生自氧化，后续裂解产生己醛等挥发性物质。",
            "预期出现油耗味/青草味，色泽和货架期下降；抗氧化剂和避氧包装只能延缓，不能逆转。",
            _refs("frankel1980"),
            "medium",
            "测过氧化值、p-茴香胺值、TBARS 和顶空己醛；加速贮藏与真实货架期并行。",
        ))
    if has_sucrose and ph <= 4.4 and temp >= 70:
        level = _level(heat_load, 1200, 5000)
        effects.append(_effect(
            "sucrose_inversion",
            "蔗糖",
            "酸催化水解为葡萄糖和果糖",
            level,
            f"当前 pH {ph:g}、约 {temp:g} °C / {time_min:g} min；酸性条件下蔗糖发生酸催化水解，生成等摩尔葡萄糖和果糖。该反应会提高还原糖含量，进而改变甜度、冰点和褐变底物。",
            "预期甜度组合变化、冰点下降，并增加美拉德/焦糖化底物；高酸高糖体系在长期贮存中也可能缓慢发生。",
            _refs("fellows2017", "vanboekel2008"),
            "medium",
            "用 HPLC 测蔗糖/葡萄糖/果糖比例，结合 pH、可滴定酸和贮存温度做动力学验证。",
        ))
    extrusion = system.get("id") == "snack_extruded" or "extrud" in str(system.get("id", "")).lower()
    if has_starch and temp >= 60 and (aw > 0.3 or extrusion):
        level = _level(temp + min(30.0, time_min), 85, 120)
        effects.append(_effect(
            "starch_gelatinization",
            "淀粉",
            "糊化、吸水膨胀和黏度上升",
            level,
            f"淀粉在水分和约 {temp:g} °C 条件下糊化；冷却后直链淀粉可能回生，支链淀粉影响持水和冻融稳定性。",
            "预期黏度/质构改变、持水增加；冷藏后可能变硬、析水，冷冻体系需考虑冰晶和回生。",
            _refs("fellows2017"),
            "medium",
            "用 RVA/快速黏度、DSC、持水和冻融循环验证；配方中的糖/脂会改变糊化温度。",
        ))
    if has_hydrocolloid and temp >= 55 and aw > 0.5:
        effects.append(_effect(
            "hydrocolloid",
            "胶体/稳定剂",
            "水合、凝胶或增稠网络形成",
            "medium" if temp < 90 else "high",
            f"亲水胶体在约 {temp:g} °C 和现有离子/pH 下吸水，可能形成凝胶或增加连续相黏度；过度剪切会破坏网络。",
            "预期提升悬浮/持水和抗融性；过量可能带来黏口、凝胶过强或风味释放下降。",
            _refs("mcclements2015"),
            "medium",
            "用流变、粒径、持水和感官验证；不同胶体的水合温度与离子敏感性差异很大。",
        ))
    if has_gelatin and temp >= 35:
        effects.append(_effect(
            "gelatin",
            "明胶",
            "螺旋解旋/冷却后重组，凝胶强度变化",
            "medium",
            f"明胶在约 {temp:g} °C 下失去三螺旋结构，冷却时部分复性形成弱凝胶；长时间高温会降解并降低凝胶强度。",
            "预期影响弹性、熔点和口感；酸性水果或蛋白酶可能进一步削弱凝胶。",
            _refs("mcclements2015"),
            "medium",
            "测凝胶强度、熔点、黏度和持水；用实际糖/酸/pH 体系验证。",
        ))
    if has_enzyme:
        effects.append(_effect(
            "enzymatic_hydrolysis",
            "蛋白质",
            "酶解产生多肽/氨基酸，苦味和溶解度改变",
            "medium",
            f"体系含蛋白酶/转谷氨酰胺酶；在约 {temp:g} °C、pH {ph:g} 下酶活和底物可及性决定水解度，后续热处理用于灭酶。",
            "预期溶解度/起泡性改变，可能产生苦味肽；过度水解会损失乳化/凝胶功能。",
            _refs("vanboekel2008"),
            "low",
            "测水解度、肽分布、苦味和功能性质；酶活单位、底物批次和灭酶条件必须记录。",
        ))
    if "high pressure processing" in str(system.get("process", "")) or "high pressure" in str(system.get("process", "")):
        effects.append(_effect(
            "high_pressure",
            "蛋白质/微生物",
            "高压诱导蛋白构象变化和微生物失活",
            "medium",
            "高压处理主要破坏非共价相互作用，对共价风味/色素影响较小；实际效果取决于压力、保压时间、温度和基质。",
            "预期延长冷藏货架期并改变蛋白凝胶/乳化性；芽孢和酶可能残留。",
            _refs("bala2015"),
            "medium",
            "用压力-时间-温度日志、微生物挑战试验和酶活/蛋白构象验证。",
        ))
    if "ultrasound" in str(system.get("process", "")) or "ultrasonic" in str(system.get("process", "")):
        effects.append(_effect(
            "ultrasound",
            "蛋白质/脂质",
            "空化剪切导致粒径下降、蛋白改性或脂质氧化",
            "medium",
            "超声空化产生局部高温高压和剪切，可降低乳液粒径、改变蛋白聚集，也可能促进脂质氧化。",
            "预期乳化/溶解性提升或黏度下降；过度处理可能产生异味和蛋白聚集。",
            _refs("chemat2011"),
            "medium",
            "用粒径、流变、蛋白溶解度和脂质氧化指标验证；记录振幅、能量密度和温度。",
        ))

    if system.get("category") == "fermented" or "发酵" in str(system.get("process", "")) or "ferment" in str(system.get("process", "")).lower():
        effects.append(_effect(
            "fermentation",
            "可发酵糖 / 乳酸菌",
            "乳酸发酵产酸，pH 下降并改变质构",
            "medium" if time_min >= 60 else "low",
            f"体系在约 {temp:g} °C 下经历 {time_min:g} min 发酵窗口；乳酸菌利用可发酵糖产生乳酸等有机酸，pH 下降抑制部分腐败菌，但盐度、温度、厌氧和起始菌数决定实际过程。",
            "预期酸味增强、pH 下降、质构软化；亚硝酸盐通常先升后降，生物胺和产气风险取决于卫生与温度控制。",
            _refs("fellows2017"),
            "medium",
            "记录发酵温度/时间、pH 或可滴定酸曲线、盐度和乳酸菌计数；必要时测亚硝酸盐和生物胺，不能只凭配方判断安全。",
        ))
    if not effects:
        effects.append(_effect(
            "low_intensity",
            "主要组分",
            "当前条件下未触发强热/氧化/胶体变化规则",
            "low",
            f"当前约 {temp:g} °C / {time_min:g} min、pH {ph:g}、aw {aw:.2f}；这是规则未触发，不代表没有变化。",
            "预期以混合、水合或温和加工为主；仍需验证微生物、酶活和货架期。",
            _refs("fellows2017"),
            "low",
            "至少实测 pH、aw、微生物和关键功能成分；不能把未触发当作稳定性证明。",
        ))

    macro = [
        {"quality": "质构", "prediction": _texture_prediction(effects, metrics), "basis": "蛋白/淀粉/胶体变化规则"},
        {"quality": "色泽", "prediction": _color_prediction(effects, temp, ph), "basis": "美拉德/花青素/抗坏血酸规则"},
        {"quality": "风味", "prediction": _flavor_prediction(effects), "basis": "美拉德/脂质氧化/酶解规则"},
        {"quality": "营养", "prediction": _nutrition_prediction(effects), "basis": "赖氨酸/维生素/蛋白消化规则"},
    ]
    return {
        "version": VERSION,
        "conditions": {
            "temperature_c": temp,
            "time_min": time_min,
            "ph": ph,
            "aw": aw,
            "protein_pct": protein,
            "sugar_pct": sugar,
            "fat_pct": fat,
            "heat_load_c_min": round(heat_load, 1),
            "system": system.get("id"),
            "category": system.get("category"),
        },
        "effects": effects,
        "macro": macro,
        "summary": _summary(effects),
        "boundary": "以上为机理规则 + 文献先验的方向性预测，不是该配方/设备的实测动力学；温度-时间曲线、传热、pH、离子强度、氧和基质都会改变结果。所有结论需中试和货架期验证。",
        "evidence_note": "每条变化保留文献来源、适用条件和置信度；没有来源的步骤只作为流程，不作为证据。",
    }


def _texture_prediction(effects: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    ids = {item["id"] for item in effects}
    notes = []
    if "thermal_protein" in ids:
        notes.append("蛋白变性/聚集可能提高黏度或凝胶强度")
    if "starch_gelatinization" in ids:
        notes.append("淀粉糊化提高黏度，冷却后可能回生变硬")
    if "hydrocolloid" in ids:
        notes.append("胶体网络提高持水和悬浮")
    if "lipid_oxidation" in ids:
        notes.append("脂质氧化可能破坏乳化体系")
    if not notes:
        notes.append(f"以现有 aw {metrics.get('aw', 0):.2f} 和蛋白 {metrics.get('protein_pct', 0):.1f}% 为基础，质构变化预计有限")
    return "；".join(notes) + "。"


def _color_prediction(effects: list[dict[str, Any]], temp: float, ph: float) -> str:
    ids = {item["id"] for item in effects}
    notes = []
    if "maillard" in ids:
        notes.append("美拉德褐变增强，可能出现烤香/焦香色泽")
    if "anthocyanin" in ids:
        notes.append("花青素可能褪色或色调漂移")
    if "ascorbic" in ids:
        notes.append("抗坏血酸氧化可能促进褐变")
    if not notes:
        notes.append(f"在 {temp:g} °C、pH {ph:g} 下未触发强褐变/色素降解规则")
    return "；".join(notes) + "。"


def _flavor_prediction(effects: list[dict[str, Any]]) -> str:
    ids = {item["id"] for item in effects}
    notes = []
    if "maillard" in ids:
        notes.append("烘焙/坚果/焦香风味增强")
    if "lipid_oxidation" in ids:
        notes.append("可能出现油耗味/青草味")
    if "enzymatic_hydrolysis" in ids:
        notes.append("可能产生鲜味或苦味肽")
    if not notes:
        notes.append("风味变化以原料和温和混合为主")
    return "；".join(notes) + "。"


def _nutrition_prediction(effects: list[dict[str, Any]]) -> str:
    ids = {item["id"] for item in effects}
    notes = []
    if "maillard" in ids:
        notes.append("赖氨酸可利用性可能下降")
    if "ascorbic" in ids:
        notes.append("维生素 C 可能损失")
    if "thermal_protein" in ids:
        notes.append("蛋白消化率可能改变，方向取决于聚集程度")
    if "anthocyanin" in ids:
        notes.append("花青素含量可能下降")
    if not notes:
        notes.append("主要营养指标预计变化较小，但仍需实测")
    return "；".join(notes) + "。"


def _summary(effects: list[dict[str, Any]]) -> str:
    high = [item["change"] for item in effects if item.get("level") == "high"]
    medium = [item["change"] for item in effects if item.get("level") == "medium"]
    if high:
        return "高影响：" + "；".join(high[:3])
    if medium:
        return "中等影响：" + "；".join(medium[:4])
    return "当前条件下主要为低强度变化；不表示无风险。"
