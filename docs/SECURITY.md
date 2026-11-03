# 安全与隐私

## 默认姿态

- v3.2 默认绑定 `0.0.0.0:8010`，以便同一局域网的手机访问；不需要 LAN 时用 `BIOFORGE_HOST=127.0.0.1` 收回环。
- v3 业务接口需要 HttpOnly 会话 Cookie 或 Bearer token；只有 `/api/health`、登录和静态资源公开。
- Token 首次鉴权请求时生成，保存在 `runtime/.token`，权限 `0600`；可用 `BIOFORGE_TOKEN` 覆盖，`BIOFORGE_REQUIRE_AUTH=0` 仅用于受控内网调试。
- 禁用 FastAPI `/docs`、`/redoc`、`/openapi.json`。
- 请求体上限 16 MB；设计 20 次/分钟、通用 120 次/分钟、外部数据库 40 次/分钟。
- 响应头：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`、`Permissions-Policy` 禁用摄像头/麦克风/定位。
- JSON 日志只记录请求 ID、方法、路径、状态、耗时、客户端；显式剔除 authorization/token/x-api-key。
- 任务 ID 白名单正则；artifacts 只允许固定文件与 `charts/`、`tables/` 前缀；解析后必须位于任务目录内。
- 外部数据库连接只允许 UniProt/KEGG/PubChem/ChEBI 固定域名，防止 SSRF。
- 反馈数据库、模型、模型卡、token 均为 `0600`；任务目录 `0700`。

## 客户端

- Web 默认离线：未配置服务器时查询不离开浏览器。
- Token 保存在本机 `localStorage`；公共设备不要保存。
- APK 只申请 `INTERNET`；内置静态壳，业务功能需要服务器。
- v3.2 为 LAN 直连启用 `usesCleartextTraffic=true`，仅适合可信局域网；跨公网必须使用 HTTPS 反向代理或 Cloudflare Tunnel/Tailscale。生产环境设置 `BIOFORGE_COOKIE_SECURE=1`，让会话 Cookie 仅经 HTTPS 发送。
- WebView 禁止 file URL 跨源访问与 content 访问，只加载 `android_asset` 本地资源；外部 http/https 链接交给系统浏览器。
- 导出通过系统 `ACTION_CREATE_DOCUMENT`，由用户选择保存位置。

## 部署建议

- 远程访问时使用反向代理（Caddy/Nginx）+ TLS，并继续绑定回环地址。
- 设置高强度 `BIOFORGE_TOKEN`，定期轮换；不要提交 token、`.env`、反馈数据库或模型文件。
- 多用户场景不要共享单个 token；当前版本没有账号、RBAC、审计用户身份，需在代理层补认证与访问控制。
- 定期备份 `runtime/feedback.db` 与 `runtime/models/`；备份也应加密。
- 对外提供服务前，审查 CORS 与限速策略；当前允许 `*` 源但禁止 credentials，适合本地/内网工具，不适合多租户公网服务。
- APK 当前使用本地演示密钥 `android/keystore/bioforge.keystore`（口令在构建脚本中）。生产发布必须重新生成密钥、离线保管，并更换包名/版本策略。

## 隐私边界

- 无遥测、无账号、无广告、无第三方分析。
- 只有用户主动调用 `/api/db/*` 时才会访问外部数据库；查询内容会发送到对应机构。
- 反馈数据只存在本地 SQLite；训练也在本地完成。
- 设计任务默认保存在本地 `runtime/jobs/`，保留最近 30 个；删除任务目录即可删除记录。
- 不要在查询或反馈中写入个人健康信息、患者数据或商业机密。

## 已知安全缺口

- Bearer token 是单密钥模型，没有过期、刷新、撤销列表或多用户隔离。
- 限速器为进程内存，重启清零，多进程不共享。
- 没有 WAF、审计告警、入侵检测。
- 演示 APK 密钥不是生产密钥。
- 外部数据库连接器只做域名 allowlist，未对返回内容做完整内容安全审查。

这些缺口不影响本地研究使用，但公网/多用户部署前必须补齐。

---

## v3.2.0 更新

- 新增 `BIOFORGE_COOKIE_SECURE`：公网 HTTPS 部署必须设为 `1`。
- 新增 Docker/Caddy/Cloudflare Tunnel 部署骨架；`deploy/Caddyfile` 负责 TLS 和安全响应头，`app` 端口不直接暴露公网。
- `scripts/public_tunnel.sh` 在检测到默认密码时拒绝启动公网隧道（除非显式 `BIOFORGE_TUNNEL_CONFIRM=1`）；Quick Tunnel URL 仍是公开地址，只用于演示。
- 文献库以只读 SQLite 挂载；查询使用参数化 SQL，不执行用户 SQL。
- 远程部署检查表见 `docs/DEPLOYMENT.md`。

## v3.1.0 更新

- 服务默认监听 `0.0.0.0:8010`；这是为手机 LAN 直连做的显式变更，不是公网部署建议。
- APK 首启配置服务器并请求 `/api/health`；地址保存在应用私有 SharedPreferences。
- 工具路径只接受绝对路径，文件必须存在且可执行，目录必须是目录；保存到 `runtime/tool_paths.json`（`0600`）。
- 结构代理只接受 4 字符 PDB ID，限制上游错误长度，不执行任意 URL 请求。
- 文献流水线只采集 `OPEN_ACCESS:Y`，保留 license/DOI/PMCID/来源；不绕付费墙。
- 新增计算参数夹取、进程组超时终止，避免恶意/异常任务长期占用资源。

## v2.0.0 更新

- 浏览器登录：PBKDF2 账户 + HMAC 会话 Cookie（HttpOnly、SameSite=Lax、12h）。
- Bearer token 仍作为脚本回退；`runtime/.token` 0600。
- v2 路由统一 `Depends(require_auth)`；health/login 例外。
- 登录、数据库、设计共享 40 次/分钟限速；失败登录写日志但不记密码。
- design/job ID 正则校验；artifact 下载做 resolve containment 与路径前缀检查；`..` 返回 404/422。
- 在线检索只访问 allowlist 中的 HTTPS 端点；外链只允许 http/https。
- APK 仅 INTERNET 权限；明文 HTTP 仅 localhost/127.0.0.1/10.0.2.2；远程需 HTTPS。
- 仍为单账户本地工具，没有 RBAC/审计/多租户隔离；不要直接暴露公网。


## 3.2.1 数据库与机构访问安全

- PostgreSQL 容器只绑定 `127.0.0.1:5432`；容器数据卷 `bioforge_pgdata`，密码在 `runtime/secrets/postgres.env`（0600）。
- `runtime/secrets/contact.env` 只保存 API 礼貌池联系邮箱，不保存密码；不得把 secret 文件复制到 Web、APK、日志或文档。
- DOI/PMID 解析不接收校园账号密码；机构访问使用 SCUT/CARSI 官方页面或管理员配置的 EZproxy 前缀。
- 资源目录明确排除 Sci-Hub、付费墙绕过、验证码规避和未授权批量下载。
- 8003 已释放给 RustDesk；BioForge 监听 8010，迁移前需确认端口占用和停服窗口。

## 3.2.2 助手与笔记安全

- Ollama 请求只发往本机 `127.0.0.1:11434`，不转发到第三方；系统提示要求不输出凭据、不提供 Sci-Hub/付费墙绕过、不编造计算结果。
- 助手限流 8 次/60 秒；问答历史保存到 `runtime/assistant/history.jsonl`（含问题与回答），按月备份，需按团队数据政策管理。
- 笔记接口只读，默认目录 `00-BioForge`；只允许 `.md`，单文件上限 2 MB，路径解析后必须仍在 vault 内，阻止 `..`、绝对路径和符号链接逃逸。
- 多组合计算会把受体/配体名称写入任务目录；不要提交含个人信息或未公开序列的文件名。
- 复合物 PDB 是计算产物，不含实验验证；下载/分享时保留方法边界说明。
