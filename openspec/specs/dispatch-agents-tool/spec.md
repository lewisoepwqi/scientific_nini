# Capability: dispatch-agents-tool

## Purpose

提供 `DispatchAgentsTool`（工具名 `dispatch_agents`），作为主 Agent 发起多 Agent 并行派发的入口。工具同时支持 `pending wave` 派发和当前任务内部子派发，并向恢复器与调试视图返回统一的调度诊断信息。

## Requirements

### Requirement: DispatchAgentsTool 工具接口
系统 SHALL 提供 `DispatchAgentsTool`，继承 `src/nini/tools/base.py:Tool`，名称为 `"dispatch_agents"`；工具 SHALL 支持两类调度形态：

- pending wave 派发：`tasks: list[{task_id, agent_id, task, input_refs?, output_refs?}]`
- 当前任务内部子派发：`tasks: list[{parent_task_id, agent_id, task, input_refs?, output_refs?}]`

兼容输入 `agents: list[{agent_id, task}]` 仍可保留，但当会话存在任务上下文时，系统 SHALL 优先将结构化 `tasks` 视为正式 contract。`execute(session, agents, tasks, wave_id, turn_id)` SHALL 先校验 agent 合法性、任务上下文、并行冲突和派发模式，再调用 `SubAgentSpawner.spawn_batch` 并返回结构化 `ToolResult`。

#### Scenario: 兼容输入在合法场景下继续工作
- **WHEN** 调用方继续使用历史 `tasks=[{task_id, agent_id, task}]` 或 `agents=[{agent_id, task}]` 形态
- **AND** 当前会话上下文允许该调用执行
- **THEN** 系统 SHALL 保持既有合法行为可用
- **AND** 新增调度字段 SHALL 以补充方式返回，而不得移除已有成功结果语义

#### Scenario: 仅有 `agents=[...]` 且任务上下文存在歧义时返回迁移提示
- **WHEN** 调用方仅传入 `agents=[{agent_id, task}]`
- **AND** 当前会话存在会影响派发语义的任务板上下文，例如 `in_progress` 任务或可执行 `pending wave`
- **THEN** 系统 SHALL 返回结构化兼容性错误或迁移提示
- **AND** SHALL 明确要求调用方改用结构化 `tasks` 形态
- **AND** SHALL NOT 将该调用隐式绑定到当前任务或当前 wave

#### Scenario: pending wave 中的任务可被正常派发
- **WHEN** 调用 `execute()` 时传入合法的 `tasks=[{task_id, agent_id, task}]`
- **AND** 所有 `task_id` 都属于当前可执行 `pending wave`
- **THEN** 系统 SHALL 并行启动对应子 Agent
- **AND** 返回结果 SHALL 包含成功与失败子任务的结构化汇总

#### Scenario: 当前进行中任务使用父任务上下文发起内部子派发
- **WHEN** 会话存在 `in_progress` 任务
- **AND** 调用 `execute()` 时传入 `tasks=[{parent_task_id, agent_id, task}]`
- **AND** `parent_task_id` 等于当前进行中任务
- **THEN** 系统 SHALL 将该请求视为当前任务内部子派发
- **AND** SHALL NOT 因该任务不在 `pending wave` 而拒绝执行

#### Scenario: 误把当前进行中任务作为 pending wave 项派发时返回结构化错误
- **WHEN** 会话存在 `in_progress` 任务 1
- **AND** 调用 `execute()` 时传入 `tasks=[{task_id: 1, agent_id, task}]`
- **THEN** `ToolResult.success` SHALL 为 `False`
- **AND** 返回数据 SHALL 包含明确的错误码、当前 `in_progress` 任务 ID、当前 `pending wave` 任务列表和建议的恢复动作
- **AND** 返回结果 SHALL 明确指出该任务应在主 Agent 内直接执行或改用父任务上下文派发

#### Scenario: 非法 agent_id 返回结构化恢复信息
- **WHEN** `tasks` 或 `agents` 中包含不存在于 AgentRegistry 的 `agent_id`
- **THEN** `ToolResult.success` SHALL 为 `False`
- **AND** 返回数据 SHALL 包含非法 agent 列表、可用 agent 列表和恢复建议
- **AND** 不得继续执行其余派发项

---

### Requirement: DispatchAgentsTool 注册到 ToolRegistry
`DispatchAgentsTool` SHALL 在 `create_default_tool_registry()` 中注册；工具名 `"dispatch_agents"` SHALL 不出现在任何子 Agent 的 `allowed_tools` 白名单中（通过 `ToolExposurePolicy` 的 `deny_names` 强制排除），防止递归派发。

#### Scenario: dispatch_agents 可通过 ToolRegistry 获取
- **WHEN** 调用 `registry.get("dispatch_agents")`
- **THEN** SHALL 返回 `DispatchAgentsTool` 实例

#### Scenario: 子 Agent 不可见 dispatch_agents
- **WHEN** 构建子 Agent 的受限工具注册表
- **THEN** `dispatch_agents` SHALL 不出现在子 Agent 可调用工具列表中

---

### Requirement: 子 Agent 并发上限
`spawn_batch` SHALL 使用 `asyncio.Semaphore` 限制并发子 Agent 数量；默认上限 SHALL 为 4，可通过 settings 配置。

#### Scenario: 并发数超过上限时排队等待
- **WHEN** `agents` 列表包含 6 个子 Agent，并发上限为 4
- **THEN** 前 4 个子 Agent SHALL 立即启动，后 2 个 SHALL 等待前序完成后再启动
- **AND** 最终所有子 Agent 的结果 SHALL 全部包含在返回文本中

---

### Requirement: DispatchAgentsTool 必须返回调度诊断元数据
`dispatch_agents` 在成功或失败时 SHALL 返回统一的调度诊断元数据，以支持 harness 恢复器、runtime snapshot 和前端调试视图。

#### Scenario: 上下文不匹配错误返回诊断元数据
- **WHEN** `dispatch_agents` 因调度上下文不匹配而失败
- **THEN** 返回结果 SHALL 包含 `dispatch_mode`
- **AND** SHALL 包含 `current_in_progress_task_id`
- **AND** SHALL 包含 `current_pending_wave_task_ids`
- **AND** SHALL 包含 `recovery_action`

#### Scenario: 派发成功时返回模式与父任务信息
- **WHEN** `dispatch_agents` 成功执行
- **THEN** 返回结果 SHALL 指明实际使用的调度模式
- **AND** 若属于当前任务内部子派发，返回结果 SHALL 包含父任务标识
