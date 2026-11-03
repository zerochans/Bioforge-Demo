# API v3：Model Lab、工具与结构

日期：2026-10-23  
版本：3.2.2  
服务：`backend/app_v3.py`，默认监听 `0.0.0.0:8010`

v3 在 v2 API（食品设计、证据、机制计算）之上新增 `/api/v3/lab/*`、工具路径、结构代理、PostgreSQL 知识库和合法资源目录。v2 端点保持兼容，见 `docs/API_V2.md`。

## 1. 鉴权

除 `/api/health` 和 `/api/auth/login` 外，所有端点需要：

- 浏览器：登录后自动携带 HttpOnly 会话 Cookie；
- 脚本：`Authorization: Bearer <runtime/.token>`。

```bash
BASE=http://127.0.0.1:8010
curl -s -c /tmp/bf-cookies -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' \
  "$BASE/api/auth/login"
```

未登录返回 `401`。登录限速 40 次/分钟/客户端；Lab 写操作另有共享限速（40 次/分钟），训练/重训 8 次/分钟。

## 2. 错误格式

Lab 业务错误：

```json
{"detail": "该数据集包含合成数据。请显式勾选“允许合成数据”后再训练。", "code": "synthetic_opt_in_required"}
```

常见 `code`：

| code | HTTP | 含义 |
|---|---|---|
| `empty_dataset` / `empty_csv` / `no_header` | 422 | 数据为空/无表头 |
| `bad_csv_row` / `duplicate_column` / `bad_json` | 422 | 解析失败 |
| `too_many_rows` | 413 | 超过行数上限 |
| `synthetic_opt_in_required` | 422 | 合成/混合数据未确认 |
| `target_not_numeric` / `target_in_features` | 422 | 目标列不合法 |
| `text_feature` / `unknown_feature` / `high_cardinality` | 422 | 特征不可用 |
| `not_enough_rows` / `not_enough_target` | 422 | 有效样本不足 |
| `constant_target` | 422 | 目标为常数 |
| `gp_too_large` | 422 | GP 超过 800 行 |
| `training_busy` | 429 | 已有训练任务 |
| `dataset_not_found` / `model_not_found` / `run_not_found` | 404 | 对象不存在 |
| `artifact_missing` | 404 | 模型文件丢失 |
| `invalid_id` | 422 | ID 格式非法 |
| `bad_range` / `bad_values` / `bad_space` | 422 | 优化空间非法 |

FastAPI 参数校验错误使用标准 `{"detail": [...]}`，没有 `code`。

## 3. 端点

### 3.1 概览

`GET /api/v3/lab/overview`

```json
{
  "version": "3.2.0",
  "datasets": 1,
  "models": 0,
  "runs": 0,
  "latest_models": [],
  "demo": {
    "available": true,
    "rows": 180,
    "source_type": "synthetic",
    "description": "...",
    "sha256": "cf93df..."
  },
  "policy": {
    "synthetic_requires_opt_in": true,
    "max_import_rows": 20000,
    "max_dataset_rows": 50000,
    "no_automatic_experimental_claims": true
  }
}
```

### 3.2 数据集

`GET /api/v3/lab/datasets` → `{"items": [...]}`（不含完整 schema）。

`POST /api/v3/lab/datasets/demo` → 载入或返回已有演示集。已存在时 `import.created=false`。

`POST /api/v3/lab/datasets`

```json
{
  "name": "2026-10 乳清饮料实测",
  "content": "sample_id,protein_pct,ph,stability_days\nS001,4.2,4.1,45",
  "source_type": "measured",
  "format": "csv",
  "description": "批次 A，n=3",
  "dedupe": true
}
```

- `content` 最大 8 MB；`format` 为 `csv` 或 `json`。
- `source_type`: `measured|literature|simulation|synthetic|mixed`。
- 返回完整数据集对象，并带 `import`：`rows`、`duplicates_skipped`、`format`、`hash`。

数据集对象关键字段：

```json
{
  "id": "DS-...",
  "name": "...",
  "source_type": "measured",
  "row_count": 12,
  "hash": "...",
  "hash_short": "...",
  "is_demo": false,
  "schema": {
    "schema_version": "1.0",
    "columns": [{"name": "ph", "type": "numeric", "role": "numeric", "leakage_risk": false, "...": "..."}],
    "target_candidates": ["stability_days"],
    "feature_candidates": ["protein_pct", "ph"],
    "warnings": []
  },
  "preview": [],
  "recent": [],
  "models": [],
  "training": {"allowed": true, "needs_synthetic_opt_in": false, "min_rows_met": true, "n_rows": 12, "reasons": []}
}
```

`GET /api/v3/lab/datasets/{dataset_id}` → 详情 + 前 8 行 preview + 最近 8 行 recent + 最近模型。

`POST /api/v3/lab/datasets/{dataset_id}/rows` 追加行：

```json
{
  "rows": [{"sample_id": "S013", "protein_pct": 4.4, "ph": 4.2, "stability_days": 58}],
  "source": "manual",
  "notes": "重复 3 次",
  "retrain_model_id": null
}
```

`source` 最长 40 字符；最多 5,000 行/次；追加后重算 schema/hash。返回数据集对象 + `append`，如指定 `retrain_model_id` 还带 `retrain`。

`GET /api/v3/lab/datasets/{dataset_id}/csv` → `text/csv` 下载响应（UTF-8，无 BOM；模板/演示 CSV 带 BOM）。

`DELETE /api/v3/lab/datasets/{dataset_id}?confirm=yes-delete-dataset` → 删除数据集、模型和 artifact；缺少 confirm 返回 400。

`GET /api/v3/lab/template.csv` → 模板 CSV；`GET /api/v3/lab/demo.csv` → 完整演示 CSV。

### 3.3 训练

`POST /api/v3/lab/train`

```json
{
  "dataset_id": "DS-...",
  "target": "stability_days",
  "features": ["system", "protein_pct", "ph"],
  "algorithm": "auto",
  "include_synthetic": false,
  "cv_folds": 5,
  "group_column": "batch"
}
```

- `features` 省略时使用 schema 的 `feature_candidates`（排除目标）。
- `include_synthetic` 对 `synthetic`/`mixed` 数据集必须为 true。
- `group_column` 必须是非缺失、类别数 ≥ 折数的列。
- 返回：

```json
{
  "model": {
    "model_id": "MDL-...",
    "model_version": "lab-20261020-v1",
    "target": "stability_days",
    "features": ["..."],
    "leakage_risk_features": [],
    "algorithm_requested": "auto",
    "algorithm_resolved": "random_forest",
    "metrics": {"r2": 0.84, "mae": 7.3, "rmse": 8.9, "baseline_mae": 19.0, "n": 180, "...": "..."},
    "fold_metrics": [],
    "parity": [],
    "feature_importance": [],
    "feature_stats": {},
    "cv": {"scheme": "KFold", "folds": 5, "group_column": null},
    "warnings": [],
    "caveats": []
  },
  "artifact_sha256": "..."
}
```

`GET /api/v3/lab/models` → `{"items": [...]}`；可选 `?dataset_id=DS-...` 过滤。

`GET /api/v3/lab/models/{model_id}` → `{"model": {...}, "artifact": {"exists": true, "sha256": "...", "size_bytes": 123}, "dataset_id": "..."}`。

`POST /api/v3/lab/models/{model_id}/retrain` → 用当前数据集和原配置重训；新模型带 `parent_model_id`，旧模型保留。

### 3.4 优化

`POST /api/v3/lab/optimize`

```json
{
  "model_id": "MDL-...",
  "direction": "maximize",
  "n_candidates": 5,
  "search_size": 2048,
  "space": {
    "system": {"values": ["yogurt"]},
    "ph": {"min": 4.2, "max": 4.6}
  },
  "seed": 42
}
```

- `n_candidates` 1–20；`search_size` 256–8,000。
- 数值空间只会被收窄到训练范围；类别只能使用训练出现过的值。
- 返回 `run_id`、`observed_best`、`observed_range`、`space`、`warnings`、`notice`、`candidates`。
- 候选字段：`rank`、`candidate_id`、`features`、`predicted`、`uncertainty`、`lower_95`、`upper_95`、`acquisition`、`confidence`。

`GET /api/v3/lab/runs/{run_id}` → 优化批次；`GET /api/v3/lab/runs/{run_id}/csv` → 候选 CSV。

### 3.5 预测

`POST /api/v3/lab/predict`

```json
{
  "model_id": "MDL-...",
  "records": [{"system": "yogurt", "protein_pct": 4.2, "ph": 4.4}]
}
```

返回：

```json
{
  "model_id": "MDL-...",
  "target": "stability_days",
  "predictions": [
    {
      "prediction": 67.2,
      "uncertainty": 6.1,
      "lower_95": 55.2,
      "upper_95": 79.2,
      "warnings": ["ph 高于训练范围（4.5）"]
    }
  ]
}
```

缺失特征会走训练时的填补；未见类别由 OneHotEncoder 忽略并给出 warning。

### 3.6 实验回灌

`POST /api/v3/lab/feedback`

```json
{
  "model_id": "MDL-...",
  "features": {"system": "yogurt", "protein_pct": 4.2, "ph": 4.4},
  "measured": {"stability_days": 70.5},
  "notes": "pH 4.4，3 次重复",
  "retrain": true
}
```

- `features` 必须属于该模型；`measured` 必须包含目标列。
- 追加行 `source=wet_lab`；不覆盖历史。
- `retrain=true` 时返回 `retrain.model`（新模型卡）。
- 返回追加后的数据集对象 + `append` + `feedback`（+ 可选 `retrain`）。

### 3.7 本地工具

`GET /api/v3/tools`

返回当前工具路径、存在状态、可编辑键：

```json
{
  "paths": {
    "gromacs": "/path/to/gmx",
    "gromacs_lib": "/path/to/share/gromacs/top",
    "cp2k": "/path/to/cp2k.ssmp",
    "cp2k_data": "/path/to/share/cp2k/data",
    "mk_prepare_receptor": "/path/to/mk_prepare_receptor.py",
    "mk_prepare_ligand": "/path/to/mk_prepare_ligand.py",
    "obabel": "/path/to/obabel",
    "haddock": "/path/to/haddock3"
  },
  "available": {"gromacs": true, "haddock": true},
  "editable": ["gromacs", "..."],
  "directory_keys": ["gromacs_lib", "cp2k_data"]
}
```

`PUT /api/v3/tools`

```json
{"paths": {"haddock": "/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/haddock3"}}
```

- 只更新提交的键；路径必须是绝对路径。
- 可执行文件必须存在且可执行；`gromacs_lib` / `cp2k_data` 必须是目录。
- 校验失败返回 `422`，`detail` 是键到错误信息的 JSON 字符串。
- 保存到 `runtime/tool_paths.json`（权限 `0600`），返回 `capabilities()`，包含工具版本、默认参数、限制和 HADDOCK 说明。

`GET /api/v2/compute/capabilities` 仍可用，返回同一组工具状态。

### 3.8 结构代理

`GET /api/v3/structure/{pdb_id}`

- 校验 4 字符 PDB ID（大小写不敏感）。
- 服务端从 RCSB 下载 `.pdb` 文本并返回 `chemical/x-pdb`，带 24 小时私有缓存。
- 非法 ID 返回 `422`；上游失败返回 `502`。
- 仅供 3D 查看器加载坐标；不会生成或修改结构。

### 3.9 本地文献库

需要登录；只读查询 `BIOFORGE_LITERATURE_DB` 指向的 SQLite。

`GET /api/v3/literature/stats`

```json
{"available":true,"papers":10000,"open_access":10000,"with_fulltext":12,"chunks":25062,"entities":48544,"edges":76954,"top_concepts":[{"concept":"formulation","papers":5458}],"notice":"Europe PMC OA 元数据与本地 BM25 索引；不是系统综述。"}
```

`GET /api/v3/literature/search?q=quercetin&limit=8`

- `q` 必填，1–200 字符；`limit` 默认 8，最大 50。
- 返回 `items[]`：`id`、`title`、`year`、`doi`、`pmcid`、`license`、`category`、`snippet`（BM25 高亮 `<mark>`）、`tags`、`mesh`、`keywords`、`chemicals`、`abstract`、`url`。
- 数据库不存在或不可读时 `available=false`，不是 500。

`GET /api/v3/literature/topics`

返回主题计数和标签映射；页面用于检索建议，不代表主题分类已经人工审核。

## 4. 示例：完整闭环

```bash
BASE=http://127.0.0.1:8010
C=/tmp/bf-cookies

curl -s -c "$C" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' "$BASE/api/auth/login"

curl -s -b "$C" -X POST "$BASE/api/v3/lab/datasets/demo"
```

从返回中选择 `id`，然后：

```bash
DS=DS-...
MODEL=$(curl -s -b "$C" -H 'Content-Type: application/json' \
  -d "{\"dataset_id\":\"$DS\",\"target\":\"stability_days\",\"algorithm\":\"auto\",\"include_synthetic\":true}" \
  "$BASE/api/v3/lab/train" | python3 -c 'import json,sys; print(json.load(sys.stdin)["model"]["model_id"])')

RUN=$(curl -s -b "$C" -H 'Content-Type: application/json' \
  -d "{\"model_id\":\"$MODEL\",\"direction\":\"maximize\",\"n_candidates\":5}" \
  "$BASE/api/v3/lab/optimize" | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')

curl -s -b "$C" "$BASE/api/v3/lab/runs/$RUN/csv" -o candidates.csv
```

## 5. 说明

- 所有 Lab 端点在 FastAPI 线程池中执行，训练有进程内互斥锁；不要并发触发多个训练。
- 模型 artifact 使用 joblib；只加载本机 `runtime/models/lab/` 下的文件。
- 删除数据集不可恢复；会删除该数据集的全部模型/artifact。
- CSV 导出会对公式型单元格加前缀，降低电子表格注入风险。
- Lab 预测不是实验结论；合成数据模型不能用于真实产品决策。

## v3.2.1 知识库与资源接口

```http
GET /api/v3/knowledge/status
GET /api/v3/knowledge/search?q=quercetin&limit=8
GET /api/v3/resources
GET /api/v3/library/resolve?q=10.3390/polym17131871
```

- `knowledge/status`：PostgreSQL 版本、pgvector 版本、表计数、最近同步和 embedding 状态。
- `knowledge/search`：优先 PostgreSQL `tsvector`；不可用时回退 SQLite FTS5，并在 `backend` 字段标记。
- `resources`：7 组 45 条来源目录、许可、接入状态和官方 URL；`policy.sci_hub=excluded`。
- `library/resolve`：接受 DOI 或 PMID；调用 Crossref、Europe PMC、Unpaywall，返回元数据、合法 OA 位置和 DOI/PubMed/SCUT/CARSI 链接。不返回 Sci-Hub 或付费墙绕过链接。


## v3.2.2 多组合计算、助手与笔记接口

### POST `/api/v2/compute/mechanism`

`options` 新增：

```json
{
  "receptors": "1BEB,1GFL",
  "ligands": "quercetin,curcumin",
  "advanced_scope": "representative",
  "docking_exhaustiveness": 8,
  "md_enabled": true,
  "md_mode": "complex",
  "qm_enabled": false
}
```

- `receptors`/`ligands` 接受逗号分隔的 PDB ID、本地 PDB 路径、配体名称、SMILES 或 SDF 路径；笛卡尔积最多 12 对，超过返回 `422`。
- 不提供 `query` 也可以运行；没有 `receptors`/`ligands` 时仍从 `query`/`design_id` 解析。
- `md_mode`：`complex`（默认，蛋白-配体复合物）或 `protein`（仅蛋白）。复合物模式需要 ACPYPE；拓扑/配体准备失败时回退到蛋白-only，并在 `gromacs.complex_error` 和报告中标注。默认 `em_steps=5000`；首轮未收敛时自动再跑一次 EM。
- `advanced_scope`：`representative`（默认）或 `all`。复合物 MD 按选定 pair 运行；蛋白-only 模式 GROMACS 每唯一受体一次；CP2K 每唯一配体一次。
- 结果含 `pairs[]`、`ranking[]`、`complex_pdb`、`artifacts[]`（`screening.csv`、`report.html`、`pairs/*/complex.pdb`、`pairs/*/gromacs_complex/md.gro` 等）。
- 复合物 MD 的 `result.gromacs` 含 `md_mode`、`ligand_atoms`、`ligand_charge`、`ligand_topology`、`ions`、`ligand_centroid_drift_angstrom`、`ligand_atom_rmsd_angstrom`、`ligand_min_protein_distance_angstrom`、`em_converged`、`em_fmax`、`em_fmax_atom`；首轮 EM 未收敛并自动续跑时，另含 `em_continuation=true`、`em_initial_converged`、`em_initial_fmax`、`em_initial_steps`，且 `em_converged`/`em_fmax` 反映最终 `em2`。`protein-only` 结果不含这些配体字段。

### HADDOCK3-only 计算

`POST /api/v2/compute/mechanism` 设置 `options.haddock_enabled=true` 时，任务只运行 HADDOCK3，不运行 Vina/GROMACS/CP2K；步骤为 `resolve`、`prepare`、`haddock`、`report`。

```json
{
  "query": "1BEB + quercetin protein-ligand docking",
  "options": {
    "haddock_enabled": true,
    "haddock_workflow": "protein-ligand",
    "haddock_receptor": "1BEB",
    "haddock_partner": "quercetin",
    "haddock_active_receptor": "",
    "haddock_active_partner": "1",
    "haddock_sampling": 20,
    "haddock_tolerance": 5.0,
    "haddock_select_top": 5,
    "haddock_flexref": true,
    "haddock_emref": true,
    "haddock_cluster": true,
    "haddock_min_population": 1,
    "haddock_top_models": 4,
    "haddock_clust_cutoff": 1.5,
    "haddock_ncores": 8,
    "haddock_seed": 917,
    "haddock_timeout": 1800,
    "haddock_w_vdw": 1.0,
    "haddock_w_elec": 1.0,
    "haddock_inter_rigid": 1.0,
    "haddock_epsilon": 10.0,
    "haddock_cmrest": true,
    "haddock_ranair": false,
    "haddock_mdsteps_rigid": 500,
    "haddock_mdsteps_cool1": 500
  }
}
```

- `haddock_workflow`：`protein-protein`、`protein-ligand`、`protein-polysaccharide`。
- 蛋白-配体的 `haddock_partner` 可为名称或 SMILES；蛋白-多糖填含糖链 PDB（可带链，如 `1LMQ:B`）。
- 结果 `result.haddock` 含 `score`、`score_unit`、`models[]`（`rank`、`score`、`cluster_id`、`cluster_population`、`artifact`）、`clusters[]`、`best_model`、`capri_ss`、`capri_clt`、`analysis_html`、`config_file`、`inputs_manifest`、`stdout`、`duration_s` 和 `target`。
- score 单位为 a.u.，越低越好；没有实验参考结构时不把 CAPRI RMSD 当作验证。score ≥ 9999 的模型会被过滤。
- 产物：`haddock/best_model.pdb`、`haddock.cfg`、`haddock_inputs.json`、`stdout.log`、`capri_ss.tsv`、`capri_clt.tsv`（若生成）、`haddock_analysis.html`（若生成）。

### GET `/api/v3/assistant/status`

返回 Ollama 是否可用、模型名、endpoint（默认 `127.0.0.1:11434`）、历史条数与失败原因；不返回模型权重或凭据。

### POST `/api/v3/assistant/ask`

```json
{"question":"低糖苹果汁的褐变风险如何控制？"}
```

立即返回 `{id, answer, model, elapsed_seconds, created}`；限流 8 次/60 秒（`429`）。问题与回答写入 `runtime/assistant/history.jsonl`。

### GET `/api/v3/assistant/history?limit=20`

返回本地历史记录，`limit` 默认 20、最大 200。

### GET `/api/v3/notes`

只读列出 Obsidian 目录下的 Markdown：`{exists, root, count, items:[{name,path,modified,size}]}`。默认目录可用 `BIOFORGE_OBSIDIAN_DIR` 覆盖。

### GET `/api/v3/notes/read?path=<relative.md>`

读取单个 Markdown，返回 `{path,name,title,modified,size,text}`；只允许目录内 `.md` 文件，单文件上限 2 MB，路径穿越返回 `422`。

### GET `/api/v3/structure/trajectory/{job_id}/{artifact:path}`

把作业内的 GROMACS `.xtc` 轨迹转换成可直接加载的 PDB。`artifact` 必须是作业 `runtime/compute/<job_id>/` 内的相对路径；当前只接受 `.xtc`，并要求同目录存在 `md.tpr`。接口调用 `gmx select` 与 `trjconv`，结果缓存为 `viewer/<name>-v2.pdb`，使用文件锁避免并发重复转换。

- 成功：`200`，`Content-Type: chemical/x-pdb`，返回多 `MODEL` PDB；默认 `Cache-Control: private, max-age=3600`。
- 路径不存在或作业文件缺失：`404`。
- 路径穿越、非 `.xtc` 或无 `md.tpr`：`403`。
- GROMACS 转换失败：`503`。
- 仅用于轨迹可视化，不代表平衡采样或结合自由能。

### GET `/api/v3/assistant/history?limit=20`

返回 `{items, count}`；`count` 优先使用历史文件计数，不受 `limit` 截断影响；`query` 可过滤问题/回答。`limit` 默认 20、最大 200。
