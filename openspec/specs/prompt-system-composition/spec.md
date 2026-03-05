# prompt-system-composition Specification

## Purpose
TBD - created by archiving change refactor-prompt-architecture. Update Purpose after archive.
## Requirements
### Requirement: System prompt composition has one trusted assembly boundary
The system SHALL assemble runtime system prompts from trusted prompt components only and SHALL keep runtime context injection out of the system prompt layer. Runtime overrides provided through the component_overrides parameter are considered part of the trusted assembly boundary and SHALL be applied before budget protection.

#### Scenario: System prompt contains only trusted prompt components
- **WHEN** the Agent builds messages for an LLM call
- **THEN** the system prompt SHALL be produced by the prompt component builder
- **AND** dataset metadata, retrieved knowledge, AGENTS.md content, and completed analysis memories SHALL NOT be appended directly to the system prompt
- **AND** long-term memory summaries and user profile summaries SHALL be injected exclusively via the component_overrides mechanism into memory.md and user.md components respectively

#### Scenario: Prompt components support runtime refresh without service restart
- **WHEN** a prompt component file is updated on disk
- **THEN** subsequent system prompt builds SHALL reflect the updated component content
- **AND** the runtime SHALL NOT require a process restart to load the change

### Requirement: Prompt component budget protection preserves core directives
The system SHALL enforce per-component and total prompt budgets while preserving core system directives.

#### Scenario: Budget protection truncates lower-priority components first
- **WHEN** the assembled system prompt exceeds the configured total budget
- **THEN** lower-priority components SHALL be truncated or dropped before higher-priority components
- **AND** identity, strategy, and security directives SHALL remain present in the final system prompt

#### Scenario: Component truncation is explicit
- **WHEN** a prompt component exceeds its configured per-component budget
- **THEN** the resulting prompt text SHALL include an explicit truncation marker
- **AND** the truncated output SHALL remain syntactically readable to the model

### Requirement: PromptBuilder 支持运行时组件内容覆盖
PromptBuilder SHALL 接受运行时传入的组件内容覆盖参数（component_overrides），以支持动态记忆和用户画像注入，同时保持磁盘文件配置的最高优先级。

#### Scenario: component_overrides 覆盖默认占位符文本
- **WHEN** `PromptBuilder` 被实例化或 `build()` 被调用时传入 `component_overrides={"memory.md": <动态内容>, "user.md": <画像内容>}`
- **AND** 对应的磁盘组件文件不存在
- **THEN** `PromptBuilder` SHALL 使用 overrides 中的字符串替代 `_DEFAULT_COMPONENTS` 中的静态默认文本
- **AND** 最终系统提示词 SHALL 包含动态注入的记忆和画像内容

#### Scenario: 磁盘组件文件存在时 overrides 不生效
- **WHEN** `component_overrides` 中包含 "memory.md" 键
- **AND** 磁盘上存在对应的 memory.md 组件文件（operator 手动配置）
- **THEN** `PromptBuilder` SHALL 使用磁盘文件内容，忽略 overrides 中的同名键
- **AND** 磁盘文件配置的优先级 SHALL 高于运行时 overrides

#### Scenario: overrides 不写入磁盘
- **WHEN** `PromptBuilder` 接收 component_overrides 并完成 `build()`
- **THEN** 磁盘上的任何组件文件 SHALL NOT 被创建或修改
- **AND** overrides 的生命周期 SHALL 仅限于本次 `build()` 调用

#### Scenario: overrides 中未指定的组件使用原有逻辑
- **WHEN** `component_overrides` 仅包含部分组件键（如仅 "memory.md"）
- **THEN** 其他组件（如 "user.md", "strategy.md"）SHALL 继续使用磁盘文件或默认文本的原有逻辑
- **AND** `build()` 行为 SHALL 与不传 overrides 时完全一致（除被覆盖的组件外）

