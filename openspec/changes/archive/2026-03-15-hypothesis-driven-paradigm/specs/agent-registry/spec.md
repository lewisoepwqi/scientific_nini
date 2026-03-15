## ADDED Requirements

### Requirement: 内置 Agent 支持 hypothesis_driven 范式声明
`AgentRegistry` 中的内置 Agent YAML 配置 SHALL 允许 `paradigm` 字段取值 `"hypothesis_driven"`（Phase 3 新增取值）。`AgentDefinition` 的 `paradigm` 字段 SHALL 支持 `"react"` 和 `"hypothesis_driven"` 两个有效值；传入其他值 SHALL 记录 WARNING 但仍完成创建。

#### Scenario: hypothesis_driven 为合法 paradigm 值
- **WHEN** 以 `paradigm="hypothesis_driven"` 实例化 `AgentDefinition`
- **THEN** 实例 SHALL 正常创建，`paradigm` 属性值 SHALL 为 `"hypothesis_driven"`

#### Scenario: 未知 paradigm 值触发警告
- **WHEN** 以 `paradigm="unknown_paradigm"` 实例化 `AgentDefinition`
- **THEN** 系统 SHALL 记录一条 WARNING 日志
- **AND** 实例 SHALL 仍被创建，不抛出异常

---

### Requirement: literature_reading 和 research_planner 使用 hypothesis_driven 范式
`src/nini/agent/prompts/agents/builtin/literature_reading.yaml` 和 `research_planner.yaml` 的 `paradigm` 字段 SHALL 更新为 `"hypothesis_driven"`；其余 7 个内置 Agent SHALL 保持 `paradigm: react`。

#### Scenario: literature_reading 的 paradigm 为 hypothesis_driven
- **WHEN** 调用 `registry.get("literature_reading")`
- **THEN** 返回的 `AgentDefinition.paradigm` SHALL 为 `"hypothesis_driven"`

#### Scenario: research_planner 的 paradigm 为 hypothesis_driven
- **WHEN** 调用 `registry.get("research_planner")`
- **THEN** 返回的 `AgentDefinition.paradigm` SHALL 为 `"hypothesis_driven"`

#### Scenario: data_cleaner 等其他内置 Agent 仍为 react
- **WHEN** 调用 `registry.get("data_cleaner")`
- **THEN** 返回的 `AgentDefinition.paradigm` SHALL 为 `"react"`
