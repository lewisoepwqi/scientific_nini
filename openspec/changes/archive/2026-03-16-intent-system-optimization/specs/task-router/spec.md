## MODIFIED Requirements

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
| 引用格式、参考文献、文献管理、bibliography、citation | `citation_manager` |
| 研究规划、研究设计、实验设计、研究方案、研究思路 | `research_planner` |
| 审稿、同行评审、评审意见、回复审稿、修改意见 | `review_assistant` |

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

#### Scenario: 引用管理意图路由到 citation_manager
- **WHEN** 用户意图包含"参考文献"或"引用格式"或"bibliography"
- **THEN** `RoutingDecision.agent_ids` SHALL 包含 `"citation_manager"`
- **AND** `strategy` SHALL 等于 `"rule"`
- **AND** `confidence` SHALL >= 0.7

#### Scenario: 研究规划意图路由到 research_planner
- **WHEN** 用户意图包含"研究设计"或"实验设计"或"研究方案"
- **THEN** `RoutingDecision.agent_ids` SHALL 包含 `"research_planner"`
- **AND** `strategy` SHALL 等于 `"rule"`
- **AND** `confidence` SHALL >= 0.7

#### Scenario: 同行评审意图路由到 review_assistant
- **WHEN** 用户意图包含"审稿"或"评审意见"或"回复审稿"
- **THEN** `RoutingDecision.agent_ids` SHALL 包含 `"review_assistant"`
- **AND** `strategy` SHALL 等于 `"rule"`
- **AND** `confidence` SHALL >= 0.7

### Requirement: TaskRouter LLM 兜底路由
当规则路由 `confidence < 0.7` 时，`TaskRouter.route()` SHALL 调用 `model_resolver.chat(purpose="planning")` 分析用户意图，输出 JSON 格式路由决策；LLM 路由的可用 Agent 列表 SHALL 与内置规则表保持同步，包含全部 9 个 Specialist Agent；LLM 调用失败时 SHALL 返回规则路由结果（不抛出异常）。

#### Scenario: 规则不足时触发 LLM 路由
- **WHEN** 规则路由 `confidence < 0.7`
- **AND** `TaskRouter` 已配置 LLM 路由（`enable_llm_fallback=True`）
- **THEN** `strategy` SHALL 等于 `"llm"`
- **AND** 返回的 `RoutingDecision` SHALL 包含至少一个 `agent_id`

#### Scenario: 单次和批量路由 Prompt 均包含全部 9 个 Agent
- **WHEN** LLM 兜底路由（单次或批量）被触发
- **THEN** 发送给 LLM 的 Prompt SHALL 包含全部 9 个 Specialist Agent 的 ID 和描述
- **AND** 包括 `citation_manager`、`research_planner`、`review_assistant`
- **AND** 单次路由 Prompt（`_LLM_ROUTING_PROMPT`）和批量路由 Prompt（`_LLM_BATCH_ROUTING_PROMPT`）SHALL 保持 Agent 列表一致

#### Scenario: LLM 路由失败时降级
- **WHEN** `model_resolver.chat()` 抛出异常或超时
- **THEN** `TaskRouter.route()` SHALL 返回规则路由结果
- **AND** SHALL 不抛出异常
