# Capability: sub-agent-spawner

## Purpose

提供 `SubAgentSpawner`，负责派生、调度和管理子 Agent 的执行，支持单次派生、指数退避重试和批量并行执行，并将子 Agent 产物回写到父会话。

## Requirements

### Requirement: ToolRegistry 支持构造受限子集
`ToolRegistry` SHALL 提供 `create_subset(allowed_tool_names: list[str]) -> ToolRegistry` 方法，返回一个新的 `ToolRegistry` 实例，仅包含 `allowed_tool_names` 中指定的工具；不存在的工具名 SHALL 被跳过并记录 WARNING 日志，不抛出异常。

#### Scenario: 正常构造受限工具集
- **WHEN** 调用 `registry.create_subset(["stat_test", "task_write"])`
- **THEN** 返回的新 `ToolRegistry` SHALL 仅包含 `stat_test` 和 `task_write` 两个工具
- **AND** 原 `registry` 中的其他工具 SHALL 不在子集中

#### Scenario: 不存在工具名被跳过
- **WHEN** 调用 `registry.create_subset(["stat_test", "nonexistent_tool"])`
- **THEN** 返回的子集 SHALL 仅包含 `stat_test`
- **AND** 系统 SHALL 记录一条包含 `"nonexistent_tool"` 的 WARNING 日志

---

### Requirement: SubAgentSpawner 派生单个子 Agent
`SubAgentSpawner.spawn(agent_id, task, session, timeout_seconds)` SHALL：
1. 从 `AgentRegistry` 获取 `AgentDefinition`；若 `agent_id` 不存在 SHALL 返回 `SubAgentResult(success=False)`
2. 创建 `SubSession`，绑定父会话的 `datasets`、`documents`、`event_callback`
3. 调用 `ToolRegistry.create_subset(agent_def.allowed_tools)` 构造受限工具集
4. 实例化 `AgentRunner`，传入受限工具集和 `SubSession`，执行 ReAct 循环
5. 超时（`asyncio.wait_for`）时返回 `SubAgentResult(success=False, summary="执行超时")`

#### Scenario: 成功派生并执行子 Agent
- **WHEN** 调用 `spawner.spawn("data_cleaner", "清洗数据集", session)`
- **THEN** 系统 SHALL 创建独立的 `SubSession`
- **AND** 返回 `SubAgentResult(success=True)` 且包含 `summary` 字段

#### Scenario: 未知 agent_id 返回失败结果
- **WHEN** 调用 `spawner.spawn("unknown_agent", "任务", session)`
- **THEN** 返回 `SubAgentResult(success=False)`
- **AND** SHALL 不抛出异常

#### Scenario: 超时返回失败结果
- **WHEN** 子 Agent 执行时间超过 `timeout_seconds`
- **THEN** 返回 `SubAgentResult(success=False, summary="执行超时")`
- **AND** SHALL 不阻塞调用方

---

### Requirement: SubAgentSpawner 支持指数退避重试
`SubAgentSpawner.spawn_with_retry(agent_id, task, session, max_retries=3)` SHALL 在子 Agent 执行失败时以指数退避（1s、2s、4s）重试，达到 `max_retries` 次后返回最终失败的 `SubAgentResult`。

#### Scenario: 失败后触发重试
- **WHEN** 子 Agent 首次执行返回 `success=False`
- **THEN** 系统 SHALL 至多再重试 `max_retries - 1` 次
- **AND** 重试间隔 SHALL 按指数递增（2^attempt 秒）

#### Scenario: 首次成功不重试
- **WHEN** 子 Agent 首次执行返回 `success=True`
- **THEN** 系统 SHALL 立即返回结果，不进行任何重试

---

### Requirement: SubAgentSpawner 支持批量并行执行
`SubAgentSpawner.spawn_batch(tasks: list[tuple[str, str]], session, max_concurrency=4)` SHALL 通过 `asyncio.Semaphore(max_concurrency)` 控制并发，并行执行所有任务，返回与输入顺序对应的 `list[SubAgentResult]`；单个子 Agent 失败 SHALL 不影响其他子 Agent 的执行。

#### Scenario: 多个子 Agent 并行执行
- **WHEN** 调用 `spawner.spawn_batch([("data_cleaner", "清洗"), ("statistician", "分析"), ("viz_designer", "作图")], session)`
- **THEN** 三个子 Agent SHALL 并发执行（受 `max_concurrency` 限制）
- **AND** 返回列表长度 SHALL 等于输入任务数量
- **AND** 返回顺序 SHALL 与输入顺序一致

#### Scenario: 单个子 Agent 失败不中断批次
- **WHEN** 批次中某个子 Agent 执行失败
- **THEN** 其他子 Agent SHALL 继续执行
- **AND** 失败的子 Agent 对应位置 SHALL 返回 `SubAgentResult(success=False)`

#### Scenario: 空任务列表立即返回空列表
- **WHEN** 调用 `spawner.spawn_batch([], session)`
- **THEN** 返回值 SHALL 为空列表 `[]`
- **AND** SHALL 不抛出任何异常

---

### Requirement: 子 Agent 产物回写父会话
`SubAgentSpawner` 在所有子 Agent 执行完毕后 SHALL 串行将 `SubAgentResult.artifacts`、`SubAgentResult.documents` 回写到父会话的 `session.artifacts`、`session.documents`；回写 SHALL 在所有并发任务完成后执行，不在执行期间并发修改父会话。

#### Scenario: 产物回写到父会话
- **WHEN** 子 Agent 执行成功并在 `sub_session.artifacts` 中写入产物
- **THEN** `spawn()` 返回后，父会话 `session.artifacts` SHALL 包含该产物
- **AND** 父会话原有的 artifacts SHALL 不受影响
