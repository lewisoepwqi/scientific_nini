## Why

应用内更新（`add-in-app-updater`）已落地 MVP，整体架构合理（双进程半自动升级、HTTPS+SHA256+Authenticode 多层防御），但作为基础设施仍存在多项必须修复的安全与可靠性缺陷。这些缺陷集中在 apply 路径的鉴权、updater 自身的二次校验、退出顺序、状态机一致性以及若干异常路径上，未修复前不应将 in-app-updater 升级到 stable 渠道默认开启。

本变更对 in-app-updater 能力做加固迭代（v2），不引入新功能、不改变用户可见流程，重点是把"自动执行已签名 exe"这一高风险通道收敛到生产可用质量。manifest 签名（cosign / Ed25519 公钥分发）作为独立 change 后续推进，本次不在范围。

## What Changes

### 安全加固（P0）

- **API 鉴权与 Origin 校验**：`/api/update/download` 与 `/api/update/apply` 必须经过统一 API Key 中间件（`X-Nini-Token`），并校验 `Origin`/`Referer` 限定为本地 web 壳；`update_require_origin_check`（默认 true）允许企业离线部署显式关闭。API Key 走 header 已构成基础 CSRF 防御（浏览器跨域简单 POST 不能自定义 header），不再引入额外 confirm token。
- **updater 二次校验**：独立 `nini-updater.exe` 在执行 NSIS 之前必须重新做一次 SHA256 与 Authenticode 校验，关闭"主进程校验通过 → 文件被替换 → updater 直接执行"的时间窗口。期望 SHA256 与签名策略仅通过命令行参数传入，不引入额外文件。
- **下载链路 redirect 禁用**：`httpx.AsyncClient` 在 manifest 与安装包下载时显式 `follow_redirects=False`，遇到 3xx 直接报错。当前发布架构无 CDN redirect 需求，不引入受控 redirect handler。

### 可靠性提升（P1）

- **有序 shutdown 替换 `os._exit(0)`**：取消所有活跃 `asyncio.Task`、向 uvicorn 发出 `should_exit`、等待 grace 周期再兜底强制退出；同时把所有 Nini 派生子进程（沙箱 `run_code` / R 子进程）的 PID 一并交给 updater 等待。
- **updater 文件锁探测**：`_wait_for_processes` 等待 PID 之后，再做"独占重命名 install_dir"探测，避免杀软或 Explorer 预览导致 NSIS 失败。这一项同时覆盖了"GUI 壳子进程未列入 PID 列表"的场景，因此不再引入 `NINI_GUI_PID` 环境变量改造。
- **备份策略瘦身**：`shutil.copytree` 改为 `os.link`（NTFS 硬链接）clone，把 676MB 备份成本降到秒级且空间近 0；`keep_backups` 默认从 3 改为 1；备份失败必须中止升级而非无感继续。
- **续传期望 SHA256 比对**：`UpdateDownloadState` 持久化 `expected_sha256`，续传前若与新 manifest 不一致则丢弃旧字节，避免"同 version 重发布"导致的浪费下载与 verify_failed。
- **updater 进程 detach（尽力而为）**：`Popen` 在 Windows 加 detach 相关 `creationflags`，并在不支持的 job 设置下 try/except fallback 到普通 detach，避免 GUI 壳的 job object 在 `KILL_ON_JOB_CLOSE` 模式下连带杀死 updater。

### 工程化（P2）

- **状态枚举统一**：`UpdateCheckResult.status` 由裸 `str` 升级为 `Literal`，与前端共享类型，新增 `channel_mismatch` 提示渠道切换无法降级。
- **`UpdateService` 改 DI**：通过 FastAPI dependency 注入，去除模块级单例，便于测试隔离；保留旧 `update_service` shim 一个迭代以兼容现有调用点。
- **downgrade 保护**：`is_safe_upgrade` 在 `is_newer_version` 之外拒绝 `manifest.version < current_version` 的"升级"。
- **HMAC 状态文件主张降级（文档级）**：`UpdateStateStore` 的密钥由 `str(path.parent)` 派生，等价于公开密钥，不能防定向篡改。仅修改注释与文档，把"防篡改"主张降级为"完整性校验"；不引入 DPAPI / keyring 等新依赖（state.json 的安全保证已被 updater 二次校验覆盖）。

### 测试补强

- 新增 fault injection / redirect 跨域 / 服务器换包 / 备份硬链接 fallback / Authenticode 异常状态枚举 / updater 二次校验失败回退 等用例。

### 不在范围

- 不实现 manifest 签名（Ed25519 / cosign 等），列入后续独立 change。
- 不引入新的更新流程（差分更新、跨平台、完全无感后台升级仍排除）。
- 不修改前端可见 UI 流程，仅做必要的状态字段扩展。
- 不改造 GUI 壳启动后端的方式（`NINI_GUI_PID` 环境变量等）；GUI 壳子进程残留场景由 install_dir 文件锁探测兜底。
- macOS / Linux 升级仍单独设计。

## Capabilities

### Modified Capabilities
- `in-app-updater`: 通过 v2 加固变更覆盖 API 鉴权、updater 二次校验、redirect 禁用、有序 shutdown、备份硬链接 clone、续传 SHA256 比对、updater detach、downgrade 保护与状态枚举等行为，提高基础设施可靠性。

### New Capabilities
无。

## Impact

- **后端**：`src/nini/update/` 多个模块，`src/nini/api/update_routes.py`，`src/nini/updater_main.py`。API 鉴权复用现有 API Key 中间件，新增 Origin 校验依赖。
- **前端**：`web/src/types/update.ts` 同步状态枚举，`channel_mismatch` 给出文案；UI 组件无可见变化。
- **打包**：本变更不引入新的打包资源（manifest 签名公钥分发延后到独立 change）。
- **配置**：新增 `update_require_origin_check`、`update_apply_grace_seconds`、`update_apply_lock_probe_seconds`；`update_signature_check_enabled` 在 `IS_FROZEN` 下保持强制开启不变。
- **发布系统**：`scripts/generate_update_manifest.py` 与 `scripts/verify_update_manifest.py` 不变。
- **测试**：新增端到端与异常路径用例，覆盖 P0/P1 全部行为变更。
- **风险与回滚**：本变更可分阶段合入，每个 P0 / P1 项目可独立 PR；所有改动均为内部行为变更，不破坏现有 manifest 协议，无客户端 / 服务器协调发布需求。
