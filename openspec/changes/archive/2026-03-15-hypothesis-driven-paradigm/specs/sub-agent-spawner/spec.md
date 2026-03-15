## ADDED Requirements

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
