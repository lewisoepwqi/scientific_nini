## MODIFIED Requirements

### Requirement: AgentDefinition 数据结构
`AgentDefinition` SHALL 包含字段：`agent_id: str`、`name: str`、`description: str`、`system_prompt: str`、`allowed_tools: list[str]`、`max_turns: int`，以及新增字段 `model_preference: str | None`（可选，默认 `None`）。

`model_preference` 的合法值 SHALL 为 `"haiku"`、`"sonnet"`、`"opus"` 或 `None`。`None` 表示继承父 Agent 的模型选择。

YAML Agent 定义文件中 `model_preference` 字段为可选——缺失时等同于 `None`，现有 YAML 无需修改。

#### Scenario: YAML 中无 model_preference 字段时默认 None
- **WHEN** 加载不含 `model_preference` 字段的 Agent YAML 文件
- **THEN** `AgentDefinition.model_preference` SHALL 为 `None`
- **AND** 系统 SHALL 不抛出异常、不记录 WARNING

#### Scenario: YAML 中 model_preference 合法值被正确解析
- **WHEN** YAML 文件包含 `model_preference: haiku`
- **THEN** `AgentDefinition.model_preference` SHALL 为字符串 `"haiku"`

#### Scenario: YAML 中 model_preference 非法值时降级
- **WHEN** YAML 文件包含非法值（如 `model_preference: gpt4`）
- **THEN** 系统 SHALL 记录 WARNING 并将 `model_preference` 设为 `None`
- **AND** SHALL 不抛出异常
