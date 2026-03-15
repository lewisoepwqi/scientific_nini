# Capability: task-router

## Purpose

提供 `TaskRouter`，负责将用户意图字符串路由到一个或多个 Specialist Agent，支持内置关键词规则路由和 LLM 兜底路由，并输出标准化的 `RoutingDecision` 数据结构。

## Requirements

### Requirement: RoutingDecision 数据结构
系统 SHALL 提供 `RoutingDecision` 数据类，字段：`agent_ids: list[str]`（目标 Agent ID 列表）、`tasks: list[str]`（各 Agent 对应任务，与 agent_ids 等长）、`confidence: float`（0.0-1.0 路由置信度）、`strategy: str`（`"rule"` 或 `"llm"`）、`parallel: bool`（是否并行执行，默认 True）。

#### Scenario: 合法 RoutingDecision 创建
- **WHEN** 以合法字段实例化 `RoutingDecision`
- **THEN** 所有字段 SHALL 可通过属性访问
- **AND** `parallel` 默认值 SHALL 为 `True`

---

### Requirement: TaskRouter 规则路由
`TaskRouter` SHALL 提供内置关键词规则表，将用户意图字符串（大小写不敏感）映射到 Specialist Agent ID；匹配置信度 SHALL 由命中关键词数 / 规则关键词总数线性计算（最高 1.0）；单次 `route()` 调用耗时 SHALL < 5ms（不含 LLM 调用）。

内置规则：
| 关键词（任一命中即匹配） | 目标 Agent |
|------------------------|-----------|
| 文献、论文、引用、期刊、搜索、检索 | `literature_search` |
| 精读、批注、阅读、理解 | `literature_reading` |
| 清洗、缺失值、异常值、预处理、脏数据 | `data_cleaner` |
| 统计、检验、p值、显著性、回归、方差、anova | `statistician` |
| 图表、可视化、画图、箱线图、散点图、柱状图 | `viz_designer` |
| 写作、润色、摘要、引言、讨论、结论 | `writing_assistant` |

#### Scenario: 规则路由高置信度命中
- **WHEN** 调用 `router.route("请帮我清洗数据并处理缺失值", {})`
- **THEN** 返回的 `RoutingDecision.agent_ids` SHALL 包含 `"data_cleaner"`
- **AND** `strategy` SHALL 等于 `"rule"`
- **AND** `confidence` SHALL >= 0.7

#### Scenario: 多关键词同时命中多个 Agent
- **WHEN** 用户意图包含"清洗"和"统计"
- **THEN** `RoutingDecision.agent_ids` SHALL 包含 `"data_cleaner"` 和 `"statistician"`
- **AND** `parallel` SHALL 为 `True`
- **AND** `tasks` 长度 SHALL 等于 `agent_ids` 长度

#### Scenario: 意图无关键词命中
- **WHEN** 用户意图不包含任何规则关键词
- **THEN** `confidence` SHALL < 0.7
- **AND** `agent_ids` SHALL 为空列表

---

### Requirement: TaskRouter LLM 兜底路由
当规则路由 `confidence < 0.7` 时，`TaskRouter.route()` SHALL 调用 `model_resolver.chat(purpose="planning")` 分析用户意图，输出 JSON 格式路由决策；LLM 调用失败时 SHALL 返回规则路由结果（不抛出异常）。

#### Scenario: 规则不足时触发 LLM 路由
- **WHEN** 规则路由 `confidence < 0.7`
- **AND** `TaskRouter` 已配置 LLM 路由（`enable_llm_fallback=True`）
- **THEN** `strategy` SHALL 等于 `"llm"`
- **AND** 返回的 `RoutingDecision` SHALL 包含至少一个 `agent_id`

#### Scenario: LLM 路由失败时降级
- **WHEN** `model_resolver.chat()` 抛出异常或超时
- **THEN** `TaskRouter.route()` SHALL 返回规则路由结果
- **AND** SHALL 不抛出异常

---

### Requirement: TaskRouter 批量路由
`TaskRouter.route_batch(tasks: list[str]) -> list[RoutingDecision]` SHALL 用一次 LLM 调用（purpose="planning"）批量分析所有任务的路由决策和依赖关系；返回顺序 SHALL 与输入一致；空列表输入 SHALL 返回空列表。

#### Scenario: 批量路由保序
- **WHEN** 调用 `route_batch(["清洗数据", "统计分析", "作图"])`
- **THEN** 返回列表长度 SHALL 等于 3
- **AND** 返回顺序 SHALL 与输入顺序一致
