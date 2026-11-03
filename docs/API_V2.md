# API v2

Base URL：`http://127.0.0.1:8010`

除 `/api/health`、`/api/auth/login` 外，均需登录 Cookie 或 `Authorization: Bearer <runtime/.token>`。

## Auth

### POST `/api/auth/login`

```json
{"username":"admin","password":"bioforge-demo"}
```

`200` + `Set-Cookie: bioforge_session=...`；失败 `401`；限速 `429`。

### GET `/api/auth/me`

返回当前用户和 `authenticated`。

### POST `/api/auth/logout`

删除 Cookie。

### POST `/api/auth/password`

```json
{"current_password":"...","new_password":"..."}
```

## Design

### POST `/api/v2/design`

```json
{
  "query": "低钠番茄酱，钠降低 30%，pH 3.7",
  "options": {"mode": "food"}
}
```

`mode`：`auto`（默认）、`food`、`biologic`。返回完整设计并保存到 `runtime/designs/<design_id>.json`。

食品目标支持带单位写法：`蛋白质 ≥ 12 g/100g`、`钠 < 300 mg/100g`、`盐 < 1 g/100g`、`糖 ≤ 5%`、`pH 4.2–4.6`。盐按 NaCl→Na 换算；pH 范围会写入 `brief.targets.ph_range`，并生成单独的目标 pH 约束行。

食品结果关键字段：

- `design_id`（F 前缀）
- `mode`：`food_formulation`
- `brief` / `system`
- `selected` / `portfolio`（8）/ `candidates`
- `decision_summary`、`warnings`
- `reasoning`：facts/rules/assumptions/uncertainty/validation_required
- `selected.constraint_report`、`constraint_status`、`intervals`；规则 ID 含 `protein_min`、`sodium_max`、`sugar_max`、`ph_window`、`ph_target`、`gluten_free` 等
- `selected.composition`、`composition.mapped_mass_pct`
- `selected.metric_provenance`、`evidence_grade`、`recipe_changes`
- `evidence`、`provenance`、`logic_chain`
- `formulation`：ingredients/process/qc/controls/storage/packaging/regulatory

### GET `/api/v2/designs/{design_id}`

读取已保存设计。

### POST `/api/v2/graph`

```json
{"design_id":"F...", "online": null}
```

或直接传 `{"design": {...}}`。返回 `nodes`、`edges`、`summary`。

## Food data

### GET `/api/v2/cases`

21 个案例；多数体系返回 8 个候选，果冻等策略较少的体系返回 7 个。

### GET `/api/v2/food/systems`

20 个体系及模板。

### GET `/api/v2/ingredients?q=&limit=`

配料搜索；`limit` 1–200。

## Evidence

### GET `/api/v2/db/status`

15 个在线源规格（含 GenBank/KEGG/ZINC 与 MassBank link-only）；`status()` 返回可查询源和 `catalog` 许可/参考来源。`data/sources.json` 有 16 条 curated 来源。

### POST `/api/v2/db/search`

```json
{
  "query": "quercetin",
  "entity": "auto",
  "sources": ["pubchem", "unichem", "chebi"],
  "context": null
}
```

`entity`：`auto`（默认）、`compound`、`protein`、`food`、`complex`。`sources` 可省略；显式请求不匹配实体的来源会被拒绝并记录在 `plan.rejected_sources`。

返回：

- `entity`、`plan`（分类理由、执行/拒绝来源、规则）
- `identity`（CID、InChIKey、UniChem mappings、UniProt IDs）
- `sources`（每个来源的 status/records/note）
- `records`（含 `match_basis`、`relevance`、`license`、`retrieved_at`）
- `cross_links`（`exact_inchikey`、`uniprot_pdb_xref`、`spectrum_reference`）
- `notice`

示例：`{"query":"quercetin","entity":"compound"}` 返回 PubChem CID 5280343、InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`、`CHEBI:16243`、`CHEMBL50`，不调用 UniProt/PDB/STRING/FDC。

## Compute

### GET `/api/v2/compute/capabilities`

工具列表：Vina、OpenMM、GROMACS、CP2K、AmberTools、ACPYPE、Open Babel。

### POST `/api/v2/compute/mechanism`

```json
{"query":"乳清蛋白与槲皮素对接、短MD和QM","options":{"max_steps":1000}}
```

或：

```json
{"design_id":"F...","options":{}}
```

多受体×多配体：

```json
{"options":{"receptors":"1BEB,1GFL","ligands":"quercetin,curcumin","advanced_scope":"representative","md_mode":"complex"}}
```

`md_mode` 为 `complex`（默认，ACPYPE/GAFF2 复合物 MD）或 `protein`（仅蛋白）。

`receptors`/`ligands` 接受 PDB ID、本地结构、配体名、SMILES 或 SDF 路径；最多 12 对，超过返回 `422`。结果含逐对目录 `pairs/NN_*`、排名 `ranking`、`screening.csv`、`report.html` 与根 `complex.pdb`。

立即返回 `{id, status:"queued", steps:[...]}`。

### GET `/api/v2/compute/jobs`

任务列表（最多按实现排序）。

### GET `/api/v2/compute/jobs/{id}`

`job.json`：status、steps、result、error、target、timestamps。

### GET `/api/v2/compute/jobs/{id}/artifacts/{path}`

下载 artifact（路径穿越防护）。

## Health

```json
{"status":"ok","version":"2.1.0","engine":"1.0.0","food_engine":"2.1.0-food","auth_required":true,"login_required":true}
```

## 错误格式

```json
{"detail":"human-readable message"}
```

常见：`401` 未登录、`404` 不存在、`422` 参数/路径非法、`429` 限速、`500` 服务端错误。
