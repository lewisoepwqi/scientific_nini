## Context

C1 实现了"路由决策驱动并行/串行分叉"，但两种路径都是扁平的——所有任务同批执行（并行）或逐一执行（串行）。科研工作流需要更精细的控制：某些任务可以并行（数据清洗 A 和数据清洗 B），而另一些必须等待前者完成（统计分析依赖清洗后的数据）。

`task_manager.py:81` 已有 `group_into_waves()` 方法（完整的 Kahn 算法，含循环依赖退化处理），但从未被派发路径调用。本 change 的核心工作是建立从 `dispatch_agents` → `DagExecutor` → `group_into_waves()` → `spawn_batch()` 的调用链。`DagExecutor` 设计为纯计算类（无状态），在 `execute()` 中直接实例化，不纳入依赖注入体系。

## Goals / Non-Goals

**Goals:**
- `dispatch_agents` 支持带 `depends_on` 的任务格式，LLM 可声明任务间依赖
- 同一 wave 内任务并行执行，wave 间串行且结果互相注入
- `fusion.py` 的 `_hierarchical()` 去掉不必要的串行批次等待

**Non-Goals:**
- 不支持条件分支（根据前一个 wave 的结果决定下一个 wave 的任务集合）
- 不实现 YAML 工作流文件格式
- 不实现循环依赖以外的 DAG 校验（任务数量限制、深度限制等由上层调用方控制）

## Decisions

### 决策 1：`tasks` 参数的两种格式兼容策略

旧格式（C1 后）：`tasks: list[str]`
新格式：`tasks: list[str | dict]`，其中 dict 格式为 `{"task": str, "id": str, "depends_on": list[str]}`

**兼容规则**：
- 字符串元素：自动分配 `id`（`t1`、`t2`...），`depends_on=[]`
- 字典元素：使用声明的 `id` 和 `depends_on`
- 混合输入：字符串和字典可混用
- 当所有任务的 `depends_on` 均为空时，走 C1 的并行/串行路径（不经过 `DagExecutor`），保持现有行为不变

### 决策 2：wave 间结果注入格式

```python
# wave N 完成后，将结果摘要注入 wave N+1 的任务描述
def _inject_context(next_wave_tasks: list[Task], completed_results: list[SubAgentResult]) -> list[Task]:
    context_lines = [
        f"[{r.agent_id}] {r.summary[:200]}"  # 截断摘要，防止上下文膨胀
        for r in completed_results if r.success and r.summary
    ]
    if not context_lines:
        return next_wave_tasks
    context_prefix = "前序 Agent 结果摘要：\n" + "\n".join(context_lines) + "\n\n"
    return [Task(task=context_prefix + t.task, id=t.id, depends_on=t.depends_on) for t in next_wave_tasks]
```

摘要截断为 200 字符，防止多个 wave 累积的上下文导致任务描述膨胀。

### 决策 3：`DagExecutor` 的循环依赖处理

`group_into_waves()` 使用 Kahn 算法（BFS 拓扑排序），循环依赖时返回空 wave 集合（剩余节点无法被排入任何 wave）。`DagExecutor` 检测到此情况时：
- 记录 ERROR 日志，列出涉及循环的任务 ID
- 回退到按原始顺序串行执行所有任务（退化为 C1 的串行路径）
- 在 `ToolResult.metadata` 中标注 `"dag_error": "circular_dependency"`

### 决策 4：`_hierarchical()` 批次并行化

直接将 `for batch in batches: await self._summarize(batch)` 改为：
```python
batch_results = list(await asyncio.gather(*(self._summarize(b) for b in batches)))
```
各批次输入独立（不同的 `SubAgentResult` 子集），无副作用，可安全并行。

### 决策 5：LLM routing prompt 的依赖分析

在 `_LLM_BATCH_ROUTING_PROMPT` 末尾增加一段：
```
如果某个任务需要其他任务的输出才能执行，请在该任务的路由结果中添加 "depends_on": ["被依赖的任务 ID"]。
没有依赖关系时，不包含 "depends_on" 字段。
```

这是软性约束（LLM 可能忽略），但与工具层的强制依赖声明互补——当 LLM 通过工具参数显式声明依赖时，不依赖路由层的推断。

## Risks / Trade-offs

- **LLM 不总是声明正确的 `depends_on`**：这是软约束；用户仍可通过工具参数显式声明来覆盖 → 接受，错误声明最坏结果是并行执行（退化为 C1 行为）
- **摘要注入膨胀上下文**：200 字符截断 × N 个 wave 可能累积 → 缓解：仅注入成功任务的摘要；后续可改为仅注入"与下一任务相关的"摘要（由 LLM 判断相关性，但成本更高）
- **`group_into_waves()` 已有实现，但未经生产验证**：需在测试中覆盖常见拓扑结构（链式、扇出、扇入、菱形）

## Migration Plan

**前提**：C1 已合并。

1. 新建 `src/nini/agent/dag_executor.py`（`DagExecutor` 类）
2. 新建 `tests/test_dag_executor.py`（单元测试覆盖拓扑结构 + 循环依赖回退）
3. 修改 `dispatch_agents.py`：`tasks` 参数解析 + DAG 路径分叉逻辑
4. 修改 `router.py`：batch routing prompt 追加依赖分析指令
5. 修改 `fusion.py`：`_hierarchical()` 并行化
6. 全量测试验证
