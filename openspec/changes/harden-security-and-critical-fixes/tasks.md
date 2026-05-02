## 1. 沙箱安全加固（Critical C1-C3）

- [x] 1.1 在 `_sandbox_worker` 中 monkey-patch `pd.DataFrame.eval`，拦截包含 `__import__`/`exec`/`compile`/`open`/`os.`/`subprocess`/`sys.` 的表达式字符串，抛出 `SandboxPolicyError` 并提供替代建议（参考 sandbox-hardening spec Requirement 1）
- [x] 1.2 在 `_sandbox_worker` 中 monkey-patch `pd.DataFrame.query`，使用与 df.eval 相同的拦截规则（参考 sandbox-hardening spec Requirement 1）
- [x] 1.3 在 `_sandbox_worker` 中 hook `pd.read_csv`/`pd.read_excel`/`pd.read_json`/`pd.read_pickle`，将路径参数限制在 `working_dir` 内，拒绝绝对路径、含 `..` 的路径、resolve 后超出 `working_dir` 的路径（参考 sandbox-hardening spec Requirement 2）
- [x] 1.4 从 `_BASE_SAFE_BUILTINS` 移除 `type`，替换为 `safe_type` 函数：仅支持单参数形式 `safe_type(obj)` 返回 `type(obj)`；多参数形式抛出 `SandboxPolicyError`（参考 sandbox-hardening spec Requirement 3）。AST 层已有 `__dunder__` 属性访问拦截（`policy.py:355-365`），`safe_type` 封堵的是 `type(lambda:0)(code,{},{})` 直接调用路径。
- [x] 1.5 编写沙箱加固回归测试：df.eval 危险表达式拦截、合法表达式放行、df.query 同理、pd.read_* 路径限制、safe_type 单/多参数行为，运行 `pytest tests/test_sandbox_*.py -q` 验证

## 2. API 鉴权加固（Critical C4-C5）

- [x] 2.1 创建 FastAPI 依赖项 `require_auth`，调用现有 `is_request_authenticated` 验证请求已认证，未认证返回 401（参考 api-auth-middleware spec Requirement 1）
- [x] 2.2 为所有写操作端点（POST/PUT/PATCH/DELETE）添加 `Depends(require_auth)`，包括 upload、session create/delete、workspace 等路由；读操作（GET）保持开放（参考 api-auth-middleware spec Requirement 1）
- [x] 2.3 `_resolve_file_path` 在 `resolve` 后增加 `os.path.realpath` 最终校验，确保解析后路径未超出预期目录，拒绝符号链接指向外部（参考 api-auth-middleware spec Requirement 2）
- [x] 2.4 编写 API 鉴权测试：未认证写操作返回 401、已认证写操作成功、未认证读操作正常、符号链接 TOCTOU 防御，运行 `pytest tests/test_api_auth*.py -q` 验证

## 3. 更新器安全加固（Critical C7-C10）

- [x] 3.1 移除 `_backup_install_dir` 之后的 `time.sleep(1.5)`（`updater_main.py:367`），备份完成后立即启动 NSIS 安装（参考 updater-security-v3 spec Requirement 1）
- [x] 3.2 从 `origin_guard.py` 默认 Shell Origin 白名单移除 `"null"`，仅当 `update_allowed_origins` 配置显式包含 `"null"` 时才放行（参考 updater-security-v3 spec Requirement 2）
- [x] 3.3 加固 `_probe_install_dir_unlocked` 恢复路径：保持 rename 探测方式（检测文件锁语义正确），确保 rename-back 失败时在任何退出路径上都尝试恢复原位（参考 updater-security-v3 spec Requirement 3）
- [x] 3.4 `prepare_apply_update` 在 `state.expected_sha256` 为空时从 `self._asset.sha256` 回填；两者均为空时抛出 `ApplyUpdateError`，消息包含"无法进行二次校验"（参考 updater-security-v3 spec Requirement 4）
- [x] 3.5 `UpdateStateStore.load` HMAC 校验失败时日志从 `logger.warning` 升级为 `logger.error`，清理 `installer_path` 指向的孤立文件，返回含 `error` 字段的空状态。保持双文件格式不变（参考 updater-security-v3 spec Requirement 5）
- [x] 3.6 编写更新器安全测试：TOCTOU 无延迟、Origin null 拒绝/放行、探测恢复路径、sha256 兜底/双重缺失、HMAC 日志升级与孤立文件清理，运行 `pytest tests/test_update_*.py -q` 验证

## 4. 更新器错误处理加固（Important A6/A8/A9/A11/A13）

- [x] 4.1 `updater_main` 在 NSIS 返回非零退出码时：调用 `_restore_backup` 并记录成功/失败；回滚成功时尝试启动旧版 `app_exe` 并捕获 `OSError`；使用独立退出码 `EXIT_RESTORE_FAILED`（值 10）区分"回滚失败"与"安装失败但已回滚"（参考 updater-security-v3 spec Requirement 6）
- [x] 4.2 `download.py` 在收到 206 响应时校验 `Content-Range` header 的起始偏移与 `resume_from` 一致；不匹配时截断已有内容以 `mode='wb'` 重新下载（参考 updater-security-v3 spec Requirement 7）
- [x] 4.3 `download.py` 错误处理改用布尔变量 `should_reset_temp` 决定是否清理临时文件，`resume_from == 0` 时清理、`resume_from > 0` 时保留以供续传（参考 updater-security-v3 spec Requirement 8）
- [x] 4.4 `UpdateService.download_update` 将 `existing.status in ("downloading", "verifying")` 均视为忙碌状态，拒绝并发下载请求（参考 updater-security-v3 spec Requirement 9）
- [x] 4.5 `updater_main._process_exists` 在 `OpenProcess` 返回空句柄时调用 `ctypes.GetLastError()`：`ERROR_ACCESS_DENIED`(5) 写 `logger.warning` 并返回 True（视为存活）；`ERROR_INVALID_PARAMETER`(87) 返回 False（参考 updater-security-v3 spec Requirement 10）
- [x] 4.6 编写更新器错误处理测试：NSIS 回滚成功/失败路径、Content-Range 偏移匹配/不匹配、下载错误分类、verifying 并发拒绝、OpenProcess 错误码区分，运行 `pytest tests/test_update_*.py -q` 验证

## 5. 集成验证

- [x] 5.1 运行全量后端测试 `pytest -q`，确认所有新测试和既有测试通过
- [x] 5.2 运行前端构建 `cd web && npm run build`，确认前端无类型错误
- [x] 5.3 运行 `gitnexus_detect_changes()` 确认变更范围符合预期，无意外影响
