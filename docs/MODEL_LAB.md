# Model Lab：数据到下一轮候选

日期：2026-10-22  
版本：BioForge Studio 3.2.0

## 1. 定位

Model Lab 是一个本地优先的小数据表格回归工作台，用来把配方/工艺表和实验结果接成可审计的闭环：

```
CSV/JSON
  → schema 推断与 SHA-256
  → 特征/目标选择
  → 交叉验证（OOF）
  → 模型 artifact
  → EI 候选
  → 湿实验回灌
  → 追加数据 + 重训（新版本）
```

它不是：

- 通用大模型或基础模型微调；
- 机理模型、CFD、分子动力学替代品；
- 食品/药品安全、法规或稳定性结论；
- 自动实验系统；
- 用合成/模拟数据冒充实测证据的工具。

## 2. 数据格式

### 支持格式

- CSV：逗号、分号、制表符、竖线分隔；第一行必须是表头。
- JSON：对象数组 `[{...}, {...}]`，或 `{"rows": [...]}`。
- 单次导入上限 20,000 行；单数据集上限 50,000 行；最大 200 列；单元格最长 4,000 字符。

### 演示模板

`GET /api/v3/lab/template.csv` 返回演示集前 3 行。演示集字段：

```
sample_id, system, protein_type, hydrocolloid,
protein_pct, sugar_pct, fat_pct, ph,
homogenization_bar, pasteurization_temp_c, pasteurization_time_s, storage_temp_c,
stability_days, particle_size_nm, viscosity_mpas, sensory_score
```

演示集 180 行，`source_type=synthetic`，SHA-256：

`cf93df6f479d236244610d5b10a81009928d6b34d21c48eb8d638979a35922ef`

文件由 `scripts/build_lab_demo.py` 以固定 seed 生成；元数据在 `data/lab_demo.meta.json`。

### 来源类型

| source_type | 含义 | 训练要求 |
|---|---|---|
| `measured` | 湿实验/中试/供应商批次实测 | 可直接训练 |
| `literature` | 文献整理 | 可训练，提示核对单位/批次/统计口径 |
| `simulation` | 模拟/计算 | 可训练，提示模拟偏差未校准 |
| `synthetic` | 合成/演示 | 必须显式 `include_synthetic=true` |
| `mixed` | 混合来源 | 必须显式 `include_synthetic=true` |

### schema 推断

- 数值比例 ≥ 90% 且非空的列 → `numeric`；否则为 `categorical`/`text`。
- 唯一值 ≤ 60 的非数值列 → `categorical`；更多 → `text`。
- `id`、`sample_id`、`batch`、`*_id`、`notes` 等 → `identifier`，默认不作特征。
- 名称含 `stability`、`score`、`particle`、`viscosity`、`yield`、`response` 等 → `outcome`/`leakage_risk`；默认不作特征，手工选择会在模型卡记录警告。
- 数值目标候选要求：非标识符、至少 5 个非空值、至少 3 个唯一值。

### 哈希与去重

- 规范化行（按列顺序、稳定 JSON）计算 SHA-256；模型卡记录来源数据集 hash。
- 可选去掉完全相同的行；界面导入默认开启。
- 追加实测会重新计算数据集 hash 和 schema。

## 3. 训练

### 算法

| algorithm | 实现 | 适用 |
|---|---|---|
| `ridge` | Ridge(alpha=1) | 小样本、基线、稳定 |
| `random_forest` | RandomForestRegressor(220 trees) | 中小样本、非线性 |
| `gradient_boosting` | HistGradientBoostingRegressor(350 iters) | 中等样本、表格非线性 |
| `gaussian_process` | GP + RBF + WhiteKernel | ≤ 800 行、小样本不确定性 |
| `ensemble` | RF + HGB + Ridge | ≥ 300 行、默认自动选择 |
| `auto` | 按样本数自动选择 | 默认 |

选择规则：`<25` → GP；`<300` → RandomForest；否则 ensemble。GP 超过 800 行会拒绝或回退。

### 预处理

- 数值：中位数填补 + StandardScaler。
- 类别：常量填补 + OneHotEncoder(handle_unknown="ignore")。
- 缺失目标行不参与训练；所有特征都缺失的行会被丢弃。

### 交叉验证

- 默认 5 折 KFold(shuffle, seed=42)；折数限制 2–10，且不超过样本数。
- 指定分组列时使用 GroupKFold；分组数必须 ≥ 折数，分组列不能缺失。
- 同批次/同配方多行时，建议用 `batch`/`sample_id` 分组，避免同组泄漏。
- 所有指标均为 OOF（折外）预测，不是训练集拟合值。

### 指标

- `r2`、`mae`、`rmse`、`mape_pct`（目标接近 0 时可能不可用）。
- `baseline_mae`：每折用训练集目标中位数预测的 MAE。
- `improvement_vs_baseline`：`1 - mae / baseline_mae`。
- `fold_metrics`：逐折 MAE/RMSE。
- `parity`：最多 300 个 OOF 实测/预测点。
- `feature_importance`：置换重要性（neg_mean_absolute_error，5 次重复，最多 700 行采样）。

### 不确定性

- GP：后验标准差。
- RandomForest：树间预测标准差。
- Ridge/HGB/ensemble：OOF 残差标准差作为 sigma。
- 集成：成员方差与成员均值方差取较大者。
- 输出 `uncertainty`、`lower_95 = mean - 1.96σ`、`upper_95 = mean + 1.96σ`。
- 这些区间未经外部校准；不能当作统计保证。

### artifact 与版本

- 每个模型一个 `runtime/models/lab/<model_id>.joblib` 和一个 `.card.json`。
- SQLite `runtime/lab.db` 存数据集、观测、模型元数据和优化 run。
- artifact SHA-256 写入模型表；模型卡含 `model_version`（如 `lab-20261020-v1`）。
- 重训不覆盖旧模型，新模型 `parent_model_id` 指向旧模型。

## 4. 优化

- 方向：`maximize` / `minimize`。
- 候选数 1–20，搜索点 256–8,000。
- 数值特征在训练范围内均匀采样；类别特征在训练出现过的类别中采样。
- 请求范围超出训练范围时自动收窄并返回 warning；不会外推。
- 采集函数：Expected Improvement：
  `EI = (μ - best) Φ(z) + σ φ(z)`（最大化；最小化取反）。
- 按归一化特征距离做多样性筛选，默认 `min_distance=0.06`；不足时回退补足。
- 置信度：σ ≤ 10% 目标范围 → high；≤ 25% → medium；否则 low。
- 输出包含 `predicted`、`uncertainty`、95% 区间、EI、置信度、特征组合。
- 候选不是实验结果；必须做虚拟复核/湿实验验证。

## 5. 回灌与重训

- 在候选卡点击“记录实测”，输入目标值；备注可写仪器、批次、重复数。
- 追加行 `source=wet_lab`，不覆盖历史记录。
- 可选 `retrain=true`：用原模型配置在新数据集上重训。
- 重训的 `include_synthetic` 固定为 true，因为数据集可能含合成/混合行；模型卡仍记录来源类型并给出警告。
- 删除数据集会级联删除模型和 artifact；界面需二次确认，API 需 `confirm=yes-delete-dataset`。

## 6. 典型限制

- 样本通常远少于真实配方空间；交叉验证误差可能很大。
- 特征间的物理/化学关系不一定能被树模型或线性模型表达。
- 类别特征只能从训练出现过的类别中选；新配料需要新数据。
- 优化是采集函数建议，不是全局最优证明。
- 预测区间未校准，且对分布外配方不成立。
- 合成数据只能验证流程，不能作为产品决策依据。
- 模型/数据版本可追溯，但不等于实验记录合规系统（如 GLP/ELN）。

## 7. 快速示例

```bash
BASE=http://127.0.0.1:8010
curl -s -c /tmp/bf-cookies -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' \
  "$BASE/api/auth/login"

curl -s -b /tmp/bf-cookies -X POST "$BASE/api/v3/lab/datasets/demo"

curl -s -b /tmp/bf-cookies -H 'Content-Type: application/json' \
  -d '{"dataset_id":"DS-...","target":"stability_days","algorithm":"auto","include_synthetic":true}' \
  "$BASE/api/v3/lab/train"
```

完整端点与错误码见 `docs/API_V3.md`。
