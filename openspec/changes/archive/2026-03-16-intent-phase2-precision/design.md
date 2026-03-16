## Context

Phase 1 完成后意图体系覆盖率达到 9/9，但三个精度问题仍存在：

1. **多意图**：`TaskRouter.route()` 每次只处理单一意图字符串，"先做相关性分析，然后画散点图"这类复合查询，第二个意图在路由层被丢弃。
2. **子检验类型**：`difference_analysis` 命中后 `tool_hints` 只给出 `t_test`/`anova` 等通用工具，LLM 需要额外对话轮次确认具体检验类型（配对/独立/非参数）。
3. **澄清过频**：`_apply_clarification_policy` 用纯相对差距判断，不感知 session 上下文，当用户已上传数据时仍频繁追问"你是想做差异分析还是数据探索"。

## Goals / Non-Goals

**Goals:**
- 规则驱动的多意图检测（无需 Embedding），顺序/并行两类
- 差异分析子类型识别，结果注入 `tool_hints`，减少额外对话轮次
- 澄清策略感知数据集存在性，有数据时降低澄清阈值

**Non-Goals:**
- 不引入 Embedding 或外部 NLU
- 不实现超过 2 层的递归意图拆分
- 不修改 WebSocket 事件协议或前端
- 不实现基于用户历史的澄清记忆（留 Phase 3）

## Decisions

### 决策 1：多意图检测作为 router.py 的前置步骤，不侵入 analyze()；合并结果不改变返回类型

`detect_multi_intent(query)` 在 `TaskRouter.route()` 入口调用，返回子意图列表时调用 `route_batch(sub_intents)` 获取各子意图路由结果，然后将所有 `RoutingDecision` 合并：

```python
merged = RoutingDecision(
    agent_ids=[aid for d in batch for aid in d.agent_ids],
    tasks=[t for d in batch for t in d.tasks],
    confidence=min(d.confidence for d in batch),
    strategy="multi_intent",
    parallel=is_parallel,   # 顺序标记→False，并行标记→True
)
return merged
```

`RoutingDecision` 已有 `agent_ids: list[str]`、`tasks: list[str]`、`parallel: bool`，可直接承载多意图结果，**`route()` 返回类型不变**，调用方（runner）收到合并结果后按 `parallel` 字段决定顺序/并行执行子任务。

`multi_intent.py` 的测试完全独立，不依赖意图分析器初始化。

**备选**：在 `analyze()` 内部拆分 → 被否决，分析器只负责意图识别，路由决策不应在此层。
**备选**：修改 `route()` 返回 `list[RoutingDecision]` → 被否决，破坏现有调用方接口；现有字段已足够承载多意图信息。

### 决策 2：子类型识别在 `analyze()` 中调用，结果写入 `tool_hints`

新建 `intent/subtypes.py` 提供 `get_difference_subtype(query)` 函数，返回 `str | None`（如 `"paired_t_test"`）。`analyze()` 在构建 `tool_hints` 后，如果 Top-1 候选为 `difference_analysis`，追加子类型提示到 `tool_hints`。

写入 `tool_hints` 而非新字段，避免修改 `IntentAnalysis` 数据结构（最小改动）。

### 决策 3：澄清策略增加 `has_datasets: bool` 参数；明确数据分析类白名单

`analyze()` 增加关键字参数 `has_datasets: bool = False`，传入 `_apply_clarification_policy(analysis, has_datasets)`。当 `has_datasets=True` 且 Top-1 候选属于数据分析类白名单时，**策略 2**（两候选接近，`relative_gap < 0.25`）和**策略 3**（三候选接近，`top1.score - top3.score < 3.0`）均收紧阈值，减少澄清触发：

- 策略 2 阈值：`0.25` → `0.15`
- 策略 3 阈值：`3.0` → `2.0`（差距更小时才触发）

**数据分析类白名单**（`has_datasets` 阈值收紧仅对以下候选生效）：
`{"difference_analysis", "correlation_analysis", "regression_analysis", "data_exploration", "data_cleaning"}`

（`visualization`、`report_generation`、`article_draft` 不在白名单，这些能力的澄清触发行为不依赖数据集存在与否。）

**调用方更新**：`AgentRunner._maybe_handle_intent_clarification()` 在调用 `analyze()` 时同步传入 `has_datasets=bool(session.datasets)`，`analyze()` 接口向后兼容（默认 `False`）。

## Risks / Trade-offs

**[风险 1] 多意图拆分误切非复合查询** → "先分析后出图"可能将"先"识别为顺序标记而误拆。缓解：`_SEQUENTIAL_MARKERS` 要求"先"后有明确的连接词（"然后"/"再"/"接着"），单独"先"不触发拆分；测试覆盖常见误拆案例。

**[风险 2] 子类型识别误判降低分析准确性** → `_SUBTYPE_MAP` 词汇与通用词汇交叉（"重复"可以是"重复测量"也可以是"重复出现"）。缓解：子类型识别只注入 `tool_hints` 作为提示，不改变最终工具调用决策权（LLM 仍有最终判断）；误判最坏结果是工具提示不准确，不会导致错误执行。

**[风险 3] `has_datasets` 参数未被调用方传入** → 澄清策略退化为当前行为（`False` 时无变化）。缓解：在 `analyze()` 调用处同步更新一处调用（`api/routes.py` 的意图分析调用），其余调用不传参则保持默认行为不变。

## Migration Plan

1. `multi_intent.py` 和 `subtypes.py` 均为新增文件，不破坏现有代码
2. `analyze()` 的 `has_datasets` 参数有默认值 `False`，所有现有调用点无需修改
3. 回滚：删除两个新文件；`router.py` 和 `optimized.py` 的修改均可独立 `git revert`
