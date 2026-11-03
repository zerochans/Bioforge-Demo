# BioForge Studio Releases

> 历史记录中的 8003 是 3.2.0 及更早版本的端口；自 3.2.1 起 BioForge 使用 8010，8003 已释放给 RustDesk。

## v3.2.2 — 2026-10-25

**主题：把案例、资源、计算、3D、图谱、助手和双语界面补成可交付的完整闭环。**

- 案例库扩至 21 个端到端案例，覆盖 20 个食品体系 + 1 个乳清蛋白-槲皮素机制案例；资源库扩至 7 组 45 条，新增 7 条光谱/波谱与结构证据入口。
- HADDOCK3 独立任务：蛋白-蛋白、蛋白-配体、蛋白-多糖；参数化 `haddock.cfg`、RDKit 配体 3D、糖链识别、活性残基约束/cmrest/ranair 回退、CAPRI 解析和 score ≥ 9999 过滤。任务卡显示 a.u. 分数、模型/簇表、步骤、产物和 3D 模型。
- 计算页支持多受体×多配体：接受 PDB ID、本地结构、配体名或 SMILES，笛卡尔积最多 12 对；逐对 Vina 对接、排名，输出 `screening.csv`、`report.html`、`pairs/*/complex.pdb` 和根 `complex.pdb`。
- 高级计算新增 `advanced_scope`：复合物 MD 按选定 pair、蛋白-only 模式按唯一受体、CP2K 按唯一配体运行；默认代表项，可选全部。受体准备加 `--delete_bad_res`，修复 1GFL 等非标准残基导致的模板匹配失败。
- 新增真实复合物 MD（默认）：RDKit pose 映射 + ACPYPE GAFF2/AM1-BCC + amber99sb-ildn，合并拓扑、中和、EM 与短 NVT；报告配体漂移/RMSD/最近蛋白接触，失败时明确回退蛋白-only。
- 新增 Ollama 本地问答（`qwen3.8:27b`，8 次/60 秒限流）与 Obsidian 只读笔记浏览；问答历史本地保存、月度备份，笔记 2 MB 上限和路径穿越防护。空回答或仅隐藏思考时自动放宽 `num_predict` 并重试。
- 3D 新增二级结构/残基极性/序列彩虹/B-factor/深度着色，蛋白与核酸全序列分组、配体组分、复合物直接加载。
- 图谱新增节点/边字典与 provenance：每条边显示 `evidence_status`/`basis`/`citations`，无引用非 workflow 边显示 caveat。
- 12 套主题增加独立纹理与卡片/导航/hero 染色；核心界面支持中英切换，英文模式通过翻译记忆、数字模板和术语替换覆盖设计/计算/图谱/3D 动态内容。
- 食品目标配料进入候选配方并受上限约束；显式荧光蛋白不再被食品色蛋白替代；计算支持 PDB 一句话解析与仅字段提交。案例/资源/助手/笔记/HADDOCK/参数/工具面板可折叠，任务卡按时间倒序并支持全部展开/收起；侧栏加入半透明科学里程碑图与星云背景。
- iOS：新增 `ios/` WKWebView 原生壳、Xcode 工程和 XcodeGen 配置；支持服务器地址/health 探测、Cookie 登录、离线预览、文件导出和外部链接跳转。新增 `.github/workflows/build-ios-unsigned.yml` 和 `ios/ci/build_unsigned_ipa.sh`；GitHub Actions run #3 已在 macOS runner 成功生成未签名 IPA 并发布到 Releases：[BioForgeStudio-3.2.2-unsigned.ipa](https://github.com/zerochans/Bioforge-Demo/releases/download/ios-unsigned-3.2.2/BioForgeStudio-3.2.2-unsigned.ipa)（634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`），仍需重签后安装。GitHub 仓库：<https://github.com/zerochans/Bioforge-Demo>。
- 版本 3.2.2；Android versionCode 8；Service Worker `bioforge-v322-shell-13`。新增 `web/i18n-data.js` 翻译记忆，20 个食品案例、机制案例、图谱、3D、HADDOCK3 表单/任务卡、资源/设置和助手英文问答均完成可见文案英文化；新增 `.xtc` 轨迹接口和缓存。配方候选按组成去重，不足 8 个时生成可追溯的原料替代变体；英文 `≤8% sugar` / `≥6% dietary fibre` 等目标量与中文解析对齐。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-3.2.2.apk` | `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f` |

| 其他交付物 | 路径/状态 |
|---|---|
| iOS 工程 | `ios/BioForgeStudio.xcodeproj`，WKWebView 壳，Xcode 15+/iOS 15+；CI 已生成未签名 artifact |

**验证记录**

- `molecule_tools/bin/python -m pytest -q tests` → `64 passed, 1 warning`。
- 服务：`0.0.0.0:8010`，health `version=3.2.2`，当前 PID `3630499`，日志 `runtime/uvicorn-8010.log`，PID 文件 `runtime/bioforge-8010.pid`。
- 多组合任务 `C20261023T073906Z-8dbbf207`：4 对中 1BEB 两对完成，1BEB-curcumin 最佳 `-7.967 kcal/mol`；1GFL 两对首次因非标准残基准备失败，修复后单对复测完成（`-2.562 kcal/mol`）。
- 单组合任务 `C20261023T072443Z-1c983bca`：`-7.435 kcal/mol`，`complex.pdb` 3,007 原子。
- 高级计算：`C20261023T075504Z-5b172d8e` 完成 GROMACS 蛋白-only EM + 0.2 ps NVT；`C20261023T075532Z-2635b9c1` 完成 CP2K PBE/DZVP 单点（32 atoms，26.4 s）。
- 复合物 MD：`C20261023T091435Z-9e283468` 完成 1BEB+quercetin 的 ACPYPE/GAFF2 拓扑、16 Na+ 中和、EM + 0.2 ps NVT；EM 首轮 5000 步后 Fmax 仍为 5707.8 kJ/mol/nm，自动二次 EM 244 步收敛到 456.8；配体质心漂移 0.218 Å、原子 RMSD 0.338 Å、最近蛋白接触 1.857 Å。
- HADDOCK3：protein–protein `1BEB+1GFL` 210.6 s（`-33.449`，2 模型/2 簇）、protein–ligand `1BEB+quercetin` 104.5 s（`-0.901`，2/2）、protein–polysaccharide `1BEB+1LMQ:B` 105.4 s（`-14.517`，2/2）；API 三工作流任务 `C20261026T033248Z-ad0d98fe`、`C20261026T033510Z-bfba7d57`、`C20261026T033510Z-782e343e` 与 UI 任务 `C20261026T033637Z-fc7630d4` 均完成。
- HADDOCK3 浏览器：表单 30 输入、三种工作流、英文标签/占位符、a.u. 分数/模型簇表/步骤/产物/3D 正常；`best_model.pdb` 加载 2,516 atoms/2 chains；20 个食品案例英文复扫 CJK 0。
- Headless Chrome CDP：登录、指南/笔记、语言切换、资源库/设置动态文案、移动端 8 个标签在 320–430 px 全部可见、390 px 无横向溢出、0 JS 异常；英文静态页仅保留语言按钮“中”和代码示例“内容”两处有意中文；最终 20 案例复扫可见 CJK 为 0。
- APK：`357,999` bytes；versionCode 8 / versionName 3.2.2；`apksigner` v2/v3 通过；内置 `assets/www/sw.js` 为 `bioforge-v322-shell-13`，含 HADDOCK3 表单/任务卡、多组合计算、助手/笔记、`i18n-data.js`、图谱/3D/计算动态翻译、可折叠 UI、侧栏里程碑图和科学背景 SVG；原生服务器标题已改为“App 服务器”。
- iOS：`ios/BioForgeStudio.xcodeproj` 已生成；Info.plist、project.yml、XML/JSON 和 pbxproj 解析通过，Swift 语法检查无错误；GitHub Actions run #1 生成未签名 artifact，未签名、无签名 `.ipa`。
- 笔记接口：默认 Obsidian 目录 `/media/h3c/Win11Pro X64/data/literature/obsidian/00-BioForge`，10 篇 Markdown 可读。
- 轨迹：`C20261023T091435Z-9e283468` 的 `pairs/01_1BEB_quercetin/gromacs_complex/md.xtc` 通过 `/api/v3/structure/trajectory/...` 返回 395,527 bytes PDB；仅接受作业内 `.xtc` 且要求 `md.tpr`，缓存 `viewer/*-v2.pdb`。
- Docker 镜像 `v300-app:latest` 已重建（约 767 MB）；临时隔离容器 `18010` health 返回 `3.2.2`，HADDOCK3 按钮和 SW shell-13 可见，验证后已停止。宿主 8010 服务已重启到新代码（PID `3630499`）；compose 全栈未启动，公网未部署。

**2026-10-28 质量收口验证**

- 助手 API 返回 547 字符、`done_reason=stop`、`eval_count=116`、29.4 s；空回答/仅隐藏思考的单元测试通过。
- 食品设计：咖啡因能量饮包含咖啡因、茶饮包含茶提取物、乳清饮包含乳清蛋白、槲皮素饮包含槲皮素；无藻蓝蛋白蓝饮不含藻蓝蛋白；显式 mNeonGreen/红色荧光蛋白查询不再回退到食品色蛋白。
- 计算：`分析 1BEB 与 quercetin 的结合`、`1GFL + caffeine`、`1BEB,1LYZ × quercetin,caffeine`、`whey,1LYZ + SMILES` 均正确解析；仅字段任务 `C20261027T021359Z-cefff7b7` 完成 4 对准备/报告。
- 英文：design/cases/evidence/compute/lab/resources/guide/settings、展开案例/资源/指南/HADDOCK/42 个任务卡、图谱节点/边均为可见 CJK 0；旧计算 query 已模板化。
- 布局：证据提示与表单不重叠；320/390 px 模式切换不溢出；1024 px 资源下方改单列；案例/资源/助手/笔记/任务卡折叠与全部展开/收起正常。
- 回归：`64 passed, 1 warning`；`node --check`、`node scripts/check_web.js` 通过；APK `357,999` bytes / SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`；Docker 镜像已重建，隔离 18010 health 3.2.2。

**已知限制**

- HADDOCK3 仅支持蛋白-蛋白、蛋白-配体、蛋白-多糖；没有实验参考结构，CAPRI RMSD/FNAT 不作为验证；HADDOCK score 是 a.u.，不是结合自由能。活性残基填错、糖链模板缺失或全部模型被拒绝时任务会失败/报解析错误。
- Docker 镜像不含 HADDOCK3/GROMACS/CP2K/Vina/ACPYPE；容器内 Web 和 HADDOCK3 表单可用，但 HADDOCK3 任务会因缺少二进制失败。
- 复合物 `complex.pdb` 是刚性受体 + 第一个对接 pose 的拼装；复合物 MD 从该 pose 出发，只做短 NVT，不证明结合自由能。
- 复合物 MD 使用自动质子化/电荷与 ACPYPE GAFF2/AM1-BCC；配体电荷、互变异构和蛋白质子化仍需人工复核。
- GROMACS 复合物 MD 在“全部”模式按 pair 运行，耗时随组合数增加；CP2K 仍按唯一配体独立运行。
- 无 adb/AVD，APK 3.2.2 真机首启、LAN WebView 登录、SW 更新未做设备级验收。
- iOS 未产出签名 `.ipa`，未做真机验收；当前有公开未签名 Release IPA（634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`）。ATS 为任意用户输入服务器放宽，公网必须 HTTPS。
- `literature_chunks.embedding` 仍未回填；没有向量召回/HNSW。
- Ollama 模型与 Obsidian 目录是本机环境依赖，换机需在设置/环境变量中重新配置。
- 英文模式覆盖导航、按钮、表单占位符、资源库/设置、设计/计算/图谱/3D 动态 UI、20 个食品案例和机制案例；Obsidian 笔记保留原文并提示按需查看，助手历史在英文模式下只显示英文记录。
- 公网部署仍需域名、Tunnel/VPS、HTTPS、强密码和访问控制；未部署。

## v3.2.1 — 2026-10-23

**主题：把合法资源目录、PostgreSQL 知识库和可切换界面真正交付到 Web/APK，同时解除 RustDesk 端口冲突。**

- 服务从 8003 迁移到 8010；`scripts/run_server.sh`、Docker、Caddy、Tunnel、Web、Android 和当前文档同步更新，8003 已确认由 RustDesk 监听。
- 新增 PostgreSQL 16.15 + pgvector 0.8.7 知识库：`bioforge-db` 容器、`bioforge_pgdata` 数据卷、`backend/db.py` schema、启动/同步脚本；同步 10,000 篇文献、25,062 个文本块、48,544 个实体、76,954 条边、361 条 catalog item。
- 新增 `/api/v3/knowledge/status|search`：PostgreSQL 全文检索，失败回退 SQLite FTS5；状态返回数据库版本、pgvector、计数、体积和 embedding pending。
- 新增软件内资源库与快速资源弹层：6 组 38 条来源、许可/状态/官方跳转、搜索与筛选；DOI/PMID 解析调用 Crossref、Europe PMC、Unpaywall，只返回合法 OA/官方入口。
- 新增 SCUT/CARSI 机构访问说明和官方入口；软件不接收、不记录、不代存校园账号密码，不提供 Sci-Hub 或付费墙绕过。
- 新增 12 套主题（极光/深海/森林/日落/莓果/石墨/赛博/卡通/国风/实验室/糖果/沙丘）+ 跟随系统/浅色/深色，低干扰背景动画尊重 `prefers-reduced-motion`。
- 设置页新增 PostgreSQL 知识库状态卡；资源库统计卡显示 38 条来源、13 条可直接查询、3 条机构入口和文献/文本块/图谱边。
- Docker 构建支持 `PIP_INDEX_URL` 与 `APT_MIRROR`（默认清华 PyPI/Debian 镜像）；compose 增加 PostgreSQL healthcheck、数据卷和可选 `env_file`。
- 版本 3.2.1；Android versionCode 7；Service Worker `bioforge-v321-shell-2`。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-3.2.1.apk` | `1cf4bb2e770d58277f49eab647d4348d8bc5002fb6ba7522373eef7521bd2f65` |

**验证记录**

- `molecule_tools/bin/python -m pytest -q tests` → `42 passed, 1 warning`。
- 服务：`0.0.0.0:8010`，health `version=3.2.1`，PID 记录在 `runtime/server-v3.pid`（本次为 `542977`）；8003 为 RustDesk（当前 PID `655985`，会随服务重启变化）。
- PostgreSQL：`10,000` 文献、`25,062` 文本块、`48,544` 实体、`76,954` 边、`187 MB`；pgvector `0.8.7`，embedding 当前为 `0`。
- 浏览器：资源库 38 卡片、顶部来源计数 38、12 主题、机构弹窗无输入框、PostgreSQL 状态卡显示已连接、DOI 解析返回合法入口。
- APK：`218,438` bytes；versionCode 7 / versionName 3.2.1；`apksigner` v2/v3 通过；内置 `assets/www` 含 `bioforge-v321-shell-2`、资源库/知识库/机构说明。
- `docker compose config` 通过（提供 `POSTGRES_PASSWORD`/`BIOFORGE_DOMAIN`）；`docker compose build app` 已用国内镜像构建成功（766 MB），容器 `GET /api/health` 返回 3.2.1；compose 全栈未启动，公网未部署。

**已知限制**

- `literature_chunks.embedding` 为 `vector(1024)` 但尚未回填，当前没有向量召回/HNSW 索引。
- 无 adb/AVD，APK 3.2.1 真机首启、LAN WebView 登录、SW 更新未做设备级验收。
- 第三方 API 注册未执行；NCBI API key 未接入，FDC key 支持保持原状；KEGG 可能间歇失败，ZINC 为 link-only。
- Crossref/Unpaywall/Europe PMC 受 DNS/网络影响，DOI 解析实测约 8–21 秒。
- 公网部署仍需域名、Cloudflare Tunnel token/VPS、HTTPS 和访问控制；未部署。
- 资源目录只列合法入口；SCUT/EZproxy 具体前缀未配置，不自动登录、不抓取图书馆全部资源。

## v3.2.0 — 2026-10-22

**主题：让生物设计结果、证据链和 3D/模拟数据真正可读、可操作、可交付。**

- 修复生物设计接口 500（`design_id`/`job_id` 回退），新增生物设计候选/保护剂/工艺/数字孪生/QC/推理链视图。
- 证据图谱改为可缩放/平移的交互图：节点详情、着色模式、数据源/推理链过滤、返回在线检索；生物体系标签收敛为“生物靶点/候选”。
- 3D 查看器支持 PDB/PDBQT 多构象/GRO，多表示法与着色、配体显隐、构象选择、残基/序列定位、PNG 导出；计算作业可直接打开结构产物并导出 JSON/CSV。
- 新增本地文献 API 和 UI：10,000 篇 OA、25,062 块、BM25 检索、MeSH/关键词/化合物标签；Obsidian 同步标签。
- 新增应用内使用指南、结果解释卡、动态候选计数、远程部署骨架与安全检查表。
- 版本 3.2.0；APK versionCode 6；SW `bioforge-v32-shell-1`；32 项测试通过。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-3.2.0.apk` | `6f260646f1ecbdb2ec589f1fb33c86d065781439b9635de1729eaf0b0801fdf5` |

**验证记录**

- `pytest tests -q` → `32 passed, 1 warning`。
- 服务：`0.0.0.0:8003`，health `version=3.2.0`、`lab_version=3.2.0`；PID 记录在 `runtime/server-v3.pid`。
- 浏览器：登录、mNeonGreen 生物设计（10 候选、4 张详情卡）、图谱 41 节点/28 边、文献 8 条、1BEB（3576 原子/2 链/596 配体原子/312 CA）、球棍/空间填充、Guide、390 px 移动端。
- APK：202,054 bytes；versionCode 6 / versionName 3.2.0；`apksigner` v2/v3 通过；内置 `assets/www` 含 SW `bioforge-v32-shell-1`、动态候选标题和图谱返回按钮。
- 文献：`quercetin protein interaction` 返回 8 条；库含 10,000 篇、25,062 块、48,544 实体、76,954 边、12 篇全文；9,197 条有 PMID 记录完成富化。

**已知限制**

- 无真机/模拟器，APK 3.2 首启、LAN WebView 登录和设置重开未做设备级验收。
- `docker compose config` 已通过；镜像构建受本机容器网络（PyPI 不可达）阻断，Caddy/公网隧道未上线；公网访问需域名、强密码和 HTTPS。
- HADDOCK3 只检测/配置；小分子默认 Vina，HADDOCK 需要配体拓扑和活性位点限制。
- Europe PMC PDF 端点仍可能 403；全文仅 12 篇；798 条无 PMID 记录未富化。
- 3D 是坐标可视化，不做结构质量、能量或结合模式验证；文献标签和 BM25 不是系统综述或湿实验证据。

## v3.1.0 — 2026-10-21

**主题：让手机直连可用、计算可调可追溯、结构可视，并把 OA 文献接成本地知识库。**

- 手机不再依赖 USB/`adb reverse`：服务监听 `0.0.0.0:8003`，APK 首启填写 LAN 服务器地址并做健康探测，登录页/设置页可重新配置。
- 计算参数化：Vina exhaustiveness/poses/box/seed、GROMACS EM/MD 步数/步长/温度/线程、CP2K cutoff/SCF、各阶段超时；参数夹取、SHA-256 运行指纹、进程组超时终止。
- 本地工具路径可在 Web 保存并检测；HADDOCK3 `2026.5.0` 已识别，但仅检测，不执行自动任务。
- 新增 canvas 3D 结构查看器，按 PDB ID 加载 RCSB 坐标，支持旋转、缩放、自动旋转和元素着色。
- 新增 OA 文献流水线：Europe PMC → SQLite FTS5/BM25 → Obsidian → 概念/作者/期刊知识图谱；实跑 10,000 篇元数据、10,000 条笔记、26,284 个文本块、48,544 个实体、76,954 条边。
- APK 3.1.0（versionCode 5）；30 项测试通过；v1/v2/v3.0 保持兼容。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-3.1.0.apk` | `764a27d58eefe3019cd7bc9ceb82cde8b78feda789031ffd05850b383496df56` |

**验证记录**

- `pytest tests -q` → `30 passed, 1 warning`。
- 服务：`0.0.0.0:8003`，health `version=3.1.0`、`lab_version=3.1.0`；LAN `http://10.194.51.41:8003/` 可访问。
- 计算：Vina `-7.47 kcal/mol` + GROMACS EM/short NVT 完成；CP2K 32 atoms `-203.4343556229248 Ha`（`-5535.73 eV`），约 36 s。seed 42/43 得到不同对接分数和不同指纹。
- 浏览器：登录、能力卡、16 个参数、8 个工具路径、1BEB 3D（3372 atoms / 2 chains）、桌面与 390 px 移动端无横向溢出，0 JS 异常。
- APK：`aapt2` versionCode 5 / versionName 3.1.0、`usesCleartextTraffic=true`；`apksigner` v2/v3 通过；内置 `assets/www` 品牌 `STUDIO 3.1`、SW cache `bioforge-v31-shell-2`。
- 文献：`quercetin protein interaction` 可返回 BSA–槲皮素、网络药理学和分子对接记录；12 篇 OA JATS XML 转为 Markdown。

**已知限制**

- 无真机/模拟器，APK 首启对话框、LAN WebView 登录和“设置中重新配置”未做设备级验收。
- HADDOCK3 只检测/配置；小分子默认 Vina，HADDOCK 需要配体拓扑和活性位点限制。
- Europe PMC PDF 端点为 403/Cloudflare；当前全文主要来自 JATS XML，仅 12 篇；磁盘约 1.2 GB 可用。
- 文献标签是规则匹配，RAG 是 BM25；不是系统综述、向量检索或湿实验证据。
- APK 仍是服务器客户端，断网只能显示提示页。

## v3.0.0 — 2026-10-20

**主题：从“可审计设计”升级为“可回灌的本地模型闭环”。**

- 新增 Model Lab：CSV/JSON 数据集、来源标记、schema 推断、SHA-256、去重、训练、预测、EI 贝叶斯优化、实验回灌与重训。
- 新增 Ridge / RandomForest / HistGradientBoosting / GaussianProcess / 自动 / 集成算法；KFold/GroupKFold；OOF 指标、散点、置换重要性。
- 不确定性来自 GP 后验、RF 树间方差或 OOF 残差；优化候选包含 95% 区间、EI 与置信度。
- 结果列自动标记 `leakage_risk` 并默认排除；合成/混合数据必须显式 opt-in。
- 数据集/模型/run 全部本地 SQLite + artifact，模型版本可追溯，重训保留父模型。
- Web 新增“模型实验室”；Android 支持 Lab 文件导入与 CSV 保存；端口改为 8003。
- 29 项测试通过；v1.0.0、v2.0.0、v2.1.0 保持原样。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-3.0.0.apk` | `31834c94ce9a581265768f03e90d56b68a0a527534e30dcea0bd0d398aad2ea1` |

**验证记录**

- `pytest tests -q` → `29 passed`。
- 演示集：180 行合成数据，SHA-256 `cf93df6f479d236244610d5b10a81009928d6b34d21c48eb8d638979a35922ef`；`auto` 训练 R² ≈ 0.85、MAE ≈ 7.3。
- API 冒烟：登录、demo、导入、训练、模型卡、optimize 5 候选、run CSV、predict、feedback+retrain、dataset CSV、delete 全部通过。
- 浏览器：1440×1000 训练/优化/结果页正常；390×844 无横向溢出，底部“实验室”标签可用。
- Android：APK versionCode 4 / versionName 3.0.0，`apksigner` v2/v3 通过；内置 `lab.js` 与 `sw.js`。

**已知限制**

- 没有湿实验/供应商批次数据；演示集是合成数据，只能验证流程。
- 表格回归不是机理模型；交叉验证误差可能很大，预测区间未外部校准。
- 优化空间不能外推；候选是 EI 建议，不是实验结论。
- 模型/数据版本可追溯，但不是 GLP/ELN 合规系统。
- APK 仍是服务器客户端；断网不能训练或设计。

## v2.1.0 — 2026-10-20

**主题：从“可解释配方”升级为“可审计证据链”。**

- 先分类实体再查库：化合物只查 PubChem/UniChem/ChEBI/ChEMBL/Europe PMC/MassBank，蛋白只查 UniProt/PDB/AlphaFold/STRING/Europe PMC，食品只查 FDC/Open Food Facts/Europe PMC。
- 删除名称型跨库候选；跨库链接只接受 InChIKey、UniProt→PDB xref 或显式谱图引用。
- 新增 96 配料组成快照：35 个 USDA FDC SR Legacy 映射 + 61 个 curated estimate，全部标记来源与置信度。
- 食品设计去随机；新增约束审计、假设区间、指标来源、证据等级、配方改动和 facts/rules/assumptions/uncertainty/validation_required。
- 修复 v2.0 的相关性错误（如槲皮素误连 UniProt/PDB/STRING/FDC）、PubChem/OFF/STRING/FDC 接口问题，以及移动端横向溢出。
- 目标解析支持 `mg`/`g`/`%` 与 pH 范围；`钠 < 300 mg/100g`、`盐 < 1 g/100g` 等会进入硬约束。
- 端口改为 8002；Android APK versionCode 3 / versionName 2.1.0。
- 25 项测试通过；v1.0.0 与 v2.0.0 保持原样。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-2.1.0.apk` | `d681102475f58ef45f7212666bd9618470703ecbd570465da7e29a8989473187` |

**验证记录**

- `pytest tests -q` → `25 passed`。
- `quercetin`：PubChem CID `5280343`，InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`，UniChem → `CHEBI:16243` / `CHEMBL50`；不调用 UniProt/PDB/STRING/FDC。
- `beta-lactoglobulin`：UniProt `P02754`，PDB xref，STRING taxon `9913`；不调用 PubChem。
- 设计 API：`package_version=2.1.0`，约束/区间/组成/来源/推理链字段齐全。
- 移动端 390×844：设计、证据、约束卡、查询计划无横向溢出。

**已知限制**

- 没有湿实验或供应商批次数据；A 级证据仍为空，配方仍需中试/实验验证。
- FDC SR Legacy 是 2018 编译数据，不是当前批次；61 个配料仍为 curated estimate。
- pH/aw/货架期/感官/微生物是规则情景，不是动力学或微生物模型。
- 在线 API 可能限速、变更或返回错误；错误隔离与缓存不等于数据正确。
- MassBank 仅链接；KEGG 默认不查询；APK 仍是服务器客户端，不是完整离线引擎。

## v2.0.0 — 2026-10-20

**主题：从单答案分子设计，升级为全食品体系的多配方组合 + 在线证据 + 本地机制计算。**

- 新增 20 个食品体系、96 项配料、46 条相互作用、8 个端到端案例。
- 每次设计生成 8 个可比较候选，而不是只返回一个答案；硬约束和 portfolio 过滤落到 `food.py`。
- 新增登录（HttpOnly 会话 Cookie + 可选 Bearer token）、v2 API、运行目录隔离。
- 新增 11 个在线数据源联邦、24 小时缓存、PubChem 质谱峰、跨库链接与证据图谱。
- 新增 Vina → GROMACS → CP2K 本地任务编排、步骤状态、artifact 下载与 HTML/Markdown 报告。
- 重写 Apple 风格 Web UI：桌面侧栏、移动底栏、横向候选卡片、滑动切页、深浅色适配。
- 新增 Android 2.0.0 APK（versionCode 2），默认连接 v2 服务器。
- 新增 19 项测试；v1 生物设计、报告与 MCP 回归保持通过。
- v1.0.0 保持原样；v2 独立在 `v2.0.0/`，服务端口 8001。

**交付物**

| 文件 | SHA-256 |
|---|---|
| `dist/BioForgeStudio-2.0.0.apk` | `1e80ccde66b488c7c902cf174dc791453b529232d4574f393113ebf148f1fed1` |

**已知限制**

- 配方/指标是 curated priors 与模板估算，不是实测或法规结论。
- Vina 是刚性受体打分；GROMACS 只有 2 ps 演示 MD；CP2K 是配体单点，不含蛋白口袋。
- OpenMM 仅 Reference 平台，不用于生产 MD；默认使用 GROMACS。
- MassBank 无稳定 JSON API，仅链接记录页；KEGG 默认不查询。
- APK 需要服务器运行；真机通过 `adb reverse` 连接。

## v1.0.0 — 2026-10-20

- 蛋白/小分子荧光设计、保护剂优化、数字孪生、光谱匹配、报告、训练、MCP。
- 13 项测试通过；APK 150 KB；服务端口 8000。
- 交付位置：`/home/h3c/md-agent/bioforge/`（v1 根目录）。


## 3.2.0 增量修正 — 2026-10-22 下午

- Web/服务端新增力导向证据图谱、3D 组分控件、中英文相关度检索、加工机制预测、GenBank/KEGG/ZINC 连接器和许可 catalog。
- `pytest tests -q` → `38 passed, 1 warning`。
- APK 重建：`dist/BioForgeStudio-3.2.0.apk`，210,246 bytes，SHA-256 `ec95a5c1e4bdb4e0d74bc758657d9867ae7f16c96044ec8fd3fc41e3d8b33b5d`，versionCode 6 / versionName 3.2.0，v2/v3 签名通过，内置 SW `bioforge-v32-shell-2`。
- 旧 3.2.0 包（202,054 bytes，SW `bioforge-v32-shell-1`）被本次构建覆盖，如有需要请从版本控制/备份恢复。
