# BioForge Studio iOS 客户端

GitHub：<https://github.com/zerochans/Bioforge-Demo>  
CI：<https://github.com/zerochans/Bioforge-Demo/actions/workflows/build-ios-unsigned.yml>

这是 3.2.2 的原生 WKWebView 壳，行为与 Android APK 对齐：首次启动填写 BioForge 服务器地址并探测 `/api/health`，登录会话保存在系统 WebKit Cookie 存储；也可进入离线静态预览。iOS 端复用 Web 的 `window.AndroidBridge` 名称，实现 `saveText`、`openServerSettings`、`getServerUrl`、`toast`。

## 状态

- 已在 Linux 上生成 Xcode 工程、Swift 源码、Info.plist、资源目录和同步脚本。
- GitHub Actions macOS 构建 workflow 已成功运行第 3 次：未签名 IPA 634,728 bytes，SHA-256 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`；[run #3](https://github.com/zerochans/Bioforge-Demo/actions/runs/41572031544)。
- **已下载并校验 Release IPA（arm64，3.2.2 (8)，shell-13，无签名）；未做真机或模拟器验收。**
- Linux 无法完成 iOS 编译和签名；必须使用 macOS、Xcode 和 Apple 签名凭据。
- 不能把“工程存在”“CI 成功”或“未签名 artifact”表述为“已安装”或“已上架”。

## 目录

```text
ios/
├── BioForgeStudio.xcodeproj/       # 可直接打开的 Xcode 工程
├── BioForgeStudio/
│   ├── AppDelegate.swift           # WKWebView 壳、服务器配置、文件导出桥
│   ├── Info.plist                  # ATS、本地网络权限、版本号
│   └── Assets.xcassets/            # AppIcon 与启动背景
├── www/                            # 由 ../web 同步的离线壳资源
├── ci/build_unsigned_ipa.sh         # macOS/CI 未签名 IPA 构建脚本
├── project.yml                     # 可选：XcodeGen 再生成工程
└── ExportOptions.plist.example     # 导出模板，需填 Team ID
```

## 前置条件

- macOS 13 或更新版本
- Xcode 15 或更新版本
- 一个可用的 Apple Developer Team（模拟器不需要签名，真机/归档需要）
- 可选：`brew install xcodegen`，仅在需要从 `project.yml` 重新生成工程时使用

## 同步 Web 资源

每次修改 `../web/` 后执行：

```bash
cd /path/to/bioforge/v3.0.0
./scripts/sync_ios_web.sh
```

脚本会重建 `ios/www/`，并检查 `index.html`、`app.js`、`styles.css` 是否存在。离线预览只包含静态壳；配方设计、证据、计算、登录等需要连接服务器。

## 打开与运行

```bash
open ios/BioForgeStudio.xcodeproj
```

1. 选择 `BioForgeStudio` target。
2. 在 Signing & Capabilities 中选择自己的 Team；如 Bundle Identifier `ai.bioforge.studio` 已被占用，请改成自己的唯一 ID。
3. 选择 iPhone/iPad 模拟器或真机，Run。
4. 模拟器默认地址为 `http://127.0.0.1:8010/`；真机填写电脑的局域网地址，例如 `http://192.168.1.23:8010/`，手机与电脑需在同一 Wi-Fi。
5. 首次连接会请求本地网络权限；服务器必须监听 `0.0.0.0:8010`。

如需从 `project.yml` 重新生成工程：

```bash
cd ios
xcodegen generate
```

## 命令行构建

模拟器编译：

```bash
cd ios
xcodebuild \
  -project BioForgeStudio.xcodeproj \
  -scheme BioForgeStudio \
  -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  build
```

归档：

```bash
cd ios
xcodebuild \
  -project BioForgeStudio.xcodeproj \
  -scheme BioForgeStudio \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/BioForgeStudio.xcarchive \
  archive
```

导出 `.ipa` 前，把 `ExportOptions.plist.example` 复制为 `ExportOptions.plist`，填入 Team ID，并确认 Xcode 已配置证书与 provisioning profile：

```bash
cp ExportOptions.plist.example ExportOptions.plist
xcodebuild \
  -exportArchive \
  -archivePath build/BioForgeStudio.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/export
```

## GitHub Actions 构建未签名 IPA

仓库根目录必须是 `v3.0.0`（即包含 `ios/`、`web/`、`scripts/` 的目录）。把源码推到 GitHub 后：

1. 打开仓库的 **Actions** 页面。
2. 选择 **Build iOS unsigned IPA**。
3. 点击 **Run workflow**，等待 macOS runner 完成。
4. 直接下载 Release IPA：[BioForgeStudio-3.2.2-unsigned.ipa](https://github.com/zerochans/Bioforge-Demo/releases/download/ios-unsigned-3.2.2/BioForgeStudio-3.2.2-unsigned.ipa)；或下载 artifact `BioForgeStudio-3.2.2-unsigned-ipa`。
5. Release 附带 `.sha256`；当前文件 SHA-256 为 `d7186d551cff597d8f913883103674eb1ce2c71e302e80b19cb0091792e5964d`。

最新运行：[41572031544](https://github.com/zerochans/Bioforge-Demo/actions/runs/41572031544)，macOS job 成功；Release：[ios-unsigned-3.2.2](https://github.com/zerochans/Bioforge-Demo/releases/tag/ios-unsigned-3.2.2)。第 1 次 [41571174925](https://github.com/zerochans/Bioforge-Demo/actions/runs/41571174925) 和第 2 次 [41571598315](https://github.com/zerochans/Bioforge-Demo/actions/runs/41571598315) 也已成功。

workflow 使用 `macos-15`，执行 `xcodebuild` 的 Release device build，关闭代码签名，然后把 `.app` 打成 `Payload/*.app` 的未签名 IPA。

在 macOS 本地也可以直接运行：

```bash
cd /path/to/bioforge/v3.0.0
./ios/ci/build_unsigned_ipa.sh
```

产物写入 `dist/BioForgeStudio-3.2.2-unsigned.ipa`。

## 安装到 iPhone

未签名 IPA 不能直接双击安装，必须先由 Apple 签名：

- **免费路线**：在 Windows/macOS 用 Sideloadly 或 AltStore，登录自己的 Apple ID 自签安装。免费 Apple ID 的 provisioning 通常只有 7 天，到期需重签；设备数量和个人使用范围受 Apple 限制。
- **正式路线**：加入 Apple Developer Program，使用 Development/Ad Hoc/App Store 证书和 provisioning profile；TestFlight 或 App Store 分发需要 Apple Developer 账号和审核。
- 安装后在 App 首次启动界面填写服务器地址。手机必须能访问该地址；例如服务器在当前局域网时可填 `http://10.194.51.41:8010/`，网络变化后以实际 IP 为准。公网必须用 HTTPS，不要把 8010 明文端口直接暴露到公网。
- iOS 16+ 可能需要在“设置 → 隐私与安全性 → 开发者模式”中开启开发者模式；首次打开自签 App 还需在“VPN 与设备管理”中信任开发者证书。

仓库不包含 Apple 证书、私钥或 provisioning profile；这些必须由你在本机或 GitHub Actions Secrets 中配置。当前 workflow 只产出未签名 IPA，不冒充已签名安装包。

## 与 Android 的行为对应

- 首次启动：地址输入 + `/api/health` 探测 + 离线预览。
- 登录：`WKWebsiteDataStore.default()` 持久化 Cookie，服务重启后需重新登录。
- 外部链接：同源留在 WebView，跨域 `http/https` 交给系统浏览器；`mailto`/`tel` 交给系统。
- 文件导出：Lab 的 CSV/JSON 通过 `UIDocumentPickerViewController` 保存。
- 文件导入：Web 的 `<input type="file">` 使用系统文件选择器。
- 离线预览：加载 `www/index.html`，仅静态壳可用；Service Worker 在 `file://` 下不注册。

## ATS 与局域网

`Info.plist` 启用了 `NSAllowsArbitraryLoads` 和 `NSAllowsLocalNetworking`，因为服务器地址由用户输入，可能是任意局域网 IP 的明文 HTTP。该配置会放宽 ATS，只应在可信家庭/实验室网络使用。公网部署必须使用 HTTPS，并配置域名、强密码和访问控制；不要把 8010 明文端口直接暴露到公网。

## 已知边界

- 未做真机验收；当前没有可安装的签名 `.ipa`，只有 CI 发布的未签名 Release IPA。
- 未做 iOS 真机上的 Service Worker、Cookie、文件选择器、分享/保存面板回归。
- iOS 端未实现 Android 的返回键行为；使用系统边缘返回手势或 Web 内导航。
- 离线预览不提供服务器功能；完整离线引擎仍只在 v1.0.0 APK 中。
- Docker 镜像不含 HADDOCK3/GROMACS/CP2K/Vina/ACPYPE；iOS 壳只负责访问宿主服务器。
- 上架 App Store 前需复核 ATS 例外、隐私说明、图标版权和医学/科研免责声明。

## 验收清单（macOS）

- [ ] `xcodebuild` 模拟器编译通过
- [ ] 模拟器连接 `http://127.0.0.1:8010/`，health 探测成功
- [ ] 真机连接局域网 HTTP 服务器，出现本地网络权限提示
- [ ] 登录、刷新、退出、重新打开 App 后 Cookie 行为符合预期
- [ ] 离线预览可打开，且明确提示服务器功能不可用
- [ ] Lab CSV 导出到“文件”App
- [ ] CSV/JSON 导入文件选择器可用
- [ ] 外部链接在 Safari 打开，不离开应用内同源页面
- [ ] 320–430 px 宽度、横屏、iPad 无布局溢出
- [ ] Release Archive 与 `.ipa` 导出成功，签名校验通过
