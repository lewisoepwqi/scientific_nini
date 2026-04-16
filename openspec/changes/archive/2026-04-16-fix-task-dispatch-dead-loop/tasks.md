## 1. 任务语义与状态建模
- [x] 1.1 在 `src/nini/agent/task_manager.py` 中引入显式 dispatch context 读取接口，区分 `current_in_progress_task`、`current_pending_wave` 与允许的派发模式。
- [x] 1.2 在保留现有 `pending wave` 计算语义的前提下，为调度路径新增 dispatch context 适配层，避免把当前 `in_progress` 任务错误视为可再次派发的 `pending` 任务。
- [x] 1.3 在 `src/nini/tools/task_write.py` 的初始化路径增加任务依赖风险检测与高置信规范化，仅对内建白名单或可枚举模板覆盖的线性分析流水线自动补全 `depends_on`，其余场景返回结构化 warning / normalization 元数据。
- [x] 1.4 为任务状态与调度上下文补充测试覆盖，验证 `pending`、`in_progress`、自动依赖补全和 wave 计算结果符合新契约。

## 2. dispatch_agents 工具契约重构
- [x] 2.1 在 `src/nini/tools/dispatch_agents.py` 中增加两类调度入口语义：基于 `task_id` 的 `pending wave` 派发，以及基于正式参数 `parent_task_id` 的当前任务内部子派发。
- [x] 2.2 将当前仅返回通用拒绝的校验分支升级为结构化错误合同，至少覆盖 `INVALID_AGENT_IDS`、`DISPATCH_CONTEXT_MISMATCH`、`TASK_NOT_IN_CURRENT_WAVE`、`PARALLEL_TASK_CONFLICT` 等错误码，并附带推荐恢复动作与工具建议。
- [x] 2.3 增加调度诊断字段输出，包括 `dispatch_mode`、`current_in_progress_task_id`、`current_pending_wave_task_ids`、`recovery_action` 与 `tool_misuse_category`。
- [x] 2.4 保持对现有调用方的兼容性，补充参数校验与回归测试，确保旧调用在合法场景下仍可工作；对仅传 `agents=[...]` 且存在歧义任务上下文的场景返回迁移提示而不是隐式绑定。

## 3. Orchestrator 与 Harness 恢复机制升级
- [x] 3.1 在 `src/nini/agent/runner.py` 中接入新的调度错误语义，并由 runner 作为唯一 owner 维护 turn-scoped guard，对 `dispatch_agents` 误用建立显式拦截与恢复路由。
- [x] 3.2 在 `src/nini/harness/runner.py` 中实现基于 `error_code` 的恢复策略表，产出恢复建议、推荐工具与阻塞依据，并通过结构化结果驱动 runner 收紧错误路径。
- [x] 3.3 改造 pending actions 与恢复记录，区分“仍阻塞当前轮次的失败”和“已被重规划吸收的历史失败”，避免旧失败在压缩与恢复轮次中持续污染上下文。
- [x] 3.4 为 harness / runner 增加集成测试，验证连续命中调度错误后系统会切换到直接执行路径，而不是进入 `tool_loop`。

## 4. 提示词与运行时上下文修正
- [x] 4.1 在 `src/nini/agent/prompts/builder.py` 中提升调度约束优先级，明确区分“工具”和“agent”，并加入当前任务内部执行与子派发的正反例。
- [x] 4.2 在 `src/nini/agent/components/context_builder.py` 中注入结构化运行时约束，显式告诉模型当前 `in_progress` 任务、当前 `pending wave`、允许的派发方式以及推荐的直接执行工具。
- [x] 4.3 统一 trace、session snapshot、pending actions 与运行时摘要中的调度诊断字段，确保后续定位无需跨多处日志拼装状态。

## 5. 回归测试与真实案例验证
- [x] 5.1 为 `TaskManager`、`task_write` 与 `dispatch_agents` 补充单元测试，覆盖依赖规范化、dispatch context、结构化错误和合法子派发。
- [x] 5.2 为 runner / harness 增加端到端集成测试，覆盖 `INVALID_AGENT_IDS` 与 `TASK_NOT_IN_CURRENT_WAVE` 连续出现时的恢复路径。
- [x] 5.3 基于会话 `3be947d505b7` 增加真实 trace 回放或等价 fixture 测试，验证系统不再走入 dispatch dead loop，并能推进任务1完成。
- [x] 5.4 运行并记录最小回归验证，至少包括 `pytest -q`；如实现波及前端协议或 UI 展示，再补充 `cd web && npm run build` 验证。
