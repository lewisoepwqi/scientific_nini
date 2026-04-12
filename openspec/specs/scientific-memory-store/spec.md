# scientific-memory-store Specification

## Purpose
TBD - created by syncing change memory-provider-architecture.

## Requirements

### Requirement: MemoryStore 在 SQLite 中维护 facts 表和 research_profiles 表
系统 SHALL 在 `data/nini_memory.db` 创建并维护 `facts` 表（通用记忆层 + `sci_metadata` JSON 列）和 `research_profiles` 表（研究画像），以 WAL 模式运行，保证多会话并发写入安全。

#### Scenario: 首次初始化创建完整 schema
- **WHEN** `MemoryStore(db_path)` 首次初始化时 `db_path` 不存在
- **THEN** `facts` 表 SHALL 被创建，包含 `id`、`content`、`memory_type`、`summary`、`tags`、`importance`、`trust_score`、`source_session_id`、`created_at`、`updated_at`、`access_count`、`dedup_key`、`sci_metadata` 列
- **AND** `research_profiles` 表 SHALL 被创建
- **AND** `PRAGMA journal_mode` SHALL 返回 `wal`

#### Scenario: 重复初始化不破坏已有数据
- **WHEN** 已有数据的 `nini_memory.db` 上再次初始化 `MemoryStore`
- **THEN** 已有数据 SHALL 完整保留
- **AND** schema 创建语句使用 `IF NOT EXISTS`，不抛出异常

### Requirement: upsert_fact 幂等写入记忆条目
系统 SHALL 提供 `upsert_fact()` 方法，基于 `dedup_key`（`MD5(memory_type|dataset_name|content)`）实现幂等写入：相同内容二次写入时更新访问计数并返回已有 id，而非重复插入。

#### Scenario: 首次写入返回新 UUID
- **WHEN** `upsert_fact(content="t(58)=3.14, p=0.002", memory_type="statistic")` 被调用
- **THEN** 返回值 SHALL 为 36 字符的 UUID 字符串
- **AND** `facts` 表中 SHALL 存在对应行

#### Scenario: 相同内容+类型+dataset 二次写入返回已有 id
- **WHEN** 相同 `content`、`memory_type`、`sci_metadata.dataset_name` 的 fact 已存在
- **AND** `upsert_fact()` 以相同参数再次调用
- **THEN** 返回值 SHALL 与首次写入的 id 相同
- **AND** `facts` 表行数 SHALL 不增加

#### Scenario: 不同内容创建独立条目
- **WHEN** 两次 `upsert_fact()` 调用的 `content` 不同
- **THEN** 两次返回值 SHALL 为不同的 UUID
- **AND** `facts` 表中 SHALL 存在两行独立记录

### Requirement: search_fts 通过 FTS5 全文检索 facts
系统 SHALL 提供 `search_fts(query, top_k)` 方法，使用 FTS5 虚拟表对 `content`、`summary`、`tags` 字段进行全文检索，FTS5 不可用时自动降级为 `LIKE` 匹配，两种路径均不抛出异常。

#### Scenario: FTS5 可用时全文检索返回匹配结果
- **WHEN** `facts` 表中存在 `content="独立样本 t 检验显著"` 的条目
- **AND** `search_fts("t 检验")` 被调用
- **THEN** 该条目 SHALL 出现在返回列表中
- **AND** 每条结果 SHALL 包含 `id`、`content`、`memory_type`、`sci_metadata` 字段

#### Scenario: FTS5 不可用时降级为 LIKE 匹配
- **WHEN** SQLite 编译版本不支持 FTS5
- **AND** `search_fts("关键词")` 被调用
- **THEN** 系统 SHALL NOT 抛出异常
- **AND** 包含关键词的 `content` 行 SHALL 被返回
- **AND** LIKE 匹配中的 `%` 和 `_` 特殊字符 SHALL 被转义（使用 `ESCAPE '\\'` 子句）防止查询字符串中的特殊字符被解释为通配符

### Requirement: filter_by_sci 通过 sci_metadata JSON 字段过滤 facts
系统 SHALL 提供 `filter_by_sci()` 方法，支持按 `dataset_name`、`analysis_type`、`max_p_value`、`min_effect_size` 过滤 `sci_metadata` JSON 列。JSON1 扩展可用时使用 `json_extract()` 查询，不可用时降级为全表扫描 + 内存过滤，两种路径均不抛出异常。

#### Scenario: 按 max_p_value 过滤返回显著结果
- **WHEN** `facts` 表中存在 `sci_metadata.p_value=0.002` 和 `sci_metadata.p_value=0.4` 的两条记录
- **AND** `filter_by_sci(max_p_value=0.05)` 被调用
- **THEN** 仅 `p_value=0.002` 的记录 SHALL 出现在返回列表中

#### Scenario: 按 dataset_name 过滤
- **WHEN** `filter_by_sci(dataset_name="survey.csv")` 被调用
- **THEN** 返回列表中所有记录的 `sci_metadata.dataset_name` SHALL 等于 `"survey.csv"`

#### Scenario: JSON1 不可用时降级为内存过滤
- **WHEN** SQLite 编译版本不支持 JSON1 扩展（`json_extract` 不可用）
- **AND** `filter_by_sci(max_p_value=0.05)` 被调用
- **THEN** 系统 SHALL 全表扫描 `facts`，在内存中解析 `sci_metadata` JSON 执行过滤
- **AND** 返回结果 SHALL 与 JSON1 路径一致
- **AND** SHALL NOT 抛出异常（解析失败的行静默跳过）

### Requirement: MemoryStore 自动迁移旧格式记忆数据
系统 SHALL 在首次初始化时自动将旧格式数据迁移到 SQLite，迁移为幂等操作，失败时记录警告日志，不阻止 agent 启动。

字段映射规则（`LongTermMemoryEntry` → `facts`）：
- `content` → `content`
- `memory_type` → `memory_type`
- `importance_score` → `importance`
- `source_dataset` → `sci_metadata.dataset_name`
- `source_session_id` → `source_session_id`
- `analysis_type` → `sci_metadata.analysis_type`
- `metadata.dedup_key` → `dedup_key`（如有，否则重新计算 `MD5(memory_type|source_dataset|content)`）

#### Scenario: JSONL 文件迁移到 facts 表
- **WHEN** `migrate_from_jsonl(jsonl_path)` 被调用，文件包含 N 条有效 JSONL 记录
- **THEN** `facts` 表中 SHALL 新增最多 N 条记录（已存在的通过 dedup_key 跳过）
- **AND** 返回值 SHALL 为实际新增的条目数
- **AND** `source_dataset` 字段 SHALL 映射到 `sci_metadata.dataset_name`

#### Scenario: JSONL 迁移幂等
- **WHEN** `migrate_from_jsonl()` 对同一文件调用两次
- **THEN** 第二次调用 SHALL NOT 增加 `facts` 表行数
- **AND** 两次调用均 SHALL NOT 抛出异常

#### Scenario: 迁移文件不存在时静默跳过
- **WHEN** `migrate_from_jsonl(non_existent_path)` 被调用
- **THEN** 系统 SHALL NOT 抛出异常
- **AND** 系统 SHALL 记录 debug 级别日志
