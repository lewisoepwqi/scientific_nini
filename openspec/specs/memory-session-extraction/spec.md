# memory-session-extraction Specification

## Purpose
TBD - created by archiving change optimize-memory-prompt-system. Update Purpose after archive.
## Requirements
### Requirement: 会话结束时自动将高置信度 AnalysisMemory 提取到长期记忆
系统 SHALL 在 Agent 会话交互完成后，自动将本次会话中置信度达标的分析发现沉淀为跨会话可检索的长期记忆。

沉淀路径 SHALL 同时触发：通过 `MemoryManager.on_session_end(session.messages)` 写入 SQLite（新路径）和通过 `consolidate_session_memories(session_id)` 写入 JSONL（旧路径，P5 删除）。两条路径均以 `asyncio.create_task` 后台执行。

#### Scenario: 高置信度 Finding 被提取为长期记忆
- **WHEN** AgentRunner 检测到本轮对话结束（无 tool_calls 的纯文本响应）
- **AND** 当前 session 存在 AnalysisMemory 记录
- **THEN** 系统 SHALL 异步触发记忆沉淀
- **AND** AnalysisMemory 中 `confidence >= 0.7` 的 Finding SHALL 被写入持久化存储
- **AND** 写入时 SHALL 携带 `source_session_id`、数据集名称（如有）、`memory_type="finding"`

#### Scenario: 低置信度 Finding 不被提取
- **WHEN** 处理某 Finding 时其 `confidence < 0.7`
- **THEN** 该 Finding SHALL NOT 被写入任何长期记忆存储
- **AND** 不产生错误或警告日志

#### Scenario: 重复提取防护（幂等性）
- **WHEN** 同一 session_id 的记忆沉淀被触发多次
- **THEN** 系统 SHALL NOT 重复写入已沉淀的记忆条目
- **AND** 已有条目 SHALL 被跳过（`dedup_key` 约束）

#### Scenario: 提取异常不影响主流程
- **WHEN** 记忆沉淀过程中抛出异常
- **THEN** 异常 SHALL 被捕获并记录到 debug 日志
- **AND** AgentRunner 的主循环 SHALL NOT 因此中断或向客户端报错

### Requirement: 长期记忆存储支持来源追踪
持久化的记忆条目 SHALL 记录其来源会话和数据集信息，支持溯源与去重。

#### Scenario: 记忆条目包含来源元数据
- **WHEN** 新记忆被写入 `facts` 表
- **THEN** 该条目 SHALL 包含 `source_session_id`（非空字符串）
- **AND** 若来自数据集分析，`sci_metadata.dataset_name` SHALL 包含数据集名称
- **AND** 若来自特定分析方法，`sci_metadata.analysis_type` SHALL 包含分析类型

### Requirement: on_session_end 接受 session.messages 参数传入完整历史
系统 SHALL 在 `MemoryManager.on_session_end()` 调用中接受 `session.messages`（`list[dict]`）作为参数，不依赖 `session.get_messages()` 方法（该方法不存在）。

#### Scenario: 正确参数传入不抛出异常
- **WHEN** `MemoryManager.on_session_end(session.messages)` 被调用，`session.messages` 为 `list[dict]` 类型
- **THEN** 调用 SHALL 正常完成，不抛出 `AttributeError` 或 `TypeError`

#### Scenario: 空消息列表时安全降级
- **WHEN** `on_session_end([])` 被调用
- **THEN** 系统 SHALL 正常完成（无 AnalysisMemory 可提取）
- **AND** SHALL NOT 向 `facts` 表写入任何记录

