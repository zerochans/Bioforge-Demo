# 升级到 BioForge Studio 3.0

日期：2026-10-20

## 概要

v3.0.0 在 v2.1.0 之上新增 **Model Lab**，并保持食品配方、在线证据、机制计算、登录、v2 API 和 v1 生物引擎兼容。

| 项目 | v2.1.0 | v3.0.0 |
|---|---|---|
| 服务入口 | `backend/app_v2.py` | `backend/app_v3.py` |
| 默认端口 | 8002 | 8010 |
| Lab 数据库 | 无 | `runtime/lab.db` |
| 模型 artifact | 无 | `runtime/models/lab/` |
| Web 资产 | app.js | app.js + lab.js |
| API | `/api/v2/*` | `/api/v2/*` + `/api/v3/lab/*` |
| APK | versionCode 3 / 2.1.0 | versionCode 4 / 3.0.0 |
| 测试 | 25 | 29 |

## 1. 依赖

新增：

```text
pandas>=2.0
joblib>=1.3
```

scikit-learn、numpy 已在 v1/v2 依赖中。安装：

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pip install -r requirements.txt
```

检查：

```bash
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python - <<'PY'
import pandas, joblib, sklearn
print(pandas.__version__, joblib.__version__, sklearn.__version__)
PY
```

## 2. 启动

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

服务：<http://127.0.0.1:8010/>

v2.1 仍在 8002 运行，互不影响。若 8010 被占用：

```bash
ss -ltnp | grep 8010
```

## 3. 数据迁移

### 设计/证据/计算

v2.1 的 `runtime/designs/`、`runtime/evidence/`、`runtime/compute/`、`runtime/cache/` 可直接复制到 v3 对应目录。v3 没有改动这些文件格式。

### 登录

`runtime/auth.json`、`runtime/.session_secret`、`runtime/.token` 可复制以保留账号和 token。若不复制，v3 首次启动会使用默认账号：

- 用户名：`admin`
- 密码：`bioforge-demo`
- 首次登录后写入 `runtime/login.txt`

生产环境请立即修改默认密码。

### Model Lab

Lab 是 v3 新功能，没有 v2 数据需要迁移。默认从空数据库开始：

- `runtime/lab.db`
- `runtime/models/lab/`

可以点击“载入内置演示数据”导入 180 行合成数据，或导入自己的 CSV/JSON。

### 不建议

- 不要直接把 v2.1 的整个 `runtime/` 覆盖到已运行的 v3（会覆盖 v3 的 `lab.db`，虽然不会损坏设计文件）。
- 不要在 v2 服务仍使用同一目录时清理 `runtime/`。

## 4. API 变化

新增 `/api/v3/lab/*`：

- 数据集：导入、演示、详情、CSV、删除
- 训练：模型、模型卡、重训
- 优化：EI 候选、run、CSV
- 预测与实验回灌

`/api/health` 现在返回：

```json
{
  "status": "ok",
  "version": "3.0.0",
  "food_engine": "2.1.0-food",
  "lab_version": "3.0.0",
  "mode": "food+biologic+lab",
  "time": "..."
}
```

原有 v2 路径和响应保持不变；食品设计响应中的 `package_version` 仍是 `2.1.0`，因为食品引擎版本独立于应用版本。

完整端点见 `docs/API_V3.md`。

## 5. Web/PWA

- 新增 `web/lab.js`，`web/index.html` 新增“模型实验室”导航和页面。
- Service Worker 缓存名升级为 `bioforge-v30-shell-3`，预缓存 `lab.js` 和图标。
- 已安装旧 PWA 需要刷新/重新打开以激活新 Service Worker；如仍看到旧界面，清除站点数据。
- 移动端底部导航新增“实验室”标签。

## 6. Android

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
ANDROID_SDK_ROOT="$PWD/android/sdk" bash android/build_apk.sh
adb install -r dist/BioForgeStudio-3.0.0.apk
```

- APK 默认端口改为 8010：
  - 模拟器：`http://10.0.2.2:8010/`
  - 真机：`adb reverse tcp:8010 tcp:8010`，然后 `http://127.0.0.1:8010/`
- versionCode 4 / versionName 3.0.0，可覆盖 v2.1 APK。
- 新增 WebView 文件选择器（Lab 导入 CSV/JSON）。
- Lab 的 CSV 下载通过 `AndroidBridge.saveText` 打开系统保存对话框。
- 仍是服务器客户端；断网只显示内置壳，不能训练或设计。

## 7. 验证清单

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python -m pytest tests -q
```

预期 `29 passed`。

手工：

1. 登录后打开“模型实验室”，确认统计卡显示演示数据 180 行。
2. 载入演示数据 → 训练 `stability_days`（勾选合成数据确认）→ 有 R²/MAE/散点/重要性。
3. 生成优化候选 → 导出 CSV。
4. 记录一条实测并重训 → 数据集行数 +1，模型列表出现新版本。
5. 删除自定义数据集 → 二次确认 → 数据集和模型消失。
6. 390 px 移动端：无横向滚动，底部“实验室”标签可用。

## 8. 回滚

v2.1 目录 `../v2.1.0/` 未修改，8002 服务可继续使用。回滚时：

```bash
cd /home/h3c/md-agent/bioforge/v2.1.0
PYTHON=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python ./scripts/run_server.sh
```

APK 可安装 `../v2.1.0/dist/BioForgeStudio-2.1.0.apk`（versionCode 3）。Android 不允许直接降级安装，需先卸载 v3 或使用 `adb install -r -d`（仅调试）。

Lab 数据只存在于 v3；回滚不会删除 `v3.0.0/runtime/lab.db`，可保留以后恢复。
