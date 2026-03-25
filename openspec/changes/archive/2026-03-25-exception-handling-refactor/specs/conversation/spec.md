## ADDED Requirements

### Requirement: 搜索 API 返回能力元数据
归档搜索 API SHALL 在响应中包含 `search_mode` 字段，表明当前使用的搜索引擎类型，使客户端可感知搜索能力降级。

注：FTS5 可用性标志追踪（`is_fts5_available()`）已在 `db.py:60-72` 实现并缓存，本需求仅补充 API 响应字段。

#### Scenario: 搜索 API 返回能力元数据
- **WHEN** 归档搜索 API 被调用
- **THEN** 响应 SHALL 包含 `search_mode` 字段，值为 `"fts5"` 或 `"like_fallback"`
- **AND** 客户端可据此展示搜索能力降级提示

#### Scenario: FTS5 不可用时搜索仍可工作
- **WHEN** FTS5 不可用且用户执行归档搜索
- **THEN** 系统 SHALL 使用 LIKE 降级路径返回结果
- **AND** `search_mode` SHALL 为 `"like_fallback"`
