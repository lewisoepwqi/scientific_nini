# conversation Specification

## Purpose
TBD - created by archiving change add-conversation-observability-and-hybrid-skills. Update Purpose after archive.
## Requirements
### Requirement: 可观测的流式对话事件
系统 SHALL 提供可观测的流式对话事件契约，至少包括 `iteration_start`、`text`、`tool_call`、`tool_result`、`retrieval`、`done`、`error`，并为同一轮对话提供稳定的 `turn_id` 关联。

#### Scenario: 多段响应可被正确分段
- **WHEN** Agent 在一次用户请求中发生“文本输出 → 工具调用 → 再次文本输出”
- **THEN** 服务端输出的事件序列必须包含多次 `iteration_start/text` 与对应 `tool_call/tool_result`
- **AND** 前端可基于 `turn_id` 正确归并为同一轮对话

#### Scenario: 工具调用结果可追踪
- **WHEN** Agent 发起工具调用并收到结果
- **THEN** `tool_result` 事件必须携带与 `tool_call` 一致的 `tool_call_id`
- **AND** 会话持久化中保留工具调用与结果的关联记录

### Requirement: 检索结果可视化输出
系统 SHALL 在启用检索增强上下文时输出 `retrieval` 事件，向客户端提供可视化所需字段（查询、命中片段、来源、相关分数）。

#### Scenario: 检索模式下返回 retrieval 事件
- **WHEN** 当前请求命中记忆或知识检索
- **THEN** 服务端在模型主回复前或过程中输出 `retrieval` 事件
- **AND** 事件内容可被前端直接渲染为检索卡片

#### Scenario: 未命中检索时不输出冗余事件
- **WHEN** 当前请求未触发检索或检索结果为空
- **THEN** 服务端不输出空的 `retrieval` 事件

### Requirement: 会话压缩与归档
系统 SHALL 支持将长会话历史压缩为摘要上下文，并将被压缩的原始消息归档保存，以降低后续推理成本且保留审计能力。

#### Scenario: 手动压缩会话
- **WHEN** 用户调用会话压缩接口且会话消息量达到压缩阈值
- **THEN** 系统归档旧消息、生成摘要并写入压缩上下文
- **AND** 后续对话构建上下文时优先注入摘要而非完整旧消息

#### Scenario: 消息不足时拒绝压缩
- **WHEN** 用户调用会话压缩接口但会话消息量低于阈值
- **THEN** 系统返回可理解的失败原因
- **AND** 不修改现有会话数据

### Requirement: Prompt 组件化装配
系统 SHALL 采用组件化方式构建系统提示词，支持固定装配顺序、长度限制、截断标记与安全清洗策略。

#### Scenario: 组件更新在下一轮生效
- **WHEN** 任一 Prompt 组件文件在运行中被更新
- **THEN** 下一轮对话请求构建提示词时自动读取最新组件内容
- **AND** 无需重启服务

#### Scenario: 超长组件被截断并标识
- **WHEN** 组件内容超过单组件或总长度限制
- **THEN** 系统执行截断并附加可识别标记
- **AND** 不因超长内容导致请求失败

