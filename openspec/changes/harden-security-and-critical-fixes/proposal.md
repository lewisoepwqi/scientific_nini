## Why

全量代码审查发现 12 个 Critical、8 个高优先 Important 安全与健壮性问题，其中沙箱逃逸（`df.eval()` / `pd.read_csv` 任意文件读 / `type()` 构造绕过）和 API 鉴权缺失可在生产环境被直接利用，更新器 TOCTOU / CSRF 问题影响升级安全。需在本版本发布前修复所有 Critical 项及高优先 Important 项。

## What Changes

### 沙箱安全加固
- **C1** 拦截 `df.eval()` / `df.query()` 中的危险表达式，防止沙箱逃逸
- **C2** Hook `pd.read_*` 系列函数，限制文件路径在 `working_dir` 内，防止任意文件读取
- **C3** 从 `_BASE_SAFE_BUILTINS` 移除 `type`，替换为仅支持单参数形式的 `safe_type`，防止 `type(lambda:0)(code,{},{})` 构造绕过。AST 层已有 `__dunder__` 属性访问拦截（`policy.py:355-365`），属性链逃逸路径已被阻断，`safe_type` 是对 `type()` 直接调用路径的封堵。

### API 鉴权加固
- **C4** 为所有写操作端点添加 `is_request_authenticated` 鉴权检查（防御浏览器跨域 CSRF，非防御本地恶意进程）
- **C5** `_resolve_file_path` 增加符号链接 TOCTOU 防御

### 更新器安全加固
- **C7** 移除备份完成后的 `time.sleep(1.5)`，消除二次校验到 NSIS 执行之间的 TOCTOU 窗口
- **C8** 从默认 Origin 白名单移除 `"null"`，仅显式配置时放行
- **C9** `_probe_install_dir_unlocked` 保持 rename 探测方式（检测文件锁语义正确），加固 rename-back 失败时的恢复路径
- **C10** `expected_sha256` 缺失时拒绝 apply 或从 `_asset` 兜底回填

### 更新器错误处理（Important 级）
- **A6** NSIS 失败回滚路径：新增 `EXIT_RESTORE_FAILED` 退出码、`Popen` 启动旧版加异常捕获、`_restore_backup` 按异常类型分类处理
- **A8** 下载续传校验 `Content-Range` 起始偏移，不匹配时截断重下
- **A9** 下载错误分类改为布尔 flag 而非字符串匹配，`unlink` 加保护
- **A11** 并发屏障增加 `verifying` 状态判断
- **A13** `OpenProcess` 失败后读 `GetLastError` 区分权限不足 vs 进程退出

## Capabilities

### New Capabilities
- `sandbox-hardening`: 沙箱安全加固——拦截 df.eval/query 危险表达式、限制 pd.read_* 路径、移除 type 内建
- `api-auth-middleware`: API 鉴权中间件——统一写操作鉴权、文件路径 TOCTOU 防御
- `updater-security-v3`: 更新器安全 v3——TOCTOU 闭合、Origin null 收紧、探测恢复加固、sha256 兜底、回滚路径加固、续传校验、下载错误分类

### Modified Capabilities
- `sandbox-import-approval`: 增加 `df.eval`/`df.query` 参数扫描与 `pd.read_*` 路径拦截规则
- `tool-guardrails`: 增加沙箱内建函数限制策略（`type` 移除）
- `websocket-protocol`: 无行为变更（仅后端鉴权，不影响 WebSocket 事件协议）

## Impact

- **沙箱**：`src/nini/sandbox/executor.py`、`src/nini/sandbox/policy.py`；影响所有通过 `run_code` / `code_session` 执行的用户代码
- **API**：`src/nini/api/routes.py`、`src/nini/api/auth_utils.py`；影响所有 HTTP 端点的鉴权行为
- **更新器**：`src/nini/update/` 全部、`src/nini/updater_main.py`、`src/nini/api/origin_guard.py`；影响应用内更新流程
- **测试**：`tests/test_sandbox_*.py`、`tests/test_update_*.py`、`tests/test_api_auth*.py`（新增）
- **非目标**：不重构 routes.py 为多个文件（属独立重构任务）、不替换 PowerShell 验签为 WinTrust API（属后续优化）、不合并前端 Store 碎片（属独立重构任务）
