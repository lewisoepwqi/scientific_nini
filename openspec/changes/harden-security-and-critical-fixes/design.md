## Context

Nini 是本地优先的科研 AI Agent，用户通过前端提交消息，后端 Agent 在沙箱中执行 LLM 生成的 Python/R 代码。当前沙箱使用进程隔离（spawn）+ AST 白名单 + 受限 builtins，但审查发现 `df.eval()`、`pd.read_csv()`、`type()` 可绕过限制。

HTTP API 层运行在 FastAPI 上，WebSocket 有鉴权但大量 HTTP 写端点无鉴权检查。更新器模块（最近 5 次提交 ~5500 行）在 TOCTOU 防御、Origin 校验、回滚路径、状态原子性等方面存在缺口。

当前版本尚未公开发布，安全修复的兼容性风险较低。

## Goals / Non-Goals

**Goals:**
- 修复所有 12 个 Critical 问题，使沙箱不可从用户代码逃逸
- 修复 5 个高优先 Important 问题（更新器错误处理、并发）
- 为所有修复补充对应的回归测试
- 保持现有 API 接口不变（不引入破坏性变更）

**Non-Goals:**
- 不重构 `routes.py` 为多文件（独立重构任务）
- 不替换 PowerShell 验签为 WinTrust API（后续优化）
- 不合并前端 Store 碎片（独立重构任务）
- 不引入新的外部依赖
- 不重构状态文件格式（保持 state.json + state.json.sig 双文件，仅升级日志级别）

## Decisions

### D1. 沙箱 df.eval/query 拦截策略

**选择**：在 `_sandbox_worker` 的 `exec_globals` 中 monkey-patch `pd.DataFrame.eval` 和 `pd.DataFrame.query`，拦截包含 `__import__`/`exec`/`compile`/`open`/`os.` 的表达式，抛出 `SandboxPolicyError`。

**替代方案**：在 AST 层拦截 —— 拒绝。Pandas eval 使用自解析器而非 Python AST，AST 检查看不到实际执行的字符串内容。

**替代方案**：完全禁止 `df.eval`/`df.query` —— 过于严格，破坏合法用法（如 `df.query('age > 30')`）。

### D2. 沙箱 pd.read_* 路径限制

**选择**：在 `_sandbox_worker` 中 hook `pd.read_csv`/`pd.read_excel`/`pd.read_json`/`pd.read_pickle` 等，将相对路径解析为 `working_dir` 下、拒绝绝对路径和 `..` 遍历。

**替代方案**：hook `builtins.open` —— 拒绝。当前沙箱已移除 `open`，加回来增加攻击面。

### D3. `type` 内建处理

**选择**：从 `_BASE_SAFE_BUILTINS` 移除 `type`，替换为仅支持单参数形式的 `safe_type(obj)` → `type(obj)`。沙箱用户代码仍可 `isinstance(x, int)` 但不能 `type(name, bases, dict)`。

**前提**：AST 层已有 `__dunder__` 属性访问拦截（`policy.py:355-365`），只放行 `__name__`/`__doc__`/`__len__`，因此 `obj.__class__.__subclasses__()` 属性链逃逸路径已被阻断。`safe_type` 封堵的是 `type(lambda:0)(code,{},{})` 这条不依赖属性链的直接调用路径。

### D4. API 鉴权实现方式

**选择**：创建 FastAPI 依赖项 `require_auth`，对写操作路由添加 `Depends(require_auth)`。读操作保持开放（前端面板需要无鉴权读取数据集列表等）。

**威胁模型说明**：本鉴权防御的是浏览器跨域 CSRF 攻击（恶意网页诱导浏览器向 localhost 发 POST），而非本地恶意进程。本地恶意进程可直接获取 HMAC Cookie。真正的跨域防御层是 `origin_guard.py` 的 Origin 校验。

**替代方案**：全局中间件 —— 拒绝。影响 WebSocket 和静态文件服务。

### D5. 更新器 TOCTOU 修复

**选择**：移除 `_backup_install_dir` 之后的 `time.sleep(1.5)`（`updater_main.py:367`），在备份完成后立即启动 NSIS。

**说明**：该 sleep 在执行流中的位置是：二次校验 → 备份 → **sleep** → NSIS。sleep 在备份之后、NSIS 之前，不在二次校验之后。移除原因：备份是同步文件系统操作，无需额外等待。

### D6. `_probe_install_dir_unlocked` 恢复加固

**选择**：保持 rename 探测方式。rename 检测的是"目录内有文件被进程锁定"（Windows 文件锁语义），这与目的一致。加固 rename-back 失败时的恢复路径：确保探测文件在任何情况下都被恢复原位。

**替代方案**：改为创建 `.nini_lockprobe` 文件 —— 拒绝。创建新文件检测的是"目录可写"，不是"目录内文件被锁定"，两者语义不同，会漏检进程持有 DLL 锁但目录仍可写的场景。

### D7. HMAC 日志级别升级

**选择**：将 `UpdateStateStore.load` 中签名不匹配的日志从 `logger.warning` 升级为 `logger.error`，在返回的空状态中设置 `error` 字段，并清理 `installer_path` 指向的孤立文件。保持 state.json + state.json.sig 双文件格式不变。

**说明**：HMAC 密钥是路径派生的（`state.py:29`），不具备防定向篡改能力。签名不匹配更可能是文件损坏或路径变更，升级日志级别是为了提高可观测性，不代表检测到真实篡改。

**替代方案**：合并为单文件 + 内嵌 HMAC —— 过度设计。当前双文件两次 `os.replace` 在同一文件系统上已是原子操作，无竞态窗口。

## Risks / Trade-offs

- **[df.eval 拦截可能误杀合法表达式]** → 使用黑名单关键词而非白名单，仅拦截已知危险模式；对误杀场景返回含替代建议的错误消息。
- **[pd.read_* hook 可能影响性能]** → hook 仅做路径校验（纳秒级），不增加 I/O。
- **[API 鉴权可能破坏现有前端]** → 仅对写操作添加鉴权，前端已有 Cookie 鉴权通道（`apiFetch` 自带 credentials），不破坏现有流程。
- **[移除 `type` 可能破坏用户代码中 `type(x)` 用法]** → 替换为 `safe_type`，`type(x)` 仍可用但 `type(name, bases, dict)` 被拦截。
