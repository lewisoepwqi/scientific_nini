## MODIFIED Requirements

### Requirement: DispatchAgentsTool 工具接口
系统 SHALL 提供 `DispatchAgentsTool`，继承 `src/nini/tools/base.py:Tool`，名称为 `"dispatch_agents"`；参数：`agents: list[{agent_id: str, task: str}]`（必填，每项声明目标 agent_id 与任务描述）；`execute(session, agents, turn_id)` SHALL 校验所有 agent_id 合法性，调用 `SubAgentSpawner.spawn_batch` 并行执行，拼接各子 Agent 原始输出后返回 `ToolResult(message=拼接文本)`。返回文本格式：`[{agent_id}] {task}\n{summary}\n\n[{agent_id}] {task}\n{summary}`。

#### Scenario: dispatch_agents 并行执行多个子 Agent
- **WHEN** 以合法 `agents` 列表调用 `execute()`，包含 2 个或以上 agent
- **THEN** 所有子 Agent SHALL 并行启动，全部完成后返回
- **AND** 返回 `ToolResult.message` SHALL 包含每个子 Agent 的输出，以 agent_id 标签分隔
- **AND** `ToolResult.success` SHALL 为 `True`（至少一个子 Agent 成功时）

#### Scenario: agents 为空时返回空结果
- **WHEN** 调用 `execute(session, agents=[])`
- **THEN** SHALL 返回 `ToolResult(success=True, message="")` 且不抛出异常

#### Scenario: agent_id 非法时返回错误
- **WHEN** `agents` 中包含不存在于 AgentRegistry 的 agent_id
- **THEN** `ToolResult.success` SHALL 为 `False`
- **AND** `ToolResult.message` SHALL 包含非法 agent_id 名称及可用 agent_id 列表

#### Scenario: 部分子 Agent 执行失败
- **WHEN** 一个子 Agent 执行失败（返回 `SubAgentResult.success=False`）
- **THEN** 其余成功子 Agent 的结果 SHALL 仍包含在返回文本中
- **AND** 失败子 Agent 的错误信息 SHALL 以 `[{agent_id}] 执行失败: {error}` 格式包含在返回文本中
- **AND** `ToolResult.success` SHALL 为 `True`（至少一个成功时）

### Requirement: DispatchAgentsTool 注册到 ToolRegistry
`DispatchAgentsTool` SHALL 在 `create_default_tool_registry()` 中注册；工具名 `"dispatch_agents"` SHALL 不出现在任何子 Agent 的 `allowed_tools` 白名单中（通过 `ToolExposurePolicy` 的 `deny_names` 强制排除），防止递归派发。

#### Scenario: dispatch_agents 可通过 ToolRegistry 获取
- **WHEN** 调用 `registry.get("dispatch_agents")`
- **THEN** SHALL 返回 `DispatchAgentsTool` 实例

#### Scenario: 子 Agent 不可见 dispatch_agents
- **WHEN** 构建子 Agent 的受限工具注册表
- **THEN** `dispatch_agents` SHALL 不出现在子 Agent 可调用工具列表中

### Requirement: 子 Agent 并发上限
`spawn_batch` SHALL 使用 `asyncio.Semaphore` 限制并发子 Agent 数量；默认上限 SHALL 为 4，可通过 settings 配置。

#### Scenario: 并发数超过上限时排队等待
- **WHEN** `agents` 列表包含 6 个子 Agent，并发上限为 4
- **THEN** 前 4 个子 Agent SHALL 立即启动，后 2 个 SHALL 等待前序完成后再启动
- **AND** 最终所有子 Agent 的结果 SHALL 全部包含在返回文本中
