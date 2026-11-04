# BioForge Studio 3.3.0

GitHub 仓库：<https://github.com/zerochans/Bioforge-Demo>  
iOS CI：[![Build iOS unsigned IPA](https://github.com/zerochans/Bioforge-Demo/actions/workflows/build-ios-unsigned.yml/badge.svg)](https://github.com/zerochans/Bioforge-Demo/actions/workflows/build-ios-unsigned.yml)  
3.3.0 当前构建：Android APK `dist/BioForgeStudio-3.3.0.apk`（versionCode 9，362,095 bytes，SHA-256 `c8b5fcc1bafa8785f02a370ff4b7e85be8ec874a1e60f2c6ef5c199d423d44cc`）；iOS 3.3.0 未签名 IPA 已发布（639,818 bytes，SHA-256 `61b17723935dbd30a99b9c26e77fc74759ae051c9529ebbd1edfb644ac198b10`，[下载](https://github.com/zerochans/Bioforge-Demo/releases/download/ios-unsigned-3.3.0/BioForgeStudio-3.3.0-unsigned.ipa) · [run](https://github.com/zerochans/Bioforge-Demo/actions/runs/41762199614)）。上一版 3.2.2 IPA 仍可下载（634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`）。

把一个产品目标，变成**一组可比较、可追溯、可计算**的食品配方或生物设计方案，并把配方/工艺实验数据接成**训练 → 不确定性 → 贝叶斯优化 → 实测回灌**的本地闭环。

BioForge Studio 3.3.0 在 3.2.2 的基础上，新增 **LangGraph RAG + 知识图谱覆盖层 + 人工审核/回滚/反馈闭环**：先查本地 10,000 篇 OA 与图谱，证据不足才调用 Europe PMC/OpenAlex 公共 OA API，逐句核验后进入审核队列；并提供手机跨 WiFi 访问的 Tailscale/Cloudflare 两种方案。完整逻辑链、标签和限制见 [`docs/KNOWLEDGE_RAG.md`](docs/KNOWLEDGE_RAG.md)。


> **科学边界**：配方、指标、稳定性与机制结果仍是 curated prior、模板估算或计算假设；RAG 回答需人工审核，不能替代系统综述、同行评审、法规批准或湿实验。模型实验室是表格回归 + 采集函数，不是机理模型、通用大模型、法规批准、食品安全结论或湿实验替代品。演示集是 180 行合成数据，训练时必须显式确认。没有湿实验数据时，A 级证据仍为空。

## v3.3.0 重点

- **RAG 路由**：`plan → 本地 BM25 → 图谱扩展 → 质量门控 → 外部 OA → 生成 → 逐句核验 → 回查`，由 LangGraph 状态图执行；证据不足时明确显示 `weak/insufficient` 警告。
- **本地优先**：10,000 篇 OA、25,062 chunks、48,544 实体、76,954 边；只有 12 篇有本地全文，回答会提示“多数仅有题录/摘要”。
- **外部回退**：Europe PMC OA + OpenAlex，24 小时缓存；外部材料标记 `external_needs_review`，不自动升级为已验证。
- **人工监督**：所有回答 `pending_review`；支持 approve/reject/rollback（保留旧记录并生成新 run）、审核备注、修订答案和反馈权重。
- **可审计记录**：SQLite `runtime/rag/rag.sqlite3` 保存 `rag_runs`、`rag_reviews`、`rag_feedback`、`rag_relation_weights`；接口见 `/api/v3/rag/*`。
- **知识图谱标签**：保留既有设计图的 `workflow/curated/verified/model/online/reference`，RAG 覆盖层新增 `query/local_paper/concept/external_paper` 与 `retrieves/mentions/co_occurs_with/routes_to_external`；共现不当作因果。
- **DeepAgent 透明化**：主进程 Python 3.10 不能安装要求 Python ≥3.11 的 `deepagents`；活跃编排是 LangGraph，另提供 `rag_worker/deep_review.py` 可选独立复核，未配置时明确 `available=false`。
- **跨 WiFi 访问**：新增 [`docs/REMOTE_ACCESS.md`](docs/REMOTE_ACCESS.md) 与 `scripts/tailscale_serve.sh`；两种方案为 Tailscale Serve（私网）和 Cloudflare Tunnel + Access（受身份策略保护的 HTTPS）。
- **同步构建**：Web 资源同步到 Android/iOS；APK 3.3.0（versionCode 9）v2/v3 签名通过，Service Worker `bioforge-v330-rag-1`；iOS 3.3.0 CI 与未签名 IPA Release 已完成，未做真机验收。
- **Docker**：`v300-app:latest` 重建为 `9d4514b067d7`（855 MB），隔离 18010 验证 health 3.3.0、`/api/v3/rag/status` 和 LangGraph 静态页；容器默认无宿主文献库，需按 `BIOFORGE_LITERATURE_DB` 挂载。
- **测试**：RAG 单元/API 测试覆盖本地命中、无证据、外部回退、审核/反馈/回滚；全量回归见下。

## v3.2.2 重点

- **案例与资源**：21 个端到端案例覆盖 20 个食品体系与 1 个乳清蛋白-槲皮素机制案例；资源 45 条，新增 NIST、SDBS、HMDB、MetaboLights、GNPS、NMREDATA 等 7 条光谱证据入口。
- **多组合计算**：计算页可输入多个受体 PDB ID/文件与多个配体（名称或 SMILES），笛卡尔积最多 12 对；每对独立 Vina 对接并按亲和力排名，输出 `screening.csv`、`report.html`、根 `complex.pdb` 和 `pairs/*/complex.pdb`。高级 GROMACS/CP2K 默认只跑代表项，可选全部。
- **HADDOCK3 独立任务**：支持蛋白-蛋白、蛋白-配体、蛋白-多糖；可调采样、容差、select top、flexref/emref、聚类、最小簇、输出模型、聚类截断、核数、种子、超时、vdW/静电/界面权重、介电常数和 mdsteps。任务卡显示 a.u. 分数、模型/簇表、CAPRI 表、日志和 3D 模型。
- **真实复合物 MD**：MD 体系可选“蛋白-配体复合物”（默认）或“仅蛋白”；复合物模式用 ACPYPE 生成 GAFF2/AM1-BCC 配体拓扑，与 amber99sb-ildn 蛋白拓扑合并，完成溶剂化、中和、EM 和可配置 NVT，并报告配体漂移/RMSD/最近蛋白接触距离。
- **本地助手与笔记**：接入本机 Ollama（`qwen3.8:27b`），只发送当前问题；问答历史本地保存并月度备份。空回答/仅隐藏思考内容时自动放宽 `num_predict` 并重试，避免返回空气泡。Obsidian 目录只读浏览、2 MB 上限、路径穿越防护。
- **设计与计算正确性**：食品需求中的目标配料（咖啡因、茶提取物、乳清蛋白、槲皮素等）会进入候选配方并受上限约束；显式输入荧光蛋白不再被食品色蛋白替代；计算页支持 `1BEB + quercetin` 一句话解析、PDB ID 识别和仅字段提交（受体/配体/PDB/SMILES）。
- **交互与视觉**：案例、资源分组、助手、笔记、HADDOCK3/参数/工具面板均为可折叠层级；任务卡按时间倒序并支持全部展开/收起；侧栏加入半透明 DNA/蛋白/RNA 里程碑图，背景增加星云/星点动画；窄屏模式切换不再溢出。
- **3D 与图谱**：元素/链/二级结构/残基极性/序列彩虹/B-factor/深度 7 种着色；蛋白与核酸聚合物全序列分组、配体组分；图谱节点类型/边关系字典、每条边显示 `evidence_status`/`basis`/`citations`，无引用边显示 caveat。
- **双语与主题**：核心界面中英切换；英文模式通过 `web/i18n-data.js` 翻译记忆、数字模板和术语替换覆盖设计/案例/计算/图谱/3D 动态内容，12 套主题各有独立纹理并同步卡片/导航/hero。
- **构建**：APK 3.2.2（versionCode 8，357,999 bytes）v2/v3 签名通过；Service Worker `bioforge-v322-shell-13`；配方候选按组成去重，并生成 8 个唯一配方（含显式原料变体）。
- **iOS 客户端**：`ios/` 提供 WKWebView 原生壳、Xcode 工程和 XcodeGen 配置，服务器配置/health 探测、Cookie、离线预览、文件导出与 Android 对齐；`.github/workflows/build-ios-unsigned.yml` 已在 macOS runner 成功生成未签名 `.ipa` artifact；仍需 Sideloadly/AltStore 或正式证书重签后才能安装，当前没有可直接安装的签名 `.ipa`。
- **配方真实性**：英文目标量（`≤8% sugar`、`≥6% dietary fibre`）与中文解析对齐；低糖/高纤目标按配方质量平衡补足；候选按组成去重，不足 8 个时生成可追溯的原料替代变体，不再用相同配方重复占位。

## v3.2.1 重点

- **端口**：BioForge 固定 8010；8003 已释放给 RustDesk。
- **知识库**：PostgreSQL 16.15 + pgvector 0.8.7，10,000 文献、25,062 文本块、48,544 实体、76,954 边；全文检索失败回退 SQLite。
- **资源库**：7 组 45 条合法来源，DOI/PMID 解析、SCUT/CARSI 官方入口；不提供 Sci-Hub，不收集校园密码。
- **界面**：12 套主题 + 明暗模式、低干扰背景、资源快速弹层、设置页数据库状态卡。
- **构建**：Docker 使用清华 apt/PyPI 镜像构建成功；APK 3.2.1（versionCode 7）v2/v3 签名通过。

## v3.2 重点

- **生物设计修复**：修复 `/api/v2/design` 生物模式因 `design_id`/`job_id` 不一致导致的 500；新增专用候选/保护剂/工艺/数字孪生视图。
- **交互式证据图谱**：力导向布局、缩放/平移、节点详情、按类型/连接度/计算状态着色、数据源/推理链过滤。
- **3D 与模拟结果**：PDB/PDBQT 多构象/GRO，卡通/线/球棍/空间填充，元素/链/深度着色，配体显隐、残基点击、单字母序列、PNG 导出；作业参数/结果 JSON 与摘要 CSV 导出。
- **本地文献库**：`/api/v3/literature/*` BM25 检索、统计和标签映射；MesH/作者关键词/化合物写入 Obsidian 标签。
- **应用内指南**：覆盖快速开始、结果解释、图谱、3D、Lab、文献、故障与科学边界。
- **远程部署**：Dockerfile、Compose、Caddy HTTPS、Cloudflare Tunnel 脚本与安全检查表。
- **UI**：动态背景、页面过渡、结果解释折叠卡、移动侧栏外点关闭；保留 reduced-motion。

## v3.1 重点

- **Model Lab**：数据导入 → 自动推断数值/类别/标识符/结果列 → 交叉验证 → 预测与不确定性 → EI 贝叶斯优化 → 实测回灌/重训。
- **来源与审计**：每次导入计算内容 SHA-256；区分 `measured` / `literature` / `simulation` / `synthetic` / `mixed`；合成/混合数据必须显式 opt-in。
- **防泄漏**：`stability_days`、`particle_size_nm`、`viscosity_mpas`、`sensory_score` 等结果列默认不作为特征；手工勾选会在模型卡中记录 `leakage_risk_features` 和警告。
- **可解释评估**：OOF 预测 vs 实测散点、逐折 MAE/RMSE、baseline MAE、置换重要性；模型 artifact 带 SHA-256。
- **带约束优化**：搜索空间只能收窄到训练范围，不自动外推；EI + 多样性筛选输出 5–20 个候选，可导出 CSV。
- **闭环可追溯**：优化候选记录实测后追加到原数据集，可选立即重训；新模型保留父模型链接，旧模型与 artifact 不覆盖。
- **手机局域网直连**：服务监听 `0.0.0.0:8010`；APK 首次启动填写服务器地址并做 `/api/health` 探测，不再依赖 USB 调试或 `adb reverse`。
- **计算参数化**：Vina 采样/盒子/种子、GROMACS EM/MD 步数与温控、CP2K cutoff/SCF、线程与分阶段超时可调；每次任务带参数指纹，超时按进程组终止。
- **工具与 HADDOCK3**：本地工具路径可在 Web 保存；检测 GROMACS、CP2K、Meeko、Open Babel 与 HADDOCK3 `2026.5.0`。HADDOCK3 已接入独立任务；Vina 仍是小分子默认对接引擎。
- **3D 结构查看器**：按 PDB ID 从 RCSB 加载结构，支持旋转、缩放、自动旋转与元素着色；不篡改坐标或假装预测结构。
- **OA 文献流水线**：Europe PMC 元数据 → SQLite FTS5/BM25 → Obsidian 笔记 → 概念/作者/期刊知识图谱；只下载许可明确的 OA 全文。
- **兼容 v3.0**：食品配方、在线证据、机制计算、Model Lab、登录和 v2/v3 API 保持可用。

## 交付物

| 交付物 | 路径 |
|---|---|
| Android APK 3.3.0 | `dist/BioForgeStudio-3.3.0.apk`（362,095 bytes；SHA-256 `c8b5fcc1bafa8785f02a370ff4b7e85be8ec874a1e60f2c6ef5c199d423d44cc`） |
| iOS 工程 3.3.0 | `ios/BioForgeStudio.xcodeproj`（WKWebView 壳；CI 未签名 IPA 639,818 bytes，SHA-256 `61b17723935dbd30a99b9c26e77fc74759ae051c9529ebbd1edfb644ac198b10`） |
| Web / PWA 3.3.0 | `web/index.html` |
| FastAPI 3.3.0（端口 8010） | `backend/app_v3.py` |
| RAG 编排 | `backend/knowledge_agent.py` + `backend/rag_store.py` |
| RAG 报告 | `docs/KNOWLEDGE_RAG.md` |
| 跨 WiFi 访问 | `docs/REMOTE_ACCESS.md` + `scripts/tailscale_serve.sh` + `scripts/public_tunnel.sh` |
| PostgreSQL 16 + pgvector | `docker-compose.yml` / `scripts/start_postgres.sh` / `backend/db.py` |
| 资源库与 DOI/PMID 解析 | `data/resources.json` / `backend/resources.py` / `backend/oa.py` |
| Model Lab 引擎 | `backend/lab.py` |
| Lab 前端 | `web/lab.js` |
| 演示数据 | `data/lab_demo.csv` + `data/lab_demo.meta.json`（180 行合成数据） |
| v1 兼容 API（端口 8000） | `backend/app.py` |
| 食品多配方引擎 | `backend/food.py` |
| 配料组成快照 | `data/ingredient_composition.json` |
| 在线数据库规划/联邦 | `backend/datasources.py` |
| 证据图谱（交互式） | `backend/graph.py` + `web/app.js` |
| 本地机制计算 | `backend/compute.py` |
| 文献/RAG/知识图谱 | `scripts/literature_pipeline.py` + `backend/literature.py` + `backend/knowledge_agent.py` + `backend/rag_store.py` |
| 登录与会话 | `backend/auth.py` |
| 测试 | `tests/`（69 passed，2026-11-03 回归） |
| Docker 镜像 | `v300-app:latest`（`9d4514b067d7`，855 MB，含 LangGraph RAG 依赖；本地文献库需挂载） |
| 远程部署 | `Dockerfile`、`docker-compose.yml`、`deploy/`、`docs/DEPLOYMENT.md` |
| 文档 | `docs/`、`RELEASES.md`、`CHANGELOG.md` |

## 快速开始

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

服务默认监听 `0.0.0.0:8010`（`BIOFORGE_HOST` 可覆盖）。局域网真机访问 `http://<本机LAN-IP>:8010/`。

### 数据库与资源库

```bash
# 启动 PostgreSQL 16 + pgvector，并同步 JSON/SQLite 语料
./scripts/start_postgres.sh
# 查看状态
curl -s -b cookies.txt http://127.0.0.1:8010/api/v3/knowledge/status
```

当前库：10,000 篇文献元数据、25,062 个文本块、48,544 个图谱实体、76,954 条边；`embedding vector(1024)` 已建列但尚未生成向量。文献检索使用 PostgreSQL `tsvector`，失败时回退 SQLite FTS5。完整来源、许可和官方跳转在软件“资源库”；不提供 Sci-Hub 或付费墙绕过链接，不收集校园账号密码。DOI/PMID 解析只调用 Crossref、Europe PMC、Unpaywall 等合法接口。

首次启动会生成：

- 登录：`runtime/login.txt`（默认 `admin` / `bioforge-demo`）
- API token：`runtime/.token`（可选 Bearer 回退）
- 会话密钥：`runtime/.session_secret`
- Lab 数据库：`runtime/lab.db`
- 模型 artifact：`runtime/models/lab/`

打开 <http://127.0.0.1:8010/>，用登录凭据进入 Web 工作台，点击左侧“模型实验室”。

### 五分钟跑通 Lab

1. 打开“模型实验室” → “载入内置演示数据”（180 行合成数据）。
2. 进入“训练与模型”，目标选 `stability_days`；勾选“允许合成/混合数据”。
3. 点“开始训练”。演示集上预期 R² ≈ 0.85、MAE ≈ 7.3（会随 sklearn 版本略有差异）。
4. 进入“贝叶斯优化”，确认搜索空间，生成候选，导出 CSV。
5. 在候选卡点“记录实测”，填一个数值并保存；可选立即重训，观察模型版本与数据集行数变化。

演示数据只验证流程；不能用于真实配方决策。

### 登录与 Token

浏览器登录使用 HttpOnly 会话 Cookie（12 小时）。外部脚本、AutoDL 或 MCP 客户端可使用：

```bash
TOKEN=$(cat runtime/.token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8010/api/v3/lab/overview
```

Token 只用于 API 鉴权，不是数据库密钥，也不会发送给第三方。生产部署请修改默认密码、使用 HTTPS，并限制访问来源。详见 `docs/LOGIN.md`。

### APK

```bash
adb install -r dist/BioForgeStudio-3.3.0.apk
```

APK 是 WebView 客户端。首次启动必须填写服务器地址，例如 `http://10.194.51.41:8010/`，点“测试并保存”会请求 `/api/health` 验证；之后可从登录页或设置页重新打开服务器配置。

- 服务器需先启动，手机与电脑在同一局域网
- 服务监听 `0.0.0.0:8010`；默认登录 `admin` / `bioforge-demo`
- 明文 HTTP 仅用于可信局域网；跨公网部署请使用 HTTPS 反向代理
- Android 模拟器可用 `http://10.0.2.2:8010/`
- Lab 的 CSV 导出通过 Android 文件保存对话框；CSV/JSON 导入使用系统文件选择器

APK 内置 v3 静态壳作为断网提示页；配方设计、在线证据、机制计算、Lab 训练和文献检索需要服务器。完整离线引擎保留在 v1.0.0 APK。

### iOS

```bash
./scripts/sync_ios_web.sh
open ios/BioForgeStudio.xcodeproj
```

iOS 壳是 WKWebView 客户端，首次启动填写服务器地址并请求 `/api/health`；模拟器默认 `http://127.0.0.1:8010/`，真机填写局域网地址。需要在 macOS + Xcode 中选择自己的 Team 才能真机运行或归档；当前没有已签名 `.ipa`。完整说明和验收清单见 `ios/README.md`。

也可以让 GitHub Actions 的 macOS runner 构建未签名 IPA：

1. 打开 <https://github.com/zerochans/Bioforge-Demo/actions/workflows/build-ios-unsigned.yml>。
2. 点击 **Run workflow**。
3. 直接下载未签名 IPA：[BioForgeStudio-3.2.2-unsigned.ipa](https://github.com/zerochans/Bioforge-Demo/releases/download/ios-unsigned-3.2.2/BioForgeStudio-3.2.2-unsigned.ipa)（634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`）；也可从 [run #3](https://github.com/zerochans/Bioforge-Demo/actions/runs/41572031544) 下载 artifact。
4. 用 Sideloadly/AltStore + 自己的 Apple ID 重签安装；正式分发需要 Apple Developer 证书/描述文件。

未签名 IPA 不能直接安装；workflow 不包含任何 Apple 私钥或证书。IPA 已校验为 arm64、Bundle ID `ai.bioforge.studio`、版本 3.2.2 (8)、内含 shell-13，且无 `embedded.mobileprovision`/`_CodeSignature`。Release：[https://github.com/zerochans/Bioforge-Demo/releases/tag/ios-unsigned-3.2.2](https://github.com/zerochans/Bioforge-Demo/releases/tag/ios-unsigned-3.2.2)。

## Model Lab

### 数据与来源

- 支持 CSV（逗号/分号/制表符/竖线）和 JSON（对象数组或 `{"rows": [...]}`），单次最多 20,000 行，单数据集最多 50,000 行。
- 自动推断数值/类别/文本/标识符；`*_id`、`batch`、`sample_id`、`notes` 等默认排除。
- 结果列（名称含 stability、score、particle、viscosity、yield 等）默认排除，避免把同批结果当特征。
- 相同行可去重；导入内容生成 SHA-256，后续模型卡记录该 hash。
- 下载模板：`GET /api/v3/lab/template.csv`，或界面“下载 CSV 模板”。

### 训练

- 目标列必须是数值型；至少 8 行有效目标。
- 算法：Ridge、RandomForest、HistGradientBoosting、GaussianProcess、自动选择、集成。
- 默认 5 折 KFold；有批次/配方分组时可指定分类列，使用 GroupKFold。
- 指标：OOF R²、MAE、RMSE、MAPE、baseline MAE、逐折指标、置换重要性。
- 不确定性：GP 后验方差、随机森林树间方差、其余模型使用 OOF 残差标准差；统一输出 `±` 与 95% 区间。
- 超过训练范围的特征在预测时返回外推警告；优化空间不允许超出训练范围。

### 优化与回灌

- 目标方向：最大化/最小化；候选数 1–20；搜索点 256–8,000。
- 采集函数：Expected Improvement（EI）；按归一化特征距离做多样性筛选。
- 候选包含预测值、不确定性、95% 区间、EI、置信度、特征组合；可导出 CSV。
- “记录实测”追加一行到原数据集，`source=wet_lab`；可选立即重训，新模型通过 `parent_model_id` 追溯旧模型。
- 删除数据集会同时删除其模型和 artifact；操作在界面需二次确认。

详见 `docs/MODEL_LAB.md` 与 `docs/API_V3.md`。

## 它做什么

| 输入 | 输出 |
|---|---|
| “低钠番茄酱，钠降低 30%，pH 3.7” | 20 个食品体系识别、8 个配方、约束审计、组成覆盖、区间、相互作用、工艺、风险、推理链 |
| “高蛋白无麸质面包，蛋白 ≥ 12%” | 无麸质结构替换、蛋白复配、胶体、8 个候选、QC 与法规提醒 |
| “天然色素软糖，无合成色素，pH 3.4” | 天然色素候选、pH/热风险、配方与来源 |
| “分析乳清蛋白与槲皮素的结合机制” | Vina 对接、可配置 GROMACS 蛋白/复合物 EM/NVT、CP2K PBE 单点、参数指纹与 HTML/Markdown 报告 |
| 配方/工艺 CSV + `stability_days` | schema、交叉验证指标、不确定性、EI 候选、实测回灌后的新模型版本 |
| “quercetin” | 化合物计划：PubChem + UniChem + ChEBI + ChEMBL + Europe PMC；不会查 UniProt/PDB/STRING/FDC |
| “beta-lactoglobulin” | 蛋白计划：UniProt + PDB xref + AlphaFold + STRING + Europe PMC；不会把蛋白名送进 PubChem |

### 食品配方

- 20 个食品体系，覆盖饮料、乳品、烘焙、植物基、肉制品、酱料、糖果、冷冻甜品等。
- 10 个策略 → 8 个可比较 portfolio；不是只返回单一答案。
- 硬过滤：体系允许、过敏原、无麸质/无大豆/无乳、pH 窗口、工艺温度、最大添加量。
- 组成：FDC 映射 + curated estimate；每个配料带 `fdc_id`/`source_type`/`confidence`。
- 约束：点估计 + 假设区间 + `pass/at_risk/fail`。
- 输出：配方、工艺、QC、控制点、储存、包装、法规提醒、警告、决策链、`reasoning`、provenance。

### 在线证据

- 实体规划：`compound/protein/food/complex`；显式请求不匹配的来源会拒绝并记录。
- 化合物：PubChem 锚点 → UniChem InChIKey 验证 → 精确 ChEBI/ChEMBL。
- 蛋白：UniProt accession → PDB xref / AlphaFold / STRING（按物种 taxon）。
- 食品：FDC / OFF；FDC 429 时回退本地 SR Legacy 快照。
- 每条记录保留检索时间、记录号、链接、许可、`match_basis`、`relevance`。

### 本地机制计算

- **AutoDock Vina 1.2.7**：Meeko 准备受体/配体，刚性受体对接；exhaustiveness、poses、box、seed 可调。
- **GROMACS 2025.3**：amber99sb-ildn/tip3p，溶剂化、可配置 EM 与 NVT 步数、温度和线程；复合物模式额外使用 ACPYPE GAFF2/AM1-BCC 配体拓扑，失败时明确回退到蛋白-only 并在报告标注。
- **CP2K 2023.2**：配体气相/周期盒 PBE/DZVP-MOLOPT-GTH 单点；cutoff、SCF 步数、线程可调。
- **HADDOCK3 2026.5.0**：蛋白-蛋白/蛋白-配体/蛋白-多糖独立任务；参数化配置、CAPRI 解析、聚类/精修和 a.u. 分数说明。小分子默认仍为 Vina。
- 后台任务写入 `runtime/compute/<job_id>/`，Web 轮询步骤与 artifact；每次运行生成参数指纹，超时按进程组终止。
- 典型耗时约 2–4 分钟（本机，2 线程 MD，8 线程 QM）；参数与体系会显著改变耗时。
- 详见 `docs/COMPUTE.md`。

## 文献与知识图谱

```bash
python scripts/literature_pipeline.py harvest --target 10000 --pdf-limit 12 --build
python scripts/literature_pipeline.py search 'quercetin protein interaction' --limit 8
python scripts/literature_pipeline.py stats
python scripts/literature_pipeline.py enrich --limit 1000
```

- 元数据来自 Europe PMC，仅保留 `OPEN_ACCESS:Y`；SQLite FTS5 提供 BM25 检索和分块 RAG。
- 生成按年份分目录的 Obsidian 笔记，含 DOI/PMCID/许可/摘要/标签；topic 之外还有 `mesh/`、`keyword/`、`chemical/` 标签。
- 知识图谱节点为论文、概念、作者、期刊；边保留 `mentions` / `authored_by` / `published_in` 及证据。
- 2026-10-22 实跑：10,000 篇元数据、10,000 条 Obsidian 笔记、25,062 个文本块、48,544 个实体、76,954 条边；12 篇 OA 全文转为 Markdown；9,197 条有 PMID 记录补全 MeSH/关键词/化合物。
- Europe PMC PDF 端点对脚本返回 403，因此全文优先使用官方 `fullTextXML`；仍保留 PDF 下载与 `pdftotext` 转换路径。
- 详见 `docs/LITERATURE_PIPELINE.md`。使用前仍需逐条核对原文、许可和期刊条款。

## 架构

```
web/ (Apple 风格 SPA)
  ├─ app.js              v2 工作台 / 路由 / 登录
  └─ lab.js              Model Lab

ios/ (WKWebView 客户端)
  ├─ BioForgeStudio.xcodeproj
  ├─ BioForgeStudio/AppDelegate.swift
  └─ www/                由 scripts/sync_ios_web.sh 同步的离线壳

backend/ (FastAPI app_v3.py :8010)
  ├─ auth.py          登录 / Cookie / Bearer
  ├─ lab.py           数据集 / 训练 / 不确定性 / BO / 回灌
  ├─ food.py          食品多配方 + 约束/区间/推理链
  ├─ composition.py   FDC 组成快照加载
  ├─ datasources.py   实体规划 + 在线数据库 + 缓存 + 验证
  ├─ graph.py         证据图谱 / 来源表
  ├─ compute.py       Vina / GROMACS / CP2K / HADDOCK3 任务
  ├─ engine.py        v1 生物设计引擎（保留）
  └─ data.py          数据加载 / 路径 / manifest
```

数据流：

`query → entity plan → 8 candidates → constraint/uncertainty → selected + formulation → graph/datasources/compute → report with audit`

Lab 数据流：

`CSV/JSON → schema + hash → OOF training → model artifact → EI candidates → wet-lab feedback → append + retrain → new model version`

## API 摘要

除 health、login 外均需要会话 Cookie 或 Bearer token。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查、版本、模式、Lab 版本 |
| POST | `/api/auth/login` | 用户名/密码 → HttpOnly Cookie |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/v3/lab/overview` | Lab 统计、最近模型、演示元数据、策略 |
| GET | `/api/v3/lab/datasets` | 数据集列表 |
| POST | `/api/v3/lab/datasets` | 导入 CSV/JSON |
| POST | `/api/v3/lab/datasets/demo` | 载入 180 行合成演示集 |
| GET | `/api/v3/lab/datasets/{id}` | 数据集详情、预览、最近追加、模型 |
| POST | `/api/v3/lab/datasets/{id}/rows` | 追加数据行（可选重训） |
| GET | `/api/v3/lab/datasets/{id}/csv` | 导出 CSV |
| DELETE | `/api/v3/lab/datasets/{id}?confirm=yes-delete-dataset` | 删除数据集与模型 |
| GET | `/api/v3/lab/template.csv` | CSV 模板 |
| POST | `/api/v3/lab/train` | 训练表格回归 |
| GET | `/api/v3/lab/models` | 模型列表 |
| GET | `/api/v3/lab/models/{id}` | 模型卡 + artifact 状态 |
| POST | `/api/v3/lab/models/{id}/retrain` | 用当前数据重训 |
| POST | `/api/v3/lab/optimize` | EI 贝叶斯优化 |
| GET | `/api/v3/lab/runs/{id}` | 优化批次详情 |
| GET | `/api/v3/lab/runs/{id}/csv` | 导出候选 |
| POST | `/api/v3/lab/predict` | 单模型批量预测 + 外推警告 |
| POST | `/api/v3/lab/feedback` | 追加实测，可选重训 |
| GET/PUT | `/api/v3/tools` | 读取/保存本地工具路径并检测 HADDOCK |
| GET | `/api/v3/structure/{pdb_id}` | 代理 RCSB PDB 文本，供 3D 查看器使用 |

v2 接口保持不变，详见 `docs/API_V2.md`。

示例：

```bash
curl -s -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' \
  http://127.0.0.1:8010/api/auth/login

curl -s -b cookies.txt -X POST http://127.0.0.1:8010/api/v3/lab/datasets/demo

curl -s -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"dataset_id":"DS-...","target":"stability_days","algorithm":"auto","include_synthetic":true}' \
  http://127.0.0.1:8010/api/v3/lab/train
```

## 测试

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest tests -q
```

覆盖：v1 生物设计/报告/MCP、v2.1 食品/证据/组成/登录、v3 Lab 导入/推断/合成 opt-in/训练/泄漏标记/优化/预测/回灌/CSV/删除/鉴权、计算参数夹取、工具 API、结构代理与静态资源、生物设计 ID/图谱回归、文献检索、多组合计算、复合物拓扑与 MD 模式。共 64 项。

## 文档

- [RELEASES.md](RELEASES.md) · [CHANGELOG.md](CHANGELOG.md) · [docs/DELIVERY.md](docs/DELIVERY.md)
- [docs/MODEL_LAB.md](docs/MODEL_LAB.md) · [docs/API_V3.md](docs/API_V3.md) · [docs/LITERATURE_PIPELINE.md](docs/LITERATURE_PIPELINE.md) · [docs/UPGRADE_3.1.md](docs/UPGRADE_3.1.md)
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) · [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) · [docs/OPTIMIZATION_LOG_3.2.md](docs/OPTIMIZATION_LOG_3.2.md)
- [docs/SCIENTIFIC_METHOD.md](docs/SCIENTIFIC_METHOD.md) · [docs/REASONING_AUDIT.md](docs/REASONING_AUDIT.md)
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) · [docs/PROVENANCE.md](docs/PROVENANCE.md)
- [docs/API_V2.md](docs/API_V2.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) · [docs/SECURITY.md](docs/SECURITY.md)
- [docs/LOGIN.md](docs/LOGIN.md) · [docs/COMPUTE.md](docs/COMPUTE.md) · [docs/CASES.md](docs/CASES.md)
- [docs/UPGRADE_2.0.md](docs/UPGRADE_2.0.md) · [docs/UPGRADE_2.1.md](docs/UPGRADE_2.1.md)

## 版本

- v1.0.0：生物蛋白/小分子设计、离线引擎、v1 APK；保持原样在 `../`。
- v2.0.0：食品多配方、在线证据、机制计算、登录、Apple 风格 Web、v2 APK；保留在 `../v2.0.0/`。
- v2.1.0：实体规划、UniChem/PDB xref 验证、FDC 组成、确定性配方、约束/区间/证据等级、审计文档；保留在 `../v2.1.0/`。
- v3.0.0：Model Lab、数据/模型版本与回灌闭环、EI 优化、Web/PWA/APK 3.0、29 项测试。
- v3.1.0：LAN 手机配置、参数化计算/指纹/进程组超时、工具与 HADDOCK3 检测、3D 查看器、OA 文献/RAG/知识图谱、APK 3.1、30 项测试。
- v3.2.0：生物设计 500 修复、专用生物结果视图、交互式证据图谱、3D/模拟结果查看与导出、应用内指南、本地文献检索与 MeSH 标签、远程部署方案、APK 3.2、32 项测试。

## 许可与数据

代码为本地研究与演示用途。数据来源和许可逐条写在 `data/sources.json`、在线记录和报告中；使用前请核对原始数据库条款。配方、模型预测与计算结果不构成法规、安全或实验批准。
