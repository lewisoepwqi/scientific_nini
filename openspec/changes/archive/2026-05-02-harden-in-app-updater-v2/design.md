## Context

`add-in-app-updater` 已落地 MVP：FastAPI 暴露 `/api/update/{check,download,status,apply}`；`UpdateService` 协调 manifest 拉取、流式下载、SHA256 校验；apply 阶段做 Authenticode 校验、运行任务闸门，启动独立 `nini-updater.exe` 后通过 `os._exit(0)` 让出文件锁；updater 等待 PID、备份、NSIS 静默安装、失败回滚、重启。

整体架构是合理的，但作为基础设施仍存在四类问题：

1. **API 攻击面**：`/api/update/apply` 等同于"在用户机器上启动任意已下载安装包"。当前路由只有日志，没有鉴权与 Origin 校验，本地浏览器中任意网页可发出 POST。
2. **校验时间窗口**：apply 阶段在主进程做完 Authenticode + SHA256，但执行人是 updater 子进程。中间存在文件被替换的窗口，且 updater 不再校验。
3. **退出路径过硬**：`os._exit(0)` 跳过 ASGI server 优雅关闭、跳过沙箱子进程清理，可能让 NSIS 因文件锁失败、走回滚路径。
4. **状态机与 redirect 边角**：续传不比对 SHA256；`httpx` 默认 follow_redirects 可能绕过同源校验；备份策略空间消耗失控。

本设计在不改变用户可见流程、不破坏 manifest 协议的前提下，把上述风险收敛到"可以默认开启自动更新"的可信度。manifest 签名（Ed25519 + 客户端公钥分发）作为独立 change 后续推进，本变更不在范围。

## Goals / Non-Goals

**Goals:**

- 关闭 apply / download API 的本地未授权调用面。
- 将 SHA256 与 Authenticode 校验前移到 updater 真正执行 NSIS 之前，关闭 TOCTOU 窗口。
- 让后端退出过程对沙箱子进程、ASGI server、外部资源都做到有序释放，确保 updater 不被文件锁阻塞。
- 把 676MB 安装目录的备份成本降到秒级、空间几乎为 0，备份失败必须中止而非无感继续。
- 把状态枚举、依赖注入与 downgrade 保护做完，给后续维护留出空间。

**Non-Goals:**

- 不实现 manifest 签名 / Ed25519 / 公钥轮换，留作独立 change。
- 不引入 DPAPI / keyring 等新依赖；state.json 的"安全主张"以注释/文档形式降级即可。
- 不改造 GUI 壳启动后端的方式（环境变量、IPC 协议等）。
- 不实现差分更新。
- 不引入新的可见 UI 流程；前端仅扩展状态字段。
- 不重写 PowerShell-based Authenticode 校验（updater 二次校验复用同一实现）。
- 不替换 NSIS 安装器，不改变 `/S /D=<path>` 调用约定。
- 不改变用户数据目录与备份目录位置。

## Decisions

### 1. API 鉴权与 Origin 校验（不引入 confirm token）

- `/api/update/download`、`/api/update/apply` 必须经过统一 API Key 中间件（`X-Nini-Token`），未携带或不匹配返回 401。
- 同时校验 `Origin`/`Referer` 头，限定在 `http://127.0.0.1:<port>` / `http://localhost:<port>` 与 Tauri/Electron 壳的来源；不匹配返回 403。
- 配置开关：`update_require_origin_check`（默认 true，企业离线部署可显式关闭）。

**为何不引入 confirm token**：API Key 走 header（`X-Nini-Token`），浏览器跨域简单 POST 不能自定义自定义 header（会触发 CORS preflight），加上 Origin 校验后已构成完整 CSRF 防御。再加一次性 token 是冗余防御，会显著增加前后端状态机复杂度（token 持久化、过期回收、check↔apply 时序耦合），收益不抵成本。

### 2. updater 二次校验

- updater 命令行新增 `--expected-sha256`、`--expected-size`、`--allowed-thumbprints`、`--allowed-publishers` 参数。
- updater 在 `_wait_for_processes` 之后、`subprocess.run(installer)` 之前，串行执行：
  1. 文件存在 + 大小校验；
  2. SHA256 重新计算并与 `--expected-sha256` 比对；
  3. Windows 下重新跑一次 `Get-AuthenticodeSignature` 校验；
  4. 任一失败立即返回非零退出码、写日志、不进入安装。
- 仅通过命令行参数传入，不引入额外的 `.sha256` / `.sig` 同目录文件，避免新文件路径与状态污染。
- updater 不校验 manifest 签名；manifest 安全由独立 change 处理，updater 只对"安装包文件"负责。

**风险**：每次升级多 1 次 PowerShell 启动 + 1 次 SHA256（676MB 约 2-3s），可接受，且本来就在用户主动确认升级路径上。

### 3. 下载链路 redirect 禁用

- `httpx.AsyncClient` 在 manifest 与 asset 下载时显式 `follow_redirects=False`，遇到 3xx 直接报错。
- 当前发布架构没有 CDN redirect 需求，不引入受控 redirect handler；如未来需要，由独立 change 评估并设计同源 + 协议 + 鉴权的统一策略。

### 4. 有序 shutdown

- 退出顺序由当前 `delay_seconds=1.0` + `os._exit(0)` 改为：
  1. 接到 apply 请求并通过鉴权 → 标记 `applying`；
  2. 触发 `uvicorn.Server.should_exit = True`，并在协程中取消所有活跃 `asyncio.Task`；
  3. 通知所有沙箱子进程（`run_code` / R）关闭，等待最多 `update_apply_grace_seconds`（默认 5s）；
  4. 释放 SQLite / 文件句柄，flush 日志；
  5. 仍未退出则 `os._exit(0)` 兜底。
- 同时把所有沙箱子进程 PID + 后端 PID 一起传给 updater，`_wait_for_processes` 全部等待。

GUI PID 仍沿用 `os.getppid()` 启发式（启动方式不改造），其残留风险由"文件锁探测"兜底。

### 5. updater 文件锁探测

- 等待 PID 退出后，再循环尝试 `os.rename(install_dir, install_dir + ".lock")`，成功则改回原名（独占语义验证）。
- 探测最长 `update_apply_lock_probe_seconds`（默认 10s），失败则记录日志并取消安装、不删除安装包，返回特定退出码（区分文件锁失败与其它失败）。
- 这一机制同时覆盖了"GUI 壳 / 杀软 / Explorer 预览仍持锁"的所有场景，无需为单独 GUI PID 改造启动协议。

### 6. 备份硬链接 clone

- `_backup_install_dir` 先尝试 `os.link` 递归克隆（NTFS 支持，PyInstaller 产物多为只读文件，硬链接安全）；失败再 fallback 到 `shutil.copytree`。
- `keep_backups` 默认改为 1。
- 备份失败必须中止升级，updater 直接返回非零退出码，不进入 NSIS。

### 7. 续传 SHA256 比对

- `UpdateDownloadState` 增加 `expected_sha256` 字段（持久化）。
- 续传前比对当前 manifest sha256 与 state.expected_sha256，不一致则删除旧 `.download` 文件、状态置 `idle`、从头开始。
- 同步增加日志说明"manifest 重发布检测，丢弃旧字节"。

### 8. updater 进程 detach（尽力而为）

- `launch_updater` 在 Windows 下尝试加 `creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB`。
- 实际是否生效取决于上层 GUI 壳是否启用了 job object 与 `JOB_OBJECT_LIMIT_BREAKAWAY_OK`，不能假设全场景成功。失败时 try/except fallback 到 `creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`，再失败 fallback 到当前的 `CREATE_NO_WINDOW`。
- POSIX 路径加 `start_new_session=True`，对未来 macOS/Linux 兼容。

由于 fallback 链的存在，spec 不写死具体 flags，只要求"尽力 detach 以避免 GUI 壳生命周期连带杀死 updater"。

### 9. HMAC 状态主张降级（文档级）

- 现状：`UpdateStateStore` 以 `str(path.parent)` 为 HMAC 密钥，等价于公开密钥。
- 决定：仅做"明确降级"——注释、docstring 与未来的 commit message 不再宣称"防篡改"，改为"完整性校验"；保留代码不动以避免引入新依赖。
- 状态文件不承担安全保证：升级安全由 API 鉴权 + updater 二次校验保证，state.json 仅用于进度恢复。
- 不引入 DPAPI / keyring：DPAPI 在 PyInstaller frozen 环境下需要额外 `pywin32` 依赖、与已废弃环境的兼容性以及失败回退路径都将增加复杂度，超出本次"加固"范畴；如未来需要真正的状态文件防篡改，可在独立 change 中评估。

### 10. 状态枚举 + DI + downgrade

- `UpdateCheckResult.status` 改为 `Literal["available","up_to_date","check_failed","not_configured","disabled","channel_mismatch"]`。
- `UpdateService` 通过 `Depends(get_update_service)` 注入，废弃 `update_service = UpdateService()` 全局单例（保留 shim 一个迭代）。
- downgrade 保护：`is_safe_upgrade(candidate, current) -> bool` 在 `is_newer_version` 之外拒绝 `candidate < current`；从 beta 切回 stable 时返回 `channel_mismatch` 给 UI 提示"无法降级"。

## Risks / Trade-offs

- **二次校验性能开销**：每次升级多 1 次 PowerShell 启动 + 1 次 SHA256（676MB 约 2-3s）。可接受。
- **detach 标志兼容性**：`CREATE_BREAKAWAY_FROM_JOB` 在某些 job 设置下会失败，已用 fallback 链覆盖；spec 不绑定具体 flags。
- **HMAC 不换源**：state.json 仍用公开路径密钥，定向篡改攻击者可伪造合法签名；接受，因为安装包安全由 updater 二次校验保证，state.json 只影响 UI 状态恢复。
- **downgrade 保护与渠道切换**：`channel_mismatch` 让 UI 给出明确提示，不再静默"up_to_date"，但 UI 文案需打磨。

## Migration Plan

1. **Phase 1（P0 安全）**：API 鉴权 + Origin；updater 二次校验；redirect 禁用。一个 PR。
2. **Phase 2（P1 可靠性）**：有序 shutdown；文件锁探测；备份硬链接；续传 sha256；updater detach。一个 PR。
3. **Phase 3（P2 工程化）**：状态枚举；DI 改造；downgrade 保护；HMAC 主张文档降级。一个 PR。
4. **Phase 4**：在测试服务器跑一遍升级 + 失败回滚 + 续传 + 重发布丢弃旧字节 + 文件锁超时 五个场景的烟测。
5. **Phase 5**：stable 发布前执行 `pytest -q`、`cd web && npm run build`、`python -m build` 与 Windows 打包升级烟测。

回滚策略：每个 Phase 都是独立 PR，可单独回滚；所有改动都是客户端内部行为变更，不需要服务器协调。

## Open Questions

- 沙箱子进程 PID 收集是否对外暴露 API；建议通过 `runtime_state.collect_owned_pids()` 内部调用，不入公开 API。
- `update_apply_grace_seconds` 默认值；建议 5s，工程上可配。
- `update_apply_lock_probe_seconds` 默认值；建议 10s，覆盖大多数杀软延迟扫描场景。
- API Key 中间件当前是否对所有路由生效；本变更需确认 update 路由正确接入而非例外放行。
