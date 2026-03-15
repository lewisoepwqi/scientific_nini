## ADDED Requirements

### Requirement: Orchestrator 钩子拦截 dispatch_agents 调用
`AgentRunner` 在 tool_calls 解析完成后、逐一执行工具之前 SHALL 检测是否有 `dispatch_agents` 工具调用；若有，SHALL 调用私有方法 `_handle_dispatch_agents()` 处理多 Agent 派发流程，将融合结果以 `tool_result` 消息注入 session，然后 `continue` 进入下一 ReAct 迭代；其他工具调用 SHALL 走原有执行路径，不受影响。

#### Scenario: dispatch_agents 调用被 Orchestrator 拦截
- **WHEN** LLM 在 tool_calls 中包含 `dispatch_agents` 调用
- **THEN** runner SHALL 不进入 `for tc in tool_calls:` 的通用执行循环
- **AND** 多 Agent 派发结果 SHALL 作为 tool_result 注入 session
- **AND** 主循环 SHALL 继续（LLM 收到结果后再次决策）

#### Scenario: 无 dispatch_agents 时原有逻辑不变
- **WHEN** tool_calls 中不包含 `dispatch_agents`
- **THEN** runner SHALL 正常执行 `for tc in tool_calls:` 循环
- **AND** 所有现有工具 SHALL 按原有逻辑执行

---

### Requirement: Orchestrator 不向子 Agent 暴露 dispatch_agents 工具
`AgentRunner` 在构建 tool_definitions 时 SHALL 检测 `session` 是否为 `SubSession` 实例；若为 `SubSession`，则从工具列表中排除 `dispatch_agents`（防止子 Agent 递归派发）。

#### Scenario: 主 Agent 可调用 dispatch_agents
- **WHEN** `session` 不是 `SubSession` 实例
- **AND** `dispatch_agents` 已注册到 ToolRegistry
- **THEN** 工具定义列表 SHALL 包含 `dispatch_agents`

#### Scenario: 子 Agent 不暴露 dispatch_agents
- **WHEN** `session` 是 `SubSession` 实例
- **THEN** 工具定义列表 SHALL 不包含 `dispatch_agents`

---

### Requirement: _handle_dispatch_agents 产生事件流
`_handle_dispatch_agents()` SHALL 通过 `yield` 产生以下事件序列：
1. 每个子 Agent 启动时 `agent_start` 事件（由 SubAgentSpawner 推送，通过 event_callback）
2. 每个子 Agent 完成时 `agent_complete` 或 `agent_error` 事件
3. 最终 `tool_result` 类型的 `AgentEvent`，包含融合结果

#### Scenario: dispatch_agents 事件链完整
- **WHEN** `dispatch_agents` 调用包含 2 个任务
- **THEN** 应收到 2 个 `agent_start` 事件
- **AND** 收到 2 个 `agent_complete` 或 `agent_error` 事件
- **AND** 最终收到 1 个包含 tool_result 内容的事件
