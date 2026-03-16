## ADDED Requirements

### Requirement: get_difference_subtype 识别差异分析子检验类型

`src/nini/intent/subtypes.py` SHALL 提供 `get_difference_subtype(query: str) -> str | None` 函数，基于关键词映射表 `_SUBTYPE_MAP` 返回具体检验类型标识符（`"paired_t_test"` / `"independent_t_test"` / `"one_way_anova"` / `"mann_whitney"` / `"kruskal_wallis"`），无法识别时返回 `None`。

#### Scenario: 配对 t 检验关键词识别

- **WHEN** 输入"帮我做配对t检验，前后对比"
- **THEN** `get_difference_subtype()` 返回 `"paired_t_test"`

#### Scenario: 非参数检验关键词识别

- **WHEN** 输入"数据不正态，用 Mann-Whitney 检验"
- **THEN** `get_difference_subtype()` 返回 `"mann_whitney"`

#### Scenario: 无子类型词时返回 None

- **WHEN** 输入"帮我分析两组数据的差异"（无具体检验类型词）
- **THEN** `get_difference_subtype()` 返回 `None`

### Requirement: analyze() 将子检验类型注入 tool_hints

当 `OptimizedIntentAnalyzer.analyze()` 的 Top-1 候选为 `difference_analysis` 且 `get_difference_subtype()` 返回非 `None` 时，SHALL 将子类型工具名追加到 `IntentAnalysis.tool_hints` 列表首位。

#### Scenario: 配对 t 检验 tool_hints 包含 paired 工具

- **WHEN** 输入"前后配对t检验"且 Top-1 为 difference_analysis
- **THEN** `analysis.tool_hints` 首位包含与 `"paired_t_test"` 对应的工具名

### Requirement: analyze() 支持 has_datasets 参数降低澄清频率

`OptimizedIntentAnalyzer.analyze()` SHALL 接受关键字参数 `has_datasets: bool = False`。当 `has_datasets=True` 且 Top-1 候选属于数据分析类白名单（`difference_analysis`/`correlation_analysis`/`regression_analysis`/`data_exploration`/`data_cleaning`）时，策略 2（两候选接近）阈值从 0.25 收紧到 0.15，策略 3（三候选接近）阈值从 3.0 收紧到 2.0。

#### Scenario: 有数据集时相对差距恰好在两阈值之间不触发澄清

- **WHEN** `has_datasets=True`，Top-1 为 `difference_analysis`，`top1.score=10.0`，`top2.score=8.5`（`relative_gap=0.15`，`top1 >= 5.0`）
- **THEN** `analysis.clarification_needed` 为 `False`（gap=0.15 不满足收紧阈值 `< 0.15`）

#### Scenario: 无数据集时相同分数触发澄清

- **WHEN** `has_datasets=False`（默认），相同分数（`top1=10.0`，`top2=8.5`，`gap=0.15`）
- **THEN** `analysis.clarification_needed` 为 `True`（gap=0.15 满足默认阈值 `< 0.25`）

#### Scenario: 非数据分析类候选不受 has_datasets 影响

- **WHEN** `has_datasets=True`，Top-1 为 `article_draft`，相对差距 0.20
- **THEN** 阈值不收紧，行为与 `has_datasets=False` 相同
