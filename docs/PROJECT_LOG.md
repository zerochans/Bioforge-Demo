# 项目日志

日期：2026-10-20（任务记录，本地时间 UTC+8；任务 ID 使用 UTC）

## 目标

构建一个自然语言驱动的蛋白 / 小分子 / 食品配方设计系统，包含数据库、MD/QM 验证方案、报告/图表/GIF/视频、手机 APK、隐私安全与任务记录。

## 时间线

### 1. 环境与可行性

- 确认主机：Ubuntu，64 核，503 GB RAM，磁盘约 15 GB 可用（97% 已用）。
- Python：`/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python`（3.10.20），已有 RDKit、OpenMM、Biopython、scikit-learn、matplotlib、networkx、reportlab、Pillow、torch。
- 安装 FastAPI、uvicorn、pytest、httpx、requests（`--no-cache-dir`）。
- 验证网络：PyPI、UniProt、KEGG、PubChem、ChEBI、dl.google.com 可用；FPbase 403。
- 安装 Android SDK：cmdline-tools、platforms;android-34、build-tools;34.0.0、platform-tools（约 458 MB）。
- 验证字体：Noto Sans CJK（matplotlib/PIL）、reportlab `STSong-Light`；ffmpeg 可用。

### 2. 数据层

- 建立 `data/build_data.py`，生成：
  - proteins：14 个（avGFP P42212、EGFP、sfGFP、mNeonGreen、mClover3、mCitrine、mTurquoise2、mCherry、mScarlet、TagRFP、UnaG、smURFP、iRFP670、藻蓝蛋白）。
  - protectants：17 个 + 6 组交互项；补充中文备注 `notes_cn`。
  - compounds：12 个，含 RDKit 描述符。
  - matrices：9 个。
  - spectra：18 组近似参考峰。
- 所有数据标注 `evidence_level=curated_prior/literature_approx`，并写入免责声明。
- 重新生成后补充 `notes_cn`，报告/前端显示中文作用与备注。

### 3. 引擎与修复

实现 `backend/engine.py`：解析、候选池、保护剂优化、数字孪生、光谱、配方、逻辑链、provenance、`design/load_job`。

迭代修复：

- 颜色解析避免把“紫外/红外”识别为紫/红。
- 食品语境识别与食品级过滤；研究级候选进入 `alternative_candidates`。
- 酸稳定项符号修正：`acid_eff = acid − 0.10 × ΔTm`。
- 小分子动力学使用 `k_ref=5e-6`、折叠因子 1.0。
- 货架温度默认取基质储存温度。
- 光谱失配与类型不匹配惩罚。
- 评分与警告：无候选达标时明确提示。
- 中文 role/notes 本地化。

### 4. 验证与报告

- `backend/validation.py`：MD/QM/光谱/实验计划、RDKit MMFF94s 快速检查、可选 PySCF。
- `backend/report.py`：9 张图、逻辑图、17 帧 GIF、MP4、HTML、中文 PDF、protocol、CSV、dataset、ZIP、任务清理（保留 30 个）。
- 实测：一次完整设计约 8 秒，任务目录约 3 MB；PDF/GIF/MP4 正常。
- 样例任务：`20261020T015754Z-0feedeb5`（3.1 MB，11 个 artifacts）。

### 5. API 与安全

- `backend/app.py`：FastAPI + Bearer/X-API-Key + 限速 + 安全头 + 日志脱敏 + 路径穿越防护 + SSRF allowlist + 静态站点。
- 修复 CORS 允许 DELETE；前端 DELETE 带 `?confirm=yes-delete-all`。
- 默认 `127.0.0.1:8000`；token 文件 `0600`；反馈库/模型 `0600`。

### 6. 训练闭环

- `backend/training.py`：SQLite WAL、Ridge + StandardScaler、LOO、模型卡、CSV 导出、清空反馈。
- 测试使用 6 条反馈，训练成功；UI 模型卡字段修正为服务端实际返回（`model_version`、`created_utc`、`total`）。

### 7. Web/PWA

- 新增 `web/offline.js`：与服务端同数据/同公式的离线引擎，含 seed 随机、MC 200、光谱、配方、报告 HTML/CSV。
- `web/app.js`：4 个视图（设计/光谱/模型/设置）、在线/离线回退、canvas 图表、导出、AndroidBridge 保存。
- `web/index.html`、`styles.css`、`manifest.webmanifest`、`sw.js`、PNG 图标。
- 修复：光谱波长数组长度 1 → 186/231；移动端标题换行；动态评分环；结果锚点避开 sticky header；中文化配料作用/备注；模型统计字段。
- Chrome headless/CDP 验证：390 px 无横向溢出，8 张 canvas 图表，结果可见，无 JS 错误。

### 8. Android APK

- 手工构建，不依赖 Gradle：aapt2 → javac → d8 → zip → zipalign → apksigner。
- `MainActivity` WebView 加载本地 assets；`AndroidBridge.saveText` 使用系统文件保存对话框；外部链接交给浏览器；返回键处理。
- 网络安全配置只允许本地明文 HTTP；APK 仅申请 INTERNET 权限，`allowBackup=false`。
- 产物：`dist/BioForgeStudio-1.0.0.apk`（150 KB），v2/v3 签名验证通过。
- SHA-256：`244a340a1d890afb954abe58cbb5d330359d5c661b50125a0a5ebee297289b1e`

### 9. MCP 与测试

- `backend/mcp_server.py`：stdio JSON-RPC，`initialize`、`tools/list`、`tools/call`、`ping`；9 个工具；紧凑/完整设计输出；错误 `isError`。
- `tests/test_bioforge.py`：13 项测试（数据、解析、三类设计、光谱、RDKit、报告产物、API 鉴权/设计/下载/CORS、反馈训练、MCP 握手/stdio）。
- 结果：`13 passed`；`node scripts/check_web.js` 通过 4 个离线场景。
- API 在线样例：`POST /api/design` 成功，job `20261020T015754Z-0feedeb5`，11 个 artifacts，中文 role/notes 生效。
- 新增 opencode Skill：`.opencode/skills/bioforge/SKILL.md`，覆盖 API/MCP/离线/APK/安全边界；重启 opencode 后生效。

## 关键决策

| 决策 | 原因 |
|---|---|
| 策展 JSON + 数字孪生，而非黑箱生成 | 可解释、可复现、可审计；明确证据等级 |
| 食品模式自动过滤 | 避免把研究级蛋白/试剂推荐到食品 |
| 离线优先 + 可选服务器 | 隐私、移动可用、弱网可用 |
| 手工构建 APK | 磁盘紧张，避免 Gradle/SDK 额外下载 |
| MCP 手写 JSON-RPC | 不引入额外依赖，便于集成 |
| 反馈只存本地 SQLite | 隐私与可删除；模型卡公开误差 |

## 未完成/后续

- 真实实验数据校准（当前反馈库为空）。
- MD/QM 生产级执行与结构准备（PySCF/OpenMM 可选未跑）。
- 生产签名密钥、应用商店打包、模拟器/真机 UI 自动化。
- 多用户/RBAC、公网部署的 WAF 与审计。
- 更多食品级候选、地区法规库、真实光谱库接入。

---

## 2026-10-20 · v2.0.0

- 创建 `v2.0.0/`，保留 v1 根目录与 APK。
- 生成食品数据：20 体系、96 配料、46 相互作用、14 来源、8 案例。
- 实现 `food.py` 多配方组合、约束/指标/相互作用/工艺/provenance；8 案例均 `constraint_met=True` 且 8 候选。
- 实现 `datasources.py` 11 在线源、24h 缓存、PubChem 质谱、交叉链接；实测 quercetin 9 源 ok。
- 实现 `graph.py` 证据图谱/来源表；修复节点 `kind` 颜色映射与默认检索覆盖。
- 实现 `compute.py` Vina→GROMACS→CP2K；修复 GROMACS 步骤顺序/线程/力场、CP2K 基组/PBE/数据路径；全流程约 2–4 分钟。
- 实现 `auth.py` 登录/会话/密码；`app_v2.py` v2 API、静态站点、artifact 下载。
- 重写 Apple 风格 Web；桌面/移动截图检查通过。
- 构建 APK 2.0.0；19 项测试通过。
- 补 RELEASES/CHANGELOG 与升级/登录/数据源/计算/案例/来源/API 文档。

### 实测

- Vina 1BEB + quercetin：-7.48 kcal/mol。
- GROMACS：EM -1,300,070 kJ/mol；2 ps NVT。
- CP2K：-203.433853 Hartree；32 atoms。
- API：登录、设计、图谱、在线检索、计算 job、artifact 均通过。

---

## 2026-10-20 · v2.1.0

- 创建 `v2.1.0/`，保留 v1.0.0 与 v2.0.0 目录/APK/端口。
- 审计 v2.0 在线证据：quercetin 误连 UniProt/PDB/STRING/FDC；根因是“先查所有源、名称候选当链接”。v2.1 改为实体分类 → 来源规划 → 身份锚点 → 精确映射。
- 新增 `datasources.py` 实体策略：compound / protein / food / complex；新增 UniChem、PDB xref、STRING taxon、FDC 本地回退、OFF legacy、MassBank link-only；删除 `same_compound_candidate`。
- 新增 `composition.py` 与 96 配料组成快照：35 个 USDA FDC SR Legacy、61 个 curated estimate；生成本地 FDC 回退快照与源 SHA-256。
- 重构 `food.py`：去随机、确定性评分；新增 `constraint_report`、`intervals`、`metric_provenance`、`evidence_grade`、`recipe_changes`、`reasoning`；修复 stability 目标未初始化。
- 新增绝对单位解析：`mg`/`g`/`%` 目标、盐→钠换算、pH 范围；`钠<300mg`、`蛋白质≥12g/100g` 进入硬约束，增加目标 pH 窗口行。
- Web：实体选择、查询计划、来源状态、约束卡/表、指标来源、推理链、组成来源列；修复移动端 68 px 横向溢出。
- 版本/端口：v2.1 端口 8002；APK versionCode 3 / versionName 2.1.0；Web 品牌、manifest、Service Worker 缓存更新到 `bioforge-v21-shell-2`。
- 测试：新增实体规划、InChIKey/xref 链接、组成快照、确定性设计、FDC 回退、绝对单位/pH 范围；总计 25 passed。
- 文档：新增 SCIENTIFIC_METHOD、REASONING_AUDIT、UPGRADE_2.1；更新 DATA_SOURCES、PROVENANCE、LIMITATIONS、ARCHITECTURE、API_V2、README、DELIVERY、CHANGELOG、RELEASES。

### 实测

- quercetin：PubChem CID 5280343，InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`；UniChem → CHEBI:16243、CHEMBL50、DB04216；不调用 UniProt/PDB/STRING/FDC。
- beta-lactoglobulin：UniProt P02754；PDB xref；STRING taxon 9913；不调用 PubChem。
- 设计 API：`package_version=2.1.0`；`constraint_status`、`intervals`、`composition`、`metric_provenance`、`reasoning` 均存在。
- 显式约束实测：高蛋白无麸质面包 + 钠<300mg/100g + pH 4.2–4.6 → 蛋白 pass、钠 fail（433 mg/100g）、体系 pH fail、目标 pH fail；结果如实显示未达标。
- 移动端 390×844：设计/证据页无横向溢出；约束卡与查询计划正常。
- APK：`BioForgeStudio-2.1.0.apk`，156,935 bytes，SHA-256 `d681102475f58ef45f7212666bd9618470703ecbd570465da7e29a8989473187`。

---

## 2026-10-22 · v3.2.0 客户级升级（下午）

- 新增 `backend/query_text.py` 共享中英文查询扩展与相关度；`datasources`、`literature` 统一使用；文献按 BM25 + 词面相关度重排。
- 修复体系识别优先级：`detect_system` 改为 (命中数, 关键词长度)，`固体饮料` 不再被 `饮料` 抢先识别。
- 新增 GenBank、KEGG REST、ZINC 连接器；`data/sources.json` 扩到 16 条；`/api/v2/db/status` 增加许可/凭据 `catalog`；设置页新增“数据源与许可”面板。
- 新增 `backend/processing.py` v1.0 与 `food.py` 集成：蛋白热变性、美拉德、花青素、抗坏血酸、脂质氧化、淀粉糊化、蔗糖酸水解、亲水胶体、明胶、酶解、乳酸发酵等规则，逐条附证据/置信度/验证建议。
- 修复挤压膨化淀粉糊化漏触发、低糖固体饮料无法通过糖约束、`renderCandidate` 未定义 `process` 变量。
- 图谱后端增加节点/边语义、稳定 edge ID、citations、置信度、工艺步骤和 `predicts_change` 边、`semantics`。
- 图谱前端改为力导向生长动画：拖拽节点牵拉邻居、背景平移、滚轮/双指缩放、双击证据、边点击关系详情；移除加减号；移动端侧栏左滑收起。
- 3D 改为按真实组分动态控件（蛋白/水/离子/糖链/脂质/配体/其他），默认隐藏水，支持预设和多构象保留选择。
- `data/cases.json` 扩到 17 个案例；新增 `tests/test_query_processing.py`。
- 回归：`38 passed, 1 warning`；`node --check web/app.js`、`node scripts/check_web.js` 通过。
- Service Worker 升至 `bioforge-v32-shell-2`，HTTPS 下也会注册；服务重启 PID 记录在 `runtime/server-v3.pid`（最近为 `52771`）。
- APK 重建：210,246 bytes，SHA-256 `ec95a5c1e4bdb4e0d74bc758657d9867ae7f16c96044ec8fd3fc41e3d8b33b5d`，v2/v3 签名通过。

### 浏览器与 API 复测（2026-10-22 下午）

- Headless Chrome CDP：登录成功；低钠番茄酱设计结果可见且含加工卡片；图谱 48 节点/35 边，双击节点 inspector 正常；PDB 1BEB 组分控件生成“蛋白/多肽 2980、配体/小分子 5、水 591”，水默认未勾选。
- API：`/api/v2/db/search` 对 `槲皮素 稳定性` 路由到 PubChem `quercetin`，获得 CID 5280343、InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`，UniChem 映射正常。
- 修复 `route_queries` 取到通用词（如 `stability`/`binding`）导致 PubChem 查询错误的问题；新增回归测试。

---

## 2026-10-23 · v3.2.1 交付收尾（资源库/PostgreSQL/端口）

- 端口：BioForge 从 8003 迁到 8010；确认 8003 由 RustDesk 监听，解决远端服务被占用问题；`scripts/run_server.sh` 默认 8010。
- 数据库：新增 `bioforge-db`（PostgreSQL 16.15 + pgvector 0.8.7）、`bioforge_pgdata` 卷、`backend/db.py` schema、`scripts/start_postgres.sh` 和 `scripts/sync_postgres.py`；同步 10,000 文献、25,062 文本块、48,544 实体、76,954 边、361 catalog、16 sources、1 owner。
- API：新增 `/api/v3/knowledge/status|search`、`/api/v3/resources`、`/api/v3/library/resolve`；PostgreSQL 不可用时回退 SQLite FTS5。
- 资源库：`data/resources.json` 6 组 38 条（13 可直接查询、3 机构入口）；Web 资源页、快速弹层、搜索筛选、DOI/PMID 解析、SCUT/CARSI 官方入口；明确排除 Sci-Hub，不收集校园密码。
- UI：12 套主题 + auto/light/dark、低干扰背景动画、机构登录说明弹窗（无输入框）、设置页 PostgreSQL 状态卡；资源库标题与来源计数修正。
- 构建：Dockerfile 支持 `PIP_INDEX_URL`/`APT_MIRROR` 清华镜像；compose 增加 db/healthcheck/卷/可选 env_file；`docker compose config` 通过，`docker compose build app` 成功（766 MB），容器 health 3.2.1。
- 版本：3.2.1、Android versionCode 7、SW `bioforge-v321-shell-2`；APK 218,438 bytes，SHA-256 `1cf4bb2e770d58277f49eab647d4348d8bc5002fb6ba7522373eef7521bd2f65`，v2/v3 签名通过。
- 回归：42 passed, 1 warning；Headless Chrome 资源库 38 卡片、12 主题、机构弹窗无输入框、PostgreSQL 状态已连接、DOI 解析成功。
- 限制：embedding 尚未回填（0 向量）；多用户仍为单用户 auth；无真机/AVD；第三方 API 注册/NCBI key 未接入；公网未部署；DOI 解析约 8–21 秒。


## 2026-10-23 · v3.2.2 功能闭环

- 案例扩至 21 个（20 食品体系 + 1 机制案例），资源扩至 7 组 45 条（新增 7 条光谱/结构入口）。
- 多组合 Vina：`receptors`/`ligands` 笛卡尔积最多 12 对，逐对子目录、排名、`screening.csv`、根/逐对 `complex.pdb`；`advanced_scope` 控制 GROMACS/CP2K 代表项或全部。
- 新增默认复合物 MD：RDKit pose 映射 + ACPYPE GAFF2/AM1-BCC + amber99sb-ildn，`genion -neutral` 后 EM + 0.2 ps NVT；首页可选择 `complex`/`protein`，失败时回退并标注。
- Docker `v300-app` 重建，隔离 8011 health 3.2.2；宿主 8010 重启到新代码，8003 RustDesk 保持运行。
- 修复 1GFL 非标准残基导致 Meeko 失败：受体准备加 `-x`；1GFL-槲皮素复测 `-2.562 kcal/mol`。
- 新增 Ollama 助手与 Obsidian 只读笔记 API/UI；问答 8 次/60 秒限流，历史本地保存并月度备份；笔记 2 MB 上限和路径穿越防护。
- 3D 增加 7 种着色、全聚合物序列/配体组分/复合物加载；图谱增加节点/边字典和边 provenance/caveat；核心界面中英切换；12 主题独立纹理。
- 版本 3.2.2 / versionCode 8；初版构建后已由 2026-10-24 最终构建替代，最终 SW/APK 哈希见文末。
- 初版回归：49 passed, 1 warning；复合物任务 `C20261023T091435Z-9e283468` 完成，配体质心漂移 0.218 Å、原子 RMSD 0.338 Å、最近蛋白接触 1.857 Å；Headless Chrome 登录/双语/图谱/3D/复合物/390 px 无溢出、0 JS 异常。

## 2026-10-24 · v3.2.2 最终回归与交付

- 修复 3D 轨迹：新增 `/api/v3/structure/trajectory/{job_id}/{artifact:path}`，仅接受作业内 `.xtc` 且要求同目录 `md.tpr`；GROMACS `select` + `trjconv` 转缓存 PDB。复合物任务 `C20261023T091435Z-9e283468` 实测返回 395,527 bytes、1 帧 PDB。
- 完成英文 UI 收口：资源库 7 组说明、许可/状态、设置页来源目录、表单占位符、证据计划/状态、统计数字和 320–430 px 移动端 8 标签；静态英文页仅保留语言按钮“中”和代码示例“内容”两处有意中文。
- 明确计算输入校验：未识别受体/配体返回可读错误并持久化 `record_rejected`，不再静默替换 1BEB 或 quercetin；`app_v2` 同步修复。
- 助手历史增加文件计数与查询/计数接口回归；`_count_history()` 修复历史计数被 `limit` 截断。
- 回归：`molecule_tools/bin/python -m pytest -q tests` → `51 passed, 1 warning`；`node --check`、`py_compile`、离线检查通过。
- 产物：APK `259,626 bytes`，SHA-256 `87cc368ae8a0dfc7ed6ebb80f9ece6063f4f8e150c6211699264345ecde92a44`，SW `bioforge-v322-shell-5`，v2/v3 签名通过；`v300-app` image `43180eb0d289`，临时 8011 health 3.2.2 后停止。
- 宿主：8010 重启为 PID `386093`，health 3.2.2；8003 RustDesk 保持运行（PID `274622`，会随重启变化）。
- 未完成：真机/AVD、compose 全栈、公网部署、embedding、Ollama 空回答根因。

## 2026-10-25 · v3.2.2 交付最终回归（英文目标量/候选唯一）

- 修复英文目标量解析：`≤8% sugar`、`≥6% dietary fibre` 等名词后置写法与中文对齐；新增膳食纤维下限硬约束、相对减糖（“糖降低 30%”）和糖/纤维目标驱动的质量平衡补足。
- 修复 `_add` 质量平衡：已有配料追加时同步扣减水/主体，避免总量膨胀后归一化稀释目标；`case_low_sugar_jelly` 糖 ≤8%、纤维 ≥6% 中英一致。
- 候选真实性：按配料/占比指纹去重；不足 8 个时生成同功能原料替代变体，带 `variant_of`、`substitution`、`strategy_en`/`strategy_note_en`；20 个食品案例均返回 8 个唯一配方，不再用相同配方重复占位。
- 英文 UI：新增 `膳食纤维下限` 和变体术语/模板；Headless Chrome 20 个食品案例复扫可见 CJK 为 0，图谱页也为 0。
- 回归：`molecule_tools/bin/python -m pytest -q tests` → `57 passed, 1 warning`；`node --check web/app.js|lab.js|sw.js`、`node scripts/check_web.js` 通过。
- 产物：APK `345,711 bytes`，SHA-256 `a084ccdb7794b08938fc4beab868b598eb89e1a95dc5f0232c83f0f81dcb34c4`，SW `bioforge-v322-shell-7`，v2/v3 签名通过；Docker `v300-app` image `5fa04a793880`，约 767 MB，18010 隔离 health 3.2.2 / login 200 后停止。
- 宿主：8010 重启为 PID `2029777`，health 3.2.2；8003 RustDesk 保持运行。
- 未完成：真机/AVD、compose 全栈、公网部署、embedding、Ollama 空回答根因、HADDOCK 引擎接入与执行验证。

## 2026-10-27 · v3.2.2 HADDOCK3 三工作流接入与最终构建

- HADDOCK3 从“仅检测”升级为独立任务管线：`haddock_enabled=true` 创建 HADDOCK3-only 作业，步骤 `resolve`/`prepare`/`haddock`/`report`，强制关闭 Vina/MD/QM。
- 支持 protein–protein、protein–ligand、protein–polysaccharide；受体/伙伴链重写，配体 RDKit 3D PDB，糖链 `NDG/NAG` 识别，活性残基 `ambig.tbl` 与 cmrest/ranair 回退。
- 参数化 `haddock.cfg`：sampling、tolerance、select_top、flexref/emref、cluster、min_population、top_models、clust_cutoff、ncores、seed、timeout、vdW/静电/界面权重、epsilon、cmrest/ranair、mdsteps；修复 flexref/emref 不接受 `inter_rigid` 的配置错误。
- CAPRI 解析：取最高编号 caprieval，过滤 score ≥ 9999 的拒绝/无分数模型；无聚类时 cluster 字段为空；报告仅列实际产物。
- HADDOCK3 UI：30 个输入、三种工作流、英文标签/占位符、a.u. 分数/模型簇表、步骤、CAPRI/日志/3D 产物、CSV 导出；HADDOCK-only 报告只列 `haddock_*` 参数并注明不执行 Vina/GROMACS/CP2K。
- 实测：protein–protein `1BEB+1GFL` 210.6 s（`-33.449`，2/2 簇）、protein–ligand `1BEB+quercetin` 104.5 s（`-0.901`，2/2）、protein–polysaccharide `1BEB+1LMQ:B` 105.4 s（`-14.517`，2/2）；API 三工作流任务和 UI 任务均完成；快速回归 `C20261027T000141Z-62c353e1` 24.4 s（`-23.900`，cluster=false）。
- 浏览器：HADDOCK3 表单 30 输入/英文标签完整，任务卡 a.u. 分数/模型表/步骤/产物正常，`best_model.pdb` 2,516 atoms/2 chains；compute 页英文可见 CJK 0（用户输入的中文 query 除外）；20 个食品案例复扫 `cjk=0`；`case_phycocyanin` 关联计算显示英文案例标题。
- 其他修复：移除 `assistant.py` 重复 `_count_history`；`capabilities` 返回完整 HADDOCK3 defaults/limits；HADDOCK3 任务卡不再误显示“高级 代表项”。
- 回归：`61 passed, 1 warning`；`node --check`、`node scripts/check_web.js` 通过。
- 产物：APK `353,903 bytes`，SHA-256 `a1d64e97bcb89aab39d310acc8d6816a736ad433874052eaf5c8d7f06eb8dd36`，SW `bioforge-v322-shell-10`，v2/v3 签名通过；Docker `v300-app:latest`，约 767 MB，18010 隔离 health 3.2.2 / HADDOCK3 表单 / shell-10 验证后停止。
- 宿主：8010 重启为 PID `3148034`，health 3.2.2；旧 PID `2907373` 已停止；8003 RustDesk 保持运行。
- 未完成：真机/AVD、compose 全栈、公网部署、embedding、Ollama 空回答根因；Docker 镜像不含 HADDOCK3 二进制。

## 2026-10-28 · v3.2.2 质量收口（助手/设计/计算/英文/布局）

- 助手空回答：Ollama 空 content 或仅隐藏 thinking 时按 `num_predict=1600/2400/4096` 重试，前两次 `think:false`、第三次省略；新增隐藏思考回退测试。API 实测 547 字符、`done_reason=stop`、`eval_count=116`、29.4 s。
- 食品设计：`backend/food.py` 新增 `_INGREDIENT_ALIASES`/`_negated_ingredient`/`_requested_ingredients`，目标配料进入每个候选并受上限约束；修复“咖啡”误映射咖啡提取物、负向“不含藻蓝蛋白”仍添加色蛋白、绿/红茶别名缺失。
- 显式生物设计：`backend/engine.py` 显式蛋白设置 `requested_kind=protein`，候选池只返回指定蛋白；非食品模式排除 `food_colorant_protein`，红色荧光蛋白不再选藻蓝蛋白；修复 `warnings` 未初始化。
- 计算：`_resolve` 识别带字母的 4 位 PDB ID；`_manual_compute_query` 支持仅字段提交；`1BEB + quercetin`、`1GFL + caffeine`、`1BEB,1LYZ × quercetin,caffeine`、`whey,1LYZ + SMILES` 均正确；字段任务 `C20261027T021359Z-cefff7b7` 完成 4 对准备/报告。
- 英文：修复 HADDOCK 工具状态、保存 toast、图谱边图例/标题、节点/边 ARIA/title、inspector、关联节点、计算错误、编号步骤和旧任务 query 的中文泄漏；新增 12 个翻译键。展开 42 个任务卡、案例/资源/指南/HADDOCK 后可见 CJK 0。
- 布局与交互：证据提示改 `10px` 正间距；320–390 px 模式切换整行/可换行；资源下方 `1080px` 以下单列；案例、资源组、助手、笔记、HADDOCK/参数/工具面板可折叠；任务卡按 `created_utc` 倒序并支持全部展开/收起；新增“HADDOCK3 运行选择”按钮。
- 视觉：侧栏新增半透明 DNA/蛋白/RNA 里程碑图，浅色自动反相；背景新增星点/星云漂移，尊重 reduced-motion；720 px 以下高度隐藏侧栏图。
- 回归：`64 passed, 1 warning`；`node --check web/app.js|lab.js|sw.js`、`node scripts/check_web.js` 通过；Headless Chrome 320/390/1024/1440 px 无页面级横向溢出。
- 产物：APK `357,999 bytes`，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，SW `bioforge-v322-shell-13`，v2/v3 签名通过；Docker `v300-app:latest` 已重建（约 767 MB），隔离 18010 health 3.2.2 / HADDOCK 按钮 / shell-13 验证后停止。
- 宿主：8010 PID `3630499`，health 3.2.2；旧 PID `3148034` 已替换；8003 RustDesk 未受影响。
- 未完成：真机/AVD、compose 全栈、公网部署、embedding；Docker 不含 HADDOCK3/GROMACS/CP2K/Vina/ACPYPE；iOS 签名包需 macOS/Xcode。

## 2026-11-02 · iOS WKWebView 壳与 shell-13

- 新增 `ios/`：`BioForgeStudio.xcodeproj`、`project.yml`、`AppDelegate.swift`、`Info.plist`、Assets.xcassets、`www/` 离线壳、`ExportOptions.plist.example` 和 `README.md`。
- 原生壳对齐 Android：服务器地址输入、`/api/health` 探测、`WKWebsiteDataStore.default()` Cookie 登录、离线静态预览、外部链接跳转、`UIDocumentPickerViewController` 文件导出、`AndroidBridge` 兼容桥；模拟器默认 `http://127.0.0.1:8010/`。
- 原生服务器标题由“Android 服务器”改为“App 服务器”（英文 “App server”），Web/APK/iOS 共用；新增 `scripts/sync_ios_web.sh` 同步 `web/` 到 `ios/www/`。
- Service Worker 升至 `bioforge-v322-shell-13`；APK 重建 `357,999 bytes`，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，v2/v3 签名通过，内置 `App 服务器` 与 shell-13。
- 回归：`64 passed, 1 warning`；`node --check web/app.js|lab.js|sw.js`、`node scripts/check_web.js` 通过。
- iOS 静态校验：Info.plist、project.yml、scheme/workspace XML、Assets JSON、pbxproj 解析通过；Swift tree-sitter 语法检查无错误；AppIcon 1024×1024 RGB 无 alpha。
- 新增 `.github/workflows/build-ios-unsigned.yml` 与 `ios/ci/build_unsigned_ipa.sh`：macOS runner 构建未签名 `.ipa`；随后 run #1 成功生成 artifact，下载后仍需 Sideloadly/AltStore/正式证书重签。
- 未完成：无签名 `.ipa`，未做模拟器/真机验收；Linux 未本地编译，CI 已生成未签名 artifact。ATS 放宽仅适用于可信局域网，公网必须 HTTPS。

## 2026-11-02 · GitHub Bioforge-Demo 与 iOS CI

- 仓库：<https://github.com/zerochans/Bioforge-Demo>，默认分支 `main`；仓库根目录对应本地 `v3.0.0`。
- 将 Web、FastAPI 后端、数据、脚本、测试、Android 源码、iOS Xcode 工程、文档和部署配置纳入仓库；保留 `dist/BioForgeStudio-3.2.2.apk` 作为下载产物。
- 不提交 `runtime/`、`logs/`、`run1/`、`android/build/`、`android/keystore/`、`ios/build/`、数据库、token、session secret、`ExportOptions.plist` 和 Apple 私钥；仓库级 `.gitignore` 已加入。
- 新增 `.github/workflows/build-ios-unsigned.yml`：macOS 15 runner 执行 Release device build，关闭代码签名，打包 `Payload/BioForgeStudio.app` 为未签名 `.ipa`，上传 artifact `BioForgeStudio-3.2.2-unsigned-ipa`。
- 新增 `ios/ci/build_unsigned_ipa.sh`：macOS 本机/CI 共用构建与打包脚本；Linux 会明确退出并提示需要 macOS/Xcode。
- 新增 `docs/GITHUB_CI.md`：记录仓库结构、安全排除、CI 触发、artifact 下载、Sideloadly/AltStore 自签安装和正式证书边界。
- 校验：`actionlint 1.7.12` 通过；`bash -n ios/ci/build_unsigned_ipa.sh` 通过；workflow YAML 由 PyYAML 读取通过。
- 推送：`main` 从 `4093e8c` 更新到 `d237f3a`；push 自动触发 GitHub Actions。
- CI run #1：[41571174925](https://github.com/zerochans/Bioforge-Demo/actions/runs/41571174925)，2026-11-03T03:16:05Z 创建，03:17:45Z 完成，结论 `success`；job `125704150277` 的 7 个步骤全部成功；artifact `13201382665`，631,892 bytes。
- 限制 workflow 触发路径后推送 `4caa64f`；CI run #2：[41571598315](https://github.com/zerochans/Bioforge-Demo/actions/runs/41571598315)，2026-11-03T03:20:18Z 创建，03:22:32Z 完成，结论 `success`；job `125705503472` 的 7 个步骤全部成功；artifact `13202045851`，631,893 bytes，2026-11-17T03:22:27Z 过期。
- 新增 Release 发布步骤（`contents: write`，`gh release upload --clobber`）；推送 `c751894` 后触发 CI run #3。
- CI run #3：[41572031544](https://github.com/zerochans/Bioforge-Demo/actions/runs/41572031544)，2026-11-03T03:24:39Z 创建，03:27:25Z 完成，结论 `success`；job `125706924794` 核心 8 步及 post 步骤全部成功；artifact `13201921951`，631,894 bytes。
- 公开 Release：[ios-unsigned-3.2.2](https://github.com/zerochans/Bioforge-Demo/releases/tag/ios-unsigned-3.2.2)；asset `BioForgeStudio-3.2.2-unsigned.ipa` 634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`，无需 GitHub 登录即可下载。
- 已下载并校验 Release IPA：26 files / 1,480,631 bytes 解压后；Mach-O arm64；Bundle ID `ai.bioforge.studio`；版本 3.2.2 (8)；iOS 15.0+；`www/sw.js` 为 shell-13；`www/index.html` 含 “App 服务器”；无 `embedded.mobileprovision`、无 `_CodeSignature`，确认未签名。
- 仍未签名、未做模拟器/真机验收；未签名 IPA 不能直接安装，必须用 Apple ID/开发者证书重签。

## 2026-11-03 · BioForge 3.3.0 RAG / 人工监督 / 跨 WiFi

- 新增 `backend/knowledge_agent.py`：LangGraph 状态图 `plan → local_retrieve → graph_expand → assess_quality → external_retrieve → generate → verify → revise`，最多 2 轮回查；本地 10,000 篇 OA 优先，证据不足才调用 Europe PMC OA + OpenAlex。
- 新增 `backend/rag_store.py`：`runtime/rag/rag.sqlite3` 保存运行、审核、反馈和关系权重；回答初始 `pending_review`，支持 approve/reject/rollback/反馈。
- 新增 `/api/v3/rag/*` 与指南页 RAG 面板：质量分级、路由链、证据/许可/链接、图谱标签、逐句核验、警告、审核队列、回滚。
- 新增 RAG 覆盖层标签：`query/local_paper/concept/external_paper` 节点；`retrieves/mentions/co_occurs_with/routes_to_external` 边；共现仅作假设，不替代既有设计图 provenance。
- 新增 `docs/KNOWLEDGE_RAG.md`（关键报告 + Mermaid）、`docs/REMOTE_ACCESS.md`（Tailscale Serve / Cloudflare Tunnel + Access）、`scripts/tailscale_serve.sh`。
- DeepAgent：主进程 Python 3.10 不能安装 `deepagents==0.7.32`（要求 Python ≥3.11、LangChain ≥1.4）；新增 `rag_worker/deep_review.py` 可选独立 worker，未配置时 API 明确 `available=false`。
- 版本 3.3.0；APK `dist/BioForgeStudio-3.3.0.apk` 362,095 bytes / SHA-256 `c8b5fcc1bafa8785f02a370ff4b7e85be8ec874a1e60f2c6ef5c199d423d44cc`，versionCode 9，SW `bioforge-v330-rag-1`；Web 已同步 Android/iOS。
- 测试：`69 passed`；`node --check web/app.js`、`node scripts/check_web.js` 通过；RAG 本地/无证据/外部回退/审核/回滚/API/LangGraph 覆盖。
- 推送 `e834233` 后 iOS CI run [41762199614](https://github.com/zerochans/Bioforge-Demo/actions/runs/41762199614) 成功（job 126352224829，8 步全过）；artifact `13291061904` 637,006 bytes；Release [ios-unsigned-3.3.0](https://github.com/zerochans/Bioforge-Demo/releases/tag/ios-unsigned-3.3.0) 已发布。
- 已下载并校验 3.3.0 未签名 IPA：639,818 bytes，SHA-256 `61b17723935dbd30a99b9c26e77fc74759ae051c9529ebbd1edfb644ac198b10`；Bundle ID `ai.bioforge.studio`，版本 3.3.0 (9)，iOS 15.0+，SW `bioforge-v330-rag-1`；无 `embedded.mobileprovision`/`_CodeSignature`。
- 待完成：iOS/Android 真机验收、DeepAgent worker 安装验收、真实人工审核抽检。
