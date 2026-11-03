# Changelog

## 3.2.2 — 2026-10-25

### Added

- 案例库扩至 21 个端到端案例，覆盖 20 个食品体系 + 1 个乳清蛋白-槲皮素机制案例；资源目录扩至 7 组 45 条，新增 NIST WebBook、SDBS、HMDB、MetaboLights、GNPS、NMREDATA、PDB CCD 光谱/结构证据入口。
- HADDOCK3 独立任务：`options.haddock_enabled=true` 时走 `resolve`/`prepare`/`haddock`/`report` 管线，强制关闭 Vina/MD/QM；支持蛋白-蛋白、蛋白-配体、蛋白-多糖，暴露采样、容差、select top、flexref/emref、聚类、最小簇、输出模型、聚类截断、核数、种子、超时、vdW/静电/界面权重、介电常数和 mdsteps。
- HADDOCK3 输入/结果：受体/伙伴链重写、配体 RDKit 3D PDB、糖链 `NDG/NAG` 识别、活性残基 `ambig.tbl` 与 cmrest/ranair 回退；解析最高编号 caprieval、过滤 score ≥ 9999，复制 `best_model.pdb`、`capri_ss.tsv`、`capri_clt.tsv`、`haddock_analysis.html`，写 `haddock_models.csv` 与 HADDOCK-only 报告。
- HADDOCK3 UI：新增独立卡片/表单、三种工作流、30 个输入、英文标签/占位符、a.u. 分数/模型簇表、CAPRI/日志/3D 产物、CSV 导出和中文步骤。
- 多受体×多配体对接：`/api/v2/compute/jobs` 接受 `receptors`/`ligands`（PDB ID、本地文件、配体名或 SMILES），笛卡尔积最多 12 对；每对独立准备/对接，按 Vina 亲和力排名，生成 `pairs/NN_*/complex.pdb`、根 `complex.pdb`、`screening.csv`、`report.html`。
- `advanced_scope`（`representative`/`all`）：复合物 MD 按选定 pair 运行；蛋白-only 模式按唯一受体、CP2K 按唯一配体运行。默认代表项，避免重复计算。
- `/api/v3/assistant/status|ask|history`：本机 Ollama（`qwen3.8:27b`）问答，限流 8 次/60 秒，历史写入 `runtime/assistant/history.jsonl` 并月度备份；系统提示禁止凭据、Sci-Hub 和编造结果。
- `/api/v3/notes`、`/api/v3/notes/read`：Obsidian 只读 Markdown 列表/读取，默认 `/media/h3c/Win11Pro X64/data/literature/obsidian/00-BioForge`，2 MB 上限和路径穿越防护。
- 复合物 MD 默认 EM 步数提高到 5000，并在首轮未收敛时自动追加一次 EM；实测 1BEB+quercetin 首轮 5000 步 Fmax 仍 5707.8，二次 244 步收敛到 456.8。
- 真实受体-配体复合物 MD：`md_mode=complex`（默认）用 RDKit 把对接 pose 映射到配体模板，ACPYPE 生成 GAFF2/AM1-BCC 拓扑，与 amber99sb-ildn 蛋白拓扑合并，经溶剂化、`genion -neutral`、EM 和短 NVT 运行；报告配体电荷、原子数、离子、EM/MD 势能、配体漂移/RMSD/最近蛋白接触距离。ACPYPE/拓扑失败时显式回退到蛋白-only。
- 3D 查看器新增二级结构、残基极性、序列彩虹、B-factor、深度着色；蛋白/核酸全序列按链分组，配体单独列出；支持作业 `complex.pdb` 直接加载。
- 图谱节点类型/边关系字典、图例点击说明；边级 `evidence_status`、`basis`、`citations`，非 workflow 且无引用时显示 caveat。
- 核心界面中英文切换（`localStorage bioforge-lang`）；资源库分组/说明、设置页来源目录、表单占位符和移动端 8 个底部标签完成英文化；动态内容由 `i18n-data.js`、`app.js` 术语/模板和英文 `strategy_en` 字段覆盖。
- `GET /api/v3/structure/trajectory/{job_id}/{artifact:path}`：把作业内 `.xtc` 通过 GROMACS `trjconv` 转为缓存 PDB，供 3D 查看器直接加载；要求同目录 `md.tpr`，拒绝路径穿越和非 `.xtc`。
- 12 套主题独立背景纹理并同步卡片、导航和 hero；新增 DNA/蛋白/RNA 科学背景 SVG。
- 配方候选去重与变体：先按配料/占比指纹去重，再对不足 8 个的组合生成同功能原料替代变体；变体带 `variant_of`、`substitution` 和英文标签，避免相同配方重复占位。
- 英文目标量解析：支持 `≤8% sugar`、`≥6% dietary fibre` 等名词后置写法；新增膳食纤维下限硬约束、低糖相对减糖（如“糖降低 30%”）和糖/纤维目标驱动的质量平衡补足。

### Changed

- 食品/机制路由识别新增“果汁、乳、奶、蛋糕、香肠、果冻、泡菜、保鲜、膜、谷物棒”等词；含“对接、结合机制、短 MD、QM”等机制词时优先走生物机制。
- 受体准备增加 `-x/--delete_bad_res`，修复 1GFL 等含非标准残基结构导致 Meeko 模板匹配失败的问题；1GFL-槲皮素复测完成，最佳 `-2.562 kcal/mol`。
- 版本升至 3.2.2；Android versionCode 8 / versionName 3.2.2；Service Worker `bioforge-v322-shell-13`；APK 内置最新 Web 资源、HADDOCK3 表单/任务卡、助手/笔记、多组合计算、`i18n-data.js` 翻译记忆、图谱/3D/计算动态文案、8 个唯一候选/显式变体和移动端 8 标签。
- 助手笔记 Markdown 渲染自动去除 YAML frontmatter；案例标题与资源计数改为动态读取，避免硬编码漂移。

### Tests

- `molecule_tools/bin/python -m pytest -q tests`：64 passed, 1 warning。
- 新增多组合解析/上限、明确计算目标校验与拒绝任务持久化、图谱 provenance、Obsidian 安全、复合物 PDB、助手历史计数/搜索、21 案例/20 体系/45 资源计数与路由、`md_mode`/GRO 合并/复合物拓扑/势能解析、HADDOCK3 默认值/残基解析/配置阶段/约束回退/CAPRI 过滤测试。
- 多组合 API 任务 `C20261023T073906Z-8dbbf207`（1BEB/1GFL × quercetin/curcumin）完成排名；1BEB-curcumin 最佳 `-7.967 kcal/mol`；1GFL 修复后单对复测完成。
- 高级计算实测：GROMACS 蛋白-only EM + 0.2 ps NVT 完成 1/1 receptor；复合物任务 `C20261023T091435Z-9e283468` 完成 1BEB+quercetin 的 32 原子配体 GAFF2 拓扑、16 Na+ 中和、EM + 0.2 ps NVT；EM 首轮 5000 步后 Fmax 仍为 5707.8 kJ/mol/nm，自动二次 EM 244 步收敛到 456.8；配体质心漂移 0.218 Å、配体原子 RMSD 0.338 Å、最近蛋白接触 1.857 Å；CP2K PBE/DZVP 单点完成 1/1 ligand（32 atoms，26.4 s）。
- Headless Chrome CDP：登录、指南/笔记、语言切换、计算多输入、图谱 9 类节点/9 类边图例、1BEB 3D（3,576 原子/312 残基/7 着色）、复合物 3D（3,677 原子/460 残基）、390 px 无横向溢出、0 JS 异常。
- APK：`dist/BioForgeStudio-3.2.2.apk`，357,999 bytes，versionCode 8 / versionName 3.2.2，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，v2/v3 签名通过；内含 HADDOCK3 表单/任务卡、`md_mode` 选择、EM 默认 5000、轨迹入口、`i18n-data.js` 翻译记忆与新 SW `bioforge-v322-shell-13`。
- 轨迹接口：复合物作业 `C20261023T091435Z-9e283468` 的 `md.xtc` 返回 395,527 bytes PDB；静态英文页仅剩语言按钮和代码示例两处有意中文。
- Docker：`v300-app:latest` 已重建（约 767 MB），临时隔离容器 `18010` 的 `/api/health` 返回 3.2.2，验证后停止；宿主 8010 重启为 PID `3630499`，8003 RustDesk 未受影响。
- HADDOCK3 直测/API：protein–protein 210.6 s（`-33.449`，2/2 簇）、protein–ligand 104.5 s（`-0.901`，2/2）、protein–polysaccharide 105.4 s（`-14.517`，2/2）；API 三工作流任务 `C20261026T033248Z-ad0d98fe`、`C20261026T033510Z-bfba7d57`、`C20261026T033510Z-782e343e` 完成；UI 提交 `C20261026T033637Z-fc7630d4` 完成。
- HADDOCK3 浏览器：表单 30 输入/三工作流/英文标签完整，任务卡 a.u. 分数/模型表/步骤/产物/3D 正常，`best_model.pdb` 2,516 atoms/2 chains；20 个食品案例英文复扫 `cjk=0`。


### 2026-10-28 质量收口

- 助手空回答修复：Ollama 返回空 content 或仅隐藏 thinking 时，依次尝试 `num_predict=1600/2400/4096`（前两次 `think:false`，第三次省略 `think`）；新增隐藏思考回退测试。API 实测返回 547 字符、`done_reason=stop`、`eval_count=116`、29.4 s，不再出现空气泡。
- 食品设计配料感知：`_INGREDIENT_ALIASES`/`_negated_ingredient`/`_requested_ingredients` 将咖啡因、茶提取物、乳清蛋白、槲皮素等目标配料写入每个候选并应用上限；修复“咖啡”宽泛别名把咖啡因映射成咖啡提取物，以及“不含藻蓝蛋白”仍添加色蛋白的问题。
- 显式生物设计：显式蛋白输入设置 `requested_kind=protein`，候选池只返回指定蛋白；非食品模式排除 `food_colorant_protein`，红色荧光蛋白查询不再选中藻蓝蛋白；修复 `warnings` 未初始化导致的 `UnboundLocalError`。
- 计算输入：`_resolve` 支持带字母的 4 位 PDB ID（如 `1BEB`、`1GFL`），新增 `_manual_compute_query` 支持仅字段提交（受体/配体/PDB/SMILES）；`1BEB + quercetin` 一句话解析和 4 对组合字段任务 `C20261027T021359Z-cefff7b7` 完成。
- 英文收口：修复 HADDOCK 工具状态、保存状态/toast、图谱边图例/标题、节点/边 ARIA/title、节点 inspector、关联节点、计算错误和编号步骤的中文泄漏；新增 12 个翻译键和手动计算/旧任务 query 模板。2026-10-28 复扫 design/cases/evidence/compute/lab/resources/guide/settings、展开案例/资源/指南/HADDOCK/42 个任务卡、图谱节点/边均为可见 CJK 0。
- 布局与交互：证据提示改为 `10px` 正间距，不再压住表单；320–390 px 模式切换改为整行/可换行，不再溢出；资源下方双卡在 `1080px` 以下改单列；案例、资源分组、助手、笔记、HADDOCK3/参数/工具面板支持折叠；任务卡按 `created_utc` 倒序并支持全部展开/收起；计算页新增“HADDOCK3 运行选择”按钮，直接打开并滚动到表单。
- 视觉：侧栏新增半透明 DNA/蛋白/RNA 里程碑图（浅色自动反相），背景新增低干扰星点/星云漂移；尊重 `prefers-reduced-motion`，720 px 以下高度隐藏侧栏图避免拥挤。
- 回归：`molecule_tools/bin/python -m pytest -q tests` → `64 passed, 1 warning`；`node --check web/app.js|lab.js|sw.js`、`node scripts/check_web.js` 通过；Headless Chrome 320/390/1024/1440 px 检查无页面级横向溢出。
- 产物：APK 357,999 bytes，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，SW `bioforge-v322-shell-13`；Docker 镜像已重建，隔离 18010 health 3.2.2、shell-13、HADDOCK 按钮可见。
- 宿主：8010 PID `3630499`，health 3.2.2；旧 PID `3148034` 已替换。


### 2026-11-02 iOS 壳与 shell-13

- 新增 `ios/` WKWebView 原生客户端：`AppDelegate.swift` 实现服务器地址输入、`/api/health` 探测、Cookie 登录、离线静态预览、外部链接跳转、`UIDocumentPickerViewController` 文件导出和 `AndroidBridge` 兼容桥。
- 新增 `ios/BioForgeStudio.xcodeproj`、`ios/project.yml`、Info.plist、AppIcon/LaunchBackground 资源、`scripts/sync_ios_web.sh` 和 `ios/README.md`；Bundle ID `ai.bioforge.studio`，iOS 15+，Xcode 15+。
- 原生服务器配置标题由“Android 服务器”改为中性的“App 服务器”，英文对应 “App server”；Web/APK/iOS 共用。
- Service Worker 升至 `bioforge-v322-shell-13`；APK 重建为 `357,999 bytes`，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，v2/v3 签名通过。
- 回归：`64 passed, 1 warning`；`node --check`、`node scripts/check_web.js` 通过；iOS 侧完成 plist/YAML/XML/JSON/pbxproj 解析和 Swift tree-sitter 语法检查，但**未在 macOS/Xcode 编译、未签名、未生成 IPA**。
- 新增 `.github/workflows/build-ios-unsigned.yml` 和 `ios/ci/build_unsigned_ipa.sh`：macOS runner 可构建未签名 IPA，需用 Sideloadly/AltStore 或正式证书重签后安装。
- 发布 GitHub 仓库 <https://github.com/zerochans/Bioforge-Demo>；补充 `docs/GITHUB_CI.md`、仓库级 README、iOS CI 说明、最终 APK 与安全排除规则。

## 3.2.1 — 2026-10-23

### Added

- PostgreSQL 16.15 + pgvector 0.8.7 知识库：`docker-compose.yml` 的 `db` 服务、`backend/db.py` schema、`scripts/start_postgres.sh` 和 `scripts/sync_postgres.py`；同步 10,000 篇文献、25,062 个文本块、48,544 个图谱实体、76,954 条边和 361 条 catalog item。
- `/api/v3/knowledge/status|search`、`/api/v3/resources`、`/api/v3/library/resolve`；PostgreSQL 全文检索失败时回退 SQLite FTS5。
- 软件内“资源库”页与顶部快速资源弹层：6 组 38 条来源、许可、接入状态、官方跳转；点击空白或弹层外自动关闭。
- DOI/PMID 解析与合法 OA 定位（Crossref / Europe PMC / Unpaywall）；SCUT 图书馆、CARSI 和可选 EZproxy 官方入口。明确不提供 Sci-Hub，不收集校园密码。
- 12 套配色主题 + 跟随系统/浅色/深色模式；低干扰屏保式背景动画，尊重 `prefers-reduced-motion`。
- Docker 构建支持 `PIP_INDEX_URL` 和 `APT_MIRROR`，默认清华 PyPI/Debian 镜像；compose 增加 PostgreSQL healthcheck 和数据卷。`docker compose build app` 成功，容器 health 3.2.1。

### Changed

- 服务端口从 8003 迁移到 8010，释放 8003 给 RustDesk；Web、Android 默认服务器地址、Caddy、Tunnel、Docker、文档同步更新。
- 版本升至 3.2.1；Android versionCode 7；Service Worker 缓存 `bioforge-v321-shell-2`。
- 应用内指南新增“数据库与来源”，交付文档、README、数据源文档和 Obsidian 同步更新。

### Tests

- `molecule_tools/bin/python -m pytest -q tests`：42 passed, 1 warning。
- 新增资源目录/DOI 解析/合法链接/ PostgreSQL 语料测试。
- Headless Chrome：资源库 38 卡片、12 主题、机构说明弹窗无输入框、PostgreSQL 状态已连接、DOI 解析返回合法入口。
- APK：`dist/BioForgeStudio-3.2.1.apk`，218,438 bytes，versionCode 7 / versionName 3.2.1，SHA-256 `1cf4bb2e770d58277f49eab647d4348d8bc5002fb6ba7522373eef7521bd2f65`，v2/v3 签名通过。


## 3.2.0 — 2026-10-22

### Added

- `backend/literature.py` 与 `/api/v3/literature/stats|search|topics`：只读 SQLite FTS5/BM25 检索，返回标题、年份、DOI、PMCID、许可、topic/MeSH/keyword/chemical 标签和原文链接；数据库缺失时返回 `available=false`。
- 文献采集脚本：`mesh`、`keywords`、`chemicals` 列与迁移；`enrich` 命令从 Europe PMC 补全元数据；FTS5 搜索覆盖这三类字段；Obsidian frontmatter 增加 `mesh/`、`keyword/`、`chemical/` 标签。
- 生物设计专用前端：候选切换、保护剂组合、Tm/保留率/亮度/λem、工艺、数字孪生、QC/控制点、风险与推理链；修复候选数标题，动态显示实际候选数。
- 交互式证据图谱：缩放/平移、点击节点详情、按类型/连接度/计算状态着色、数据源/推理链过滤、返回在线检索、移动端手势。
- 3D/模拟查看器：PDB/PDBQT 多 MODEL/GRO 多帧、卡通/主链/球棍/空间填充、元素/链/深度着色、蛋白/配体显隐、构象选择、残基点击、单字母序列、PNG 导出。
- 计算作业产物支持 `3D ·` 打开 `.pdb/.pdbqt/.gro`；新增参数/结果 JSON 与摘要 CSV 导出。
- 应用内“使用指南”和结果“这张结果怎么读？”解释卡。
- `Dockerfile`、`.dockerignore`、`docker-compose.yml`、`deploy/Caddyfile`、`deploy/.env.example`、`scripts/public_tunnel.sh`；新增 `docs/USER_GUIDE.md`、`docs/DEPLOYMENT.md`、`docs/OPTIMIZATION_LOG_3.2.md`。
- `BIOFORGE_COOKIE_SECURE`：HTTPS 部署可强制安全 Cookie。

### Changed

- 应用、health、Web 品牌、manifest、Service Worker 缓存 `bioforge-v32-shell-1`、Android versionCode 6 / versionName 3.2.0 全部升级到 3.2.0。
- 生物证据图中的体系节点显示为“生物靶点”，候选图标签缩短为“候选”，全名保留在节点详情。
- 图谱选中/悬停不再使用 CSS `filter`，改用描边/透明度，减少软件渲染和截图异常。
- Service Worker 对导航请求改为 network-first，离线时回退缓存页面，避免部署后长期显示旧 HTML。
- 文献库重建后统计为 10,000 篇、25,062 块、48,544 实体、76,954 边、12 篇全文；9,197 条有 PMID 记录完成 MeSH/keyword/chemical 富化。

### Fixed

- 修复 `/api/v2/design` 生物模式因 `design_id`/`job_id` 不一致导致的 500。
- 修复生物设计候选标题固定为“8 个可比较候选”的问题。
- 修复图谱生物设计 `system:None`、空标签和候选/体系长名称重复。
- 修复移动端侧栏点击外部不关闭。
- 验证 3D 查看器在关闭自动旋转后球棍/卡通/空间填充、配体显隐和序列定位均正常；截图测试同时关闭动画以避免 headless 合成伪影。

### Tests

- `pytest tests -q`：32 passed, 1 warning。
- Headless Chrome：3.2 登录、生物设计 10 候选、图谱 41 节点、文献 8 条、PDB 1BEB 3576 原子/312 CA、桌面与 390 px 移动端。
- APK：202,054 bytes，versionCode 6，versionName 3.2.0，v2/v3 签名通过。

## 3.1.0 — 2026-10-21

### Added

- `scripts/literature_pipeline.py`：Europe PMC OA 元数据采集、游标分页、DOI 去重、SQLite FTS5/BM25、1000 字符分块、Obsidian 导出、概念/作者/期刊知识图谱、OA 全文抓取与 `pdftotext` 转换。实跑 10,000 篇元数据、10,000 条笔记、26,284 个文本块、48,544 个实体、76,954 条边、12 篇全文。
- `backend/compute.py`：可调对接/MD/QM 参数、工具路径持久化（`runtime/tool_paths.json`）、GROMACS/CP2K/Meeko/Open Babel/HADDOCK3 能力检测、参数 SHA-256 指纹、分阶段超时、进程组 SIGTERM/SIGKILL、阶段失败隔离。
- `backend/app_v3.py`：`GET/PUT /api/v3/tools`、`GET /api/v3/structure/{pdb_id}`；CORS 支持 PUT。
- Web：16 个计算参数、恢复默认、工具路径设置、任务配置 chip/指纹/PDB artifact；canvas 3D 结构查看器（旋转、缩放、自动旋转、元素着色）。
- Android：原生首启服务器配置对话框、`/api/health` 连接测试、URL 规范化、离线预览、登录页/设置页重新配置；`usesCleartextTraffic` 与网络安全配置允许局域网 HTTP。
- `scripts/run_server.sh`：默认 `0.0.0.0:8003`、端口占用检查、Python 解释器回退。
- `docs/LITERATURE_PIPELINE.md`、`docs/UPGRADE_3.1.md`；`docs/COMPUTE.md`、`docs/API_V3.md`、README、RELEASES、DELIVERY 更新到 3.1。

### Changed

- 应用版本、Web 品牌、manifest、health、Lab 概览升级到 3.1.0；APK versionCode 5 / versionName 3.1.0。
- GROMACS 顺序固定为 `grompp em → mdrun em → grompp md → mdrun md`；EM/MD 步数、步长、温度、线程可配。
- 结构准备与对接解耦；对接关闭时仍生成 `receptor.pdb` / `ligand.sdf`。
- 报告新增实际参数 JSON、运行指纹、各阶段错误和解释边界。
- Service Worker 缓存升级为 `bioforge-v31-shell-2`。
- 计算测试任务清理，`runtime/compute/` 交付时为空。

### Fixed

- `_prepare_structures` 引用未定义 `ligand_sdf` 导致任务失败。
- GROMACS `grompp`/`mdrun` 顺序错误和超时后子进程残留；现按进程组终止。
- 登录成功后旧错误提示未清空。
- 任务卡片在移动端横向溢出；修复 `min-width:0`、`minmax(0,1fr)` 和长字符串换行。
- 构建后确认 APK 内 `assets/www` 的品牌、Service Worker 缓存和移动端 CSS 已更新。

### Security

- 工具路径仅接受绝对路径、存在且可执行的文件/目录；保存文件权限 `0600`。
- 结构代理只接受 4 字符 PDB ID，限制上游错误长度。
- 文献只抓 `OPEN_ACCESS:Y` 和许可明确的记录；不绕付费墙，保留 license/source/retrieved_at。
- APK 明文 HTTP 仅用于可信局域网；远程部署要求 HTTPS。

### Known Limitations

- HADDOCK3 `2026.5.0` 只检测/配置，未执行自动任务。
- 无真机/模拟器，APK 首启对话框与 LAN 登录未做设备级验收。
- Europe PMC PDF 端点对脚本返回 403；当前全文主要来自 JATS XML，数量仅 12 篇。
- 文献标签是规则匹配，检索是 BM25，不是系统综述或向量 RAG。

## 3.0.0 — 2026-10-20

### Added

- `backend/lab.py`：Model Lab 数据集导入（CSV/JSON）、schema 推断、SHA-256、去重、训练、预测、EI 贝叶斯优化、实测回灌与重训。
- `backend/app_v3.py`：v3 API、`/api/v3/lab/*` 路由、Lab 异常处理，默认端口 8003；health 返回 `lab_version` 与 `mode=food+biologic+lab`。
- `web/lab.js` + 页面：数据集列表/详情、CSV/JSON 导入、演示数据、训练配置、OOF 散点、置换重要性、搜索空间、候选卡、实测 modal、导出、删除二次确认。
- 模型算法：Ridge、RandomForest、HistGradientBoosting、GaussianProcess、自动选择、RF+HGB+Ridge 集成；KFold/GroupKFold；残差/树间/GP 不确定性。
- 模型 artifact（joblib + card JSON）、模型版本、父模型链接、artifact SHA-256、artifact 状态。
- 防泄漏：结果列自动标记 `outcome`/`leakage_risk` 并默认排除；手工选入会在模型卡记录警告。
- 合成/混合数据显式 opt-in；演示集 180 行合成数据与 SHA-256 元数据。
- 数据集 CSV/模板/演示/优化候选导出；公式注入防护；Android 下载桥接与文件选择器。
- `tests/test_v3.py`：导入、schema、合成拦截、训练、泄漏、优化、预测、回灌、CSV、删除、鉴权、静态资源。
- 文档：`docs/MODEL_LAB.md`、`docs/API_V3.md`、`docs/UPGRADE_3.0.md`。

### Changed

- 应用版本、API、Web 品牌、manifest 升级到 3.0；服务默认端口 8003。
- Android versionCode 4 / versionName 3.0.0；默认连接 8003；支持 Lab 文件导入/CSV 保存。
- Service Worker 缓存升级为 `bioforge-v30-shell-3`，预缓存 `lab.js` 与 maskable 图标。
- 模型训练使用线程池与互斥锁，避免并发训练争抢 CPU/artifact。
- 模型列表、健康检查、概览、数据集详情均带 Lab 元数据；v2 API 与食品引擎版本保持兼容。

### Fixed

- `feature_candidates` 曾把数值结果列当默认特征，导致数据泄漏。
- 冷启动直接进入 Lab 时页面不显示（`pages` 映射缺少 `lab`）。
- 切换 Lab 标签时优化页不自动加载搜索空间。
- 全局 checkbox `appearance:none` 导致 Lab 复选框不可见；改为原生 checkbox + accent-color。
- 合成数据导入被 `window.confirm` 阻塞；移除确认，改为训练时显式 opt-in。
- 导入 JSON 时必须手动选择格式；现自动识别 `[`/`{`。
- 切换数据集时合成勾选状态残留；现在按数据集重置。
- 训练后概览统计不刷新；现在训练完成会刷新 overview。
- 模型版本显示重复 `v` 前缀。
- 数据集 CSV 导出/模板/候选下载在 Android WebView 中无法保存；现通过 `AndroidBridge.saveText`。
- 表头被强制大写、chip 内边距异常、select 箭头缺失等 Lab 样式问题。

### Security

- Lab 端点全部要求会话 Cookie 或 Bearer token；训练/写操作有速率限制。
- 删除数据集需要 `confirm=yes-delete-dataset`；界面二次确认。
- 模型 artifact 文件名使用服务端生成 ID；删除仅限该数据集的模型路径。
- 导入内容 8 MB / 20,000 行 / 200 列限制；CSV 导出对公式前缀做转义。
- Android 仍仅申请 INTERNET 权限，明文 HTTP 仅允许 localhost/127.0.0.1/10.0.2.2。

## 2.1.0 — 2026-10-20

### Added

- `backend/composition.py` 与 `data/ingredient_composition.json`：96 个配料的每 100 g 组成快照，其中 35 个映射 USDA FDC SR Legacy、61 个明确为 curated estimate；含 FDC ID、来源、置信度、匹配方法与源文件 SHA-256。
- `datasources.py` 实体规划：`compound` / `protein` / `food` / `complex`；按实体选择数据库，显式记录 `plan.selected_sources`、`plan.rejected_sources` 与分类依据。
- 在线检索新增 UniChem InChIKey 映射；PDB 只使用 UniProt `uniProtKBCrossReferences`；STRING 使用 UniProt accession + taxon；FDC 失败回退本地 SR Legacy 快照。
- 每条在线记录新增 `match_basis`、`relevance`、`retrieved_at`；跨库链接只接受精确 InChIKey、UniProt→PDB xref 或显式谱图引用。
- 食品设计新增 `constraint_report`（`pass` / `at_risk` / `fail`）、`intervals`、`composition`、`metric_provenance`、`evidence_grade`、`recipe_changes` 与 `reasoning`。
- Web UI 新增实体选择、查询计划、来源状态、约束卡/表、指标来源、推理链和组成来源列；移动端约束表改为卡片。
- 新增 `docs/SCIENTIFIC_METHOD.md`、`docs/REASONING_AUDIT.md`、`docs/UPGRADE_2.1.md`。
- 新增组成、确定性设计、FDC 回退、实体规划、验证跨库链接与绝对单位解析测试；总计 25 项。

### Changed

- 食品设计删除随机 tie-break；同输入、同数据版本生成相同配方，排序依据为可解释评分与 ID。
- 营养计算改为调用组成快照，不再使用 `food.py` 的内联营养表；旧表保留为回退代码。
- 证据响应返回 identity、查询计划和来源级错误隔离；化合物不再调用蛋白/食品库，食品不再调用蛋白库。
- 默认端口改为 8002；APK versionCode 3 / versionName 2.1.0，Web 品牌与 manifest 同步到 2.1。
- 约束解析支持 `mg`、`g`、`%` 绝对目标与 pH 范围；盐按 NaCl→Na 换算，pH 范围取中点作为情景锚点，并单独输出目标 pH 窗口。
- 界面在线源说明改为“11 个可检索源 + 1 个链接源”。

### Fixed

- v2.0 将槲皮素错误关联到 UniProt/PDB/STRING/FDC 的相关性缺陷；删除名称型 `same_compound_candidate`。
- PubChem 标题字段解析、Open Food Facts legacy CGI、STRING taxon 404、FDC `DEMO_KEY` 429 回退。
- 移动端结果页 68 px 横向溢出；证据页/约束页在 390 px 下的卡片与表格布局。
- `targets["stability"]` 未初始化导致稳定性优先策略不生效。
- 仅带百分号的旧目标解析；`钠<300mg`、`蛋白质≥12g/100g`、`盐<1g/100g` 现在正确进入硬约束。
- `metric_provenance` 中文说明未生效（需重启服务）。

### Security

- 保持 v2.0 的 PBKDF2 账户、HttpOnly 会话、Bearer token、路径穿越防护与外链白名单。
- 在线请求继续使用超时、缓存和错误隔离；缓存不存登录凭据，第三方 API 不接收用户会话。

## 2.0.0 — 2026-10-20

### Added

- `backend/food.py`：食品体系识别、10 策略组合、8 候选 portfolio、约束/指标/相互作用/工艺/法规/来源。
- `data/food_systems.json`（20）、`ingredients.json`（96）、`interactions.json`（46）、`sources.json`（14）、`cases.json`（8）。
- `backend/datasources.py`：PubChem、ChEBI、UniProt、PDB、AlphaFold、Europe PMC、USDA FDC、Open Food Facts、ChEMBL、STRING、MassBank；缓存与跨库链接。
- `backend/graph.py`：design/system/strategy/ingredient/target/data_source/literature/online_record 节点与证据边。
- `backend/compute.py`：Vina、GROMACS、CP2K 后台任务、步骤状态、artifact 与报告。
- `backend/auth.py`：PBKDF2 账户、HMAC 会话、登录限速、密码修改。
- `backend/app_v2.py`：v2 API、登录路由、静态站点、artifact 安全下载。
- `web/`：Apple 风格 SPA，桌面/移动、深浅色、滑动切页、候选横滑、证据图谱、计算轮询。
- `tests/test_v2.py`：食品数据、8 案例、图谱、数据源、登录 API、路径穿越。
- 文档：`UPGRADE_2.0.md`、`LOGIN.md`、`DATA_SOURCES.md`、`COMPUTE.md`、`CASES.md`、`PROVENANCE.md`、`API_V2.md`。

### Changed

- 食品温和热处理默认上限从 85°C 调整为 250°C，避免把烘焙/杀菌误判为不可行。
- pH 估算改为相对基础配方的酸/缓冲负荷，钳制在体系 pH 范围附近。
- 无麸质烘焙使用显式结构替换（米粉/玉米淀粉/豌豆蛋白 + 黄原胶），不再依赖通用 function 交集。
- 植物基乳品/冷冻甜品支持燕麦基与椰子油替换。
- 低糖酸奶乳粉部分替换为乳清蛋白并降低甜味剂负荷。
- v2 服务默认端口 8001；v1 保持 8000。

### Fixed

- GROMACS 步骤顺序错误（先 EM 再 MD grompp）、`OMP_NUM_THREADS` 与 `-nt` 不一致、force field 重复发现问题。
- CP2K `DZVP-MOLOPT-SR-GTH` 不可用 → 改为 `DZVP-MOLOPT-GTH`，并显式加 PBE/XC。
- 在线证据图谱被默认检索覆盖的问题；图谱节点字段 `kind` 的颜色映射。
- PubChem 质谱 heading、MassBank 无 JSON 的解释。
- 配方百分比、约束过滤、候选多样性回退。

### Security

- 登录 Cookie HttpOnly/SameSite=Lax；API token 文件 0600；密码 PBKDF2 240k。
- 路径穿越防护覆盖设计、任务与 artifact；外链仅 `http/https`。
- APK 仅 INTERNET 权限；明文 HTTP 只允许 localhost/127.0.0.1/10.0.2.2。

## 3.2.0 增量 — 2026-10-22（下午）

### Added

- `backend/query_text.py`：共享中英文别名、术语、相关度与强度分级；`datasources`、`literature` 统一使用。
- `datasources.route_queries`：化合物/蛋白查询分离，过滤 `stability`/`binding` 等通用词，修复 PubChem 收到错误名称的问题。
- `backend/processing.py` v1.0：蛋白热变性、美拉德、花青素、抗坏血酸、脂质氧化、淀粉糊化、蔗糖酸水解、亲水胶体、明胶、酶解和乳酸发酵等机制规则，逐条附证据、置信度和验证建议。
- `backend/food.py` 输出 `processing_effects`；低糖固体饮料支持赤藓糖醇/菊粉/reb_a 替代路径。
- 数据源：GenBank、KEGG REST、ZINC 连接器；`/api/v2/db/status` 返回许可/凭据 `catalog`；`data/sources.json` 扩到 16 条。
- 图谱：节点/边语义、稳定 edge ID、citations、置信度、工艺步骤和 `predicts_change` 边、`semantics` 字典。
- 3D：按真实组分动态生成蛋白/水/离子/糖链/脂质/配体/其他控件，默认隐藏水，支持预设和多构象保留选择。
- 设置页“数据源与许可”面板；移动端侧栏左滑收起；背景低速漂移并尊重 `prefers-reduced-motion`。
- 案例：`data/cases.json` 扩到 17 个；新增 `tests/test_query_processing.py`。

### Changed

- 图谱前端改为力导向生长动画，支持节点拖拽牵拉、滚轮/双指缩放、双击证据、边点击关系详情；移除加减号按钮。
- 文献检索用扩展术语召回后按 BM25 + 词面相关度重排，返回 `relevance`、`strength`、`match_terms`。
- `detect_system` 改为 (命中数, 关键词长度) 优先级，修复“固体饮料”被“饮料”抢先匹配。
- Service Worker 缓存升至 `bioforge-v32-shell-2`，HTTPS 下也注册。

### Tests

- `pytest tests -q`：38 passed, 1 warning。
- `node --check web/app.js`、`node scripts/check_web.js` 通过。
