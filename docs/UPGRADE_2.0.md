# 从 v1.0.0 升级到 v2.0.0

## 1. 目录与端口

v1.0.0 保持不变：

```
/home/h3c/md-agent/bioforge/              # v1 根目录，端口 8000
/home/h3c/md-agent/bioforge/v2.0.0/       # v2，端口 8001
```

v2 不会覆盖 v1 的 `backend/`、`web/`、`dist/BioForgeStudio-1.0.0.apk` 或 `runtime/`。两个版本可以同时运行。

## 2. 启动 v2

```bash
cd /home/h3c/md-agent/bioforge/v2.0.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

打开 <http://127.0.0.1:8001/>。

首次启动生成：

- `runtime/auth.json`：PBKDF2 账户
- `runtime/login.txt`：演示用户名/密码（0600）
- `runtime/.session_secret`：会话 HMAC 密钥
- `runtime/.token`：API Bearer token（0600）

## 3. 登录方式的变化

| 项目 | v1 | v2 |
|---|---|---|
| 浏览器 | 在设置里粘贴 token | 用户名/密码登录，HttpOnly Cookie |
| 脚本 | Bearer token | Bearer token 仍可用 |
| 默认端口 | 8000 | 8001 |
| 默认凭据 | token | `admin` / `bioforge-demo` |

**必须修改默认密码**：

```bash
curl -s -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' \
  http://127.0.0.1:8001/api/auth/login

curl -s -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"current_password":"bioforge-demo","new_password":"<new-strong-password>"}' \
  http://127.0.0.1:8001/api/auth/password
```

## 4. 新 API

v2 接口在 `/api/v2/*`，v1 的 `/api/*` 生物设计接口仍保留在 `app_v2.py` 中。推荐新代码使用：

- `POST /api/v2/design`
- `POST /api/v2/db/search`
- `POST /api/v2/graph`
- `POST /api/v2/compute/mechanism`
- `GET /api/v2/compute/jobs/{id}`

详见 `API_V2.md`。

## 5. APK 升级

```bash
adb install -r dist/BioForgeStudio-2.0.0.apk
```

- versionCode 2 / versionName 2.0.0；与 v1 APK 使用同一签名，可直接覆盖安装。
- 默认连接模拟器宿主 `10.0.2.2:8001`；真机使用：

```bash
adb reverse tcp:8001 tcp:8001
```

- 然后 App 使用 `http://127.0.0.1:8001/`。服务器未启动时 App 会提示连接失败。
- 明文 HTTP 仅允许 localhost/127.0.0.1/10.0.2.2；远程服务请配置 HTTPS。

## 6. 数据与运行目录

v2 的 `runtime/` 独立于 v1：

```
runtime/
  auth.json
  login.txt
  .session_secret
  .token
  designs/<design_id>.json
  compute/<job_id>/
  cache/
```

v1 的 `runtime/jobs/` 不会被修改。若要从 v1 迁移已经生成的设计，复制相应 JSON 并保持 schema 兼容；v2 不自动迁移旧 job。

## 7. 回滚

停止 v2 服务，继续使用 v1：

```bash
cd /home/h3c/md-agent/bioforge
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

v1 文件和 APK 均未被覆盖。
