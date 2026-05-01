## 1. API 鉴权与 Origin 校验（P0）

- [x] 1.1 确认现有 API Key 中间件（`X-Nini-Token`）已对 `/api/update/download`、`/api/update/apply` 生效；如有放行例外则修复
- [x] 1.2 实现 Origin/Referer 校验依赖：限定 `http://127.0.0.1:<port>` / `http://localhost:<port>` 与 Tauri/Electron 壳来源；不匹配返回 403
- [x] 1.3 新增配置 `update_require_origin_check`（默认 true，企业离线部署可显式关闭）
- [x] 1.4 测试：未带 token / 错误 token / 错误 Origin / 关闭 Origin 检查后正常通过
- [x] 1.5 文档更新：`.env.example`、`packaging/README.md`

## 2. updater 二次校验（P0）

- [x] 2.1 `src/nini/update/apply.py:build_updater_command` 增加 `--expected-sha256`、`--expected-size`、`--allowed-thumbprints`、`--allowed-publishers` 参数
- [x] 2.2 `src/nini/updater_main.py` 在 `_wait_for_processes` 后、`subprocess.run(installer)` 前实现：
  - [x] 2.2.1 大小校验
  - [x] 2.2.2 SHA256 重新计算并比对
  - [x] 2.2.3 Windows 下重新校验 Authenticode 签名（复用 `signature.py` 或子集实现）
- [x] 2.3 任一二次校验失败返回非零退出码、写日志、不进入 NSIS
- [x] 2.4 测试：mock installer 文件被替换、sha256 不匹配、签名失败时 updater 退出码与日志断言
- [x] 2.5 性能基线测试：676MB 安装包二次校验耗时不超过 5s（自动化层面以 16MB 烟测覆盖吞吐回归；676MB 完整门由 §11.8 Windows 打包烟测验证）

## 3. 下载链路 redirect 禁用（P0）

- [x] 3.1 `src/nini/update/manifest.py:fetch_manifest` 与 `src/nini/update/download.py` 中所有 `httpx.AsyncClient` 显式 `follow_redirects=False`
- [x] 3.2 测试：服务器返回 302 时下载/manifest 拉取被拒绝并报可读错误

## 4. 有序 shutdown（P1）

- [x] 4.1 `src/nini/update/apply.py:schedule_current_process_exit` 改为：
  - [x] 4.1.1 设置 uvicorn `Server.should_exit = True`
  - [x] 4.1.2 取消所有活跃 `asyncio.Task`
  - [x] 4.1.3 通知沙箱子进程关闭并等待 `update_apply_grace_seconds`（默认 5）
  - [x] 4.1.4 flush 日志、关闭 SQLite/文件句柄
  - [x] 4.1.5 仍未退出则 `os._exit(0)` 兜底
- [x] 4.2 实现 `runtime_state.collect_owned_pids()` 收集所有 Nini 派生子进程 PID
- [x] 4.3 `build_updater_command` 增加 `--child-pids` 参数（逗号分隔）
- [x] 4.4 `updater_main._wait_for_processes` 同时等待后端 + GUI + 子进程 PID
- [x] 4.5 测试：mock 沙箱子进程未退出场景，验证 grace 等待与超时行为

## 5. updater 文件锁探测（P1）

- [x] 5.1 `updater_main` 在 PID 退出后增加文件锁探测循环（最长 `update_apply_lock_probe_seconds`，默认 10）
- [x] 5.2 探测策略：尝试独占重命名 `install_dir`，成功则改回原名
- [x] 5.3 探测失败：写日志、取消安装、保留安装包以便重试，返回特定退出码（区分文件锁失败与其它失败）
- [x] 5.4 测试：mock 文件锁场景的探测超时与日志输出

## 6. 备份硬链接 clone（P1）

- [x] 6.1 `updater_main._backup_install_dir` 优先用 `os.link` 递归 clone，失败 fallback 到 `shutil.copytree`
- [x] 6.2 `keep_backups` 默认值由 3 改为 1
- [x] 6.3 备份失败时返回非零并不进入 NSIS
- [x] 6.4 测试：硬链接成功 / 失败回退 / 备份失败中止 三条路径

## 7. 续传 SHA256 比对（P1）

- [x] 7.1 `UpdateDownloadState` 增加 `expected_sha256` 字段并持久化
- [x] 7.2 `download_asset` 在判定 `can_resume` 之后比对 `existing.expected_sha256` 与新 manifest sha256，不一致则丢弃旧字节、状态置 `idle`
- [x] 7.3 测试：同 version 服务器换 sha256 重发布场景，验证旧 `.download` 被删除、从头开始下载

## 8. updater 进程 detach（P1）

- [x] 8.1 `launch_updater` 在 Windows 优先尝试 `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB`，失败 fallback 到 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`，再失败 fallback 到 `CREATE_NO_WINDOW`
- [x] 8.2 POSIX 路径加 `start_new_session=True`
- [x] 8.3 测试：mock `Popen` 调用参数断言主路径与 fallback 链

## 9. 状态枚举 + DI + downgrade（P2）

- [x] 9.1 `UpdateCheckResult.status` 改为 `Literal[...]`，包含 `channel_mismatch`
- [x] 9.2 `web/src/types/update.ts` 同步类型，UI 文案给出"渠道切换无法降级"提示
- [x] 9.3 实现 `versioning.is_safe_upgrade(candidate, current) -> bool`，拒绝 `candidate < current`
- [x] 9.4 `UpdateService` 通过 FastAPI `Depends(get_update_service)` 注入，保留 `update_service` 全局单例 shim 一个迭代
- [x] 9.5 测试：DI 替换后所有现有路由测试不破；channel_mismatch 场景断言

## 10. HMAC 状态主张降级（P2，文档级）

- [x] 10.1 `src/nini/update/state.py` 注释与 docstring 改写为"完整性校验，非防篡改"
- [x] 10.2 移除 commit message / PR 描述中"防状态文件篡改"主张
- [x] 10.3 不引入 DPAPI / keyring；不修改密钥派生逻辑

## 11. 测试与验收

- [x] 11.1 扩展 `tests/test_update_routes.py`：API 鉴权、Origin 校验
- [x] 11.2 扩展 `tests/test_updater_main.py`：二次校验、文件锁探测、备份硬链接、回滚
- [x] 11.3 扩展 `tests/test_update_download.py`（新建）：redirect 拒绝、续传 sha256 比对
- [x] 11.4 新建 `tests/test_update_apply_shutdown.py`：有序 shutdown 与子进程等待
- [x] 11.5 全部 `pytest -q` 通过
- [x] 11.6 `python scripts/check_event_schema_consistency.py` 通过
- [x] 11.7 `cd web && npm run build` 通过
- [ ] 11.8 Windows 打包烟测：手动验证 升级成功 / 升级失败回滚 / 续传 / 重发布丢字节 / 文件锁超时 五个场景的日志与最终版本号
