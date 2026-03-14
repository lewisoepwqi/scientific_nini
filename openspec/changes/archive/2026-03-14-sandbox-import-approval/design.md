## Context

当前 Python 沙盒有两层导入限制：
- `src/nini/sandbox/policy.py` 在 AST 静态校验阶段按固定白名单拒绝非允许导入；
- `src/nini/sandbox/executor.py` 在运行期通过 `_safe_import()` 再次按固定白名单拦截。

这种“双重静态白名单”保证了默认安全，但也使 `run_code` 无法在用户明确同意的前提下临时使用低风险扩展包。与此同时，仓库已经具备三项可以复用的基础设施：
- `ask_user_question`：可发起结构化审批并等待前端回答；
- `SessionManager`：可持久化会话级状态；
- `AgentRunner`：可在工具执行失败后做受控重试。

这次变更是典型的跨模块安全改动，涉及沙盒策略、执行器、工具结果契约、Agent 事件流与会话持久化，因此需要在实现前先明确边界与决策。

## Goals / Non-Goals

**Goals:**
- 为 `run_code` 增加“低风险扩展包导入需审批”的受控分支。
- 保证 AST 校验与运行期导入校验使用同一份动态允许集合，避免审批后仍被执行器拒绝。
- 复用现有 `ask_user_question` 事件流，提供一次性、会话级、永久级三种授权范围。
- 让审批决定具备可追踪、可持久化、可回滚的最小闭环。
- 保持默认拒绝策略不变，高风险导入仍然直接拦截。

**Non-Goals:**
- 不为 `run_r_code` 增加审批能力。
- 不支持 `pip install` 自动安装或动态拉取依赖。
- 不放宽网络、系统、动态执行类模块的硬拒绝策略。
- 不引入专门的前端审批 UI；继续使用现有 `ask_user_question` 组件。
- 不把任意未知包都纳入审批范围；仅首批 reviewable 清单内的包可申请放行。

## Decisions

### 决策 1：采用“三层导入分级”，而不是“白名单外全部可审批”

设计：
- `ALLOWED_IMPORT_ROOTS`：继续自动允许。
- `REVIEWABLE_IMPORT_ROOTS`：低风险扩展包，未授权时抛 `SandboxReviewRequired`。
- `HARD_DENY_IMPORT_ROOTS`：网络、系统、动态执行类模块，继续抛 `SandboxPolicyError`。

原因：
- 这能保持默认安全边界，同时避免把高风险能力错误暴露给用户确认流程。
- 审批疲劳可控，用户只会在少数明确可审查的扩展包上看到确认。

备选方案：
- 方案 A：所有白名单外导入都进入审批。
  - 放弃原因：风险面过大，且与当前沙盒不是 OS 级隔离的现实不匹配。
- 方案 B：继续全部硬拒绝。
  - 放弃原因：无法解决低风险科研扩展包的可用性问题。

### 决策 2：新增 `SandboxReviewRequired`，通过工具结果契约回传审批需求

设计：
- `policy.py` 新增 `SandboxReviewRequired(packages=[...])`。
- `code_runtime.py` 捕获该异常，返回 `SkillResult(success=False, data={"_sandbox_review_required": True, "sandbox_violations": [...]})`。
- `runner.py` 在 `result = await self._execute_tool(...)` 之后、`has_error` 判断之前拦截该标记并发起审批。

原因：
- 这样可以复用当前工具调用与 WebSocket 事件流，不需要新增独立控制通道。
- 将审批需求显式编码到工具结果中，比依赖错误文案解析更稳定。

备选方案：
- 方案 A：让执行器直接抛异常到 runner。
  - 放弃原因：会绕过现有 `SkillResult` 契约，增加跨层耦合。
- 方案 B：让前端从错误文本中猜测是否需要审批。
  - 放弃原因：不稳定，也不利于测试和协议演进。

### 决策 3：执行器按“本次请求”动态构造 safe import / builtins

设计：
- `SandboxExecutor.execute()`、`_execute_sync()`、`_sandbox_worker()` 增加 `extra_allowed_imports` 参数。
- 每次执行动态生成：
  - `allowed_import_roots`
  - `_make_safe_import(...)`
  - `_make_safe_builtins(...)`
  - `_build_exec_globals(..., extra_allowed_imports=...)`
- `validate_code()` 与运行期 `_safe_import()` 共用同一份允许集合。

原因：
- 当前 `SAFE_BUILTINS` 是模块级静态对象，无法表达“当前这次执行允许额外导入哪些包”。
- 若只改静态校验、不改运行期导入，将出现审批通过后仍然 ImportError 的失配。

备选方案：
- 方案 A：只在 AST 校验层放行。
  - 放弃原因：运行期仍会被 `_safe_import()` 拦截。
- 方案 B：把额外允许集合写入全局变量。
  - 放弃原因：并发执行下容易串会话，且难于测试。

### 决策 4：授权状态分为一次性、会话级、永久级三层

设计：
- `allow_once`：只用于当前工具调用的立即重试，不写入会话状态。
- `allow_session`：写入 `session.sandbox_approved_imports`，并通过 `SessionManager` 持久化到会话元数据。
- `always_allow`：在会话级基础上额外写入 `sandbox/approval_manager.py` 管理的全局持久化文件。

原因：
- 一次性授权适合低频试探，避免用户被迫做持久决策。
- 会话级授权符合当前 `tool_approval_grants` 的使用习惯。
- 永久授权满足高频科研扩展包的长期复用场景。

备选方案：
- 方案 A：只有“一次性”和“永久”两种。
  - 放弃原因：缺少最常用的会话级折中选项。
- 方案 B：所有授权都写入全局。
  - 放弃原因：不符合最小权限原则，也增加误授权的持久影响。

### 决策 5：会话与永久审批的加载统一放在 `SessionManager`

设计：
- `Session` 只保留 `sandbox_approved_imports` 运行时字段。
- `SessionManager.create_session()` 负责：
  - 加载会话元数据中的 `sandbox_approved_imports`
  - 读取永久审批集合
  - 合并后传入 `Session(...)`
- 新增 `save_session_sandbox_import_approvals()` 等辅助方法。

原因：
- 当前 `chart_output_preference`、`tool_approval_grants` 已采用同样模式。
- 避免在 `Session.__post_init__()` 中引入额外 I/O 和跨模块依赖。

备选方案：
- 方案 A：在 `Session.__post_init__()` 直接读取永久审批文件。
  - 放弃原因：破坏 dataclass 轻量性，也让测试注入更困难。

### 决策 6：审批交互复用现有 `ask_user_question`，但答案解析按文本归一

设计：
- runner 新增沙盒审批专用辅助函数：
  - `_build_sandbox_import_approval_payload(...)`
  - `_request_sandbox_import_approval(...)`
  - `_resolve_sandbox_import_approval_choice(...)`
- 审批问题聚合为单题，选项固定为：
  - `仅本次允许`
  - `本会话允许`
  - `始终允许`
  - `拒绝`
- 解析答案时不依赖额外 question id，而是沿用当前文本归一方式。

原因：
- 现有 `ask_user_question` 标准化结构并不保留稳定 id。
- 复用现有交互路径可以最小化前端与协议变更。

备选方案：
- 方案 A：扩展 `ask_user_question` 协议，引入稳定 question id。
  - 放弃原因：这会扩大本次改动范围，可在后续迭代单独推进。

## Risks / Trade-offs

- [风险：reviewable 清单过宽，误把高风险模块纳入审批] → 仅允许预定义低风险包进入 reviewable 集合，并在 `approval_manager` 写入时再次校验。
- [风险：AST 放行但运行期仍拦截] → 强制 `validate_code()` 与 `_safe_import()` 共用同一份 `allowed_import_roots` 构造逻辑。
- [风险：审批重试形成死循环] → 每次工具调用最多触发一次审批重试；重试后仍返回审批需求则直接失败。
- [风险：永久授权文件损坏或读写失败] → 记录日志并 fail-secure，回退为未授权状态。
- [风险：审批文案与前端答案解析不一致] → 使用固定中文选项文本，并补充 WebSocket 事件流回归测试。
- [风险：`torch` 等大包获批后引发性能波动] → 风险说明中明确提示初始化耗时与内存占用，且本期不保证包已安装。

## Migration Plan

1. 先落地 `policy.py` 与 `executor.py` 的导入分级和动态允许集合。
2. 再扩展 `code_runtime.py`，让 `run_code` 能返回结构化审批需求。
3. 接入 `session.py`、`approval_manager.py` 与 `runner.py`，完成审批、持久化与重试。
4. 补齐单元测试与 WebSocket 事件流测试。
5. 以默认关闭高风险能力、默认拒绝 reviewable 未授权导入的方式上线，无需数据迁移。

回滚策略：
- 如审批链路出现异常，可回退到旧行为：移除 `SandboxReviewRequired` 分支，恢复全部非白名单导入直接拦截。
- 永久审批文件即使保留，也不会在旧逻辑中生效，不影响回滚安全性。

## Open Questions

- `torch` 是否应纳入首批 reviewable 清单，还是等完成性能评估后再开放？
- 永久授权是否需要在后续提供撤销入口，还是先仅保留手工清理文件能力？
- 是否需要把 reviewable 包清单迁移到配置文件，而不是先硬编码在 `policy.py` 中？
