## MODIFIED Requirements

### Requirement: SubAgentSpawner 派生单个子 Agent
`SubAgentSpawner.spawn(agent_id, task, session, ...)` SHALL：
1. 从 `AgentRegistry` 获取 `AgentDefinition`；若 `agent_id` 不存在 SHALL 返回 `SubAgentResult(success=False)`
2. 创建 `SubSession`，其中 `datasets` SHALL 为父会话 `datasets` 的浅拷贝（`dict(parent_session.datasets)`），`artifacts` 和 `documents` SHALL 为独立空字典
3. 调用 `ToolRegistry.create_subset(agent_def.allowed_tools)` 构造受限工具集
4. 实例化 `AgentRunner`，传入受限工具集和 `SubSession`，执行 ReAct 循环
5. 超时（`asyncio.wait_for`）时返回 `SubAgentResult(success=False, summary="执行超时")`

#### Scenario: datasets 浅拷贝隔离
- **WHEN** 子 Agent 向 `session.datasets` 写入新键
- **THEN** 父会话的 `datasets` SHALL 不包含该新键
- **AND** 子 Agent 对已有键对应的 DataFrame 内容的修改不受本要求约束（浅拷贝不覆盖对象内部修改）

#### Scenario: 成功派生并执行子 Agent
- **WHEN** 调用 `spawner.spawn("data_cleaner", "清洗数据集", session)`
- **THEN** 系统 SHALL 创建独立的 `SubSession`，其 `datasets` 为父会话的浅拷贝
- **AND** 返回 `SubAgentResult(success=True)` 且包含 `summary` 字段

---

### Requirement: SubAgentSpawner 批量执行产物回写
`spawn_batch()` 在所有子任务完成后，将子 Agent 产物回写到父会话时 SHALL 使用命名空间键格式 `{agent_id}.{original_key}`（点分隔）。若多个子 Agent 产出相同原始键，各自以命名空间键写入，互不覆盖；系统 SHALL 记录一条 WARNING 日志说明冲突。

#### Scenario: 多 Agent 产出同名产物时使用命名空间隔离
- **WHEN** Agent A 产出 `artifacts["result"]`，Agent B 也产出 `artifacts["result"]`
- **THEN** 父会话 `session.artifacts` SHALL 包含 `"agent_a.result"` 和 `"agent_b.result"` 两个键
- **AND** 两者的值均被完整保留，无一被覆盖
- **AND** 系统 SHALL 记录一条 WARNING 日志

#### Scenario: 单 Agent 产物写入不引起命名空间冲突
- **WHEN** 只有一个子 Agent 产出 `artifacts["chart"]`
- **THEN** 父会话 SHALL 包含 `"{agent_id}.chart"` 键
- **AND** SHALL 不记录 WARNING 日志

---

### Requirement: SubAgentSpawner 停止信号字典预创建
`Session` 初始化时 SHALL 预创建 `subagent_stop_events: dict` 和 `sub_agent_snapshots: list`，避免并发派发时的 TOCTOU 竞态。

#### Scenario: 多个子 Agent 并行注册停止事件
- **WHEN** `spawn_batch()` 并行派发 3 个子 Agent
- **THEN** 每个子 Agent SHALL 成功将自己的 `child_stop_event` 注册到 `session.subagent_stop_events`
- **AND** 三个事件 SHALL 同时存在，互不覆盖
