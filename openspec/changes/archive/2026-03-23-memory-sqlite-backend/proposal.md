## Why

当前会话持久化层由三种异构文件格式拼凑而成：

- `memory.jsonl` — 消息历史（逐行 JSON，追加写入）
- `meta.json` — 会话元数据（标题、压缩段、timestamps 等）
- `archive/*.json` — 压缩归档消息（独立 JSON 文件，每次压缩生成一个）
- `archive/search_index.jsonl` — 归档全文索引（C2 阶段引入的 JSONL 增量索引）

这一设计存在以下问题：

1. **原子性缺失**：meta 更新与消息写入是两次独立 fsync，崩溃时可能产生不一致状态。
2. **查询能力弱**：跨消息的任意条件检索（如按 role、时间范围、关键词）只能靠全文件扫描；search_index.jsonl 也只是线性遍历。
3. **文件碎片化**：随着会话增长，archive/ 目录下文件数量线性增加，目录遍历成本上升；多个写入进程并发时存在竞争。
4. **迁移/备份不便**：单会话数据分散在多个文件，无法一次 `cp` 或 `sqlite3 .dump` 导出完整状态。

SQLite 可以在保持"本地优先、零服务器"特性的前提下，统一解决上述问题：单文件、事务写入、原生 FTS5 全文检索、行级查询。

## What Changes

将每个会话的存储从多文件格式迁移到单一 SQLite 数据库文件（`session.db`），具体变化：

- **`memory.jsonl` → `messages` 表**：JSONL 追加写入改为 INSERT，支持按 id/role/timestamp 查询与分页。
- **`meta.json` → `session_meta` 表**（单行 upsert）：title、compressed_context、compression_segments、timestamps 统一原子更新。
- **`archive/*.json` → `archived_messages` 表**：归档消息改为行存储，archive_file 字段保留原始文件名以兼容旧引用。
- **`search_index.jsonl` → FTS5 虚拟表**：基于 `archived_messages` 的 FTS5 索引，支持 MATCH 语法，查询效率从 O(行数线性扫描) 变为 O(log)。
- **向后兼容读取**：首次访问旧格式会话时，自动迁移 memory.jsonl + meta.json + archive/*.json 到 session.db，原文件保留（可选清理）。

## Capabilities

### New Capabilities

- `sqlite-session-store`: SQLite 统一会话存储层，包含 schema 定义、读写接口、旧格式迁移逻辑，以及基于 FTS5 的归档全文检索。

### Modified Capabilities

（无需变更现有 spec；`sqlite-session-store` 是新增实现层，上层 API 契约不变。）

## Impact

**后端文件**：
- `src/nini/memory/conversation.py` — ConversationMemory 改为读写 SQLite `messages` 表
- `src/nini/agent/session.py` / `src/nini/agent/session_manager.py` — 持久化逻辑改为 upsert `session_meta`
- `src/nini/memory/compression.py` — `_archive_messages()` 改为 INSERT 到 `archived_messages` 表；`_append_to_search_index()` 改为写入 FTS5
- `src/nini/tools/search_archive.py` — 检索改为 FTS5 MATCH 查询，fallback 保留全量扫描

**新增文件**：
- `src/nini/memory/db.py` — SQLite 连接池、schema 初始化、migration 工具函数

**依赖变更**：
- 新增 `aiosqlite`（用于异步 I/O 路径）；标准库 `sqlite3` 用于同步迁移路径

**数据目录结构变化**：
```
data/sessions/{session_id}/
  session.db          ← 新：统一存储
  memory.jsonl        ← 旧：迁移后保留（可删除）
  meta.json           ← 旧：迁移后保留（可删除）
  archive/            ← 旧：迁移后保留（可删除）
  workspace/          ← 不变
```
