## Why

当前会话运行时存在一类严重死循环：主任务已进入 `in_progress` 后，模型仍会把“当前任务内部的直接执行”错误地改写成 `dispatch_agents(task_id=当前任务)`，触发波次校验失败，并在恢复轮次中稳定重复，最终被 harness 以 `tool_loop` 阻断。这个问题暴露出任务状态机、并行派发契约、恢复策略和提示词约束之间存在系统性语义错位，已经影响分析任务的可完成性与运行可靠性，必须尽快做成一轮完整重构而不是局部补丁。

## What Changes

- 重构任务执行语义，明确区分“计划任务”“当前执行任务”和“子派发单元”，不再默认用同一个 `task_id` 同时承载三种不同语义。
- 为任务初始化增加依赖风险检测与高置信规范化，只对可判定的线性流水线自动补全依赖，其余场景保留原计划并返回结构化 warning，避免静默改写用户计划。
- 升级 `dispatch_agents` 契约，正式引入 `parent_task_id` 表示“当前任务内部子派发”，并为上下文不匹配返回结构化恢复建议，而不是仅返回通用拒绝错误。
- 重写 Orchestrator 与 harness 的恢复路径，由 runner 负责 turn 级调度护栏与路径切换，harness 负责恢复建议与阻塞判定，而不是继续重复同类工具调用直至熔断。
- 强化运行时上下文与提示词约束，显式注入“当前任务不可再次以 `task_id` 方式派发”“工具不是 agent_id”“失败后应回退到直接工具执行”等规则，并补充正反例。
- 统一 `pending_actions`、trace snapshot 和运行诊断中的调度上下文字段，提升此类问题的可观测性与回放分析能力。
- 补齐从单元测试、集成测试到真实 trace 回放的回归体系，覆盖本次死循环案例与相关恢复路径。

## Capabilities

### New Capabilities
- `task-dispatch-coordination`: 定义任务状态机、当前执行上下文、pending wave 与子派发之间的统一协调契约，包括依赖规范化、派发模式识别与结构化恢复建议。

### Modified Capabilities
- `dispatch-agents-tool`: 调整 `dispatch_agents` 的参数语义、上下文校验、错误模型与恢复提示，支持区分当前任务内部子派发与 pending wave 派发。
- `orchestrator-mode`: 修改 `AgentRunner` 对 `dispatch_agents` 的拦截与恢复行为，在误用场景下限制错误工具路径并切换到可执行路径。
- `agent-harness-runtime`: 调整坏循环识别、恢复策略、阻塞判定与 `pending_actions` 账本行为，使其能识别“调度语义错误”而不只是机械计数。

## Impact

- 受影响代码主要包括 `src/nini/agent/task_manager.py`、`src/nini/tools/task_write.py`、`src/nini/tools/dispatch_agents.py`、`src/nini/agent/runner.py`、`src/nini/harness/runner.py`、`src/nini/agent/prompts/builder.py`、`src/nini/agent/components/context_builder.py` 以及相关 trace / session 诊断写入逻辑。
- 受影响系统包括任务计划与状态推进、主 Agent 与 specialist agent 的协作路径、坏循环恢复器、运行时上下文构建、会话压缩摘要与可观测性事件。
- 对外 API 以兼容现有合法调用为前提：旧 `tasks=[{task_id,...}]` 与 `agents=[...]` 输入继续可用，新增字段以补充方式返回；仅对原本就不安全或语义错误的调用改为返回更严格的结构化错误。前端若消费新增诊断字段，需要同步验证显示行为。
- 验证范围至少覆盖 `tests/test_dispatch_agents.py`、任务状态机与 harness 相关测试，以及针对 `session_id=3be947d505b7` 的真实问题回放用例。
