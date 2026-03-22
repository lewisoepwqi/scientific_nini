## ADDED Requirements

### Requirement: SQLite 统一存储初始化
系统应在每个会话目录下维护一个 `session.db` SQLite 数据库，包含 `messages`、`session_meta`、`archived_messages` 和 `archived_fts`（FTS5 虚拟表）四张表。

#### Scenario: 首次访问新会话
- **WHEN** 调用 `get_session_db(session_dir)` 且目录下无任何持久化文件
- **THEN** 创建 `session.db` 并初始化四张表，返回可用连接

#### Scenario: 重复访问已存在的数据库
- **WHEN** `session.db` 已存在且 schema 完整
- **THEN** 直接返回连接，不重建 schema

---

### Requirement: 消息历史存储
ConversationMemory 的消息读写应通过 SQLite `messages` 表实现，每条消息完整 JSON 存储于 `raw_json` 字段。

#### Scenario: 追加消息
- **WHEN** 调用 `ConversationMemory.append(message)`
- **THEN** 将消息 INSERT 到 `messages` 表，`raw_json` 为完整 JSON 序列化结果，`ts` 为当前 UTC 时间戳

#### Scenario: 读取所有消息
- **WHEN** 调用 `ConversationMemory.read_all()`
- **THEN** 按 `id ASC` 顺序返回所有消息（从 `raw_json` 反序列化），顺序与写入顺序一致

#### Scenario: 清空消息历史
- **WHEN** 调用 `ConversationMemory.clear()`
- **THEN** DELETE FROM messages，表保留但行清空

---

### Requirement: 会话元数据存储
会话元数据（title、compressed_context、compression_segments、timestamps）应以键值对存储于 `session_meta` 表。

#### Scenario: 保存元数据
- **WHEN** 调用 `SessionManager.save_session_title()` 或 `save_session_compression()`
- **THEN** 以 `INSERT OR REPLACE` 更新 `session_meta` 对应 key，所有更新在单一事务内完成

#### Scenario: 加载元数据
- **WHEN** `create_session()` 或 `get_or_create()` 加载已有会话
- **THEN** 从 `session_meta` 读取 title、compression_segments 等字段，与旧 meta.json 格式语义完全相同

---

### Requirement: 归档消息存储
压缩归档操作应将消息写入 `archived_messages` 表，同时更新 `archived_fts` FTS5 索引。

#### Scenario: 归档消息批量写入
- **WHEN** `_archive_messages()` 执行压缩归档
- **THEN** 所有消息在单一事务内 INSERT 到 `archived_messages`，`archive_file` 字段保留原始文件名格式（如 `compressed_20240101_120000.json`）；同时通过触发器或显式 INSERT 更新 `archived_fts`

#### Scenario: FTS5 不可用时降级
- **WHEN** SQLite 编译未包含 FTS5 扩展
- **THEN** `archived_fts` 创建失败时捕获异常，归档消息仍写入 `archived_messages` 表；检索时 fallback 为全表扫描

---

### Requirement: FTS5 归档全文检索
`SearchMemoryArchiveTool` 应优先使用 FTS5 `MATCH` 查询检索归档消息。

#### Scenario: FTS5 检索命中
- **WHEN** `execute(session, keyword=kw)` 且 `archived_fts` 表存在
- **THEN** 执行 `SELECT * FROM archived_fts WHERE archived_fts MATCH ?` 返回匹配行；`result.data["used_index"]` 为 `True`，`result.data["files_searched"]` 为 `0`

#### Scenario: FTS5 不可用时 fallback
- **WHEN** `archived_fts` 表不存在或查询异常
- **THEN** fallback 为全量扫描 `archived_messages` 表（LIKE 匹配）；结果格式与 FTS5 路径一致

#### Scenario: 旧 JSONL 索引兼容
- **WHEN** 会话目录存在 `archive/search_index.jsonl` 但无 `session.db`（迁移尚未触发）
- **THEN** 继续使用 JSONL 索引路径（现有逻辑），迁移后自动切换为 FTS5

---

### Requirement: 旧格式自动迁移
系统应在首次访问旧格式会话时，自动将文件数据迁移到 `session.db`。

#### Scenario: 旧格式完整迁移
- **WHEN** `session_dir` 存在 `memory.jsonl` 且无 `session.db`
- **THEN** 创建 `session.db`，在单一事务内导入 memory.jsonl → messages、meta.json → session_meta、archive/*.json → archived_messages；迁移成功后 `session.db` 持久化，原文件保留不删除

#### Scenario: 迁移失败回滚
- **WHEN** 迁移事务中任意步骤抛出异常
- **THEN** 事务回滚，`session.db` 不创建（或删除），下次访问重新尝试迁移；原文件完整保留

#### Scenario: 无旧格式文件
- **WHEN** `session_dir` 既无 `memory.jsonl` 也无 `session.db`
- **THEN** 直接创建空 `session.db`，不执行迁移逻辑
