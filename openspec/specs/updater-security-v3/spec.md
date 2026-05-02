## ADDED Requirements

### Requirement: TOCTOU 时间窗口闭合
更新器在 `_backup_install_dir` 完成后 SHALL 立即启动 NSIS 安装，移除中间的 `time.sleep(1.5)`（`updater_main.py:367`）。

#### Scenario: 备份后无延迟直接安装
- **WHEN** `_backup_install_dir` 完成（或无需备份）
- **THEN** 立即执行 NSIS 安装命令，中间无 `time.sleep`

### Requirement: Origin null 默认不放行
`origin_guard.py` 的默认 Shell Origin 白名单 SHALL NOT 包含字符串 `"null"`。仅当 `update_allowed_origins` 配置显式包含 `"null"` 时才放行。

#### Scenario: 请求 Origin: null 被默认拒绝
- **WHEN** 请求头 `Origin: null` 且配置未显式包含 `"null"`
- **THEN** 返回 403

#### Scenario: 显式配置允许 null
- **WHEN** `update_allowed_origins` 包含 `"null"` 且请求 `Origin: null`
- **THEN** 请求被放行

### Requirement: 目录探测恢复路径加固
`_probe_install_dir_unlocked` SHALL 保持 rename 探测方式（检测文件锁语义正确）。当 rename 成功但 rename-back 失败时，SHALL 确保探测路径在任何退出路径上都尝试恢复原位。恢复失败时 SHALL 记录日志并返回 False。

#### Scenario: 目录未被占用
- **WHEN** rename 成功且 rename-back 成功
- **THEN** 返回 True

#### Scenario: 目录被占用
- **WHEN** rename 失败（PermissionError / OSError）
- **THEN** 继续重试直到超时，返回 False

#### Scenario: rename 成功但 rename-back 失败
- **WHEN** rename 成功但恢复 rename 失败
- **THEN** 再次尝试恢复，记录日志，返回 False

### Requirement: expected_sha256 缺失兜底
`prepare_apply_update` 在 `state.expected_sha256` 为空时 SHALL 从 `self._asset.sha256` 回填。若两者均为空则拒绝 apply 并抛出 `ApplyUpdateError`。

#### Scenario: 从 asset 回填 sha256
- **WHEN** `state.expected_sha256` 为空但 `self._asset.sha256` 有值
- **THEN** 使用 `self._asset.sha256` 作为二次校验依据

#### Scenario: 双重缺失拒绝 apply
- **WHEN** `state.expected_sha256` 和 `self._asset.sha256` 均为空
- **THEN** 抛出 `ApplyUpdateError`，消息包含"无法进行二次校验"

### Requirement: HMAC 日志级别升级与孤立文件清理
`UpdateStateStore.load` 在 HMAC 校验失败时 SHALL 使用 `logger.error` 级别日志，区分"HMAC 不匹配"与"JSON 损坏"，清理 `installer_path` 指向的孤立文件，并在返回的空状态中设置 `error` 字段。

保持 state.json + state.json.sig 双文件格式不变。HMAC 密钥是路径派生的，签名不匹配更可能是文件损坏而非真实篡改。

#### Scenario: HMAC 不匹配检测
- **WHEN** 状态文件 HMAC 不匹配
- **THEN** `logger.error` 输出"更新状态文件签名不匹配"，清理 installer 孤立文件，返回含 `error` 的空状态

#### Scenario: JSON 损坏检测
- **WHEN** 状态文件不是合法 JSON
- **THEN** `logger.warning` 输出"更新状态文件损坏"，返回含 `error` 的空状态

### Requirement: NSIS 失败回滚加固
`updater_main` 在 NSIS 返回非零退出码时 SHALL：(1) 调用 `_restore_backup` 并记录成功/失败；(2) 回滚成功时尝试启动旧版 `app_exe` 并捕获 `OSError`；(3) 使用独立退出码 `EXIT_RESTORE_FAILED`（值 10）区分"回滚失败"与"安装失败但已回滚"。

#### Scenario: NSIS 失败回滚成功
- **WHEN** NSIS 返回非零且 `_restore_backup` 成功
- **THEN** 启动旧版 app_exe，返回 NSIS 退出码

#### Scenario: 回滚也失败
- **WHEN** NSIS 返回非零且 `_restore_backup` 失败
- **THEN** 返回 `EXIT_RESTORE_FAILED`（10），日志包含"安装目录可能已损坏"

### Requirement: 下载续传 Content-Range 校验
`download.py` 在收到 206 响应时 SHALL 校验 `Content-Range` header 的起始偏移与 `resume_from` 一致。不匹配时 SHALL 截断已有内容并以 `mode='wb'` 重新下载。

#### Scenario: Content-Range 偏移匹配
- **WHEN** 服务器返回 `Content-Range: bytes 1000-1999/2000` 且 `resume_from == 1000`
- **THEN** 以 `mode='ab'` 追加写入

#### Scenario: Content-Range 偏移不匹配
- **WHEN** 服务器返回 `Content-Range: bytes 0-1999/2000` 但 `resume_from == 1000`
- **THEN** 截断已有内容，以 `mode='wb'` 从头下载

### Requirement: 下载错误分类改用布尔 flag
`download.py` 的错误处理 SHALL 使用布尔变量 `should_reset_temp` 而非字符串子串匹配 `"不支持 Range"` 来决定是否清理临时文件。

#### Scenario: 不支持 Range 时清理临时文件
- **WHEN** 下载异常且 `resume_from == 0`
- **THEN** `should_reset_temp = True`，清理临时文件

#### Scenario: 网络中断时保留临时文件
- **WHEN** 下载异常且 `resume_from > 0` 且非服务器不支持 Range
- **THEN** `should_reset_temp = False`，保留临时文件以供续传

### Requirement: 并发屏障增加 verifying 状态
`UpdateService.download_update` SHALL 将 `existing.status in ("downloading", "verifying")` 均视为忙碌状态，拒绝并发下载请求。

#### Scenario: verifying 状态下拒绝二次下载
- **WHEN** 现有状态为 `verifying` 且收到新的下载请求
- **THEN** 返回当前状态，不启动新下载

### Requirement: OpenProcess 错误码区分
`updater_main._process_exists` 在 `OpenProcess` 返回空句柄时 SHALL 调用 `ctypes.GetLastError()`，区分 `ERROR_ACCESS_DENIED`(5) 与 `ERROR_INVALID_PARAMETER`(87)。前者 SHALL 写 `logger.warning` 并返回 True（视为进程存活），后者返回 False。

#### Scenario: 权限不足视为进程存活
- **WHEN** `OpenProcess` 失败且 `GetLastError() == 5`
- **THEN** `logger.warning` 记录"权限不足"，返回 True

#### Scenario: 进程已退出
- **WHEN** `OpenProcess` 失败且 `GetLastError() == 87`
- **THEN** 返回 False
