## ADDED Requirements

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

### Requirement: TaskRouter.route 在检测到多意图时合并路由结果，返回类型不变

`TaskRouter.route()` SHALL 在路由前调用 `detect_multi_intent()`；当返回非 `None` 时，将子意图列表传入 `route_batch()`，将所有子 `RoutingDecision` 合并（`agent_ids` 与 `tasks` 扁平合并，`confidence` 取最小值，`strategy="multi_intent"`），返回合并后的单个 `RoutingDecision`，`route()` 返回类型不变。

#### Scenario: 多意图查询触发 route_batch 并返回合并决策

- **WHEN** `route()` 收到含顺序标记的两段复合查询
- **THEN** 内部调用 `route_batch(sub_intents)`，返回 `strategy == "multi_intent"` 的 `RoutingDecision`，`agent_ids` 包含所有子意图的路由目标

#### Scenario: 无多意图时 route 行为不变

- **WHEN** `route()` 收到普通单意图查询
- **THEN** 行为与 Phase 0 实现完全一致，`strategy` 为 `"rule"` 或 `"llm"`，不为 `"multi_intent"`
