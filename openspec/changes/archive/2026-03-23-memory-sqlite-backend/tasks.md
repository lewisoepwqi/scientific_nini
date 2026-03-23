## 1. 数据库基础层（db.py）

- [x] 1.1 新建 `src/nini/memory/db.py`，实现 `get_session_db(session_dir: Path) -> sqlite3.Connection`：检测 session.db 是否存在；不存在时调用 `_init_schema()` 创建四张表（messages、session_meta、archived_messages、archived_fts）；返回连接（WAL 模式）
- [x] 1.2 实现 `_init_schema(conn)`：建表 SQL 含 `CREATE TABLE IF NOT EXISTS` 和 `CREATE VIRTUAL TABLE IF NOT EXISTS archived_fts USING fts5(...)`；FTS5 不可用时捕获异常并记录警告，允许降级
- [x] 1.3 实现 `_migrate_legacy(session_dir, conn)` 迁移函数：在单一事务内读取 memory.jsonl → INSERT messages、读取 meta.json → INSERT session_meta、遍历 archive/*.json → INSERT archived_messages + archived_fts；任意步骤异常时 rollback；迁移函数在 `get_session_db` 内首次调用时触发
- [x] 1.4 为 `db.py` 新增单元测试 `tests/test_db.py`：覆盖首次建库、重复访问、FTS5 可用检测、迁移（含回滚场景）

## 2. ConversationMemory 改写

- [x] 2.1 读取 `src/nini/memory/conversation.py` 现有实现，理解公共接口（append、read_all、clear、line_count 等）
- [x] 2.2 将 `append(message)` 实现改为 `INSERT INTO messages`（raw_json=json.dumps(msg), ts=time.time(), role/content 提取）
- [x] 2.3 将 `read_all()` 改为 `SELECT raw_json FROM messages ORDER BY id ASC`，反序列化后返回列表
- [x] 2.4 将 `clear()` 改为 `DELETE FROM messages`
- [x] 2.5 保持其他现有方法（如 line_count 等）行为不变，改为对应 SQL 查询
- [x] 2.6 更新 ConversationMemory 相关测试，确保通过

## 3. SessionManager 元数据改写

- [x] 3.1 读取 `src/nini/agent/session.py`（SessionManager 类）现有 `save_session_title`、`save_session_compression`、`create_session`（元数据加载部分）实现
- [x] 3.2 将 `save_session_title` 改为 `INSERT OR REPLACE INTO session_meta(key, value)` 更新 `title`
- [x] 3.3 将 `save_session_compression` 改为批量 upsert：compressed_context、compression_segments、compressed_rounds、last_compressed_at 各一行，在单一事务内提交
- [x] 3.4 将 `create_session` 元数据加载改为从 `session_meta` SELECT，旧 meta.json fallback（迁移已触发则无旧文件；迁移未触发则先触发迁移）
- [x] 3.5 更新会话加载/持久化相关测试，确保通过

## 4. 压缩归档改写

- [x] 4.1 读取 `src/nini/memory/compression.py` 中 `_archive_messages()` 和 `_append_to_search_index()` 实现
- [x] 4.2 将 `_archive_messages()` 改为 INSERT INTO archived_messages（保留 archive_file 字段以兼容旧引用），并在同一事务内 INSERT archived_fts
- [x] 4.3 将 `_append_to_search_index()` 改为写入 archived_fts（通过 `INSERT INTO archived_fts(rowid, content, role, archive_file)` 方式同步）；FTS5 不可用时 fallback 写 JSONL（兼容旧路径）
- [x] 4.4 更新压缩相关测试，确保通过

## 5. SearchMemoryArchiveTool 检索改写

- [x] 5.1 读取 `src/nini/tools/search_archive.py` 现有三段式检索逻辑
- [x] 5.2 新增 FTS5 检索路径：通过 `get_session_db` 获取连接，执行 `SELECT rowid, archive_file, role, content FROM archived_fts WHERE archived_fts MATCH ?`；返回结果格式与现有一致（snippet 截断逻辑复用）
- [x] 5.3 FTS5 路径返回 `used_index=True`、`files_searched=0`、`indexed_files=<FTS5行数>`
- [x] 5.4 FTS5 不可用或查询异常时，fallback 为 `SELECT content, role, archive_file FROM archived_messages WHERE content LIKE ?`（LIKE 全表扫描）
- [x] 5.5 旧 JSONL 索引路径（`archive/search_index.jsonl`）保留为最终 fallback（session.db 不存在时）
- [x] 5.6 更新 `tests/test_search_archive.py`：新增 `TestFTS5Search` 类，覆盖 FTS5 命中、fallback、旧格式兼容

## 6. 依赖与配置

- [x] 6.1 检查 `pyproject.toml`：`sqlite3` 为标准库无需添加；确认无需引入 `aiosqlite`（搜索路径通过 `asyncio.to_thread` 包装）
- [x] 6.2 在 `src/nini/config.py` 新增 `session_db_filename: str = "session.db"` 配置项（可选，方便测试覆盖）

## 7. 集成验证

- [x] 7.1 运行全量测试套件 `pytest -q`，确保所有现有测试通过
- [x] 7.2 手动验证迁移路径：创建旧格式会话文件，启动后访问会话，确认消息可读、归档可检索
- [x] 7.3 运行 `black --check src tests` 和 `mypy src/nini` 确保格式与类型正确
