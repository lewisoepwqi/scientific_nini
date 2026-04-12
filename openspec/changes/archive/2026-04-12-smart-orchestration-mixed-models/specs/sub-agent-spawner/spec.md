## MODIFIED Requirements

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
