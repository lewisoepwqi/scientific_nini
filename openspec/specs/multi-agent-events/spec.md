# Capability: multi-agent-events

## Purpose

定义多 Agent 协作过程中的事件类型、payload 结构及前端状态管理，实现子 Agent 生命周期的可观测性。

## Requirements

### Requirement: EventType 枚举包含多 Agent 事件类型
`src/nini/agent/events.py` 的 `EventType(str, Enum)` SHALL 新增以下枚举值，遵循 `UPPER_SNAKE = "lower_snake"` 命名规范：
- `AGENT_START = "agent_start"`
- `AGENT_PROGRESS = "agent_progress"`（Phase 1 仅声明枚举值，payload 结构与触发时机在 Phase 2 规划）
- `AGENT_COMPLETE = "agent_complete"`
- `AGENT_ERROR = "agent_error"`
- `WORKFLOW_STATUS = "workflow_status"`（Phase 1 仅声明枚举值，payload 结构与触发时机在 Phase 2 规划）

#### Scenario: 新事件类型可通过枚举访问
- **WHEN** 代码引用 `EventType.AGENT_START`
- **THEN** 其值 SHALL 等于字符串 `"agent_start"`

#### Scenario: 新增枚举值不影响现有事件
- **WHEN** 系统接收到现有事件类型（如 `text`、`tool_call`）
- **THEN** 现有事件处理逻辑 SHALL 不受新增枚举值影响

---

### Requirement: agent_start 事件 payload 结构
系统 SHALL 在子 Agent 开始执行时推送 `agent_start` 事件，payload 中 SHALL 包含字段：`event_type`（值为 `"agent_start"`）、`agent_id`（Agent 类型 ID）、`agent_name`（Agent 显示名称）、`task`（分配给该 Agent 的任务描述）。

#### Scenario: 子 Agent 启动时推送 agent_start
- **WHEN** `SubAgentSpawner.spawn()` 开始执行某个子 Agent
- **THEN** 父会话的 `event_callback` SHALL 被调用一次，传入包含 `agent_id` 和 `task` 的 `agent_start` 事件

---

### Requirement: agent_complete 事件 payload 结构
系统 SHALL 在子 Agent 成功完成时推送 `agent_complete` 事件，payload 中 SHALL 包含字段：`event_type`（值为 `"agent_complete"`）、`agent_id`、`agent_name`、`summary`（子 Agent 的执行结果摘要）、`execution_time_ms`（执行耗时毫秒数）。

#### Scenario: 子 Agent 成功完成时推送 agent_complete
- **WHEN** 子 Agent 执行成功并返回 `SubAgentResult(success=True)`
- **THEN** 父会话的 `event_callback` SHALL 被调用，传入包含 `summary` 的 `agent_complete` 事件

---

### Requirement: agent_error 事件 payload 结构
系统 SHALL 在子 Agent 执行失败（包括超时、重试耗尽）时推送 `agent_error` 事件，payload 中 SHALL 包含字段：`event_type`（值为 `"agent_error"`）、`agent_id`、`agent_name`、`error`（失败原因描述）。

#### Scenario: 子 Agent 失败时推送 agent_error
- **WHEN** 子 Agent 返回 `SubAgentResult(success=False)`
- **THEN** 父会话的 `event_callback` SHALL 被调用，传入包含 `error` 的 `agent_error` 事件

#### Scenario: 超时时推送 agent_error
- **WHEN** 子 Agent 执行超时
- **THEN** `agent_error` 事件的 `error` 字段 SHALL 包含 `"超时"` 相关描述

---

### Requirement: 前端 AgentSlice 维护子 Agent 运行状态
前端 Zustand store SHALL 包含 `AgentSlice`，维护 `activeAgents`（当前运行中的 Agent 映射，键为 `agent_id`）和 `completedAgents`（已完成 Agent 列表）。

#### Scenario: 接收 agent_start 事件后更新 activeAgents
- **WHEN** WebSocket 接收到 `agent_start` 事件
- **THEN** `activeAgents` SHALL 新增对应 `agent_id` 的条目，`status` 为 `"running"`

#### Scenario: 接收 agent_complete 后从 activeAgents 移出
- **WHEN** WebSocket 接收到 `agent_complete` 事件
- **THEN** 对应 `agent_id` SHALL 从 `activeAgents` 中移除
- **AND** SHALL 被追加到 `completedAgents` 列表，`status` 为 `"completed"`

#### Scenario: 接收 agent_error 后标记失败状态
- **WHEN** WebSocket 接收到 `agent_error` 事件
- **THEN** 对应 `agent_id` SHALL 从 `activeAgents` 中移除
- **AND** SHALL 被追加到 `completedAgents` 列表，`status` 为 `"error"`

---

### Requirement: AgentExecutionPanel 展示并行 Agent 状态
前端 SHALL 提供 `AgentExecutionPanel` 组件，在有 `activeAgents` 时展示每个运行中 Agent 的名称、任务描述、状态指示器和已运行时长；`completedAgents` 中的条目 SHALL 展示执行结果摘要。

#### Scenario: 有运行中 Agent 时面板可见
- **WHEN** `activeAgents` 不为空
- **THEN** `AgentExecutionPanel` SHALL 在界面上显示，列出所有运行中 Agent

#### Scenario: 所有 Agent 完成后面板显示结果
- **WHEN** `activeAgents` 变为空且 `completedAgents` 不为空
- **THEN** 面板 SHALL 展示所有已完成 Agent 的摘要信息
