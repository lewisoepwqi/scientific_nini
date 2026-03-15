## ADDED Requirements

### Requirement: SubAgentSpawner 支持 Hypothesis-Driven 执行路径
`SubAgentSpawner.spawn()` SHALL 在 `agent_def.paradigm == "hypothesis_driven"` 时调用 `_spawn_hypothesis_driven()` 而非 `_spawn_react()`，实现范式路由。

#### Scenario: paradigm 为 react 时走 ReAct 路径
- **WHEN** `agent_def.paradigm == "react"`
- **THEN** `spawn()` SHALL 调用 `_spawn_react()` 执行路径

#### Scenario: paradigm 为 hypothesis_driven 时走假设推理路径
- **WHEN** `agent_def.paradigm == "hypothesis_driven"`
- **THEN** `spawn()` SHALL 调用 `_spawn_hypothesis_driven()` 执行路径
- **AND** 返回的 `SubAgentResult.detailed_output` SHALL 包含假设链内容

---

### Requirement: _spawn_hypothesis_driven 假设迭代循环
`_spawn_hypothesis_driven(agent_def, task, session, timeout_seconds)` SHALL：
1. 创建 `SubSession`，绑定父会话 `datasets`、`documents`、`event_callback`
2. 初始化 `HypothesisContext(max_iterations=3)` 并存入 `sub_session.artifacts["_hypothesis_context"]`
3. 执行迭代循环：每轮调用 `AgentRunner` 单次 ReAct 回合，根据返回内容更新 `HypothesisContext` 置信度和证据
4. 每轮迭代后推送相应的假设事件（`hypothesis_generated` / `evidence_collected` / `hypothesis_validated` / `hypothesis_refuted`）
5. 调用 `HypothesisContext.should_conclude()` 判断是否收敛，收敛后退出循环
6. 整体受 `asyncio.wait_for(timeout=timeout_seconds)` 约束

#### Scenario: 假设在首轮生成
- **WHEN** `_spawn_hypothesis_driven` 开始第一轮迭代
- **THEN** 系统 SHALL 通过 `session.event_callback` 推送至少一个 `hypothesis_generated` 事件

#### Scenario: 收集证据后更新置信度
- **WHEN** 一轮迭代结束且 LLM 返回支持或反驳证据
- **THEN** 对应假设的 `confidence` SHALL 被更新
- **AND** 系统 SHALL 推送 `evidence_collected` 事件

#### Scenario: 达到收敛后结束循环
- **WHEN** `HypothesisContext.should_conclude()` 返回 `True`
- **THEN** 循环 SHALL 终止，不继续发起新一轮 LLM 调用
- **AND** 返回 `SubAgentResult(success=True)`，`summary` 包含最终结论

#### Scenario: 假设循环整体超时
- **WHEN** 整个假设循环执行时间超过 `timeout_seconds`
- **THEN** 返回 `SubAgentResult(success=False, summary="执行超时")`
- **AND** SHALL 不阻塞调用方

---

### Requirement: Hypothesis-Driven 范式触发检测
系统 SHALL 通过 `AgentDefinition.paradigm` 静态字段决定执行路径，不在运行时做意图推断。`paradigm` 字段由 AgentRegistry YAML 配置决定，`literature_reading` 和 `research_planner` 的 `paradigm` SHALL 为 `"hypothesis_driven"`，其余 7 个内置 Agent SHALL 保持 `"react"`。

#### Scenario: literature_reading 使用假设驱动范式
- **WHEN** 调用 `spawner.spawn("literature_reading", task, session)`
- **THEN** `spawner` SHALL 走 `_spawn_hypothesis_driven()` 路径

#### Scenario: data_cleaner 仍使用 ReAct 范式
- **WHEN** 调用 `spawner.spawn("data_cleaner", task, session)`
- **THEN** `spawner` SHALL 走 `_spawn_react()` 路径
- **AND** SHALL 不创建 `HypothesisContext`
