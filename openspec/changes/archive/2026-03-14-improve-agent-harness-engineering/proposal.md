## Why

当前 Nini 已具备 ReAct 主循环、计划事件流、工具重试和部分可观测性基础，但仍缺少系统化的 harness 层来约束 Agent 在运行中的完成条件、恢复策略和失败归因。这导致多步科研分析中仍会出现“未验证就结束”“重复尝试同一路径”“结果与原始任务脱节”等稳定性问题，而维护期优化也缺乏可回放、可比较的本地评测闭环。

## What Changes

- 新增运行时 harness 能力，在 `AgentRunner` 外围统一处理运行上下文注入、完成前校验、坏循环恢复和阶段化推理预算。
- 新增本地 trace 与 harness 评测能力，记录一次运行的关键轨迹并支持回放、失败归因与聚合分析。
- 扩展 WebSocket 事件协议，增加运行上下文、完成校验和阻塞状态相关事件，支持前端呈现验证与恢复过程。
- 扩展可解释性展示，将 completion check、loop recovery、blocked 状态纳入现有推理/任务可视化，而不是仅展示最终文本与工具结果。

## Capabilities

### New Capabilities
- `agent-harness-runtime`: 定义 Agent 运行时 harness 层，包括确定性上下文装配、完成前校验、坏循环检测与恢复、按阶段分配 reasoning 策略。
- `agent-harness-evaluation`: 定义本地 trace 记录、回放评测、失败归因与维护者侧 harness 分析接口。

### Modified Capabilities
- `websocket-protocol`: 扩展事件契约，支持 `run_context`、`completion_check`、`blocked` 等 harness 相关事件及其元数据。
- `explainability-enhancement`: 扩展用户可见的运行过程展示，使验证结果、恢复提示和阻塞原因成为可追踪、可理解的界面状态。

## Impact

- 受影响代码主要包括 Agent 运行编排、WebSocket 事件发送与前端 store/面板展示。
- 将新增本地 trace 存储与维护者侧 CLI/分析入口，但不依赖外部 tracing 平台。
- 将引入新的运行时与协议约束，影响前后端事件契约、测试回放样例和回归测试覆盖范围。
