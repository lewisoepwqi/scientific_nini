# Capability: workflow-topology-ui

## Purpose

提供前端 `WorkflowTopology` React 组件，使用纯 CSS flexbox 可视化多 Agent 并行执行拓扑，实时反映各子 Agent 的运行状态；同时扩展 `MessageBubble` 组件，在子 Agent 消息上显示来源标签。

## Requirements

### Requirement: WorkflowTopology 组件
系统 SHALL 提供 `WorkflowTopology` React 组件，使用纯 CSS flexbox 实现（不引入图形库）；组件 SHALL 仅在 `activeAgents` 或 `completedAgents` 中有 ≥2 个 Agent 时渲染；0 或 1 个 Agent 时组件 SHALL 返回 `null`。

#### Scenario: 无或单个 Agent 时不渲染
- **WHEN** `activeAgents` 总数 + `completedAgents` 总数 < 2
- **THEN** 组件 SHALL 返回 `null`，不渲染任何 DOM

#### Scenario: 并行 Agent 时展示拓扑
- **WHEN** 存在 ≥2 个 Agent（运行中或已完成）
- **THEN** 组件 SHALL 展示所有 Agent 节点

---

### Requirement: WorkflowTopology 节点状态样式
每个 Agent 节点 SHALL 根据状态显示对应颜色：`running`→蓝色、`completed`→绿色、`error`→红色、`waiting`→灰色；节点 SHALL 显示 `agent_name` 和状态文字。

#### Scenario: 运行中节点样式
- **WHEN** Agent 状态为 `running`
- **THEN** 节点背景 SHALL 为蓝色系（如 `bg-blue-100 border-blue-400`）
- **AND** 节点 SHALL 显示 agent_name

#### Scenario: 完成节点样式
- **WHEN** Agent 状态为 `completed`
- **THEN** 节点背景 SHALL 为绿色系（如 `bg-green-100 border-green-400`）

#### Scenario: 错误节点样式
- **WHEN** Agent 状态为 `error`
- **THEN** 节点背景 SHALL 为红色系（如 `bg-red-100 border-red-400`）

---

### Requirement: WorkflowTopology 实时状态更新
组件 SHALL 订阅 Zustand store 的 `activeAgents` 和 `completedAgents`；每当 `agent_start`、`agent_complete`、`agent_error` 事件到达时，组件 SHALL 自动重渲染反映最新状态（无需手动刷新）。

#### Scenario: agent_start 后节点出现
- **WHEN** `agent_start` 事件推送到 store
- **THEN** 对应节点 SHALL 以 `running` 状态出现在拓扑图中

#### Scenario: agent_complete 后节点变绿
- **WHEN** `agent_complete` 事件推送到 store
- **THEN** 对应节点 SHALL 从 `activeAgents` 移入 `completedAgents`
- **AND** 节点颜色 SHALL 变为绿色

---

### Requirement: MessageBubble 子 Agent 来源标签
`MessageBubble` 组件 SHALL 在渲染来自子 Agent 的消息时，在消息气泡上方显示来源标签 `[{agent_name}]`；标签来源为事件 payload 中的 `agent_id`，通过 `completedAgents` 列表查找对应 `agentName`；普通主 Agent 消息 SHALL 不显示来源标签。

#### Scenario: 子 Agent 消息显示来源标签
- **WHEN** 消息 event payload 包含 `agent_id`
- **AND** `completedAgents` 中存在对应记录
- **THEN** 消息顶部 SHALL 显示 `[{agentName}]` 标签
- **AND** 标签样式 SHALL 与普通消息区分（如浅色 badge）

#### Scenario: 普通消息不显示来源标签
- **WHEN** 消息 event payload 不包含 `agent_id`
- **THEN** 消息顶部 SHALL 不显示任何来源标签
