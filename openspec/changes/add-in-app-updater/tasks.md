## 1. 版本来源统一

- [x] 1.1 新增 `src/nini/version.py`，实现当前版本读取函数，优先使用 `importlib.metadata.version("nini")`，fallback 到 `nini.__version__`
- [x] 1.2 更新 `src/nini/__init__.py`、`src/nini/app.py` 和 CLI 相关版本展示入口，统一复用 `src/nini/version.py`
- [x] 1.3 修正当前仓库版本漂移，确保 `pyproject.toml`、包元数据 fallback 与 FastAPI app version 一致
- [x] 1.4 新增或更新版本一致性测试，覆盖包版本、fallback 版本和 API 元数据版本
- [x] 1.5 运行 `pytest -q` 中与版本和路由相关的最小测试集

## 2. 更新服务模型与 Manifest 校验

- [x] 2.1 新建 `src/nini/update/__init__.py` 和 `src/nini/update/models.py`，定义 manifest、asset、检查结果、下载状态与错误模型
- [x] 2.2 新建 `src/nini/update/versioning.py`，实现 PEP 440 版本比较，覆盖 stable、pre-release、rc 和无效版本拒绝规则
- [x] 2.3 新建 `src/nini/update/manifest.py`，实现 manifest 拉取、Pydantic v2 校验、product/channel/platform/asset 校验
- [x] 2.4 增加配置项：更新源 URL、渠道、自动检查开关、检查间隔、企业禁用更新开关，默认不配置真实服务器地址
- [x] 2.5 新增测试覆盖 manifest 正常解析、产品不匹配、平台不支持、缺少 sha256、非 HTTPS URL、服务器不可用、未配置更新源 no-op 和 important 仅提示

## 3. 后端更新 API

- [x] 3.1 新建 `src/nini/update/service.py`，实现 `check_update()` 并返回当前版本、最新版本、是否可更新、更新说明和错误信息
- [x] 3.2 新建 `src/nini/update/download.py`，实现安装包下载、进度状态记录、文件大小校验、SHA256 校验和同版本下载幂等
- [x] 3.3 新建 `src/nini/update/state.py`，将下载状态保存到 `%USERPROFILE%\.nini\updates\state.json`，支持重启后恢复 ready 状态
- [x] 3.4 新建 `src/nini/api/update_routes.py`，实现 `GET /api/update/check`、`POST /api/update/download`、`GET /api/update/status`、`POST /api/update/apply`
- [x] 3.5 在 `src/nini/app.py` 注册 update router，并确保 API Key 中间件保护更新 API
- [x] 3.6 新增 API 路由测试，覆盖无更新、有更新、下载失败、校验失败、签名失败、ready 状态、重复下载幂等和 apply 前置条件失败
- [x] 3.7 运行 `pytest -q tests/test_api_routes_import.py` 和新增更新 API 测试

## 4. 半自动安装与 Updater

- [x] 4.1 新建 `src/nini/update/runtime_state.py`，复用或封装服务端运行状态判定，供 apply 判断是否存在运行中的 Agent 任务
- [x] 4.2 新建 `src/nini/update/signature.py`，在 Windows 打包环境校验安装包 Authenticode 签名和允许的发布者或证书指纹
- [x] 4.3 新建 `src/nini/update/apply.py`，实现打包环境检测、安装目录解析、updater 路径解析、GUI/CLI 进程信息收集和 apply 前置条件检查
- [x] 4.4 新建 `src/nini/updater_main.py`，实现独立 updater CLI：接收安装包路径、安装目录、app exe、后端 PID、可选 GUI PID、日志路径和等待超时
- [x] 4.5 updater 实现等待 Nini 相关进程退出、短暂缓冲、运行 `Setup.exe /S /D=<install-dir>`、记录退出码和重启 `nini.exe`
- [x] 4.6 后端 apply 成功启动 updater 后，协调 GUI 壳和后端服务退出，不直接在 API 请求线程中阻塞安装
- [x] 4.7 新增单元测试覆盖非打包环境禁止 apply、未 ready 禁止 apply、Agent 运行中禁止 apply、签名失败禁止 apply、updater 命令参数构造和进程等待逻辑
- [ ] 4.8 在 Windows 打包版手动验证 updater 日志写入 `%USERPROFILE%\.nini\logs\updater.log`

## 5. 前端更新体验

- [x] 5.1 新建 `web/src/types/update.ts`，定义更新检查结果、下载状态、错误状态和 UI 状态类型
- [x] 5.2 新建或扩展 `web/src/store/update.ts`，实现检查更新、下载、轮询状态、apply 和本地自动检查限频
- [x] 5.3 新建 `web/src/components/UpdateDialog.tsx`，展示新版本说明、下载进度、校验状态、安装前确认和失败重试
- [x] 5.4 新建 `web/src/components/UpdatePanel.tsx`，在设置或可发现位置提供手动检查入口和当前版本展示
- [x] 5.5 在应用初始化流程中接入低频自动检查，发现更新时显示非阻塞提示
- [x] 5.6 增加前端测试覆盖未配置更新源静默跳过、无更新、有更新、important 提示、下载中、ready、错误可重试、Agent 运行中禁止安装
- [x] 5.7 运行 `cd web && npm run build`

## 6. 打包与发布元数据

- [x] 6.1 更新 `nini.spec`，新增 `nini-updater.exe` 打包入口，并确保 updater 不依赖 GUI 壳
- [x] 6.2 更新 `build_windows.bat`，确保 `NINI_VERSION` 同步到安装包、release manifest 草稿和 SHA256 生成步骤
- [x] 6.3 更新 `packaging/installer.nsi`，验证覆盖安装不会触发用户数据删除流程，并保留静默安装兼容性
- [x] 6.4 新增 `scripts/generate_update_manifest.py`，根据安装包路径、版本、渠道、下载 URL 和更新说明生成 `latest.json` 草稿
- [x] 6.5 新增 `scripts/verify_update_manifest.py`，校验 manifest 中 size 与 sha256 和安装包实际值一致
- [x] 6.6 更新 `packaging/README.md`，增加发布服务器目录、manifest 上传、SHA256 校验和应用内升级烟测说明
- [ ] 6.7 执行 `python -m build` 和 Windows 打包流程，确认生成 `nini.exe`、`nini-cli.exe`、`nini-updater.exe` 和安装包

## 7. 安全、配置与企业场景

- [x] 7.1 确保下载逻辑只接受 HTTPS URL，并拒绝前端传入任意下载 URL
- [x] 7.2 增加更新源域名或基础 URL 限制，防止 manifest 将下载重定向到非预期来源
- [x] 7.3 在配置中支持禁用更新入口，满足企业离线部署或内网版本冻结需求
- [x] 7.4 在配置中支持 Authenticode 允许列表，正式发布使用证书指纹，测试构建允许显式关闭签名校验
- [x] 7.5 在发布文档中明确正式发布必须对 `nini.exe`、`nini-updater.exe` 和安装包进行 Authenticode 签名
- [x] 7.6 为后续 manifest 签名预留字段和验证扩展点，但不阻塞 MVP 发布

## 8. 验证与回归

- [ ] 8.1 运行 `black --check src tests`
- [ ] 8.2 运行 `mypy src/nini`
- [ ] 8.3 运行 `pytest -q`
- [x] 8.4 运行 `cd web && npm run build`
- [ ] 8.5 执行打包烟测：安装旧版、检查新版、下载校验、确认升级、静默覆盖安装、自动重启新版
- [ ] 8.6 验证升级后 `%USERPROFILE%\.nini` 中配置、数据库、会话、上传文件和日志仍存在
- [x] 8.7 准备 PR 描述，包含变更内容、验证方式、风险点、回滚方式和更新服务器发布步骤
