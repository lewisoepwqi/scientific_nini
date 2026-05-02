## Context

Nini 当前通过 Windows PyInstaller 产物和 NSIS 安装包交付，用户运行时数据默认位于 `%USERPROFILE%\.nini`，程序安装目录默认位于 `%LOCALAPPDATA%\Nini`。现有打包流程已经支持 `build_windows.bat`、`nini.spec`、`packaging/installer.nsi`，NSIS 安装器支持 `/S /D=<path>` 静默安装参数。

当前升级体验依赖用户手动下载新版安装包并覆盖安装。该流程不利于安全修复、稳定性修复和用户留存。应用内升级需要跨越前端 UI、FastAPI 本地 API、下载校验、Windows 进程退出、安装目录覆盖、用户数据保留和发布服务器元数据等多个边界。

本设计以 Windows 打包版为第一目标，源码开发环境仅支持检查更新与展示状态，不执行安装升级。实现必须保持最小改动，不改变 Agent 运行链路，不把升级逻辑接入 WebSocket 事件流。

## Goals / Non-Goals

**Goals:**

- 提供软件内版本检查能力，支持自动低频检查与手动检查。
- 提供半自动升级流程：用户确认后下载、校验、退出、静默安装、重启。
- 保证升级过程不删除配置解析后的用户数据目录，默认 `%USERPROFILE%\.nini`。
- 使用服务器 manifest 作为发布元数据来源，支持 stable/beta 渠道。
- 统一当前版本读取来源，消除 `pyproject.toml`、`nini.__version__`、FastAPI version 漂移。
- 在失败场景下保留当前可运行版本，并提供可诊断日志。

**Non-Goals:**

- 不实现二进制差分更新。
- 不实现跨平台升级；macOS/Linux 后续单独设计。
- 不实现完全无感后台升级；安装动作必须由用户确认触发。
- 不实现自动回滚；失败时保留现有安装，回滚通过重新安装旧版本完成。
- 不把下载进度通过 WebSocket 推送；第一版使用 HTTP status 轮询。

## Decisions

### 1. 采用完整 NSIS 安装包升级，而不是差分更新

选择下载完整 `Nini-<version>-Setup.exe`，校验后通过 NSIS 静默覆盖安装。Nini 的 PyInstaller 产物包含 Python 运行时、科学计算依赖、前端静态文件和可选运行时，差分更新会显著增加文件清单、patch 生成、回滚和校验复杂度。

备选方案是二进制差分或文件级更新。该方案下载体积较小，但更容易受到文件锁、杀毒拦截和半更新状态影响，不适合作为第一版。

### 2. 使用独立 `nini-updater.exe` 执行安装，并处理 GUI/CLI 双进程

主程序无法可靠覆盖自身正在占用的文件，因此由后端在用户确认后启动独立 updater。Windows 打包版存在 `nini.exe` GUI 壳和 `nini-cli.exe` 后端服务两个进程，apply API 通常运行在后端服务内，不能只等待单个父进程退出。

updater 接收安装包路径、安装目录、主程序路径、当前后端 PID、可选 GUI PID 或安装目录进程匹配信息。apply 成功后，后端应通过本地升级状态通知前端展示“即将重启”，并触发 GUI 壳和后端服务共同退出。updater 必须等待相关 Nini 进程退出或确认不再占用安装目录后再运行安装器，安装成功后重启 `nini.exe`。

updater 职责保持单一：等待、安装、记录日志、重启。不读取业务配置、不访问数据库、不调用 Agent 逻辑。

### 3. 通过 HTTP API 暴露更新状态

新增 `/api/update/check`、`/api/update/download`、`/api/update/status`、`/api/update/apply`。前端通过 Zustand 状态管理轮询 status，不引入 WebSocket 更新事件，避免影响现有 Agent 实时协议。

下载任务在后端本地运行，状态存储在进程内和用户数据目录中的轻量状态文件。Nini 重启后可以根据下载目录和状态文件恢复“已下载待安装”状态。第一版只允许一个 active update；重复下载请求返回当前任务状态，manifest 切换到更新版本时旧 ready 包必须作废或降级为历史文件。

### 4. 服务器使用静态 manifest 协议

服务器第一版只需要托管静态文件：`latest.json`、安装包和 SHA256 文件。manifest 包含 schema version、product、channel、version、minimum_supported_version、important、release notes、asset URL、size 和 sha256。`important` 仅表示重要更新提示，不阻断用户继续使用；真正强制升级不属于 MVP。

客户端只信任配置中的更新源基础 URL，并默认要求下载 URL 使用 HTTPS。对于无域名、仅能通过 IP:端口访问的部署，允许通过显式配置开启 HTTP 例外，但仅限 `localhost` 或字面量 IP 地址；普通域名的 HTTP 仍必须拒绝。前端不能提交任意下载 URL，避免本地 API 被滥用为任意文件下载器。默认未配置更新源时，自动检查必须 no-op，不向用户显示失败提示，只在调试日志中记录跳过原因。

### 5. 第一版默认使用 HTTPS + SHA256 + Authenticode 签名，预留 manifest 签名

SHA256 来自 manifest，只能防止下载损坏，不能单独防止服务器或 manifest 被篡改。由于本功能会自动执行下载的 exe，第一版必须在 Windows 打包环境中验证安装包 Authenticode 签名，并校验证书发布者或证书指纹符合配置的允许列表。无域名环境如果临时使用 HTTP，必须显式开启配置且仍然执行 SHA256 与 Authenticode 校验。manifest 签名作为预留字段和后续增强，不阻塞 MVP，但数据模型应保留 `signature_url` 或 `signature` 扩展空间。

### 6. 统一版本读取

后端新增版本工具，优先使用 `importlib.metadata.version("nini")` 获取安装包版本，fallback 到 `nini.__version__`。FastAPI app version、更新检查和 CLI 显示应复用同一工具，避免当前 `pyproject.toml` 与 `src/nini/__init__.py` 中的 `__version__` 不一致的问题继续扩大。版本比较遵循 Python 包发布实际使用的 PEP 440；如果发布脚本输入 SemVer 风格版本，必须在发布前规范化或拒绝。

### 7. 开发环境只检查，不安装

当 `getattr(sys, "frozen", False)` 为假时，`apply` 返回明确错误，不启动安装器。这样可以避免源码环境误执行覆盖安装，也便于测试 `/api/update/check` 与前端 UI。

## Risks / Trade-offs

- 安装包体积较大 → 第一版接受完整包下载；前端显示大小，下载失败可重试，后续再评估差分更新。
- GUI/CLI 双进程退出不完整导致文件锁未释放 → apply 必须协调 GUI 壳与后端服务退出，updater 等待相关 Nini 进程释放后再安装，并在超时失败时记录日志而不覆盖安装。
- 静默安装失败用户无感 → updater 写入 `%USERPROFILE%\.nini\logs\updater.log`，失败时不删除安装包，便于重试和排查。
- Manifest 被篡改 → 第一版默认要求 HTTPS、SHA256 与 Authenticode 签名校验；HTTP 只允许显式开启且限制为 IP 地址或 localhost，后续补 manifest 签名与内置公钥验证。
- 用户正在执行 Agent 任务 → 前端和后端在 apply 前检查运行状态；允许下载但阻止立即安装。
- 杀毒软件拦截 updater 或安装器 → 发布包做代码签名，错误日志中记录启动失败和安装退出码。
- 版本号来源漂移 → 本 change 首先统一版本读取，并补测试覆盖。

## Migration Plan

1. 新增版本读取工具并统一后端使用点，修正当前版本不一致问题。
2. 新增更新服务与 API，但默认配置中仅启用检查，不自动下载或安装。
3. 新增前端更新入口，先支持手动检查；自动检查使用本地时间戳限频。
4. 新增下载、SHA256 与 Authenticode 签名校验，确认不会影响已有会话和 Agent 任务。
5. 新增 updater 打包入口和 NSIS 静默安装集成。
6. 在测试服务器发布 beta manifest，用打包版验证从旧版本升级到新版本。
7. stable 发布前执行 `pytest -q`、`cd web && npm run build`、`python -m build` 和 Windows 打包升级烟测。

回滚策略：如果升级功能出现问题，服务器可将 manifest 回退到上一稳定版本或关闭 update_available；客户端失败时保留当前安装。已经升级到新版本但异常时，通过重新运行上一版本安装包回滚，用户数据目录保持不变。

## Open Questions

- 服务器最终域名和发布路径是否固定；实现时需要一个默认空配置或占位 URL。
- Authenticode 允许列表使用发布者名称还是证书指纹；建议正式发布使用证书指纹，测试构建允许显式关闭签名校验。
- 自动检查的默认频率建议为 24 小时，是否需要 UI 允许关闭自动检查。
- 企业离线部署是否允许禁用更新入口；建议通过配置开关支持。
