# v3.2.2 交付说明

日期：2026-11-02  
版本：BioForge Studio 3.2.2  
目录：`/home/h3c/md-agent/bioforge/v3.0.0`  
GitHub：<https://github.com/zerochans/Bioforge-Demo>

## 最终产物

| 产物 | 路径 | 说明 |
|---|---|---|
| Android APK | `dist/BioForgeStudio-3.2.2.apk` | 357,999 bytes，minSdk 24，targetSdk 34，versionCode 8，versionName 3.2.2，2026-11-02 重建（含 HADDOCK3 UI/可折叠界面） |
| APK SHA-256 | `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f` | `sha256sum` 可复核；v2/v3 签名通过 |
| Web/PWA | `web/index.html` + `web/app.js` + `web/lab.js` | 品牌 `STUDIO 3.2.2`，SW `bioforge-v322-shell-13` |
| iOS 工程 | `ios/BioForgeStudio.xcodeproj` | WKWebView 壳，iOS 15+ / Xcode 15+；未编译、未签名、无 `.ipa` |
| API 服务 | `backend/app_v3.py` | 监听 `0.0.0.0:8010` |
| PostgreSQL | `bioforge-db` + `backend/db.py` | PostgreSQL 16.15 + pgvector 0.8.7，数据卷 `bioforge_pgdata` |
| 资源目录 | `data/resources.json` + `backend/resources.py` | 7 组 45 条，含光谱/波谱证据，合法官方入口，排除 Sci-Hub |
| DOI/PMID 解析 | `backend/oa.py` | Crossref / Europe PMC / Unpaywall，只返回合法 OA/官方入口 |
| 文献 API | `backend/literature.py` | SQLite FTS5/BM25；PostgreSQL 不可用时回退 |
| 本地助手 | `backend/assistant.py` | Ollama `qwen3.8:27b`，本地历史/月度备份 |
| Obsidian 笔记 | `backend/notes.py` | 只读、2 MB 上限、路径穿越防护 |
| 登录 | `backend/auth.py` | Cookie + Bearer token；当前仍为单用户 |
| 测试 | `tests/` | 64 passed, 1 warning（2026-11-02 回归） |
| 部署 | `Dockerfile`、`docker-compose.yml`、`deploy/` | PostgreSQL healthcheck、Caddy HTTPS、Tunnel 骨架 |
| 文档 | `README.md`、`docs/`、`RELEASES.md`、`CHANGELOG.md` | 含用户指南、部署、数据源、限制说明 |
| GitHub CI | `.github/workflows/build-ios-unsigned.yml` | macOS runner 构建未签名 IPA；需重签后安装 |

旧版 `dist/BioForgeStudio-3.2.1.apk`、3.2.0、3.1.0 和 3.0.0 保留用于回滚，不作为本次交付主包。

## 2026-10-28 质量收口

- 助手：空 content/仅隐藏 thinking 自动重试 `num_predict=1600/2400/4096`；API 实测 547 字符、`done_reason=stop`、`eval_count=116`、29.4 s，不再返回空气泡。
- 食品设计：目标配料（咖啡因、茶提取物、乳清蛋白、槲皮素）进入每个候选并受上限约束；修复“咖啡”误映射和“不含藻蓝蛋白”仍添加的问题；显式荧光蛋白不再被食品色蛋白替代。
- 计算：`_resolve` 识别带字母的 4 位 PDB ID；`_manual_compute_query` 支持仅字段提交；`1BEB + quercetin`、`1GFL + caffeine`、多受体×多配体、`whey + SMILES` 均正确解析；字段任务 `C20261027T021359Z-cefff7b7` 完成 4 对。
- 英文与布局：修复工具状态/图谱/节点 inspector/计算错误等动态中文；展开 42 个任务卡、案例/资源/指南/HADDOCK 后可见 CJK 0；证据提示不再重叠，320–390 px 模式切换不溢出，资源下方在 1080 px 以下单列。
- 交互与视觉：案例、资源组、助手、笔记、HADDOCK/参数/工具面板可折叠；任务卡倒序 + 全部展开/收起；新增 HADDOCK3 运行选择按钮、侧栏半透明 DNA/蛋白/RNA 里程碑图和星云/星点背景。
- 回归：`64 passed, 1 warning`；`node --check`、`node scripts/check_web.js` 通过；APK `357,999` bytes / SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`；Docker 镜像已重建。

## iOS 客户端（2026-11-02）

- 路径：`ios/BioForgeStudio.xcodeproj`；源码 `ios/BioForgeStudio/AppDelegate.swift`；资源 `ios/BioForgeStudio/Assets.xcassets`；离线壳 `ios/www/`。
- 功能：服务器地址输入 + `/api/health` 探测、Cookie 登录、离线静态预览、外部链接跳转、文件导出、`AndroidBridge` 兼容桥。
- 同步：修改 `web/` 后执行 `./scripts/sync_ios_web.sh`；工程也可用 `cd ios && xcodegen generate` 从 `project.yml` 再生成。
- 构建：需要 macOS 13+、Xcode 15+ 和 Apple Developer Team；`ios/README.md` 含模拟器编译、Archive 和 `.ipa` 导出命令。
- CI 构建：`.github/workflows/build-ios-unsigned.yml` + `ios/ci/build_unsigned_ipa.sh`，在 macOS runner 上生成未签名 `.ipa`；需用 Sideloadly/AltStore 或正式证书重签后才能安装。当前尚未实际运行 CI。
- 状态：**未在 Linux 编译或签名，未做模拟器/真机验收，当前没有可安装 `.ipa`**；不能表述为“已交付 iOS 安装包”。
- ATS：为任意用户输入的局域网 HTTP 服务器启用 `NSAllowsArbitraryLoads`/`NSAllowsLocalNetworking`；公网必须 HTTPS。

## 英文覆盖（2026-10-28）

- `web/i18n-data.js` 已加载到 Web/PWA 与 APK：exact 1740、numeric 199、terms 115、bad 0；冲突数字骨架 295 条由 exact/pattern 回退覆盖。
- Headless Chrome 可见文本扫描：20 个食品案例、机制案例、资源弹层、图谱节点/边详情、3D 查看器、HADDOCK3 表单/展开面板、42 个任务卡和 8 个主页面均为 0 CJK；旧计算 query 已模板化，用户新输入的中文 query 仍按原文显示。
- 英文目标量解析与中文对齐：`≤8% sugar` / `≥6% dietary fibre` 等名词后置写法可解析；配方候选按组成去重，不足 8 个时生成显式原料替代变体，20 个案例均返回 8 个唯一配方。
- 英文助手回答新增语言校验：英文问题得到非英文回答时会重试，最终仍失败则返回英文错误，不写入历史。

## 当前运行状态

- 服务：`0.0.0.0:8010`，health `version=3.2.2`、`lab_version=3.2.2`、`mode=food+biologic+lab`
- LAN：`http://10.194.51.41:8010/`（以 `hostname -I` 当前值为准）
- PID：`3630499`，记录在 `runtime/bioforge-8010.pid`
- 日志：`runtime/uvicorn-8010.log`
- 登录：`admin` / `bioforge-demo`，凭据文件 `runtime/login.txt`；**交付客户前必须修改**
- PostgreSQL：`127.0.0.1:5432`，容器 `bioforge-db`，`10,000` 篇文献、`25,062` 文本块、`48,544` 实体、`76,954` 边、`187 MB`
- 向量：`literature_chunks.embedding` 为 `vector(1024)`，当前 `0` 条，尚无向量召回/HNSW
- 8003：已释放给 RustDesk（当前 PID `274622`，会随服务重启变化），不要再把 BioForge 改回 8003
- 文献库：`/media/h3c/Win11Pro X64/data/literature`，10,000 篇 OA、25,062 块、12 篇全文
- Obsidian：`/media/h3c/Win11Pro X64/data/literature/obsidian/00-BioForge`，10 篇只读笔记
- 助手：Ollama `127.0.0.1:11434`，模型 `qwen3.8:27b`，历史 `runtime/assistant/history.jsonl`
- 计算运行目录：`runtime/compute/`；模型 artifact：`runtime/models/lab/`
- Secret：`runtime/secrets/postgres.env`、`contact.env`（0600）；不得复制到 Web/APK/文档

## 启动

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
./scripts/start_postgres.sh
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

公网/远程访问见 `docs/DEPLOYMENT.md`。不要直接暴露 `http://IP:8010` 和默认密码。

## 3.2.2 交付验证

- `molecule_tools/bin/python -m pytest -q tests` → `64 passed, 1 warning`（2026-11-02 复跑；含助手隐藏思考回退、食品目标配料/显式蛋白、计算 PDB/仅字段提交回归）。
- Headless Chrome（2026-11-02 CDP 复测）：登录、指南/笔记、中英切换、资源库/设置页、20 个食品案例、机制案例、证据图谱/节点/边详情、计算作业与 3D 查看器、移动端 8 个底部标签在 320–430 px 全部可见、390 px 无横向溢出、0 JS 异常；英文模式可见 CJK 扫描为 0。
- 数据库状态：PostgreSQL 16.15、pgvector 0.8.7、10,000 文献、25,062 文本块、76,954 图谱边、187 MB、0 向量。
- 8003 端口：`ss -ltnp` 确认 RustDesk 监听；BioForge 8010 health 正常。
- 配方候选：20 个食品案例均返回 8 个唯一配方；`case_low_sugar_jelly` 糖 ≤8%、纤维 ≥6% 中英一致，`Settings` 中显示膳食纤维下限；变体带 `strategy_en`、`substitution` 和“variant … for …”标签，不再用相同配方重复占位。
- APK：2026-11-02 重建，357,999 bytes，versionCode 8 / versionName 3.2.2，SW `bioforge-v322-shell-13`；`apksigner` v2/v3 通过；内置 `assets/www` 含 HADDOCK3 表单/任务卡/运行选择按钮、多组合计算、助手/笔记、`i18n-data.js`、资源/设置/图谱/3D/计算动态翻译、可折叠 UI、侧栏里程碑图、科学背景 SVG 和 EM 默认 5000。
- 计算：多组合任务 `C20261023T073906Z-8dbbf207` 完成 1BEB 两对排名（curcumin `-7.967`、quercetin `-7.484 kcal/mol`）；1GFL 修复非标准残基后单对复测 `-2.562 kcal/mol`。
- 高级计算：`C20261023T075504Z-5b172d8e` 完成 GROMACS 蛋白-only EM + 0.2 ps NVT（1/1 receptor）；`C20261023T075532Z-2635b9c1` 完成 CP2K PBE/DZVP 单点（1/1 ligand，32 atoms，26.4 s）。
- 复合物 MD：`C20261023T091435Z-9e283468` 完成 1BEB+quercetin 的 32 原子配体 ACPYPE/GAFF2 拓扑、16 Na+ 中和、EM + 0.2 ps NVT；EM 首轮 5000 步后 Fmax 仍为 `5707.8 kJ/mol/nm`，自动二次 EM 244 步收敛到 `456.8`；配体质心漂移 `0.218 Å`、配体原子 RMSD `0.338 Å`、最近蛋白接触 `1.857 Å`；`md_mode=complex` 默认开启，UI 可切换为仅蛋白。
- 文献：`quercetin` 检索正常；DOI `10.3390/polym17131871` 解析返回标题、期刊、年份和 OA 位置。
- `docker compose config` 已通过（需提供 `POSTGRES_PASSWORD`/`BIOFORGE_DOMAIN`）；`v300-app:latest` 已重建（约 767 MB），临时隔离容器 `18010` 的 `/api/health` 返回 3.2.2、`haddock-open` 和 SW shell-13 可见；容器内无 HADDOCK3 二进制，验证后已停止。compose 全栈未启动，公网隧道未上线。不能把“文件存在”表述为“已部署”。
- 轨迹：`GET /api/v3/structure/trajectory/C20261023T091435Z-9e283468/pairs/01_1BEB_quercetin/gromacs_complex/md.xtc` 返回 395,527 bytes PDB，含 `MODEL` 帧；只接受 `.xtc` 且有 `md.tpr` 的作业内文件，缓存 `viewer/*-v2.pdb`。
- HADDOCK3 全流程直测：protein–protein `1BEB+1GFL` 210.6 s（score `-33.449`，2 模型/2 簇）、protein–ligand `1BEB+quercetin` 104.5 s（`-0.901`，2/2）、protein–polysaccharide `1BEB+1LMQ:B` 105.4 s（`-14.517`，2/2）。
- HADDOCK3 API：`C20261026T033248Z-ad0d98fe`（protein–ligand，`-30.953`）、`C20261026T033510Z-bfba7d57`（protein–protein，`-35.297`）、`C20261026T033510Z-782e343e`（protein–polysaccharide，`-41.814`）均完成；UI 提交任务 `C20261026T033637Z-fc7630d4` 完成（`-25.645`）。
- HADDOCK3 快速回归：`C20261027T000141Z-62c353e1`（sampling=2、无精修/聚类）24.4 s 完成，`-23.900`；cluster 字段显示 `—`，报告仅列实际产物。
- HADDOCK3 UI：CDP 打开表单 30 个输入、三种工作流、英文标签/占位符完整；任务卡显示 a.u. 分数、模型表、步骤、产物和 3D；`best_model.pdb` 加载 2,516 atoms / 2 chains；compute 页英文可见 CJK 0（用户输入的中文 query 除外）。
- 英文扫描：2026-10-28 复扫 20 个食品案例全部 `done=True`、`cjk=0`；`case_phycocyanin` 关联计算显示 “Acidic phycocyanin beverage”。

## 已知限制

- 无 adb/AVD，APK 3.2.2 真机首启、LAN WebView 登录、Service Worker 更新未做设备级验收。
- iOS 工程未在 macOS/Xcode 编译、未签名、未生成 `.ipa`；未做真机 Cookie、文件选择器、ATS/本地网络权限回归。
- Docker 服务器镜像只包含 Web/后端/文档，不包含 `ios/` 客户端源码；iOS 工程从源码目录单独交付。
- 多用户认证尚未迁移：`app_users` 表已建但登录仍走单用户 `auth.json`。
- 第三方 API 注册未执行；NCBI key 未接入，FDC key 支持保持原状；KEGG 可能间歇失败，ZINC 为 link-only。
- Crossref/Unpaywall/Europe PMC 受 DNS/网络影响，DOI 解析实测约 8–21 秒。
- 不提供 Sci-Hub、付费墙绕过、验证码规避或未授权批量下载；SCUT/EZproxy 具体前缀未配置。
- Docker 镜像不含 GROMACS/CP2K/Vina/ACPYPE/HADDOCK；容器 Web/HADDOCK3 表单可用，但 HADDOCK3 任务会因容器内无二进制失败。机制计算需宿主工具或专用计算镜像。compose 全栈（app+db）尚未在 8010 上启动，避免与宿主服务冲突。
- 复合物 MD 从刚性对接 pose 出发，使用自动电荷/质子化与短 NVT；结果不证明结合自由能，配体电荷和互变异构仍需人工复核。
- 公网部署需要域名、强密码、HTTPS 和访问控制；当前默认单用户/受控团队模型。
- Europe PMC PDF 端点可能 403；本地全文仅 12 篇；798 条无 PMID 记录未富化。
- 候选变体是同一目标下的原料替代筛选，不是独立验证过的配方；变体仍需做稳定性、感官和法规复核。
- 3D 是坐标可视化；图谱布局、文献标签、BM25 和向量都不是实验或临床证据。
- Ollama 仍可能出现空回答；当前有重试但根因未完全定位，不能把助手输出当作事实来源。

## 客户验收建议

1. 用真机安装 3.2.2 APK，填写 LAN/HTTPS 服务器地址，完成登录与重新打开设置。
2. 打开“资源库”，确认 45 条来源、筛选、DOI 解析和 SCUT/CARSI 官方入口。
3. 在“设置”查看 PostgreSQL 知识库状态，确认文献/文本块/图谱边和 0 向量提示。
4. 跑一个食品配方和一个生物设计，检查候选切换、图谱节点详情、计算入口。
5. 在“机制计算”输入 `1BEB,1GFL` 与 `quercetin,curcumin`，确认多组合排名、`screening.csv`、复合物 3D 和 `.xtc` 轨迹加载；在“使用指南”检查助手与 Obsidian 笔记。
6. 切换 English，确认资源库/设置/图谱/3D/计算动态文案、20 个食品案例和 320–430 px 底部 8 个标签；Obsidian 笔记按提示保留原文，助手历史只显示英文记录。
7. 公网部署前修改密码，按 `docs/DEPLOYMENT.md` 选择 Cloudflare Tunnel、Tailscale 或 VPS+Caddy。
8. iOS 如需交付，在 macOS 上按 `ios/README.md` 选择 Team、编译、Archive 并导出签名 `.ipa`，完成真机验收后再称为安装包。
