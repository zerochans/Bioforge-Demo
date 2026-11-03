# 来源、追溯与科学边界（v2.1.0）

## 设计结果的 provenance

每个食品设计包含：

```json
{
  "engine_version": "2.1.0-food",
  "package_version": "2.1.0",
  "created_utc": "...",
  "mode": "food_formulation",
  "datasets": {
    "ingredient_composition.json": {
      "sha256_16": "...",
      "items": 96,
      "schema_version": "2.1",
      "source_type": "usda_fdc_sr_legacy + curated_estimate"
    }
  },
  "parameter_provenance": [],
  "citations": [],
  "limitations": []
}
```

- `datasets`：每个本地数据文件的内容哈希（前 16 位）、字节数、条目数、schema 与来源类型。
- `parameter_provenance`：pH、aw、组成、稳定性、货架期、综合评分的来源与置信度。
- `citations`：方法、食品化学、胶体、法规与方法学参考。
- `limitations`：明确数字原型不是实测/法规结论。
- `reasoning`：facts/rules/assumptions/uncertainty/validation_required。

## 配料级来源

`formulation.ingredients[]` 与 `selected.ingredients[]` 带：

- `source_type`：`usda_fdc_sr_legacy` 或 `curated_estimate`。
- `confidence`：low/medium/high（FDC mapped 通常 medium；估算 low）。
- `composition`：protein/fat/sugar/fiber/sodium per 100 g。
- `fdc_id`、`fdc_description`、`composition_match`、`composition_note`。
- `evidence`、`notes_cn`、`typical_range`、`max_pct`、`e_number`、`allergen`、`food_additive`。

## 组成快照

`data/ingredient_composition.json`：

- 96 个配料；35 个 USDA FDC SR Legacy 映射；61 个 curated estimate。
- 主数据源：`FoodData_Central_sr_legacy_food_json_2018-04.zip`。
- SHA-256：`70d4235ae3a2bdf48a7b9eaa1286a83fa67b6f3270436c9ce8b008213f500129`。
- 7,793 条 SR Legacy 记录；公共领域/CC0。
- 生成脚本：`scripts/build_composition.py`。
- 明确的限制：编译参考数据，不是供应商批次、COA 或湿实验。

## 指标来源

| 字段 | 来源 | 证据等级 |
|---|---|---|
| `protein_pct` / `fat_pct` / `sugar_pct` / `fiber_pct` / `sodium_mg` | 组成快照质量加权 | B/C |
| `ph` | 目标 pH + 酸/缓冲负荷规则 | D |
| `aw` | 模板 + aw_effect 规则 | D |
| `stability` | 热/微生物/色素/pH/相互作用启发式 | E |
| `shelf_life` | 模板 × 稳定性修正 | E |
| `sensory` / `cost` / `nutrition` / `process_fit` | curated 规则 | D/E |
| `overall_score` | 六项加权 + 约束惩罚 | E |

`selected.metric_provenance` 和 `evidence_grade` 会随每个候选返回；界面在指标卡和“指标是怎么来的”中显示。

## 在线记录

每条在线记录保留：

- 数据源与记录号（如 PubChem CID、ChEBI ID、UniProt accession、PDB ID）。
- 原始 URL。
- 许可。
- 检索时间。
- `match_basis`：`pubchem_name_exact`、`exact_inchikey`、`uniprot_search`、`uniprot_pdb_xref`、`food_search`、`literature_search`、`local_fdc_snapshot` 等。
- `relevance`：0–1 的查询相关性，不是身份置信度。

跨库链接只使用：

- `exact_inchikey`（UniChem 验证）
- `uniprot_pdb_xref`
- `spectrum_reference`

v2.0.0 的 `same_compound_candidate` 和 `sequence_structure_candidate` 已删除。

在线摘要只用于线索；法规、结构和安全性必须回到原始记录核验。

## 证据图谱

`POST /api/v2/graph` 生成：

- 节点：design、food_system、strategy、ingredient、target/constraint、data_source、literature、online_record。
- 边：`targets_system`、`selects_strategy`、`uses`、`interaction`、`constraint`、`supported_by`、`candidate_evidence`、跨库链接。
- 摘要：节点/边/配料/相互作用/在线记录/curated 来源计数。

图谱是“证据组织图”，不是因果证明或定量网络模型。

## 计算 provenance

`report.md`/`report.html` 与 `job.json` 保留：

- 工具版本与可执行路径。
- 受体 PDB ID、配体名称/SMILES。
- Vina box、exhaustiveness、每个 mode 的 affinity。
- GROMACS 力场/水模型、步数、dt、EM 势能。
- CP2K 泛函/基组/截断/盒尺寸/SCF 能量。
- 步骤时间戳与日志/artifact 路径。

## 科学边界（必须保留）

- 配方与指标是 curated priors/模板估算，不是实测。
- 法规状态、最大使用量、过敏原标签需按销售地法规逐项核验。
- 微生物安全、货架期、感官必须中试/实测。
- Vina 打分不是自由能；2 ps MD 不是稳定性证明；CP2K 配体单点不含口袋。
- 在线数据库可能延迟、缺项或名称匹配错误。
- 无湿实验数据时，A 级证据为空；不得把 B/C/D/E 包装成已验证。
- 任何食品/临床/法规用途都需要有资质团队复核。
