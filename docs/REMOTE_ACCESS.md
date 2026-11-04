# 手机访问不同 WiFi 的服务器 · 两种方案

> 目标：服务器和手机不在同一 WiFi 时，仍能从 Android/iOS App 访问 BioForge Studio。
> 不要把 8010 端口直接端口转发到公网；至少先改掉默认密码并启用 TLS/身份访问。

## 方案 A：Tailscale Serve（推荐给个人/小团队，私网）

适合：手机和服务器都登录同一个 Tailscale tailnet；不需要公开网址。

1. 服务器和手机安装 Tailscale，登录同一账号/tailnet。
2. 在服务器运行：

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
BIOFORGE_PORT=8010 scripts/tailscale_serve.sh
```

等价手工命令（视 Tailscale 版本）：

```bash
tailscale serve --bg http://127.0.0.1:8010
tailscale serve status
```

3. 手机 Tailscale 保持连接，浏览器打开输出的 `https://<machine>.<tailnet>.ts.net/`，或把该地址填入 App 的“服务器地址”。
4. 用 BioForge 账号登录；会话保存在 WebKit Cookie。

优点：不暴露公网、无端口转发、自动 HTTPS；缺点：每个访问者都必须加入 tailnet。

不要使用 `tailscale funnel`，除非你明确要让整个公网访问；Funnel 是另一个暴露面。

## 方案 B：Cloudflare Tunnel + Access（公开 HTTPS + 身份策略）

适合：外部合作者、不同组织、需要稳定域名和登录策略。

1. 域名接入 Cloudflare，安装 `cloudflared`。
2. 创建命名隧道并绑定 DNS：

```bash
cloudflared tunnel login
cloudflared tunnel create bioforge
cloudflared tunnel route dns bioforge bioforge.example.com
```

3. 配置入口（示例 `~/.cloudflared/config.yml`）：

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /home/<user>/.cloudflared/<TUNNEL_UUID>.json
ingress:
  - hostname: bioforge.example.com
    service: http://127.0.0.1:8010
  - service: http_status:404
```

4. 运行并设为服务：

```bash
cloudflared tunnel run bioforge
sudo cloudflared service install
```

5. 在 Cloudflare Zero Trust → Access 创建应用：
   - hostname：`bioforge.example.com`
   - policy：只允许指定邮箱/域名/一次性 PIN；
   - 不要只依赖 BioForge 的演示密码。

6. App 服务器地址填 `https://bioforge.example.com`。

快速测试可临时用 `scripts/public_tunnel.sh`，但它生成的是公开 Quick Tunnel、URL 会变化，不适合长期使用；正式环境用命名隧道 + Access。

## 两种方案对比

| 项目 | Tailscale Serve | Cloudflare Tunnel + Access |
|---|---|---|
| 是否公网 | 否，tailnet 内 | 是，受 Access 策略保护 |
| 谁可访问 | 加入 tailnet 的设备 | 通过身份策略的用户 |
| HTTPS | Tailscale 自动 | Cloudflare 边缘证书 |
| 手机配置 | 装 Tailscale + 输 ts.net 地址 | 直接输 HTTPS 域名 |
| 适用 | 个人、小团队、最高隐私 | 合作者、跨组织、稳定入口 |
| 主要风险 | tailnet 成员权限过大 | 配置错误的 Access 策略/公开绕过 |

## 移动端与安全清单

- 先在服务器设置中修改默认 `admin / bioforge-demo` 密码；不要继续使用演示密码。
- Android 允许明文是兼容旧内网地址，不等于建议用 HTTP 公网；优先 HTTPS。
- iOS ATS 友好：使用有效 HTTPS 域名；自签证书需要额外配置，不推荐。
- App 的“服务器地址”只保存 URL，不保存密码；登录 Cookie 由系统 WebKit 保存。
- 如果手机离线，App 仍可打开内置静态预览，但 RAG/文献/图谱查询必须连服务器。
- 远程访问只解决网络路径；RAG 的审核队列、回滚和证据链接仍在服务器端。
- 不要把 Cloudflare Tunnel token、Tailscale auth key、API token 或 `runtime/login.txt` 提交到 Git。
- 建议在反向代理层限制请求体、启用访问日志；BioForge 自身已有登录、限流和 CORS 安全头。

## 验收步骤

```bash
curl -fsS https://<your-host>/api/health
curl -fsS https://<your-host>/api/v3/rag/status
```

然后在手机 App 中：

1. 设置服务器地址；
2. 登录；
3. 打开“使用指南 → 问 BioForge”；
4. 提一个本地可命中的问题，确认出现证据、质量分级和审核按钮；
5. 提一个无命中问题，确认出现“证据不足/偏弱”警告，而不是编造答案；
6. 点“回滚并重查”，确认旧记录保留、新记录进入待审核队列。
