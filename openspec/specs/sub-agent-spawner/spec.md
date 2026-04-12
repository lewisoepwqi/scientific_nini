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

---

### Requirement: SubAgentSpawner 根据 model_preference 选择子 Agent 模型
`SubAgentSpawner._execute_agent()` SHALL 在实例化子 Agent 的 `AgentRunner` 时，根据 `AgentDefinition.model_preference` 选择对应的模型（通过 `purpose` 参数传入 `ModelResolver`）：

| `model_preference` | 对应 `purpose` |
|--------------------|---------------|
| `"haiku"` | `"fast"` |
| `"sonnet"` | `"analysis"` |
| `"opus"` | `"deep_reasoning"` |
| `None` | `"analysis"`（与父 Agent 默认一致） |

子 Agent 的 model resolver SHALL 基于父 Agent 的 resolver 派生（保留 API key、base_url 等配置），仅 `purpose` 参数按 `model_preference` 覆盖。

#### Scenario: model_preference="haiku" 时子 Agent 使用快速模型
- **WHEN** `AgentDefinition.model_preference` 为 `"haiku"`
- **THEN** 子 Agent 的 `AgentRunner` SHALL 使用 `purpose="fast"` 对应的模型
- **AND** 父 Agent 的模型 SHALL 不受影响

#### Scenario: model_preference=None 时子 Agent 继承默认模型
- **WHEN** `AgentDefinition.model_preference` 为 `None`
- **THEN** 子 Agent SHALL 使用 `purpose="analysis"` 对应的模型（与父 Agent 默认一致）

---

### Requirement: SubAgentSpawner 支持范式路由
`SubAgentSpawner.spawn()` SHALL 在获取 `AgentDefinition` 后，根据 `agent_def.paradigm` 字段路由到对应的执行路径：
- `"react"`（默认）→ 现有 `_spawn_react()` 路径（行为不变）
- `"hypothesis_driven"` → 新增 `_spawn_hypothesis_driven()` 路径

范式路由 SHALL 在 `spawn()` 内部透明处理，调用方无需感知执行路径差异；`spawn_batch()` 和 `spawn_with_retry()` 中的 `spawn()` 调用 SHALL 自动继承范式路由行为。

#### Scenario: spawn 对 react Agent 保持原有行为
- **WHEN** 以 `paradigm == "react"` 的 Agent 调用 `spawn()`
- **THEN** 行为 SHALL 与 Phase 1/2 完全一致，不创建 `HypothesisContext`

#### Scenario: spawn 对 hypothesis_driven Agent 触发假设迭代
- **WHEN** 以 `paradigm == "hypothesis_driven"` 的 Agent 调用 `spawn()`
- **THEN** `sub_session.artifacts["_hypothesis_context"]` SHALL 在执行过程中被创建和更新

#### Scenario: spawn_batch 中混合范式 Agent 可并发执行
- **WHEN** `spawn_batch` 中同时包含 `react` 和 `hypothesis_driven` 类型的 Agent
- **THEN** 两类 Agent SHALL 并发执行，互不影响
- **AND** 各自返回正确的 `SubAgentResult`
