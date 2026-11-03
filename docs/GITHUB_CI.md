# GitHub 仓库与 iOS CI

## 仓库

- URL：<https://github.com/zerochans/Bioforge-Demo>
- 默认分支：`main`
- 仓库根目录对应本地 `v3.0.0`，即包含 `web/`、`backend/`、`ios/`、`docs/` 的目录。
- 不提交 `runtime/`、`logs/`、`run1/`、`android/build/`、`android/keystore/`、`ios/build/`、数据库、token、session secret 和任何 Apple 私钥。

## 已纳入仓库的内容

| 内容 | 路径 |
|---|---|
| Web/PWA | `web/` |
| FastAPI 后端 | `backend/` |
| 数据与案例 | `data/` |
| Python 脚本 | `scripts/` |
| 测试 | `tests/` |
| Android 源码 | `android/app/`、`android/build_apk.sh` |
| Android 最终 APK | `dist/BioForgeStudio-3.2.2.apk`（强制加入） |
| iOS Xcode 工程 | `ios/BioForgeStudio.xcodeproj` |
| iOS 源码/资源 | `ios/BioForgeStudio/`、`ios/www/` |
| iOS CI 脚本 | `ios/ci/build_unsigned_ipa.sh` |
| GitHub Actions | `.github/workflows/build-ios-unsigned.yml` |
| 文档 | `README.md`、`docs/`、`CHANGELOG.md`、`RELEASES.md` |
| 容器部署 | `Dockerfile`、`docker-compose.yml`、`deploy/` |

## 未签名 IPA 构建

workflow 在 GitHub 的 macOS runner 上执行：

```bash
xcodebuild \
  -project ios/BioForgeStudio.xcodeproj \
  -scheme BioForgeStudio \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -derivedDataPath ios/build/DerivedData \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build
```

随后把 `BioForgeStudio.app` 放入 `Payload/` 并打包为：

```text
dist/BioForgeStudio-3.2.2-unsigned.ipa
dist/BioForgeStudio-3.2.2-unsigned.ipa.sha256
```

触发方式：

1. 打开 <https://github.com/zerochans/Bioforge-Demo/actions/workflows/build-ios-unsigned.yml>。
2. 点击 **Run workflow**。
3. 等待 macOS job 完成。
4. 下载 artifact `BioForgeStudio-3.2.2-unsigned-ipa`。

push 到 `main` 且改动涉及 `ios/**`、`web/**`、`scripts/sync_ios_web.sh` 或 workflow 本身时，也会自动触发。

## 安装到 iPhone

未签名 IPA 不能直接安装。可选：

- **免费自签**：Windows/macOS 上使用 Sideloadly 或 AltStore，登录自己的 Apple ID，把未签名 IPA 重签后安装。免费 provisioning 通常 7 天到期，需要重新签名；设备数量和个人使用范围受 Apple 限制。
- **正式签名**：使用 Apple Developer Program 的 Development/Ad Hoc/App Store 证书和 provisioning profile，通过 Xcode Archive 或签名版 CI 导出 `.ipa`。TestFlight/App Store 还需要 Apple 审核。
- **临时网页入口**：在 iPhone Safari 打开服务器地址并“添加到主屏幕”，可得到 PWA 入口，但这不是原生 IPA，也不能替代 App Store 安装。

安装后在 App 首次启动页面填写服务器地址。手机必须能访问该地址；例如当前局域网服务器可用 `http://10.194.51.41:8010/`，网络变化后以实际 IP 为准。公网必须使用 HTTPS，不要把 `8010` 明文端口直接暴露到公网。

## 签名版 CI 的扩展条件

如果要把签名步骤也放进 GitHub Actions，需要配置：

- Apple Developer Team ID
- 导出的 `.p12` 证书及密码
- 对应 Bundle ID 的 provisioning profile
- `ExportOptions.plist` 的导出方式（development / ad-hoc / app-store）

这些内容必须放在 GitHub Actions Secrets，不要提交到仓库，也不要在 issue、README 或聊天中发送私钥。当前仓库只包含未签名构建，没有 Apple 证书、私钥或 provisioning profile。

## 验证记录

- workflow YAML：`actionlint 1.7.12` 通过。
- 构建脚本：`bash -n` 通过。
- Linux 主机无法运行 `xcodebuild`；实际 macOS 编译必须在 GitHub Actions 或 macOS 本机执行。
- 当前仓库中的 APK：357,999 bytes，SHA-256 `d11806eb0bb74f0e9517eb9597add7d75fd4a33435e95f4b6f15ffcd2e3dcb7f`，v2/v3 签名通过。
- iOS 当前状态：工程、资源和 CI 已准备；尚未产出签名 `.ipa`，未做模拟器/真机验收。
