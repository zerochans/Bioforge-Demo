# 登录、会话与 Token

## 默认账户

首次启动 v2 时创建：

- 用户名：`admin`
- 密码：`bioforge-demo`
- 凭据文件：`runtime/login.txt`（权限 0600）

生产使用前必须修改密码，或通过环境变量在首次启动前覆盖：

```bash
BIOFORGE_ADMIN_USER=alice \
BIOFORGE_ADMIN_PASSWORD='<strong-password>' \
./scripts/run_server.sh
```

环境变量只在 `runtime/auth.json` **不存在**时用于创建账户；已有账户不会被环境变量覆盖。

## 浏览器登录

```http
POST /api/auth/login
Content-Type: application/json

{"username":"admin","password":"bioforge-demo"}
```

成功返回 `200`，并设置：

```
Set-Cookie: bioforge_session=<signed>; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200
```

- 会话有效期 12 小时。
- Cookie 由 HMAC-SHA256 签名，载荷包含用户名、过期时间和随机 nonce；服务端校验签名和过期时间。
- 登录限速：每个来源 IP 每分钟最多 40 次（与数据库/设计请求共享限速器）。
- 登出：`POST /api/auth/logout` 删除 Cookie。

## API Token

`runtime/.token` 是可选回退，用于脚本、MCP 或 AutoDL：

```bash
TOKEN=$(cat runtime/.token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8002/api/v2/cases
```

也可以使用 `X-API-Key: <token>`。

Token 的用途：

- 只证明“调用者被允许访问本地 BioForge API”。
- 不是数据库 API key，不会发送给 PubChem/UniProt 等第三方。
- 不包含账户密码；泄露后应删除 `runtime/.token` 并重启服务，或设置 `BIOFORGE_TOKEN`。
- 文件权限 0600；不要提交到 Git、截图或公开日志。

## 修改密码

```http
POST /api/auth/password
Content-Type: application/json

{"current_password":"bioforge-demo","new_password":"<at least 8 chars>"}
```

成功后 `runtime/login.txt` 不再保存明文密码，只记录修改时间。

## 环境变量

| 变量 | 作用 |
|---|---|
| `BIOFORGE_ADMIN_USER` | 首次创建账户的用户名 |
| `BIOFORGE_ADMIN_PASSWORD` | 首次创建账户的密码 |
| `BIOFORGE_TOKEN` | 覆盖 API token |
| `BIOFORGE_REQUIRE_AUTH=0` | 关闭鉴权（仅限可信本机，UI 会警告） |
| `BIOFORGE_HOST` / `BIOFORGE_PORT` | 监听地址/端口（默认 127.0.0.1:8002） |

## 部署建议

- 默认只监听 `127.0.0.1`，不要直接暴露到公网。
- 远程访问使用反向代理 + HTTPS；Cookie 的 `Secure` 标志应在 HTTPS 终止层配置。
- 失败登录会写入 `logs/bioforge.log`，但不会记录密码。
- 定期轮换密码、token 和 `.session_secret`。
