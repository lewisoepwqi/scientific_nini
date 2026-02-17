## MODIFIED Requirements

### Requirement: 可观测的流式对话事件
系统 SHALL 提供可观测的流式对话事件契约，至少包括 `iteration_start`、`text`、`tool_call`、`tool_result`、`retrieval`、`plan_progress`、`done`、`error`，并为同一轮对话提供稳定的 `turn_id` 关联。

#### Scenario: 多段响应可被正确分段
- **WHEN** Agent 在一次用户请求中发生“文本输出 → 工具调用 → 再次文本输出”
- **THEN** 服务端输出的事件序列必须包含多次 `iteration_start/text` 与对应 `tool_call/tool_result`
- **AND** 前端可基于 `turn_id` 正确归并为同一轮对话

#### Scenario: 工具调用结果可追踪
- **WHEN** Agent 发起工具调用并收到结果
- **THEN** `tool_result` 事件必须携带与 `tool_call` 一致的 `tool_call_id`
- **AND** 会话持久化中保留工具调用与结果的关联记录

#### Scenario: 计划进度事件可驱动顶部任务列表
- **WHEN** 分析流程进入新步骤、更新步骤状态或出现阻塞/失败
- **THEN** 服务端输出 `plan_progress` 事件
- **AND** 事件至少包含 `current_step_index`、`total_steps`、`step_title`、`step_status`
- **AND** 在存在下一步提示时附带 `next_hint`
