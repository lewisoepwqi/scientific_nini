# Capability: agent-registry

## Purpose

提供 `AgentDefinition` 数据类与 `AgentRegistry` 注册表，用于声明、加载和管理 Specialist Agent 的完整配置，支持内置 Agent 自动加载和用户自定义覆盖。

## Requirements

### Requirement: AgentDefinition 声明模型
系统 SHALL 提供 `AgentDefinition` 数据类，用于声明一个 Specialist Agent 的完整配置，字段包括：`agent_id`（唯一标识）、`name`（显示名称）、`description`（能力描述）、`system_prompt`（系统提示词）、`purpose`（用途路由键）、`allowed_tools`（工具白名单列表）、`max_tokens`（默认 8000）、`timeout_seconds`（默认 300）、`paradigm`（默认 `"react"`）。

#### Scenario: 创建有效的 AgentDefinition
- **WHEN** 以合法字段实例化 `AgentDefinition`
- **THEN** 实例 SHALL 可通过属性访问所有字段
- **AND** `paradigm` 未传入时 SHALL 默认为 `"react"`
- **AND** `max_tokens` 未传入时 SHALL 默认为 8000

#### Scenario: allowed_tools 为空列表时仍可创建
- **WHEN** `allowed_tools` 传入空列表
- **THEN** `AgentDefinition` SHALL 正常创建，不抛出异常

---

### Requirement: AgentRegistry 加载内置 Agent
系统 SHALL 在 `AgentRegistry` 初始化时自动加载 9 个内置 Specialist Agent：`literature_search`、`literature_reading`、`data_cleaner`、`statistician`、`viz_designer`、`writing_assistant`、`research_planner`、`citation_manager`、`review_assistant`。

#### Scenario: 初始化后可查询内置 Agent
- **WHEN** 实例化 `AgentRegistry`
- **THEN** `registry.get("data_cleaner")` SHALL 返回有效的 `AgentDefinition`
- **AND** `registry.list_agents()` SHALL 返回至少 9 个 Agent

#### Scenario: 查询不存在的 Agent 返回 None
- **WHEN** 调用 `registry.get("nonexistent_agent")`
- **THEN** SHALL 返回 `None`，不抛出异常

---

### Requirement: AgentRegistry 加载内置与自定义 Agent 配置
系统 SHALL 在初始化时分两步加载 Agent 配置：
1. 内置配置：扫描 `src/nini/agent/prompts/agents/builtin/*.yaml`（随包发布的默认配置）
2. 自定义配置：扫描 `src/nini/agent/prompts/agents/*.yaml`（用户自定义，不含 `builtin/` 子目录）

自定义 Agent 与内置 Agent 同名时，自定义配置 SHALL 覆盖内置配置。两个目录均不存在时，`AgentRegistry` SHALL 正常初始化（返回零 Agent），不抛出异常。

#### Scenario: 有效 YAML 文件被加载
- **WHEN** `src/nini/agent/prompts/agents/builtin/` 目录下存在合法 YAML 文件
- **THEN** `AgentRegistry` 初始化后 SHALL 可通过 `registry.get()` 查询该 Agent

#### Scenario: 配置目录不存在时不报错
- **WHEN** `src/nini/agent/prompts/agents/` 目录不存在
- **THEN** `AgentRegistry` SHALL 正常初始化，不抛出异常

---

### Requirement: AgentRegistry 校验 allowed_tools
`AgentRegistry` 在注册 Agent 时 SHALL 对 `allowed_tools` 中每个工具名进行校验；工具名不在 `ToolRegistry` 白名单内时 SHALL 记录 WARNING 日志，但仍完成注册（不阻断启动）。

#### Scenario: 无效工具名触发警告
- **WHEN** 注册一个 `allowed_tools` 含有不存在工具名（如 `"knowledge_search"`）的 Agent
- **THEN** 系统 SHALL 记录一条 WARNING 级别日志，包含工具名和 Agent ID
- **AND** 该 Agent SHALL 仍被注册到注册表中

#### Scenario: 全部工具名合法时无警告
- **WHEN** 注册一个 `allowed_tools` 全部为已注册工具名的 Agent
- **THEN** 系统 SHALL 不产生任何 WARNING 日志

---

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
