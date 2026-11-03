# BioForge Studio 3.2 优化记录

日期：2026-10-22

## 1. 生物设计 500 修复

- 现象：`POST /api/v2/design` 生物模式返回 Internal Server Error。
- 根因：`backend/app_v3.py` 的 `design_v2` 读取 `result['design_id']`，但 v1 `engine.design()` 只返回 `job_id`。
- 修复：`design_id = result.get("design_id") or result.get("job_id")`，并回填 `result["design_id"]`。
- 验证：生物查询返回 200、可保存、可构图；新增回归测试。

## 2. 生物设计专用前端

- `renderDesign` 识别 `mode=biologic` / 无 `portfolio` 的响应，交给 `renderBiologic`。
- 新增候选切换、生物指标卡（Tm、工艺/总保留、亮度、λem）、保护剂组合表、工艺卡、数字孪生、QC/控制点、风险与推理链。
- 非当前候选只展示其保护剂组合，避免把当前候选的工艺/QC 误套到其他候选。
- 修复结果标题、候选数、计算入口和“运行机制计算”的标签。

## 3. 交互式证据图谱

- 从固定径向 SVG 改为力导向布局 + 可缩放/平移视图。
- 支持按类型/连接度/计算状态着色，隐藏数据源/推理链，点击节点查看字段、相关边和外部链接。
- 生物设计图新增蛋白/靶点、候选、保护剂、机制、推理步骤节点；食品设计保持兼容。
- 修复生物设计图 `system:None` 与空标签问题。

## 4. 3D 查看器升级

- 支持 PDB、PDBQT 多 MODEL、GROMACS GRO 多帧。
- 表示法：卡通主链、主链线、球棍、空间填充；着色：元素、链、深度。
- 蛋白/配体显隐、构象选择、点击原子查看残基、单字母序列条、聚焦/重置、PNG 导出。
- 计算作业中的 `receptor.pdb`、`poses.pdbqt`、`md.gro` 可直接打开；新增参数/结果 JSON 与摘要 CSV 导出。

## 5. 文献库增强

- 新增 `backend/literature.py` 与 `/api/v3/literature/stats|search|topics`。
- 本地 BM25 检索接进“在线证据”页，展示年份、许可、来源、MeSH/关键词标签和原文链接。
- 采集脚本新增 `mesh`、`keywords`、`chemicals` 列和 `enrich` 命令；本轮补全 9,197 条记录的 MeSH/关键词。
- Obsidian frontmatter 增加 `mesh/`、`keyword/`、`chemical/` 标签；索引仅把 topic 写入知识图谱，避免图谱被主题词淹没。

## 6. 应用内说明与 UI

- 新增“使用指南”页面和顶栏 `?` 入口，解释设计结果、图谱、3D、Lab、文献、故障和边界。
- 结果区新增“这张结果怎么读？”可展开解释。
- 新增柔和动态背景、页面进入动画、卡片阴影过渡，并尊重 `prefers-reduced-motion`。
- 移动端侧栏点击外部自动关闭；补齐远程部署提示。

## 7. 远程部署

- 新增 `Dockerfile`、`docker-compose.yml`、`deploy/Caddyfile`、`deploy/.env.example`、`scripts/public_tunnel.sh`。
- 新增 `docs/DEPLOYMENT.md`：Cloudflare Tunnel、Tailscale、VPS+Caddy 三条路径和安全检查表。
- 登录 Cookie 支持 `BIOFORGE_COOKIE_SECURE=1`；Compose 默认开启 HTTPS 安全 Cookie。

## 8. 版本与验证

- 版本：3.2.0；APK versionCode 6；SW cache `bioforge-v32-shell-1`。
- 测试：32 项通过（含生物设计 ID/图谱回归、文献检索）。
- 新增文献检索测试在数据库不存在时跳过，保证可移植性。
- 仍保留科学边界：模型/模拟/文献标签都不是湿实验或法规结论。

## 12. 客户级升级（2026-10-22 下午）

### 12.1 共享中英文查询

- 新增 `backend/query_text.py`：中文→英文别名、英文缩写、连接词清理、术语抽取、相关度/强度分级。
- `datasources` 和 `literature` 统一使用该模块；文献 FTS 用扩展术语召回，再按 BM25 + 词面相关度重排。
- 修复 `固体饮料` 被 `饮料` 抢先匹配为 `beverage_generic` 的问题：`detect_system` 改为 (命中数, 关键词长度) 的优先级。
- 修复化合物/蛋白查询路由取到 `stability`、`binding` 等通用词导致 PubChem 查询错误的问题；`route_queries` 会过滤通用词和蛋白词，并新增回归测试。

### 12.2 新增数据源与许可边界

- 新增 GenBank（NCBI E-utilities）、KEGG REST、ZINC 连接器；`data/sources.json` 扩到 16 条。
- `datasources.status()` 增加 `catalog`：DrugBank/CCDC/ChemBook（需许可/凭据）、NMRShiftDB2/LIPID MAPS/GlyTouCan（公开参考入口）、高校图书馆（需机构代理）。
- 设置页新增“数据源与许可”面板，明确区分“可查询”和“未授权不抓取”。

### 12.3 加工分子机制引擎

- 新增 `backend/processing.py` v1.0，并在 `backend/food.py` 的候选和选中结果中输出 `processing_effects`。
- 规则覆盖蛋白热变性、美拉德、花青素、抗坏血酸、脂质氧化、淀粉糊化、蔗糖酸水解、亲水胶体、明胶、酶解、乳酸发酵和低强度兜底。
- 每条输出保留参照文献、机制、宏观影响、置信度和验证建议；无证据的步骤只作为流程。
- 修复挤压膨化未触发淀粉糊化：识别 `snack_extruded` 和低水分挤压条件。
- 低糖固体饮料增加赤藓糖醇/菊粉/reb_a 替代路径，使“活菌 + 低糖 + 冲调 pH 4.5”案例通过硬约束。

### 12.4 图谱与 3D 交互

- 图谱后端增加节点/边语义、稳定 edge ID、citations、置信度、工艺步骤和 `predicts_change` 边、`semantics` 字典。
- 图谱前端改为力导向生长动画：节点拖拽牵拉邻居、背景平移、滚轮/双指缩放、双击证据、边点击关系详情；移除加减号按钮。
- 3D 改为按真实组分动态生成控件：蛋白/水/离子/糖链/脂质/配体/其他；默认隐藏水，支持预设和多构象保留选择。
- 移动端侧栏支持左滑收起，正文滑动切页；背景加低对比度缓慢漂移，并尊重 `prefers-reduced-motion`。

### 12.5 案例与回归

- `data/cases.json` 扩到 17 个案例，新增高蛋白谷物棒、高纤挤压零食、低盐泡菜、可食膜、益生菌固体饮料、低糖果冻、UHT 乳、低脂蛋黄酱和减糖巧克力。
- 新增 `tests/test_query_processing.py`：查询扩展、相关度、加工证据、图谱语义、体系识别和案例硬约束。
- 回归结果：`38 passed, 1 warning`；`node --check web/app.js` 和 `node scripts/check_web.js` 通过。
- Service Worker 缓存升至 `bioforge-v32-shell-2`，HTTPS 下也会注册。

## 13. 3.2.1 交付优化（2026-10-23）

### 13.1 端口与运行

- BioForge 固定 8010；8003 释放给 RustDesk。Web、Android、Docker、Caddy、Tunnel、脚本和当前文档统一；历史 CHANGELOG 中的 8003 保留为历史事实。
- `scripts/run_server.sh` 默认 8010；当前服务 PID 542977，日志 `runtime/server-v3.log`。

### 13.2 PostgreSQL + pgvector

- 容器 `bioforge-db` 使用 `pgvector/pgvector:pg16`，数据卷 `bioforge_pgdata`，只绑定 `127.0.0.1:5432`。
- schema 覆盖 literature、chunks、entities、edges、catalog、sources、app_users；`embedding vector(1024)` 已建列但未回填。
- `scripts/start_postgres.sh` 幂等启动/初始化；`scripts/sync_postgres.py` 同步 SQLite/JSON 并写 `last_sync`；`backend/db.py` 提供状态与全文检索，异常回退 SQLite。

### 13.3 合法资源目录

- 38 条来源分 6 组，标注许可/接入状态/用途；13 条可直接查询、3 条机构入口；Sci-Hub 明确排除。
- `backend/oa.py` 只用 Crossref、Europe PMC、Unpaywall；DOI/PMID 返回合法 OA 或官方入口，不绕过付费墙。
- 机构访问使用 SCUT/CARSI 官方链接和可选 `BIOFORGE_EZPROXY_PREFIX`；不提供账号密码输入框。

### 13.4 UI 与构建

- 资源库页、快速弹层、DOI 表单、12 主题、明暗模式、背景动画、机构说明弹窗、设置页数据库状态卡。
- Docker 国内 PyPI/Debian 镜像默认清华；compose 增加 db 服务、healthcheck、卷和可选 env_file；镜像构建成功（766 MB），独立容器 health 3.2.1。
- SW `bioforge-v321-shell-2`；APK versionCode 7 / versionName 3.2.1，218,438 bytes，v2/v3 签名通过。

### 13.5 验证与边界

- 42 passed, 1 warning；Headless Chrome 资源库 38 卡片、12 主题、PostgreSQL 已连接、机构弹窗无输入框、DOI 解析成功。
- 未完成：embedding 回填/HNSW、多用户 auth 迁移、NCBI key、compose 全栈启动、真机验收、公网部署。


## 14. 3.2.2 功能闭环（2026-10-23）

### 14.1 案例、资源与路由

- 案例 21 个，覆盖 20 食品体系 + 1 机制案例；资源 7 组 45 条，新增 7 条光谱/结构入口。
- 食品识别补充果汁、乳、奶、蛋糕、香肠、果冻、泡菜、保鲜、膜、谷物棒等词；机制词优先走生物路径，21 个案例逐条路由测试通过。

### 14.2 多组合计算

- 受体/配体笛卡尔积最多 12 对，逐对目录 `pairs/NN_*`；排名、`screening.csv`、`report.html`、根/逐对 `complex.pdb`。
- 受体准备加 `-x/--delete_bad_res`，修复 1GFL 非标准残基；1BEB-curcumin `-7.967`、1BEB-quercetin `-7.484`、1GFL-quercetin `-2.562 kcal/mol`。
- `advanced_scope` 支持代表项/全部；复合物 PDB 是刚性拼装，不是能量最小化结构；复合物 MD 则从该 pose 出发，运行 ACPYPE/GAFF2 拓扑、中和、EM + 短 NVT。

### 14.3 助手、笔记、3D、图谱与双语

- Ollama `qwen3.8:27b` 问答 8 次/60 秒限流，历史本地保存/月备份；Obsidian 只读、2 MB、路径安全。
- 3D 7 种着色、全聚合物序列、配体组分、复合物加载；图谱字典与 provenance/caveat；核心界面中英切换；12 主题独立纹理。

### 14.4 验证与构建

- 51 passed, 1 warning；CDP 登录/双语/图谱/3D/复合物/390 px 无溢出、0 JS 异常；移动端 8 标签在 320–430 px 全部可见。
- SW `bioforge-v322-shell-5`；APK versionCode 8 / versionName 3.2.2，259,626 bytes，SHA-256 `87cc368ae8a0dfc7ed6ebb80f9ece6063f4f8e150c6211699264345ecde92a44`，v2/v3 签名通过。
- 复合物 MD：`md_mode=complex` 默认开启，UI 可切到仅蛋白；1BEB+quercetin 任务 `C20261023T091435Z-9e283468` 使用 32 原子配体、16 Na+ 中和、0.2 ps NVT，EM 首轮 5000 步后 Fmax 仍为 5707.8 kJ/mol/nm，自动二次 EM 244 步收敛到 456.8；配体质心漂移 0.218 Å、原子 RMSD 0.338 Å、最近蛋白接触 1.857 Å。
- 轨迹接口转换 `C20261023T091435Z-9e283468` 的 `md.xtc`，返回 395,527 bytes PDB；资源库/设置动态文案与占位符完成英文化。
- Docker `v300-app` 重建（image `43180eb0d289`），临时隔离容器 `8011` health 3.2.2，验证后停止；宿主 8010 重启为 PID `386093`；SW 升至 `bioforge-v322-shell-5`，APK 重建并保持 v2/v3 签名。
- 未完成：compose 全栈、真机验收、embedding、公网部署。
