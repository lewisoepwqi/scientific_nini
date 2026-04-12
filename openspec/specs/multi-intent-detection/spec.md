# Capability: multi-intent-detection

## Purpose

检测用户查询中的多意图模式，区分顺序型复合查询与并行型复合查询，为路由层提供结构化的子意图列表及分类信息，避免误判主从语义关系为独立并行。

## Requirements

### Requirement: detect_multi_intent 函数识别顺序复合查询

`src/nini/intent/multi_intent.py` SHALL 提供 `detect_multi_intent(query: str) -> list[str] | None` 函数。当查询包含顺序标记词（"先…然后…"/"首先…其次…"/"接着"等）时，返回按顺序排列的子意图字符串列表；无多意图时返回 `None`。

#### Scenario: 顺序复合查询返回子意图列表（含标点）

- **WHEN** 输入"先帮我做相关性分析，然后画散点图"
- **THEN** `detect_multi_intent()` 返回包含两个子字符串的列表，顺序对应相关性分析和可视化

#### Scenario: 顺序复合查询无标点时仍能识别

- **WHEN** 输入"先做相关性分析然后画散点图"（连接词之间无标点）
- **THEN** `detect_multi_intent()` 返回包含两个子字符串的列表（通过连接词分割）

#### Scenario: 单一意图查询返回 None

- **WHEN** 输入"帮我做一个差异分析"
- **THEN** `detect_multi_intent()` 返回 `None`

#### Scenario: 并行复合查询被识别

- **WHEN** 输入"同时帮我做相关分析和画柱状图"
- **THEN** `detect_multi_intent()` 返回包含两个子字符串的列表

---

### Requirement: 多意图并行标记词集合
`_PARALLEL_MARKERS` 正则表达式 SHALL 仅包含语义上真正独立并行的连接词：`同时`、`另外还`、`以及同时`。`顺便` SHALL 从并行标记词中移除（语义为主从关系而非独立并行），不再触发并行分类。

#### Scenario: "顺便"不触发并行分类
- **WHEN** 用户输入"分析数据，顺便帮我画个图"
- **THEN** `detect_multi_intent()` SHALL NOT 返回 `is_parallel=True` 的分类
- **AND** 系统 SHALL 按单一意图或顺序意图处理该请求

#### Scenario: "同时"触发并行分类
- **WHEN** 用户输入"同时进行数据清洗和统计分析"
- **THEN** `detect_multi_intent()` SHALL 返回多个子意图
- **AND** 对应的并行标记 SHALL 被正确识别

---

### Requirement: 并/串行标记互斥保存
`detect_multi_intent()` 在执行标点分割（策略 1）前，SHALL 先计算并保存 `is_parallel` 和 `is_sequential` 的布尔值。策略 1 分割后，返回的子意图列表 SHALL 附带对应的分类信息，供调用方（`router.py`）使用，而非由调用方重复扫描原始字符串。

#### Scenario: 标点分割路径保留分类信息
- **WHEN** 输入同时命中并行标记和串行标记（如"同时做A，然后做B"）
- **THEN** 标点分割结果 SHALL 附带 `is_parallel=True` 和 `is_sequential=True` 两个标记
- **AND** 调用方可根据业务规则决定如何处理冲突（优先串行）

#### Scenario: 仅命中串行标记时分类明确
- **WHEN** 输入仅命中串行标记（如"先清洗数据，然后做统计分析"）
- **THEN** `detect_multi_intent()` 的返回结果 SHALL 附带 `is_sequential=True, is_parallel=False`

---

### Requirement: TaskRouter.route 在检测到多意图时合并路由结果，返回类型不变

`TaskRouter.route()` SHALL 在路由前调用 `detect_multi_intent()`；当返回非 `None` 时，将子意图列表传入 `route_batch()`，将所有子 `RoutingDecision` 合并（`agent_ids` 与 `tasks` 扁平合并，`confidence` 取最小值，`strategy="multi_intent"`），返回合并后的单个 `RoutingDecision`，`route()` 返回类型不变。

#### Scenario: 多意图查询触发 route_batch 并返回合并决策

- **WHEN** `route()` 收到含顺序标记的两段复合查询
- **THEN** 内部调用 `route_batch(sub_intents)`，返回 `strategy == "multi_intent"` 的 `RoutingDecision`，`agent_ids` 包含所有子意图的路由目标

#### Scenario: 无多意图时 route 行为不变

- **WHEN** `route()` 收到普通单意图查询
- **THEN** 行为与 Phase 0 实现完全一致，`strategy` 为 `"rule"` 或 `"llm"`，不为 `"multi_intent"`
