# 科学方法与计算逻辑（v2.1.0）

本文说明 BioForge Studio 到底做了什么、每一步的证据来源、哪些是公式、哪些是假设，以及哪些结论当前**没有**实验支持。

## 1. 证据等级

| 等级 | 含义 | v2.1 中的例子 |
|---|---|---|
| A | 本产品/本批次的实测或经过验证的预测 | 当前没有；必须由用户中试/实验室产生 |
| B | 权威数据库中可定位的参考记录 | USDA FDC SR Legacy 组成；PubChem/UniProt/PDB/ChEBI/ChEMBL 记录 |
| C | curated 的配料/体系/文献先验 | `ingredients.json`、`food_systems.json`、`interactions.json` |
| D | 基于规则的情景估算 | pH、aw、相互作用方向、工艺适配 |
| E | 规划假设/待验证命题 | 稳定性、货架期、感官、成本、综合评分 |

界面中的“证据等级 C”表示该候选主要依赖 B/C 组成与 C 先验，**不代表**已经过实验验证。

## 2. 在线检索：先分类，再查库

`backend/datasources.py` 的顺序：

1. **实体分类**：`compound`、`protein`、`food`、`complex`。显式 `entity` 优先；否则按蛋白/食品/相互作用词判断；无上下文时默认 `compound`。
2. **来源规划**：只调用与该实体匹配的库（见 `docs/DATA_SOURCES.md`）。
3. **身份锚点**：
   - 化合物：PubChem 名称 → CID + InChIKey。
   - 蛋白：UniProt 名称 → accession + taxon + PDB/AlphaFold xref。
   - 食品：FDC / Open Food Facts + Europe PMC。
4. **跨库验证**：
   - UniChem 用 InChIKey 返回 ChEBI/ChEMBL 等精确 ID。
   - ChEBI/ChEMBL 按精确 ID 取详情；没有精确映射才名称搜索，并标记 `name_search`。
   - PDB 只使用 UniProt `uniProtKBCrossReferences`。
   - MassBank 仅 link-only。
5. **相关性过滤**：FDC/OFF 记录按查询词与标题/类别重叠度过滤；文献记录标记 `literature_search`，不当作身份证明。
6. **审计字段**：每条记录保留 `source`、`id`、`url`、`license`、`retrieved_at`、`match_basis`、`relevance`。

禁止的旧逻辑：

- 不再对配体名调用 UniProt/PDB/STRING/FDC。
- 不再用 PDB 全文检索猜“相关结构”。
- 不再用名称相同生成 `same_compound_candidate`。
- 不再把 MassBank 的 HTML 页面解析成 JSON 记录。

## 3. 配料组成

`data/ingredient_composition.json` 由 `scripts/build_composition.py` 生成：

- 96 个配料；
- 35 个映射 USDA FDC SR Legacy 2018-04；
- 61 个保留 curated estimate，明确 `source_type=curated_estimate`、`confidence=low`；
- 每条记录含 `fdc_id`、`fdc_description`、`source_url`、`match`、`nutrients`；
- 数据源 SHA-256 记录在文件内。

配方营养计算：

```text
protein_pct = Σ (pct_i / 100 × protein_i)
fat_pct     = Σ (pct_i / 100 × fat_i)
sugar_pct   = Σ (pct_i / 100 × sugar_i)
fiber_pct   = Σ (pct_i / 100 × fiber_i)
sodium_mg   = Σ (pct_i / 100 × sodium_i)
```

`pct_i` 是配方百分比；组成按每 100 g 配料计。FDC 是参考组成，不是供应商批次检测；当前没有供应商 COA 或湿实验输入。

## 4. 目标解析与配料选择

### 4.0 目标解析

目标值按单位解析，不是只抓数字：

- `蛋白质 ≥ 12 g/100g`、`蛋白 ≥ 12%` → 蛋白质下限 12%；
- `钠 < 300 mg/100g` → 钠上限 300 mg/100g；
- `盐 < 1 g/100g` → 按 NaCl 含钠 40% 换算为 400 mg 钠/100g；
- `糖 ≤ 5 g/100g` → 糖上限 5%；
- `pH 4.2–4.6` → 情景锚点取中点 4.4，同时保留目标 pH 窗口 [4.2, 4.6]。

无法确定单位或比较符的数字不会被当作目标，避免把“稳定 12 个月”误读成糖 12%。约束报告同时输出体系 pH 窗口和目标 pH 窗口；目标超出体系模板时会明确 `fail`，而不是静默截断。

### 4.1 硬过滤

配料必须先通过：

- 体系允许（`allowed_systems`）；
- 目标禁用项（过敏原、gluten/soy/dairy、vegan）；
- pH 窗口与工艺温度上限；
- 最大添加量 `max_pct`；
- 角色/功能匹配。

### 4.2 确定性评分

合法配料按以下可解释分数排序，不使用随机数：

```text
score = 8 × |功能角色 ∩ 需求角色|
      + 清洁标签加分/合成添加剂扣分
      + 成本指数项
      + 蛋白质/糖/钠/纤维目标项
      + pH 兼容加分
      + 工艺温度兼容加分
      + 组成置信度加分（FDC mapped）
      + 过敏原/禁用项惩罚
```

同分时按 `ingredient_id` 排序，因此同一输入可复现。这个分数是筛选偏好，不是概率或实验测量。

### 4.3 百分数

策略生成后按角色上下限和 `max_pct` 截断，再归一化到 100%。输出中保留每个配料的 `role`、`composition_source`、`fdc_id` 和原始 `pct`。

## 5. pH 与 aw

pH 不是实测：

```text
pH = target_pH
     - (acid_load - base_acid) × 0.06
     + (buffer_load - base_buffer) × 0.04
```

其中 `acid_load = Σ acid_strength_i × pct_i`，酸强度是 curated 常数；结果夹在体系范围附近。它只能用于排序，不能作为配方 pH 标签值。

aw 也不是水活度模型：

```text
aw = 体系 aw 中点
     - Σ aw_effect_i × min(1, pct_i / max_pct_i)
```

结果夹在 0.20–0.995。必须用水分活度仪在 25°C 实测。

## 6. 相互作用

`data/interactions.json` 是 46 条 curated 方向性先验。对配方中同时出现的 `a`、`b`：

```text
effect = curated_effect × max(0.15, min(1, (pct_a + pct_b) / 8))
```

正/负效应只用于风险提示和评分惩罚，不是该基质、该 pH、该热处理条件下的实测值。

## 7. 稳定性、感官、成本、营养、工艺适配

```text
thermal_risk   = 0.18 × 热敏配料数 + max(0, 工艺温度 - 100) × 0.002
microbial_risk = f(aw, pH, 防腐剂, 体系类别, 工艺温度)
color_risk     = f(色素类型, pH, 储存温度, 包装)
stability      = clamp(0.92 - thermal_risk - color_risk - microbial_risk
                       + interaction_score × 0.12 - pH_mismatch × 0.02)
sensory        = 0.62 + 脂肪/糖/风味/胶体项 - 低糖/低钠惩罚
cost           = clamp(1 - Σ(cost_index_i × pct_i/100) / 5 × 1.25)
nutrition      = f(蛋白质/糖/钠/纤维目标)
process_fit    = clamp(1 - 0.16 × 热敏数 - 0.08 × pH 不匹配数)
overall        = Σ 权重_k × 子分数_k，再乘硬约束惩罚
```

权重来自查询目标，默认：

```text
stability 0.30, sensory 0.20, cost 0.15,
nutrition 0.20, clean_label 0.10, process_fit 0.05
```

“综合评分”是候选排序指数，不是成功概率。

## 8. 约束、区间与不确定性

`constraint_report` 对每个硬约束给出：

- 点估计；
- 限制；
- 假设筛选区间；
- `pass` / `at_risk` / `fail`。

pH 有两条约束：体系模板允许窗口，以及用户显式给出的目标窗口。两者都可能 `fail`；这表示当前体系/配方无法满足目标，而不是把 pH 强行夹到目标值。

组成区间默认按配方质量的 FDC 覆盖度取 ±8%（覆盖 ≥70%）或 ±15%；pH ±0.30；aw ±0.03；稳定性 ±0.15。这些是**工程筛选区间**，不是统计置信区间，也不是实验误差。

`constraint_status=at_risk` 表示点估计过线但区间跨过边界，必须实测复核。

## 9. 货架期

```text
factor = 0.55 + 0.45 × stability
       + 0.10 (aw < 0.6)
       + 0.08 (pH < 4.5)
       + 0.06 (有防腐剂)
       - min(0.15, |interaction_net| × 0.6)
predicted_days = clamp(base × factor, 3, base × 1.3)
```

这是情景外推，不是动力学或微生物模型；界面同时输出“必须实测”的警告。

## 10. 机制计算

Vina/GROMACS/CP2K 是独立的分子机制探索：

- Vina 分数不是自由能；
- 2 ps NVT 不是稳定性结论；
- CP2K 单点不含口袋/溶剂效应。

这些结果不能反过来证明配方有效，也不能替代食品实验。

## 11. 必须做的验证

| 指标 | 方法 | 当前状态 |
|---|---|---|
| pH | 校准 pH 计，25°C，滴定 | 未测 |
| aw | 水分活度仪，25°C | 未测 |
| 蛋白质 | Kjeldahl/Dumas/NIR（矩阵验证） | 未测 |
| 糖/钠/脂肪 | HPLC/ICP-OES/离子色谱/GC | 未测 |
| 微生物 | 菌落总数、霉菌酵母、致病菌 | 未测 |
| 感官 | 训练小组、盲样、9 点标度 | 未测 |
| 货架期 | 加速试验 + 实时试验 | 未测 |
| 法规 | 销售地法规、配料表、过敏原、最大使用量 | 未核验 |

## 12. 复现

```bash
cd /home/h3c/md-agent/bioforge/v2.1.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest -q
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python scripts/build_composition.py \
  --sr-json /tmp/opencode/fdc/FoodData_Central_sr_legacy_food_json_2018-04.json
```

FDC 快照可通过以下地址重建：

```text
https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip
```
