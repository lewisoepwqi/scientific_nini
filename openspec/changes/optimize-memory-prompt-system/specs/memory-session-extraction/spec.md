## ADDED Requirements

### Requirement: 会话结束时自动将高置信度 AnalysisMemory 提取到长期记忆
系统 SHALL 在 Agent 会话交互完成后，自动将本次会话中置信度达标的分析发现沉淀为跨会话可检索的长期记忆。

#### Scenario: 高置信度 Finding 被提取为长期记忆
- **WHEN** AgentRunner 检测到本轮对话结束（无 tool_calls 的纯文本响应）
- **AND** 当前 session 存在 AnalysisMemory 记录
- **THEN** 系统 SHALL 异步触发 `consolidate_session_memories(session_id)`
- **AND** AnalysisMemory 中 `confidence >= 0.7` 的 Finding SHALL 被写入 LongTermMemoryStore
- **AND** 写入时 SHALL 携带 `source_session_id`、`source_dataset`、`importance_score`（等于 confidence 值）、`memory_type="finding"`

#### Scenario: 低置信度 Finding 不被提取
- **WHEN** `consolidate_session_memories()` 处理某 Finding 时，其 `confidence < 0.7`
- **THEN** 该 Finding SHALL NOT 被写入长期记忆存储
- **AND** 不产生错误或警告日志

#### Scenario: 重复提取防护（幂等性）
- **WHEN** 同一 session_id 的 `consolidate_session_memories()` 被多次调用
- **THEN** 系统 SHALL NOT 重复写入已沉淀的记忆条目
- **AND** 已有条目 SHALL 被跳过（基于内容哈希或 source_session_id 去重）

#### Scenario: 提取异常不影响主流程
- **WHEN** `consolidate_session_memories()` 执行过程中抛出异常
- **THEN** 异常 SHALL 被捕获并记录到日志
- **AND** AgentRunner 的主循环 SHALL NOT 因此中断或向客户端报错

### Requirement: 长期记忆存储支持来源追踪
LongTermMemoryEntry SHALL 记录其来源会话和数据集信息，以支持未来的溯源与去重。

#### Scenario: 记忆条目包含来源元数据
- **WHEN** 新记忆通过 `add_memory()` 写入 LongTermMemoryStore
- **THEN** 该条目 SHALL 包含 `source_session_id`（非空字符串）
- **AND** 若来自数据集分析，SHALL 包含 `source_dataset`（数据集名称）
- **AND** 若来自特定分析方法，SHALL 包含 `analysis_type`（如 "t_test", "anova"）
