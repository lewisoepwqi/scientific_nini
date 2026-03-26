## ADDED Requirements

### Requirement: search_literature 工具定义
系统 SHALL 提供 `search_literature` 工具，继承 Tool 基类，支持关键词检索学术文献。

#### Scenario: 基本检索
- **WHEN** 调用 search_literature(query="machine learning drug discovery", max_results=10)
- **THEN** 返回包含 title、authors、year、abstract、doi、citation_count 的文献列表

#### Scenario: 按年份过滤
- **WHEN** 调用 search_literature(query="CRISPR", year_from=2020)
- **THEN** 返回的文献均发表于 2020 年及之后

### Requirement: API 降级链
search_literature SHALL 按优先级尝试多个学术 API：Semantic Scholar → CrossRef。前者失败时自动降级到后者。

#### Scenario: Semantic Scholar 不可用时降级
- **WHEN** Semantic Scholar API 请求失败
- **THEN** 自动尝试 CrossRef API，返回结果中标注数据来源

#### Scenario: 所有 API 不可用时返回降级信息
- **WHEN** 所有学术 API 均不可用
- **THEN** 返回 ToolResult 包含降级提示和手动替代建议

### Requirement: 限流保护
search_literature SHALL 实现 API 请求限流（Semantic Scholar 每秒最多 1 请求），避免触发 API 限制。

#### Scenario: 连续调用不超限
- **WHEN** 短时间内多次调用 search_literature
- **THEN** 请求间隔不小于 1 秒

### Requirement: 工具注册
search_literature SHALL 在 `tools/registry.py` 中注册。

#### Scenario: 工具可查询
- **WHEN** 从 ToolRegistry 中查询 "search_literature"
- **THEN** 返回对应的 Tool 实例

### Requirement: NetworkPlugin 依赖检测
search_literature 在执行前 SHALL 检查 NetworkPlugin 可用性。不可用时直接返回降级 ToolResult，不尝试网络请求。

#### Scenario: 离线时不发起请求
- **WHEN** NetworkPlugin.is_available() 返回 False
- **THEN** search_literature 立即返回降级 ToolResult，不发起任何 HTTP 请求
