# 远程访问与生产部署（v3.2）

目标：让客户不在同一 Wi-Fi 时也能使用，同时不把默认密码和明文 HTTP 暴露到公网。三选一，优先推荐 Cloudflare Tunnel 或 Tailscale；有域名和 VPS 时用 Docker + Caddy。

## 0. 部署前必须做

1. 启动服务，登录后到“设置”修改默认密码；不要继续使用 `bioforge-demo`。若复用已有 `runtime/auth.json`，`BIOFORGE_ADMIN_PASSWORD` 不会覆盖已保存密码；请在设置中修改，或仅在全新部署时初始化 runtime。
2. 确认 `runtime/auth.json`、`runtime/.token`、`runtime/login.txt` 权限为 `0600`。
3. 备份 `runtime/`、`logs/`、`data/` 与文献目录。不要把密钥、Token 或客户数据提交到 Git。
4. 公网只开放 HTTPS 入口；不要直接端口转发 `8010` 明文端口。
5. 计算节点包含本地 Vina/GROMACS/CP2K 路径；容器镜像不含这些二进制，生产计算应放回受控主机或单独计算节点。

## 1. Cloudflare Tunnel（推荐，最快）

适用：服务器在实验室/办公室 NAT 后，没有公网 IP，想给客户一个稳定域名。

### 临时 Quick Tunnel（演示，不用于正式客户）

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
# 先在设置里改密码，然后：
BIOFORGE_TUNNEL_CONFIRM=1 ./scripts/public_tunnel.sh
```

脚本用 Docker 启动 `cloudflare/cloudflared`，输出一个 `https://*.trycloudflare.com` 地址。该地址公开、会变化、不能用于长期客户交付。

### 固定域名 Named Tunnel（正式）

1. 在 Cloudflare Zero Trust 创建 Tunnel，添加 Public Hostname，例如 `studio.example.com`，Service 指向 `http://host.docker.internal:8010`（Linux 需 `--add-host=host.docker.internal:host-gateway`）。
2. 把 Tunnel Token 放入环境变量，启动：

```bash
export CLOUDFLARE_TUNNEL_TOKEN='...'
./scripts/public_tunnel.sh
```

或直接用 Docker 常驻：

```bash
docker run -d --restart unless-stopped --name bioforge-tunnel \
  --add-host=host.docker.internal:host-gateway \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run \
  --token "$CLOUDFLARE_TUNNEL_TOKEN"
```

3. 手机 APK 的服务器地址改为 `https://studio.example.com`，不要填 `http://IP:8010`。

优点：无需公网 IP、自动 TLS、可加 Access 策略。注意：Quick Tunnel 的 URL 是公开的，必须先改密码。

## 2. Tailscale（私有网络，适合内部客户）

适用：客户/同事都是受控用户，不需要公开互联网。

1. 服务器与客户设备安装 Tailscale 并加入同一 tailnet。
2. 服务器继续监听 `0.0.0.0:8010`，用 Tailscale IP 或 MagicDNS 访问。
3. 需要 HTTPS 时：

```bash
sudo tailscale serve --bg 8010
tailscale serve status
```

然后使用 `https://<machine>.<tailnet>.ts.net`。Tailscale 的 WireGuard 已加密，但 `tailscale serve` 可提供浏览器可信 HTTPS。

优点：不暴露公网、访问控制清晰。缺点：每个客户设备都要安装并授权 Tailscale。

## 3. VPS + Docker + Caddy（自有域名）

> 本机已用 `docker compose config` 校验 Compose 结构，并用清华 PyPI/Debian 镜像重建 `v300-app`（约 766 MB）；隔离容器 `8011` 的 `/api/health` 返回 `3.2.2`。若在目标网络仍出现 `Network is unreachable` 或 `No matching distribution found`，检查 Docker DNS/代理后重试。

适用：有云服务器和域名，想完全掌控入口。

1. 域名 A/AAAA 记录指向 VPS；防火墙开放 80/443，关闭 8010 公网入站。
2. 安装 Docker/Compose，复制项目到服务器：

```bash
cp deploy/.env.example .env
# 编辑 .env：域名、强密码、文献目录、POSTGRES_PASSWORD/DATABASE_URL
docker compose up -d --build
docker compose logs -f db app caddy
# 首次启动后把宿主机语料同步到 PostgreSQL（compose 内部执行）
docker compose exec app python scripts/sync_postgres.py
```

3. 访问 `https://你的域名`。Caddy 自动申请/续期证书，并反向代理到内部 `app:8010`。
4. `db` 服务使用 `pgvector/pgvector:pg16`，数据卷 `bioforge_pgdata`，只供 compose 内部访问；不要映射到公网。
5. 文献库默认挂载为只读：

```env
BIOFORGE_LITERATURE_HOST_DIR=/srv/bioforge/literature
```

容器内路径为 `/data/literature/bioforge_literature.db`。

6. 更新：

```bash
git pull   # 或在服务器解压新版本
docker compose up -d --build
```

### 容器边界

`Dockerfile` 安装 Python Web/Lab/文献依赖；不包含 GROMACS、CP2K、Vina、Open Babel、HADDOCK。需要机制计算时：

- 在宿主机运行 `scripts/run_server.sh`，容器只作为 Web 入口；或
- 构建包含计算工具的专用镜像，并把工具路径写入 `/api/v3/tools`。

## 4. 安全与运维检查表

- [ ] 已修改默认密码，`runtime/login.txt` 不再是明文默认密码。
- [ ] 公网只开放 443（Cloudflare 可在 80 上做跳转）。
- [ ] 已启用 HTTPS；APK 服务器地址为 `https://`。
- [ ] 已备份 `runtime/`、`data/`、文献库；备份文件加密。
- [ ] 已限制服务器 SSH、Docker API、8010 和 PostgreSQL 5432 端口来源。
- [ ] `runtime/secrets/postgres.env`、`contact.env` 权限为 0600，未进入 Git/镜像/APK。
- [ ] 日志保留并定期检查登录失败、计算失败和异常下载。
- [ ] 文献仅用于 OA 元数据/全文；遵守许可，不绕过付费墙。
- [ ] 不存放患者数据、临床数据或未授权的商业配方。

## 5. 健康检查

```bash
curl -fsS https://你的域名/api/health
```

应返回 `status=ok`、`version=3.2.2`、`mode=food+biologic+lab`。若返回 502，检查 `docker compose logs app`；若证书失败，检查域名解析和 80/443。

## 3.3.0 远程访问与 RAG

- 跨 WiFi 两种方案：`docs/REMOTE_ACCESS.md`（Tailscale Serve / Cloudflare Tunnel + Access）。
- 推荐个人/小团队用 Tailscale Serve；外部合作者用命名 Cloudflare Tunnel + Access，不要直接转发 8010。
- RAG 依赖已加入 `requirements.txt`；服务启动后检查：

```bash
curl -fsS http://127.0.0.1:8010/api/v3/rag/status
```

- RAG 记录默认写 `runtime/rag/rag.sqlite3`，不要把 `runtime/` 打进镜像或提交到 Git。
- 3.3.0 镜像 `v300-app:latest` 为 `9d4514b067d7`（855 MB）；容器默认没有 `/media/h3c/.../bioforge_literature.db`，需要把宿主机文献库以只读卷挂载，并设置 `BIOFORGE_LITERATURE_DB` 指向容器内路径。
- Ollama 必须可从服务进程访问；不可用时 RAG 退回确定性证据模板，不会伪造模型输出。
- 外部 API 只使用 Europe PMC/OpenAlex 等合法 OA 公共入口；网络受限时会在 warnings 中报告。
