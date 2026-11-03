# v2.0.0 数据与推理审计记录（v2.1.0）

日期：2026-10-20
审计对象：`v2.0.0/backend/datasources.py`、`v2.0.0/backend/food.py`
触发问题：用户质疑“公开数据库 API 到底怎么调用、筛选/预测逻辑是什么、没有实验数据和数据库支撑”。

## 1. 结论

v2.0.0 的声明与实现不一致，必须升级。主要问题不是界面，而是：

1. 查询不区分实体，配体名也会查 UniProt/PDB/STRING/FDC，返回无关结果。
2. 跨库链接按名称/全文命中生成，却放在“交叉证据”下。
3. 文档声称“11 源全部检索”，默认实际只查 9 个，且没有相关性过滤。
4. 配料选择使用随机数；同一输入不能保证可复现。
5. 营养指标来自内联 curated 值，没有真实组成数据库覆盖说明。
6. pH/aw/货架期/感官是规则估算，却容易被综合评分包装成“预测”。
7. 没有实验数据输入，也没有把“未验证”提升为一等输出。

v2.1.0 的处理：保留 v2.0.0 交付；新增实体规划、InChIKey/UniProt xref 验证、USDA 组成快照、确定性选择、约束/区间/证据等级/推理链；不伪造实验结果。

## 2. 实测证据

### 2.1 quercetin 检索

v2.0.0 `search_all("quercetin")` 返回：

| 来源 | 结果 | 问题 |
|---|---|---|
| PubChem | CID 5280343 | 正确 |
| ChEBI | 5 条 | 名称检索，未验证 |
| UniProt | `O00625 Pirin`、`Q7SIC2 Quercetin 2,3-dioxygenase` | 蛋白，不是槲皮素身份 |
| PDB | `1H1I`、`1GQG` | 全文命中，不是配体结构 |
| FDC | `MOONSHOT ENERGY DRINK` | 食品品牌，与槲皮素身份无关 |
| STRING | `PIR` network | 蛋白网络，与槲皮素无关 |
| Europe PMC | 6 条 | 文献语境，正确但非身份 |

根因：`search_all` 对每个 query 调用同一批来源；没有实体分类；`_cross_links` 使用 `pubchem[0] ↔ chebi[0]` 名称候选和 `uniprot[0] ↔ pdb[0]` 全文命中。

### 2.2 UniChem 验证

槲皮素正确 InChIKey：

```text
REFJWTPEDVJJIY-UHFFFAOYSA-N
```

UniChem 返回：

```text
CHEBI:16243
CHEMBL50
DB04216
HMDB0005794
```

这证明 PubChem/ChEBI/ChEMBL 可以在结构标识符层面连接；名称相同不能。

### 2.3 PDB 映射

v2.0.0 用 RCSB 全文搜索 `query`，可能把任意提及该词的条目当作“相关结构”。

v2.1.0 改为：先从 UniProt 取 `uniProtKBCrossReferences` 中 `database=PDB` 的 ID，再生成 PDB 链接。示例 `beta-lactoglobulin` 返回 `1B0O`、`1B8E` 等，来源链为 `uniprot:P02754 → pdb:1B0O`。

### 2.4 STRING

v2.0.0 固定 `species=9606`（人），对牛 β-乳球蛋白等会查错物种；并且直接使用 query 字符串。

v2.1.0 使用 UniProt 的 `taxonId`，调用 `interaction_partners`。`beta-lactoglobulin` 的 P02754 使用牛 taxon `9913`，返回 `PAEP` 相关伙伴。

### 2.5 USDA FDC

- 实时 API：`https://api.nal.usda.gov/fdc/v1/foods/search`，`DEMO_KEY` 会 429。
- 批量数据：`FoodData_Central_sr_legacy_food_json_2018-04.zip`，13,456,312 bytes；解压 JSON 210,758,826 bytes；7,793 条；公共领域/CC0。
- 快照 SHA-256：`70d4235ae3a2bdf48a7b9eaa1286a83fa67b6f3270436c9ce8b008213f500129`。
- v2.1.0 生成 96 配料组成：35 个 FDC 映射、61 个 curated estimate。
- FDC 是参考组成，不是供应商批次；`degraded` 状态表示实时 API 失败后用了本地快照。

### 2.6 MassBank / Open Food Facts

- MassBank 公共端点返回 HTML SPA，不是 JSON。v2.1.0 改为 `link_only`；谱图 accession 仅通过 PubChem 谱图引用。
- Open Food Facts 的 v2 search 全文本行为不稳定（实测返回与 `orange juice` 无关的奶酪/矿泉水）。v2.1.0 使用 legacy `cgi/search.pl` 并做相关性过滤。
- FDC 对 `quercetin` 的搜索会返回能量饮料；v2.1.0 在 compound 实体下不调用 FDC。

## 3. v2.0.0 食品逻辑缺陷

| # | 缺陷 | 证据 | v2.1.0 处理 |
|---|---|---|---|
| 1 | 随机 tie-break | `_pick` 中 `rng.random()`；`_choose` 中 `shuffle` | 删除随机；确定性评分 + ID 排序 |
| 2 | 组成不透明 | `_nutrient` 内联值 | `ingredient_composition.json` + FDC ID/来源/置信度 |
| 3 | 约束只看点估计 | `constraint_met` 布尔 | `constraint_report` + `pass/at_risk/fail` + 区间 |
| 4 | 指标无来源 | `metrics` 无 provenance | `metric_provenance` + 证据等级 |
| 5 | pH/aw 易被误读 | 公式无说明 | 明确 D 级、`at_risk`、必须实测 |
| 6 | 货架期外推 | 单因子公式 | E 级、区间/警告、验证协议 |
| 7 | 选择理由不可审计 | `strategy_note` 文本 | `reasoning` facts/rules/assumptions + `recipe_changes` |
| 8 | 文档源数量不一致 | UI 11，默认 9 | 统一 `datasources.status()` + 查询计划 |
| 9 | 绝对目标被静默忽略 | `钠<300mg` 只匹配 `%`，钠目标仍为默认 1200 mg | 单位感知解析 `mg/g/%`；盐→钠换算；pH 范围写入 `brief.targets` 并新增目标 pH 窗口行 |

## 4. v2.1.0 验收

已执行：

```bash
cd /home/h3c/md-agent/bioforge/v2.1.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest -q
```

结果：`25 passed`。

已实测：

- `quercetin` → entity `compound`；PubChem CID 5280343；InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`；UniChem → `CHEBI:16243`、`CHEMBL50`；不调用 UniProt/PDB/STRING/FDC。
- `beta-lactoglobulin` → entity `protein`；UniProt P02754；PDB xrefs；STRING taxon 9913；不调用 PubChem。
- `orange juice` → entity `food`；FDC 5 条、OFF 5 条、Europe PMC 6 条。
- 设计 API → `package_version=2.1.0`；`constraint_status`、`intervals`、`composition`、`metric_provenance`、`reasoning` 均存在。
- 移动端 390×844：结果页 `scrollWidth == viewport`，无横向溢出；约束卡在移动端改为卡片。
- 绝对目标：`蛋白质 ≥ 12 g/100g`、`钠 < 300 mg/100g`、`pH 4.2–4.6` 均进入 `brief.targets`；`盐 < 1 g/100g` 换算为 400 mg 钠；`低糖，稳定 12 个月` 不会把 12 误读为糖。
- 显式约束设计如实返回 `constraint_status=fail`，并分别列出钠、体系 pH、目标 pH 未达标。

## 5. 仍未解决的边界

- 没有湿实验/供应商数据；A 级证据仍为空。
- FDC SR Legacy 是 2018 编译数据；不是当前批次。
- 61 个配料仍是 curated estimate。
- pH/aw/货架期/感官/微生物仍未验证。
- 在线 API 可能限速、变更或返回错误；缓存与错误隔离不等于数据正确。
- 机制计算（Vina/MD/QM）不能证明配方性能。

这些边界现在写入 `SCIENTIFIC_METHOD.md`、`LIMITATIONS.md` 和每次设计的 `reasoning.validation_required`；不以免责声明替代缺失数据。
