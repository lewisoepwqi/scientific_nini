## 1. 多意图检测模块

- [x] 1.1 新建 `src/nini/intent/multi_intent.py`，定义顺序标记正则 `_SEQUENTIAL_MARKERS = re.compile(r"先.{0,10}(然后|再|接着|之后)|首先.{0,10}(其次|然后|再)")`
- [x] 1.2 定义并行标记正则 `_PARALLEL_MARKERS = re.compile(r"同时|顺便|另外还|以及同时")`
- [x] 1.3 定义辅助分割正则 `_SENTENCE_SPLIT = re.compile(r"[，。；！？,.;!?]+")`（用于有标点的查询），以及连接词分割正则 `_CONNECTOR_SPLIT = re.compile(r"然后|接着|之后|再(?=\S)|其次")`（用于无标点的顺序查询）
- [x] 1.4 实现 `detect_multi_intent(query: str) -> list[str] | None`：先检测 `_SEQUENTIAL_MARKERS` 或 `_PARALLEL_MARKERS` 是否命中；若命中，依次尝试（1）用 `_SENTENCE_SPLIT` 分割（有标点场景），（2）用 `_CONNECTOR_SPLIT` 分割（无标点场景，如"先做相关分析然后画散点图"）；过滤长度 <= 3 的片段，片段数 >= 2 时返回列表，否则返回 `None`
- [x] 1.5 在 `src/nini/intent/__init__.py` 中导出 `detect_multi_intent`

## 2. 多意图路由集成

- [x] 2.1 在 `src/nini/agent/router.py` 顶部添加 `from nini.intent import detect_multi_intent`
- [x] 2.2 修改 `TaskRouter.route()` 方法：在 `_rule_route(intent)` 之前调用 `detect_multi_intent(intent)`，若返回非 `None`（含 N 个子意图），则调用 `await self.route_batch(sub_intents)` 获取 N 个 `RoutingDecision`，将它们合并为单个 `RoutingDecision`：`agent_ids` 为各子决策 agent_ids 的扁平列表、`tasks` 为各子决策 tasks 的扁平列表、`confidence` 取最小值、`strategy="multi_intent"`、`parallel` 根据是并行标记（True）还是顺序标记（False）设置；返回该合并结果，**`route()` 返回类型不变**（`RoutingDecision`）
- [x] 2.3 确认合并后的 `RoutingDecision` 中 `agent_ids` 与 `tasks` 包含所有子意图的路由结果（长度等于子意图数量之和），`strategy` 为 `"multi_intent"`，不新增任何返回类型或方法签名

## 3. 差异分析子类型识别模块

- [x] 3.1 新建 `src/nini/intent/subtypes.py`，定义 `_SUBTYPE_MAP: dict[str, list[str]]`，包含以下条目：
  - `paired_t_test`：配对t检验、重复测量、前后对比、paired、配对样本
  - `independent_t_test`：独立样本、两组比较、独立t检验、两独立样本
  - `one_way_anova`：单因素方差、one-way anova、多组比较、三组及以上
  - `mann_whitney`：mann-whitney、Mann-Whitney、秩和检验、非参数两样本
  - `kruskal_wallis`：kruskal、Kruskal-Wallis、非参数多组
- [x] 3.2 实现 `get_difference_subtype(query: str) -> str | None`：遍历 `_SUBTYPE_MAP`，返回首个关键词命中的子类型标识符，无命中时返回 `None`
- [x] 3.3 在 `src/nini/intent/__init__.py` 中导出 `get_difference_subtype`

## 4. 子类型注入 analyze()

- [x] 4.1 在 `src/nini/intent/optimized.py` 顶部添加 `from nini.intent.subtypes import get_difference_subtype`
- [x] 4.2 在 `analyze()` 的 `_build_tool_hints()` 调用之后，检查 Top-1 候选是否为 `difference_analysis`；若是且 `get_difference_subtype(user_message)` 返回非 `None`，将子类型工具名插入 `analysis.tool_hints` 首位
- [x] 4.3 `analyze()` 方法签名在现有 `*` 之后新增关键字参数 `has_datasets: bool = False`，并将其传入 `_apply_clarification_policy(analysis, has_datasets=has_datasets)`
- [x] 4.4 修改 `_apply_clarification_policy(self, analysis, has_datasets: bool = False)`：当 `has_datasets=True` 且 Top-1 候选名称属于数据分析类白名单 `{"difference_analysis", "correlation_analysis", "regression_analysis", "data_exploration", "data_cleaning"}` 时，同时调整两处阈值：（1）策略 2（两候选接近）：`relative_gap < 0.25` 改为 `relative_gap < 0.15`；（2）策略 3（三候选接近）：`top1.score - top3.score < 3.0` 改为 `top1.score - top3.score < 2.0`
- [x] 4.5 在 `src/nini/agent/runner.py` 的 `_maybe_handle_intent_clarification()` 中，将现有 `analyze(user_message, capabilities=capability_catalog)` 调用改为 `analyze(user_message, capabilities=capability_catalog, has_datasets=bool(session.datasets))`；`session.datasets` 即 `Session.datasets: dict[str, pd.DataFrame]`，已有字段无需新增

## 5. 编写测试

- [x] 5.1 编写测试：`detect_multi_intent("先做相关性分析，然后画散点图")` 返回含两个元素的列表（有标点场景）
- [x] 5.2 编写测试：`detect_multi_intent("帮我做差异分析")` 返回 `None`
- [x] 5.3 编写测试：`detect_multi_intent("同时帮我做相关分析和画柱状图")` 返回含两个元素的列表
- [x] 5.4 编写测试：`detect_multi_intent("先做相关性分析然后画散点图")` 返回含两个元素的列表（无标点场景，验证 `_CONNECTOR_SPLIT` 生效）
- [x] 5.5 编写测试：`route()` 收到顺序复合查询时，返回 `RoutingDecision` 的 `strategy == "multi_intent"`，且 `agent_ids` 长度等于子意图数
- [x] 5.6 编写测试：`get_difference_subtype("帮我做配对t检验")` 返回 `"paired_t_test"`
- [x] 5.7 编写测试：`get_difference_subtype("Mann-Whitney 检验")` 返回 `"mann_whitney"`
- [x] 5.8 编写测试：`get_difference_subtype("帮我分析差异")` 返回 `None`
- [x] 5.9 编写测试：含"配对t检验"输入且 Top-1 为 difference_analysis 时，`tool_hints` 首位包含 paired 相关工具名
- [x] 5.10 编写测试（验证 `has_datasets` 阈值差异）：构造两个候选 `top1.score=10.0`（`difference_analysis`）、`top2.score=8.5`，`relative_gap=0.15`，满足 `top1 >= min_confidence(5.0)`；断言：`has_datasets=True` → `clarification_needed=False`（gap=0.15 不满足收紧阈值 `< 0.15`），`has_datasets=False` → `clarification_needed=True`（gap=0.15 满足默认阈值 `< 0.25`）
- [x] 5.11 运行 `pytest tests/ -q` 验证全部测试通过

## 6. 收尾

- [x] 6.1 运行 `black --check src tests` 格式检查，必要时格式化
- [x] 6.2 运行 `mypy src/nini` 验证无新增类型错误
- [x] 6.3 按 git workflow 规范提交并创建 PR，base 分支为 `main`
