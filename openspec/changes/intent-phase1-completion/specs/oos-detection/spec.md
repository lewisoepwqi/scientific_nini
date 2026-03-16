## ADDED Requirements

### Requirement: QueryType 枚举包含 OUT_OF_SCOPE 值

`src/nini/intent/base.py` 的 `QueryType` 枚举 SHALL 包含 `OUT_OF_SCOPE = "out_of_scope"` 值，用于标记明确超出科研助手服务范围的请求。

#### Scenario: OUT_OF_SCOPE 不触发 RAG 检索

- **WHEN** `analysis.query_type` 为 `QueryType.OUT_OF_SCOPE`
- **THEN** `analysis.rag_needed` 为 `False`（不触发知识库检索）

### Requirement: _OUT_OF_SCOPE_RE 覆盖通用非科研类黑名单词汇

`src/nini/intent/optimized.py` 中的 `_OUT_OF_SCOPE_RE` SHALL 扩展覆盖以下类别：订票/订餐/外卖/天气/股票/购物/播放音乐/导航/翻译等明显非科研类通用服务词汇。

#### Scenario: 订机票请求被识别为 OUT_OF_SCOPE

- **WHEN** 用户输入"帮我订一张明天去北京的机票"
- **THEN** `_classify_query_type()` 返回 `QueryType.OUT_OF_SCOPE`

#### Scenario: 天气查询请求被识别为 OUT_OF_SCOPE

- **WHEN** 用户输入"明天北京天气怎么样"
- **THEN** `_classify_query_type()` 返回 `QueryType.OUT_OF_SCOPE`

#### Scenario: 科研相关词汇不被误判为 OUT_OF_SCOPE

- **WHEN** 用户输入"帮我分析气候数据"（含"气候"但为科研场景）
- **THEN** `_classify_query_type()` 不返回 `QueryType.OUT_OF_SCOPE`

### Requirement: _classify_query_type 优先检测 OUT_OF_SCOPE

`_classify_query_type` 方法 SHALL 在检测 CASUAL_CHAT 之前先检测通用 OOS 词汇；命中时直接返回 `OUT_OF_SCOPE`，不再继续后续分类逻辑。

#### Scenario: OOS 检测优先于闲聊检测

- **WHEN** 用户输入"帮我订个外卖吧"（同时含有"帮"等闲聊语气词和 OOS 词）
- **THEN** 返回 `QueryType.OUT_OF_SCOPE`，而非 `QueryType.CASUAL_CHAT`
