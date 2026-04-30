## 变更内容

- 统一 Nini 当前版本来源，CLI、FastAPI 元数据和更新检查共用 `nini.version.get_current_version()`。
- 新增应用内更新后端模块，支持 manifest 拉取校验、PEP 440 版本比较、HTTPS 与同域限制、安装包下载、大小与 SHA256 校验、下载状态持久化。
- 新增 `/api/update/check`、`/api/update/download`、`/api/update/status`、`/api/update/apply`，apply 在源码环境、更新包未就绪、Agent 任务运行中或签名不可信时拒绝执行。
- 新增独立 `nini-updater.exe` 入口，负责等待旧进程退出、运行 NSIS 静默安装器、写入 updater 日志并重启 Nini。
- 新增前端更新状态 store、启动低频自动检查、设置页手动检查入口和全局更新对话框。
- 更新 Windows 打包流程，打包 `nini-updater.exe`，签名全部 EXE，生成安装包 SHA256，并在配置发布 URL 时生成与校验 `latest.json`。
- 更新发布文档，说明更新服务器目录、manifest 上传、代码签名、企业禁用配置和应用内升级烟测。

## 验证方式

- `pytest -q tests/test_version.py tests/test_update_manifest.py tests/test_update_manifest_scripts.py tests/test_update_service.py tests/test_update_routes.py tests/test_update_apply.py tests/test_updater_main.py tests/test_api_routes_import.py tests/test_phase7_cli.py::test_cli_version_outputs_current_version`
- `cd web && npm run test -- UpdatePanel UpdateDialog update.test`
- `black --check` 本次新增与修改的 Python 文件
- `mypy src/nini/update src/nini/api/update_routes.py src/nini/updater_main.py src/nini/version.py`
- `cd web && npm run build`
- `python -m build`
- `openspec validate add-in-app-updater --strict`
- 使用临时安装包文件执行 `scripts/generate_update_manifest.py` 与 `scripts/verify_update_manifest.py`

## 未通过或未执行项

- `black --check src tests`：失败，仓库既有多处文件不符合 Black，本 PR 未做全仓格式化以避免无关改动。
- `mypy src/nini`：失败，错误集中在既有 `windows_launcher.py`、sandbox、provider 和 `export_report.py`。
- `pytest -q`：失败 7 项，集中在既有技能快照、PDF 导出、hybrid skills、sandbox 错误文案和 `windows_launcher` 路径断言。
- Windows 完整打包流程和应用内升级烟测未在本轮执行，需要在具备 NSIS、签名证书和测试更新服务器的 Windows 发布环境验证。

## 风险点

- 应用内安装依赖 `nini-updater.exe`、NSIS 静默安装和 Windows 文件锁释放，真实可靠性必须通过打包版烟测确认。
- Manifest 第一版未做独立签名，只预留 `signature` 与 `signature_url` 字段；当前安全边界依赖 HTTPS、SHA256 与 Authenticode 签名。
- 企业环境若禁止外网访问，应设置 `NINI_UPDATE_DISABLED=true` 或不配置 `NINI_UPDATE_BASE_URL`。

## 回滚方式

- 服务器端可删除或回退 `latest.json`，客户端未配置可用更新时不会提示升级。
- 已下载但未 apply 的更新包不会影响当前版本运行，可删除 `%USERPROFILE%\.nini\updates`。
- 已升级后如新版本异常，可重新运行上一版本 `Nini-<version>-Setup.exe` 覆盖安装；用户数据目录 `%USERPROFILE%\.nini` 不会在覆盖安装中删除。

## 发布服务器步骤

1. 设置 `NINI_VERSION`、`NINI_UPDATE_ASSET_BASE_URL`、`NINI_UPDATE_CHANNEL`、`NINI_UPDATE_NOTES` 和 `SIGNING_CERT_THUMBPRINT`。
2. 执行 `build_windows.bat`，确认生成 `dist\nini\nini.exe`、`dist\nini\nini-cli.exe`、`dist\nini\nini-updater.exe`、安装包、`.sha256` 和 `latest.json`。
3. 校验 `latest.json` 的 `channel`、`version`、asset URL、`size` 和 `sha256`。
4. 上传安装包、`.sha256` 和 `latest.json` 到对应渠道目录。
5. 用旧版打包安装版执行应用内升级烟测，确认 updater 日志和用户数据保留。
