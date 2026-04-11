## ADDED Requirements

### Requirement: ScientificMemoryProvider 实现三段式记忆检索（prefetch）
系统 SHALL 提供 `ScientificMemoryProvider.prefetch()` 方法，按「FTS5 全文检索 → 上下文加权重排序 → top_k 截取」三段流程检索相关记忆，返回格式化纯文本（不含 fencing 标签）。

#### Scenario: 全文检索命中相关记忆
- **WHEN** `facts` 表中存在含"t 检验"的 statistic 条目
- **AND** `prefetch("当前数据集做了 t 检验")` 被调用
- **THEN** 返回值 SHALL 包含该条目的内容或摘要
- **AND** 返回值 SHALL NOT 包含 `<memory-context>` 标签（fencing 由调用方负责）

#### Scenario: dataset_name 匹配的记忆获得重排加权
- **WHEN** `facts` 表中存在两条记忆，一条 `sci_metadata.dataset_name` 与 prefetch 查询上下文匹配，另一条不匹配
- **AND** 两条记忆的基础 `importance` 相同
- **THEN** dataset_name 匹配的记忆 SHALL 排名更靠前

#### Scenario: facts 表为空时返回空字符串
- **WHEN** `facts` 表中无任何记录
- **AND** `prefetch("任意查询")` 被调用
- **THEN** 返回值 SHALL 为空字符串

### Requirement: ScientificMemoryProvider 每轮轻量提取统计结论（sync_turn）
系统 SHALL 在每轮对话结束后，通过 `sync_turn()` 扫描 assistant 回复，识别含统计数值或显式结论标记的内容，写入 `facts` 表（importance < 0.4 不写入）。

#### Scenario: 含 p 值的 assistant 回复被提取为 statistic 记忆
- **WHEN** assistant 回复包含类似 "p = 0.002" 的文本
- **AND** `sync_turn(user_content, assistant_content)` 被调用
- **THEN** 系统 SHALL 向 `facts` 表写入一条 `memory_type="statistic"` 的记录
- **AND** 该记录的 `importance` SHALL 大于等于 0.4

#### Scenario: 不含统计数值的普通回复不触发写入
- **WHEN** assistant 回复为普通解释性文本，不含 p 值、效应量或显式结论标记
- **AND** `sync_turn()` 被调用
- **THEN** `facts` 表 SHALL NOT 新增记录

#### Scenario: sync_turn 异常不影响对话主流程
- **WHEN** `facts` 表写入过程中发生异常（如磁盘错误）
- **THEN** 异常 SHALL 被捕获并记录警告日志
- **AND** 调用 `sync_turn()` 的代码 SHALL NOT 收到异常

### Requirement: ScientificMemoryProvider 会话结束时重度沉淀分析记忆（on_session_end）
系统 SHALL 在 `on_session_end()` 中，将本会话 `AnalysisMemory` 中的 Finding、StatisticResult、Decision 按置信度阈值写入 `facts` 表，并更新 `research_profiles` 表。

#### Scenario: 高置信度 Finding 被沉淀到 facts 表
- **WHEN** 会话包含 `confidence >= 0.7` 的 `Finding`
- **AND** `on_session_end(messages)` 被调用
- **THEN** 该 Finding 的 content 和 summary SHALL 写入 `facts(memory_type='finding')`
- **AND** 写入 SHALL 包含 `source_session_id`

#### Scenario: 显著统计结果被沉淀
- **WHEN** 会话包含 `significant=True` 的 `StatisticResult`
- **AND** `on_session_end(messages)` 被调用
- **THEN** 该结果 SHALL 写入 `facts(memory_type='statistic', importance=0.8)`
- **AND** `sci_metadata` SHALL 包含 `p_value`、`effect_size`、`dataset_name`（如有）

#### Scenario: on_session_end 幂等
- **WHEN** 同一会话的 `on_session_end()` 被调用两次
- **THEN** `facts` 表中 SHALL NOT 出现重复记录（`dedup_key` 约束保护）

#### Scenario: on_session_end 接受 session.messages 列表
- **WHEN** 传入 `session.messages`（`list[dict]` 类型）
- **THEN** `on_session_end()` SHALL 正常处理，不要求 `session` 对象本身

### Requirement: ScientificMemoryProvider 压缩前保护统计数值（on_pre_compress）
系统 SHALL 在上下文压缩前，通过 `on_pre_compress()` 从待压缩消息中提取含统计数值的行，生成「必须完整保留」提示，追加到压缩 prompt，防止统计结果被摘要化丢失。

#### Scenario: 含统计数值的消息触发保留提示
- **WHEN** `messages` 中存在 assistant 消息包含 "t(58)=3.14, p=0.002, d=0.45"
- **AND** `on_pre_compress(messages)` 被调用
- **THEN** 返回值 SHALL 包含该统计行
- **AND** 返回值 SHALL 包含「必须完整保留」的中文提示语

#### Scenario: 无统计数值时返回空字符串
- **WHEN** messages 中所有 assistant 消息均不含统计数值模式
- **AND** `on_pre_compress(messages)` 被调用
- **THEN** 返回值 SHALL 为空字符串

### Requirement: ScientificMemoryProvider 向 LLM 暴露 nini_memory_find 和 nini_memory_save 工具
系统 SHALL 通过 `get_tool_schemas()` 向 LLM 暴露两个记忆工具：`nini_memory_find`（全文 + sci_metadata 过滤检索）和 `nini_memory_save`（主动保存发现），并通过 `handle_tool_call()` 路由执行。

#### Scenario: nini_memory_find 按 max_p_value 过滤返回显著结果
- **WHEN** `handle_tool_call("nini_memory_find", {"query": "检验结果", "max_p_value": 0.05})` 被调用
- **AND** `facts` 表中存在 `p_value=0.002`（显著）和 `p_value=0.4`（不显著）两条记录
- **THEN** 返回的 JSON 字符串 SHALL 包含 `"success": true`
- **AND** results 列表 SHALL 仅包含 `p_value=0.002` 的记录

#### Scenario: nini_memory_save 写入新发现
- **WHEN** `handle_tool_call("nini_memory_save", {"content": "数据呈正偏斜", "memory_type": "finding"})` 被调用
- **THEN** 返回的 JSON SHALL 包含 `"success": true` 和新记录的 `id`
- **AND** `facts` 表中 SHALL 新增对应记录

#### Scenario: provider 未初始化时工具调用返回错误
- **WHEN** `ScientificMemoryProvider` 的 `initialize()` 尚未被调用
- **AND** 任一工具被调用
- **THEN** 返回 JSON SHALL 包含 `"success": false` 和错误信息
- **AND** SHALL NOT 抛出异常
