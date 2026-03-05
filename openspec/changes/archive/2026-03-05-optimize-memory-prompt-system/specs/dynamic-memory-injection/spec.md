## ADDED Requirements

### Requirement: 系统提示词构建前执行长期记忆检索
每次 Agent 构建系统提示词时，系统 SHALL 以当前用户消息为 query 检索最相关的长期记忆，并将检索结果注入 memory.md 组件内容。

#### Scenario: 有相关长期记忆时动态填充 memory.md
- **WHEN** AgentRunner 构建新一轮 LLM 上下文，且 LongTermMemoryStore 中存在记忆条目
- **THEN** 系统 SHALL 以当前用户消息作为检索 query，调用 `search_long_term_memories(query, top_k=3, context=...)`
- **AND** 检索结果 SHALL 经 `format_memories_for_context()` 格式化为可读 Markdown 文本
- **AND** 格式化后的文本 SHALL 作为 memory.md 组件的内容，覆盖静态默认文本

#### Scenario: 无相关记忆或检索结果为空时回退默认文本
- **WHEN** 长期记忆检索返回空列表，或 LongTermMemoryStore 尚未初始化
- **THEN** 系统 SHALL 回退到 memory.md 组件的原始默认文本（"长期记忆：当前会话未提供额外长期记忆。"）
- **AND** 主流程 SHALL NOT 因此抛出异常或中断

#### Scenario: 检索异常时静默回退
- **WHEN** `search_long_term_memories()` 抛出任意异常
- **THEN** 系统 SHALL 捕获该异常并记录日志
- **AND** 系统 SHALL 回退到静态默认文本，不中断 Agent 主循环

#### Scenario: 情境参数传递给检索调用
- **WHEN** 当前 session 有已加载的数据集
- **THEN** 检索调用 SHALL 携带 `context={"dataset": current_dataset_name}` 参数
- **AND** `search()` 的情境加权逻辑 SHALL 优先返回与当前数据集相关的历史记忆

### Requirement: 记忆检索结果通过 component_overrides 参数注入，不写磁盘
系统 SHALL 通过 `PromptBuilder` 的运行时参数注入动态记忆内容，不修改磁盘上的 memory.md 文件。

#### Scenario: component_overrides 参数覆盖默认文本
- **WHEN** `PromptBuilder` 被调用时传入 `component_overrides={"memory.md": <动态内容>}`
- **THEN** `PromptBuilder` SHALL 使用 overrides 中的内容替代 `_DEFAULT_COMPONENTS["memory.md"]` 的静态文本
- **AND** 磁盘上的 memory.md 文件（若存在）内容 SHALL 不被修改

#### Scenario: 磁盘文件优先于 overrides
- **WHEN** 磁盘上存在自定义 memory.md 组件文件，同时传入了 component_overrides
- **THEN** 系统 SHALL 优先使用磁盘文件内容
- **AND** component_overrides 仅在组件文件缺失（使用默认值）时生效
