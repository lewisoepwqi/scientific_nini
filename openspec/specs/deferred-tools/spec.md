## ADDED Requirements

### Requirement: search_tools 工具按名称精确获取工具 schema
系统 SHALL 提供 `search_tools` 工具，当查询字符串以 `select:` 开头时，按逗号分隔的名称列表精确返回对应工具的完整 JSON Schema。若某工具名称不存在，SHALL 在结果中标注"未找到"，不报错。

#### Scenario: select 精确获取单个工具 schema
- **WHEN** LLM 调用 `search_tools(query="select:t_test")`
- **THEN** 返回 `t_test` 工具的完整 JSON Schema（name、description、parameters）
- **THEN** 返回结果中包含足以直接调用该工具的参数信息

#### Scenario: select 获取多个工具 schema
- **WHEN** LLM 调用 `search_tools(query="select:t_test,anova")`
- **THEN** 返回 `t_test` 和 `anova` 两个工具的完整 schema

#### Scenario: select 查询不存在的工具名
- **WHEN** LLM 调用 `search_tools(query="select:nonexistent_tool")`
- **THEN** 返回成功结果，结果中包含说明 `nonexistent_tool` 未找到的提示，不返回 success=False

### Requirement: search_tools 工具按关键词搜索工具
当查询字符串不以 `select:` 开头时，系统 SHALL 对所有已注册工具（包括 `expose_to_llm=False` 的工具）的名称和 description 做子字符串匹配（大小写不敏感），返回最多 5 个匹配结果的工具名称、description 和完整 schema。

#### Scenario: 关键词搜索返回匹配工具
- **WHEN** LLM 调用 `search_tools(query="t检验")`
- **THEN** 返回包含 `t_test` 在内的匹配工具列表，每条包含工具名、描述和参数 schema

#### Scenario: 无匹配结果时返回空列表
- **WHEN** LLM 调用 `search_tools(query="不存在的工具描述xyz")`
- **THEN** 返回成功结果，tools 字段为空数组，message 说明未找到匹配工具

#### Scenario: 搜索结果最多返回 5 个
- **WHEN** 查询关键词匹配到超过 5 个工具
- **THEN** 只返回前 5 个匹配结果

### Requirement: search_tools 自身暴露给 LLM
`search_tools` 工具 SHALL 设置 `expose_to_llm = True`，出现在 LLM 的工具列表中，使 LLM 知道可以通过它发现其他工具。

#### Scenario: search_tools 出现在 LLM 工具列表中
- **WHEN** `ToolRegistry.get_tool_definitions()` 被调用
- **THEN** 返回结果包含 `search_tools` 工具的 schema

### Requirement: 低频工具标记为 expose_to_llm = False
以下工具 SHALL 将 `expose_to_llm` 属性改为返回 `False`：
`t_test`、`mann_whitney`、`anova`、`kruskal_wallis`、`correlation_analysis`、`regression_analysis`、`export_chart`、`export_document`、`export_report`、`analysis_memory`、`search_memory_archive`、`update_profile_notes`、`fetch_url`

#### Scenario: 低频工具不出现在默认 LLM 工具列表
- **WHEN** `ToolRegistry.get_tool_definitions()` 被调用
- **THEN** `t_test`、`mann_whitney` 等上述工具的 schema 不包含在返回结果中

#### Scenario: 低频工具可通过 search_tools 发现
- **WHEN** LLM 调用 `search_tools(query="select:t_test")`
- **THEN** 返回 `t_test` 的完整 schema，可直接用于调用

### Requirement: system prompt 包含 search_tools 使用说明
`agent/prompts/builder.py` 生成的 system prompt SHALL 包含关于 `search_tools` 的说明：当需要的工具不在当前工具列表中时，应调用 `search_tools` 按名称或关键词获取其 schema。

#### Scenario: system prompt 包含 search_tools 使用说明
- **WHEN** `builder.py` 构建系统提示文本
- **THEN** 输出文本中包含 `search_tools` 的使用引导说明
