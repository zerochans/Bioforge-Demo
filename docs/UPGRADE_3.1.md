# 升级到 BioForge Studio 3.1

日期：2026-10-21

## 概要

v3.1.0 在 v3.0.0 的 Model Lab 之上，新增手机局域网直连、参数化计算、工具/HADDOCK 检测、3D 结构查看器和 OA 文献知识库。食品设计、在线证据、Model Lab、登录和 v2/v3 API 保持兼容。

| 项目 | v3.0.0 | v3.1.0 |
|---|---|---|
| 服务监听 | `127.0.0.1:8010` | `0.0.0.0:8010`（可覆盖） |
| APK | versionCode 4 / 3.0.0 | versionCode 5 / 3.1.0 |
| 手机连接 | USB + `adb reverse` | 首次启动填 LAN 地址，`/api/health` 探测 |
| 计算 | 固定参数为主 | 参数化 + SHA-256 运行指纹 + 进程组超时 |
| 工具设置 | 无 UI | `GET/PUT /api/v3/tools`，含 HADDOCK3 检测 |
| 3D 结构 | 无 | `GET /api/v3/structure/{pdb_id}` + canvas 查看器 |
| 文献 | 在线检索 | Europe PMC → SQLite FTS5 → Obsidian → 知识图谱 |
| 测试 | 29 | 30 |

## 1. 启动与 LAN

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

`scripts/run_server.sh` 现在：

- 默认 `BIOFORGE_HOST=0.0.0.0`，`BIOFORGE_PORT=8010`；
- 启动前用 `ss -ltn` 检查端口占用；
- 优先使用 `molecule_tools` 解释器；该环境不可用时回退到 `mychem`。

查看 LAN 地址：

```bash
hostname -I
curl -s http://127.0.0.1:8010/api/health
```

手机与电脑必须同一局域网，且防火墙允许 8010。跨公网请用 HTTPS 反向代理，不要直接暴露明文 HTTP。

## 2. Android

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
ANDROID_SDK_ROOT="$PWD/android/sdk" bash android/build_apk.sh
adb install -r dist/BioForgeStudio-3.1.0.apk
```

- 首次启动弹出原生服务器配置：填写 `http://<LAN-IP>:8010/`，点“测试并保存”。
- 连接测试会请求 `/api/health`，检查 `status` 和 `version`；失败可重试或离线预览。
- 登录页“修改服务器地址”和设置页可重新配置。
- versionCode 5 / versionName 3.1.0，与 v3.0 使用同一签名，可覆盖安装并保留应用数据。
- 明文 HTTP 已对整个应用启用，仅适合可信局域网。
- 首次配置对话框不可用返回键绕过；配置成功后不再强制弹窗。

## 3. 计算参数与工具

- 旧的 `options.max_steps` 不再作为参数入口；使用 `docking_*`、`md_*`、`em_steps`、`dt_ps`、`temperature_k`、`threads`、`qm_*`、`timeout_*`。
- 参数会被夹取到安全范围，非法值回退默认值；响应/报告中的 `config` 是实际使用值。
- 每次任务生成 `parameter_fingerprint`；相同目标+参数指纹相同。
- 后台进程超时会终止整个进程组，不再需要手工清理 `gmx`/`cp2k`。
- 工具路径保存到 `runtime/tool_paths.json`（`0600`）；保存前校验绝对路径、存在性和可执行权限。
- HADDOCK3 路径可检测，`capabilities` 会显示版本；**尚未接入自动任务**。小分子任务继续使用 Vina。

详见 `docs/COMPUTE.md` 和 `docs/API_V3.md`。

## 4. Web/PWA

- 设置页新增“本地工具”和 Android 服务器卡片。
- 计算页新增 16 个参数输入、恢复默认、运行指纹和配置 chip。
- 结构页/计算页可加载 PDB，支持旋转、缩放和自动旋转。
- Service Worker 缓存为 `bioforge-v31-shell-2`。旧 PWA 需刷新或清除站点数据。
- 新增 `docs/LITERATURE_PIPELINE.md`。

## 5. 文献库

默认根目录：`/media/h3c/Win11Pro X64/data/literature`。

```bash
PY=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python
$PY scripts/literature_pipeline.py stats
$PY scripts/literature_pipeline.py search 'beta-lactoglobulin quercetin' --limit 5
```

- 首次采集：`harvest --target 10000 --pdf-limit 12 --build`。
- 已有库不要重复全量采集；脚本按 DOI 去重，可增量运行。
- 当前库为 10,000 篇 OA 元数据、10,000 条 Obsidian 笔记、26,284 个文本块、48,544 个实体、76,954 条边、12 篇全文。
- 全文转换优先 Europe PMC JATS XML；`pdf=render` 可能被 Cloudflare 403 拦截。
- 磁盘仅约 1.2 GB 可用，不要批量下载上万 PDF。

## 6. 验证

```bash
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest tests -q
```

预期 `30 passed`。

手工：

1. `curl http://127.0.0.1:8010/api/health` → `version=3.1.0`。
2. 手机浏览器打开 `http://<LAN-IP>:8010/`，登录成功。
3. APK 首次启动填写服务器地址，测试连接通过。
4. 计算页提交短任务，确认参数 chip、指纹、报告和 artifact。
5. 结构页输入 `1BEB`，确认 3D 渲染。
6. 设置页确认 GROMACS/CP2K/HADDOCK 检测状态。
7. 文献 `stats` 和 `search` 正常。

## 7. 已知限制

- 无真机/模拟器验证 APK 首启对话框与 LAN WebView 登录；构建、签名和清单已验证。
- HADDOCK 只检测，不执行。
- 文献是规则标签 + BM25，不是系统综述或向量 RAG；全文只有 12 篇。
- APK 仍是服务器客户端，断网只能显示提示页。

## 8. 回滚

v3.0 目录/配置未删除。回滚 APK 使用 `dist/BioForgeStudio-3.0.0.apk`；服务回滚到 3.0 代码后重启即可。`runtime/tool_paths.json` 和文献库不影响旧版本，可保留。
