## Why

`RoutingDecision.parallel` 字段在路由层被精心计算，但在执行层从未被读取——`dispatch_agents` 的 `spawn_batch()` 无论路由决策为何都无条件并行派发所有子任务，导致有依赖关系的串行任务（如"先清洗数据再统计分析"）在并行执行时后任务拿到未处理数据而静默失败。此外，子会话对父会话 `datasets` 的共享引用、产物回写的 last-write-wins 覆盖、以及 `depends_on` 字段在任务状态更新时的静默丢弃，共同破坏了"并行前提：任务独立/只读/无状态冲突"的核心理念。

## What Changes

- **`dispatch_agents.py`**：读取 `RoutingDecision.parallel` 字段驱动执行策略——`parallel=true` 调用 `spawn_batch()`，`parallel=false` 按顺序逐一调用 `spawn()`；`_route_task_pairs()` 向上透传完整决策对象
- **`router.py`**：`RoutingDecision.parallel` 默认值从 `True` 改为 `False`（串行安全优先）；规则路由命中多 Agent 时，仅当各 Agent 职责正交时显式设置 `parallel=True`
- **`spawner.py`**：`SubSession` 构造时对 `datasets` 做浅拷贝（`dict(parent_session.datasets)`）；产物回写改为命名空间键（`{agent_id}.{key}`），同名键冲突时记录 WARNING；`subagent_stop_events` / `sub_agent_snapshots` 从懒初始化改为 `Session.__init__()` 预创建，消除 TOCTOU 竞态
- **`task_manager.py`**：`update_tasks()` 构造新 `TaskItem` 时保留 `depends_on` 字段
- **`session.py`**：修复任务恢复逻辑的字段名漂移（从读取 `updates` 键改为读取 `tasks` 键）

## Capabilities

### New Capabilities
<!-- 本 change 为纯修复性质，不引入新 Capability -->

### Modified Capabilities
- `dispatch-agents`：执行策略从"无条件并行"改为"由 `RoutingDecision.parallel` 驱动的并行/串行分叉"；`parallel` 字段语义从装饰性标注升级为执行控制信号
- `sub-agent-session`：`datasets` 隔离从共享引用升级为浅拷贝视图（子 Agent 只读语义得到代码层保证）；产物回写从 last-write-wins 升级为命名空间隔离

## Impact

- **受影响代码**：
  - `src/nini/tools/dispatch_agents.py`（核心：执行策略分叉，`_route_task_pairs` 返回值扩展）
  - `src/nini/agent/router.py`（`parallel` 默认值 + 规则路由多命中时的 `parallel` 赋值逻辑）
  - `src/nini/agent/spawner.py`（datasets 浅拷贝 + 命名空间回写 + Session 预创建）
  - `src/nini/agent/task_manager.py`（`depends_on` 字段保持）
  - `src/nini/agent/session.py`（恢复字段名对齐）
  - `src/nini/agent/sub_session.py`（如需配合 datasets 初始化调整）
- **受影响测试**：
  - `tests/test_spawner.py`（新增串行执行路径、命名空间回写、浅拷贝隔离测试）
  - `tests/test_fusion.py`（回写冲突场景验证）
  - `tests/test_phase4_session_persistence.py`（任务恢复字段名修复验证）
- **破坏性变更风险**：命名空间键（`agent_id.key`）变更会影响通过 `session.artifacts["key"]` 直接访问产物的调用方；需全局搜索受影响访问路径，或提供向后兼容的别名层
- **非目标**：不实现 DAG 依赖图执行引擎；不修改 `dispatch_agents` 工具的外部 LLM 接口；不引入新外部依赖
