# citation-management Specification

## Purpose
定义引用管理能力在意图层的识别规则、同义词覆盖范围，以及用户引用格式转换与参考文献整理请求的稳定路由要求，确保相关请求能被一致识别并交给正确的能力处理。

## Requirements

### Requirement: citation_management Capability 在意图层可被识别

系统 SHALL 在 `create_default_capabilities()` 中注册 `citation_management` Capability，使意图分析器能推荐该能力，用户的引用管理请求能通过意图层路由到 `citation_manager` Agent。

#### Scenario: 用户请求格式化参考文献时意图层推荐 citation_management

- **WHEN** 用户输入含"参考文献"、"引用格式"、"bibliography"等关键词的请求
- **THEN** `OptimizedIntentAnalyzer.analyze()` 返回的 `capability_candidates` 中包含 `citation_management`

### Requirement: citation_management 同义词覆盖中英文科研引用术语

`config/intent_synonyms.yaml` 中 SHALL 包含 `citation_management` 条目，同义词列表覆盖常见引用格式名称和操作词汇（APA、MLA、GB/T、bibliography、引用管理等）。

#### Scenario: YAML 同义词匹配 APA 格式请求

- **WHEN** 用户输入"帮我转成 APA 格式"
- **THEN** 同义词倒排索引命中 `citation_management`，该 Capability 出现在候选列表中

#### Scenario: YAML 同义词匹配中文引用词

- **WHEN** 用户输入"整理一下文献引用"
- **THEN** 意图候选中包含 `citation_management`
