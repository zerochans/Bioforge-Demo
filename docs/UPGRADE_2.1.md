# 从 v2.0.0 升级到 v2.1.0

## 1. 目录、版本与端口

```text
/home/h3c/md-agent/bioforge/                 # v1.0.0，端口 8000，保持原样
/home/h3c/md-agent/bioforge/v2.0.0/          # v2.0.0，端口 8001，保持原样
/home/h3c/md-agent/bioforge/v2.1.0/          # v2.1.0，端口 8002
```

v2.1 不覆盖 v1/v2.0 的 `backend/`、`web/`、`data/`、`dist/` 或 `runtime/`。三个版本可以同时运行。

## 2. 启动

```bash
cd /home/h3c/md-agent/bioforge/v2.1.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

打开 <http://127.0.0.1:8002/>。

首次启动生成：

- `runtime/auth.json`：PBKDF2 账户
- `runtime/login.txt`：默认 `admin` / `bioforge-demo`（0600）
- `runtime/.session_secret`：会话 HMAC 密钥
- `runtime/.token`：API Bearer token（0600）

生产部署必须修改默认密码并启用 HTTPS。

## 3. API 变化

v2.1 保留 v2.0 的所有路由；新增/扩展的是响应字段，没有删除字段：

- `POST /api/v2/db/search` 新增可选 `entity`（`auto`/`compound`/`protein`/`food`/`complex`）和 `context`；响应新增 `entity`、`plan`、`identity`、`match_basis`、`relevance`、`cross_links`。
- `POST /api/v2/design` 的 `selected` 新增 `constraint_status`、`constraint_report`、`intervals`、`composition`、`metric_provenance`、`evidence_grade`、`recipe_changes`；顶层新增 `reasoning`。
- `GET /api/health` 新增 `food_engine`；`version` 为 `2.1.0`。
- 数据库缓存键已更新，旧 v2.0 缓存不会被误用。

建议客户端检查 `constraint_status`，不要把 `selected` 当作必然满足硬约束；`fail` 表示当前模板/配方无法满足目标，必须调整目标或配方后重算。

## 4. 数据变化

新增 `data/ingredient_composition.json`：96 配料、35 个 USDA FDC SR Legacy 映射、61 个 curated estimate。每条记录含 `source_type`、`confidence`、`fdc_id`、`source_url`、`match`、`nutrients`。

组成来自参考数据库/先验，不是供应商 COA；FDC 是 2018-04 编译快照，不是当前批次。配方营养值仅用于筛选和排序。

## 5. APK 升级

```bash
adb install -r dist/BioForgeStudio-2.1.0.apk
```

- versionCode 3 / versionName 2.1.0，与 v2.0/v1 使用同一签名，可直接覆盖安装。
- 默认连接模拟器宿主 `10.0.2.2:8002`；真机：

```bash
adb reverse tcp:8002 tcp:8002
```

- 然后 App 使用 `http://127.0.0.1:8002/`。
- 明文 HTTP 仅允许 localhost/127.0.0.1/10.0.2.2；远程服务请使用 HTTPS。

## 6. 验证

```bash
cd /home/h3c/md-agent/bioforge/v2.1.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest tests -q
```

结果应为 `25 passed`。重点检查：

- `quercetin` 只返回化合物计划；
- `beta-lactoglobulin` 只返回蛋白计划；
- 同一食品输入连续设计两次，`selected.recipe` 一致；
- 显式 `钠<300mg/100g`、`蛋白质≥12g/100g`、`pH 4.2–4.6` 出现在 `brief.targets`，并在 `constraint_report` 中逐条给出状态。
