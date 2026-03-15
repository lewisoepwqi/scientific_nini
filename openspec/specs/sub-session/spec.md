# Capability: sub-session

## Purpose

提供 `SubSession`，继承 `Session` 接口但跳过磁盘持久化，支持子 Agent 在内存中独立运行，同时共享父会话的数据集、文档和事件回调。

## Requirements

### Requirement: SubSession 实现 Session 接口
`SubSession` SHALL 继承 `Session` 并覆盖 `__post_init__`，跳过磁盘持久化初始化（不创建 `ConversationMemory` 文件、不初始化 `KnowledgeMemory`），同时保留 `AgentRunner` 所需的全部字段和方法接口（`add_message`、`add_tool_call`、`add_tool_result`、`task_manager`、`event_callback` 等）。

#### Scenario: SubSession 可传入 AgentRunner 正常运行
- **WHEN** 将 `SubSession` 实例作为 `session` 参数传入 `AgentRunner`
- **THEN** `AgentRunner` SHALL 能正常执行 ReAct 循环，不抛出 `AttributeError` 或 `TypeError`

#### Scenario: SubSession 初始化不写磁盘
- **WHEN** 实例化 `SubSession`
- **THEN** `data/sessions/` 目录下 SHALL 不创建任何新文件或目录

---

### Requirement: SubSession 消息历史不持久化
`SubSession` 的 `add_message`、`add_tool_call`、`add_tool_result` 等方法 SHALL 将消息写入内存（`self.messages`），不写入 `memory.jsonl` 文件。

#### Scenario: 添加消息仅存内存
- **WHEN** 调用 `sub_session.add_message("user", "执行数据清洗")`
- **THEN** `sub_session.messages` SHALL 包含该消息
- **AND** 文件系统 SHALL 不产生任何新文件

---

### Requirement: SubSession 共享父会话数据集（写新键）
`SubSession` 初始化时 SHALL 接收父会话 `datasets` 的同一 dict 引用；子 Agent 写入数据集时 SHALL 使用新键（不覆盖父会话原有键），以避免污染父会话已有数据。Python 无法在运行时阻止 DataFrame 原地修改，此约束通过约定（文档 + 代码审查）而非技术手段强制。

#### Scenario: 子 Agent 可读取父会话数据集
- **WHEN** 父会话 `datasets` 中存在键为 `"raw_data"` 的 DataFrame
- **AND** `SubSession` 以该 `datasets` 的引用初始化
- **THEN** `sub_session.datasets["raw_data"]` SHALL 返回相同的 DataFrame 对象

#### Scenario: 子 Agent 写入数据集使用新键
- **WHEN** 子 Agent 向 `sub_session.datasets` 写入处理后的数据
- **THEN** 写入 SHALL 使用区别于父会话原有键的新键（如 `"cleaned_data"`）
- **AND** 父会话 `datasets["raw_data"]` SHALL 保持不变

---

### Requirement: SubSession 包含 documents 字段
`SubSession` SHALL 包含 `documents` 字段，初始化时接收父会话 `documents` 的引用，供文献类 Specialist Agent（`literature_search`、`literature_reading`）写入文档产物。

#### Scenario: 文献 Agent 可写入 documents
- **WHEN** 子 Agent 向 `sub_session.documents` 写入新文档键值对
- **THEN** 该文档 SHALL 可通过 `sub_session.documents` 读取
- **AND** 执行完毕后，Spawner SHALL 将 `sub_session.documents` 中的新键回写到父会话 `session.documents`

---

### Requirement: SubSession knowledge_memory 为 None 时不崩溃
`SubSession` 的 `knowledge_memory` SHALL 设为 `None`；`AgentRunner` 在构建上下文时 SHALL 能处理 `session.knowledge_memory is None` 的情况（跳过知识库检索，不抛出 `AttributeError`）。

#### Scenario: 无知识库时 AgentRunner 正常运行
- **WHEN** `SubSession.knowledge_memory` 为 `None`
- **WHEN** `AgentRunner.run()` 执行到知识库检索步骤
- **THEN** AgentRunner SHALL 跳过检索，继续执行后续步骤
- **AND** SHALL 不抛出 `AttributeError` 或 `TypeError`

---

### Requirement: SubSession event_callback 绑定父会话回调
`SubSession` 初始化时 SHALL 接收并绑定父会话的 `event_callback`，子 Agent 执行期间产生的所有事件（text、tool_call、agent_progress 等）SHALL 通过该回调推送，事件 payload 中 SHALL 包含 `agent_id` 字段标识来源。

#### Scenario: 子 Agent 事件通过父会话回调推送
- **WHEN** 子 Agent 在 `SubSession` 中调用工具并产生事件
- **THEN** 父会话的 `event_callback` SHALL 被调用
- **AND** 事件 payload 中 SHALL 包含 `agent_id` 字段
