## Context

当前会话存储使用文件系统多格式方案：`memory.jsonl`（消息历史）、`meta.json`（元数据）、`archive/*.json`（归档消息）、`archive/search_index.jsonl`（增量索引）。这些格式在 A/B/C2 阶段逐步堆叠，现已到达维护边界——原子性和查询能力均无法满足进一步扩展需求。

SQLite 是"本地优先、零服务器"场景下的标准选择：单文件、ACID 事务、内置 FTS5、Python 标准库支持。

## Goals / Non-Goals

**Goals:**
- 用 `session.db` 单文件替代 memory.jsonl + meta.json + archive/*.json + search_index.jsonl
- ConversationMemory、SessionManager、compression 的持久化路径全部改为 SQLite
- 归档检索改用 FTS5，废弃 JSONL 线性扫描
- 旧格式会话首次访问时自动迁移，无需手动工具
- 所有现有测试通过，新增覆盖 SQLite 路径的测试

**Non-Goals:**
- 不引入 ORM（直接写 SQL，保持零运行时依赖增长）
- 不支持多进程并发写入（单进程服务场景，WAL 模式足够）
- 不支持远程数据库（保持本地优先原则）
- 不删除旧格式文件（迁移后原文件保留，清理由用户手动执行）
- 不变更对外 API 契约（HTTP endpoints 返回格式不变）

## Decisions

### D1：同步 vs 异步 SQLite

**选择：主路径同步（sqlite3），异步路径 aiosqlite 可选**

ConversationMemory 和 SessionManager 当前均为同步 I/O，全部改为 aiosqlite 会引入大量 await 传染。因此：
- `db.py` 提供同步接口（`sqlite3`），覆盖 ConversationMemory、SessionManager
- `compression.py` 中的归档写入在同步 `_archive_messages()` 内调用同步接口
- FTS5 检索在 `search_archive.py` 的 `async execute()` 中使用 `asyncio.to_thread` 包装同步查询

不引入 `aiosqlite` 依赖，避免额外安装步骤。

### D2：Schema 设计

```sql
-- 消息历史
CREATE TABLE messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    role     TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    raw_json TEXT    NOT NULL,  -- 完整消息 JSON，保留所有字段
    ts       REAL    NOT NULL   -- Unix timestamp（与 _ts 字段一致）
);

-- 会话元数据（单行）
CREATE TABLE session_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 归档消息
CREATE TABLE archived_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    archive_file TEXT    NOT NULL,  -- 原始文件名，如 compressed_20240101_120000.json
    role         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    raw_json     TEXT    NOT NULL
);

-- FTS5 全文索引（映射到 archived_messages）
CREATE VIRTUAL TABLE archived_fts USING fts5(
    content,
    role UNINDEXED,
    archive_file UNINDEXED,
    content='archived_messages',
    content_rowid='id'
);
```

`raw_json` 保存完整消息字典，确保任何上层字段（tool_calls、chart_data 等）不丢失。

### D3：旧格式迁移策略

在 `db.py` 的 `get_session_db(session_dir)` 中检测：
- 如果 `session.db` 已存在 → 直接返回连接
- 如果存在 `memory.jsonl` 或 `meta.json` → 执行一次性迁移后返回连接

迁移步骤（同步，在首次 `get_session_db` 调用时执行）：
1. 创建 session.db + schema
2. 读取 memory.jsonl → INSERT INTO messages
3. 读取 meta.json → INSERT INTO session_meta
4. 遍历 archive/*.json → INSERT INTO archived_messages + 写入 archived_fts
5. 迁移完成，原文件不删除

迁移为原子事务，失败时 session.db 不创建（下次重试）。

### D4：ConversationMemory 接口不变

`ConversationMemory` 保持现有公共接口（append、read_all、clear），内部从 JSONL 改为 SQLite。调用方（session.py、runner.py）无需修改。

### D5：search_index.jsonl 废弃路径

`search_archive.py` 新增 SQLite FTS5 检索路径（优先），原 JSONL 索引路径改为 fallback（兼容旧数据库迁移未触发时）。FTS5 不可用时 fallback 全量扫描，行为与现在一致。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|------|------|------|
| 迁移逻辑 bug 导致消息丢失 | 高 | 原文件不删除；迁移失败时 session.db 不保留（原子事务） |
| FTS5 未编译进 SQLite（某些 Linux 发行版） | 中 | 检测 `USING fts5` 是否可用；不可用时 fallback JSONL 扫描 |
| 并发写入竞争（多请求同时写同一会话） | 低 | 服务单进程，WAL 模式下读写并发安全；写入冲突由 SQLite EXCLUSIVE 锁处理 |
| 测试需要临时数据库隔离 | 低 | 使用 `tmp_path` fixture，与现有 `isolate_data_dir` 模式一致 |
