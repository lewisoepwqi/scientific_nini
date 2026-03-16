## Why

Phase 0/1 完成了 Bug 修复和基础路由建设，意图体系的覆盖率已从 6/9 提升到 9/9，同义词可外置维护。但系统在以下三个精度维度仍有明显不足：（1）复合查询（"先做相关性分析，然后画散点图"）只能识别首个意图，第二个意图被丢弃；（2）差异分析类请求无法区分具体检验类型（配对 t 检验 vs. 独立样本 t 检验 vs. 非参数检验），导致 `tool_hints` 不包含具体工具建议，LLM 需要额外轮次确认；（3）澄清策略在有数据集的场景下仍频繁追问，影响分析流畅度。

## What Changes

- **新增** `src/nini/intent/multi_intent.py`：规则驱动的多意图检测模块，支持顺序（先…然后…）和并行（同时、顺便）两类复合查询，无多意图时返回 `None`
- **修改** `TaskRouter.route()`：多意图时调用 `route_batch()` 获取各子意图路由结果，将所有子结果合并为单个 `RoutingDecision`（合并 `agent_ids` 与 `tasks` 列表），不改变 `route()` 返回类型
- **新增** `src/nini/intent/subtypes.py`：差异分析子检验类型映射表 `_SUBTYPE_MAP`，识别结果注入 `IntentAnalysis.tool_hints` 首位
- **修改** `OptimizedIntentAnalyzer._apply_clarification_policy()`：有已加载数据集时，对数据分析类候选降低澄清触发阈值（relative_gap 从 0.25 收紧到 0.15）
- **修改** `AgentRunner._maybe_handle_intent_clarification()`：从 `session.datasets` 判断是否有已加载数据集，将 `has_datasets` 传入 `analyze()`

## Capabilities

### New Capabilities

- `multi-intent-detection`：多意图检测——规则识别顺序/并行复合查询，拆分为子任务列表路由
- `statistical-subtype`：统计子检验类型识别——在差异分析意图中进一步区分具体检验类型，注入 `tool_hints`

### Modified Capabilities

（无现有 spec 级别行为变更）

## Impact

- `src/nini/intent/multi_intent.py`（新建）：多意图检测逻辑
- `src/nini/intent/subtypes.py`（新建）：子检验类型映射表与识别函数
- `src/nini/agent/router.py`：`route()` 方法增加多意图检测前置调用
- `src/nini/intent/optimized.py`：`_apply_clarification_policy()` 增加数据集感知逻辑；`analyze()` 新增 `has_datasets` 参数并调用子类型识别更新 `tool_hints`
- `src/nini/agent/runner.py`：`_maybe_handle_intent_clarification()` 传入 `has_datasets=bool(session.datasets)`
- 无 API 变更，无数据库迁移，无新外部依赖
