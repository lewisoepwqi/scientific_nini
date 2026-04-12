## Context

`dispatch_agents` 是 Nini 多 Agent 系统的唯一入口工具。现有调用链为：

```
DispatchAgentsTool.execute()
  → _build_task_pairs()         # 为每个任务路由 Agent
  → spawn_batch()               # 无条件并行执行所有任务
  → fuse()                      # 融合结果
```

路由层（`TaskRouter.route()`）返回 `RoutingDecision`，其中 `parallel` 字段明确标注"这批任务是否可并行"。但 `_build_task_pairs()` 目前只提取 `(agent_id, task)` 元组，`parallel` 字段在向上传递时被丢弃，`spawn_batch()` 对此一无所知。

与此同时，`SubSession` 对父会话 `datasets` 的共享引用、产物回写的 `dict.update()` 语义，以及 `TaskItem.update_tasks()` 丢弃 `depends_on` 字段，是三个独立但同属"状态隔离"范畴的漏洞，在同一次改动中修复成本最低。

## Goals / Non-Goals

**Goals:**
- `RoutingDecision.parallel` 成为执行层的真实控制信号（而非装饰性元数据）
- 并行任务走 `spawn_batch()`，串行任务按顺序逐一调用 `spawn()`
- `datasets` 隔离从"语义只读"升级为"代码层浅拷贝保证"
- 产物回写改为命名空间键，消除多 Agent 同名产物的静默覆盖
- `depends_on` 字段在任务状态更新全程保持完整

**Non-Goals:**
- 不实现 DAG 依赖图执行引擎（由 `dag-workflow-execution-engine` change 负责）
- 不修改 `dispatch_agents` 工具的 LLM 可见接口（`tasks`/`context` 参数保持不变）
- 不对 `datasets` 做深拷贝（大型 DataFrame 不需要，且成本过高）
- 不改变 `ResultFusionEngine` 的融合策略

## Decisions

### 决策 1：执行策略分叉点选在 `execute()` 而非 `spawn_batch()`

**选项 A**：修改 `spawn_batch()` 使其接受 `parallel` 参数（在 spawner 层分叉）
**选项 B**：在 `execute()` 中根据 `parallel` 决定调用 `spawn_batch()` 还是循环调用 `spawn()`（在工具层分叉）

**选择 B**，原因：
- `spawn_batch()` 是通用的并行执行原语，它不应关心"是否应该并行"——这是上层策略
- 工具层分叉保持 spawner 的职责单一（执行并发控制，而非策略决策）

**注意**：规则路由（`_rule_route()`）命中多 Agent 时，`parallel` 保持默认 `False`，不自动设为 `True`——规则路由基于关键词匹配，无法判断命中的任务是否真正独立。`parallel=True` 仅由 LLM 路由明确判断后设置（C3 的 `depends_on` 机制提供更精确的独立性声明）。

**串行路径不实现上下文注入**：串行执行时，本 change 仅保证任务按顺序执行，不将前一个任务的 `summary` 注入下一个任务描述。上下文注入属于 DAG 工作流的语义，由 `dag-workflow-execution-engine` change 统一实现，以避免两个 change 分别设计不兼容的注入格式。

### 决策 2：`_route_task_pairs()` 返回 `RoutingDecision` 而非 `list[tuple]`

为使 `execute()` 能感知 `parallel` 字段，`_build_task_pairs()` 需返回 `(task_pairs, decision)` 二元组。考虑到调用方已存在，选择扩展返回值而非新增函数，保持改动最小。

### 决策 3：产物命名空间键格式为 `{agent_id}.{original_key}`

**选项 A**：`{agent_id}_{original_key}`（下划线拼接）
**选项 B**：`{agent_id}.{original_key}`（点分隔）
**选项 C**：`{agent_id}/{original_key}`（路径风格）

**选择 B**（点分隔），原因：
- 点分隔在多语言中通用，且与 Python 属性访问风格一致
- 比斜杠更不容易与文件路径混淆
- 与现有 `artifacts` 键的命名习惯（小写英文 + 下划线）最兼容

**兼容性处理**：`session.artifacts` 仍然是 `dict`，调用方可通过 `artifacts["data_cleaner.result"]` 直接访问。对于依赖旧键名的调用方，需在代码层面手动迁移（全局搜索 `session.artifacts[`）。

### 决策 4：`datasets` 浅拷贝而非深拷贝

科研场景中 `datasets` 的值通常是 pandas `DataFrame`。深拷贝会在大数据集时引入显著内存开销（一个 100MB DataFrame 每个子 Agent 额外消耗 100MB）。浅拷贝足以防止键的增删污染父会话，而不防止 DataFrame 内容的原地修改（`df.iloc[0] = ...`）——这类情况在实际使用中极罕见，且子 Agent 工具调用通常产生新 DataFrame 而非原地修改。

### 决策 5：TOCTOU 修复通过预创建而非 setdefault

`Session.__init__()` 预创建 `subagent_stop_events: dict[str, asyncio.Event] = {}` 和 `sub_agent_snapshots: list = []`，而非在运行时懒初始化。优势：彻底消除竞态，无需修改读取代码；劣势：略微增加每个 Session 的初始内存，但影响可忽略。

## Risks / Trade-offs

- **命名空间键破坏现有访问模式** → 缓解：PR 中全局搜索 `session.artifacts["`，逐一确认受影响调用方；如有必要提供 `get_artifact(session, key)` 兼容辅助函数
- **串行路径增加延迟** → 这是正确行为；串行任务本来就应顺序执行，延迟是有依赖关系任务的必然代价
- **`RoutingDecision.parallel` 的路由准确性** → 路由层的误判会导致应串行的任务被并行执行（已由审计报告记录为 P1-3 问题，由后续 change 修复）；本 change 只建立执行层的消费机制

## Migration Plan

1. 新建 `feature/fix-dispatch-parallel-serial-chain` 分支
2. 修改 `router.py`（`parallel` 默认值 + 规则路由赋值）→ 更新对应单元测试
3. 修改 `spawner.py`（浅拷贝 + 命名空间回写 + Session 预创建）→ 更新 `test_spawner.py`
4. 修改 `dispatch_agents.py`（执行策略分叉）→ 更新集成测试
5. 修改 `task_manager.py`（`depends_on` 保持）→ 更新 `test_phase4_session_persistence.py`
6. 修改 `session.py`（恢复字段名对齐）
7. 全局搜索 `session.artifacts["` 确认调用方兼容性
8. 回滚策略：所有修改局限在 5 个文件内，git revert 单个 PR 即可完整回滚
