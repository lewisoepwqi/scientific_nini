## 1. 路由层修复（router.py）

- [x] 1.1 将 `RoutingDecision.parallel` 默认值从 `True` 改为 `False`
- [x] 1.2 `_rule_route()` 命中多 Agent 时，`parallel` 保持默认值 `False`（规则路由基于关键词匹配，无法判断任务间依赖关系；`parallel=True` 应由 LLM 路由决定，或由用户通过 C3 的 `depends_on` 显式声明）
- [x] 1.3 更新 `router.py` 中所有假设 `parallel=True` 的测试断言

## 2. 执行策略分叉（dispatch_agents.py）

- [x] 2.1 修改 `_route_task_pairs()` / `_build_task_pairs()` 返回完整 `RoutingDecision`（或至少传递 `parallel` 字段）
- [x] 2.2 在 `execute()` 中根据 `RoutingDecision.parallel` 分叉：`True` → `spawn_batch()`，`False` → 循环 `spawn()`
- [x] 2.3 补充集成测试：串行路径下任务按顺序执行，第 N+1 个任务在第 N 个完成后才开始（上下文注入不在本 change 范围内）

## 3. 数据隔离修复（spawner.py）

- [x] 3.1 `_execute_agent()` 中构造 `SubSession` 时将 `datasets=dict(parent_session.datasets)`（浅拷贝）
- [x] 3.2 `spawn_batch()` 产物回写改为命名空间键 `{result.agent_id}.{key}`；同名原始键冲突时记录 WARNING
- [x] 3.3 在 `Session.__init__()` 中预创建 `subagent_stop_events: dict = {}` 和 `sub_agent_snapshots: list = []`，删除 `_spawn_impl()` 中的懒初始化代码
- [x] 3.4 更新 `test_spawner.py`：新增 datasets 浅拷贝隔离测试、命名空间回写测试、多 Agent 同名键冲突测试

## 4. 任务状态持久化修复（task_manager.py + session.py）

- [x] 4.1 `update_tasks()` 构造新 `TaskItem` 时传递 `depends_on=task.depends_on`
- [x] 4.2 `session.py` 任务恢复逻辑：将读取 `"updates"` 键改为读取 `"tasks"` 键（字段名漂移修复）
- [x] 4.3 更新 `test_phase4_session_persistence.py`：验证任务恢复后 `depends_on` 字段保持完整

## 5. 兼容性验证

- [x] 5.1 全局搜索 `session.artifacts["` 和 `session.documents["`，逐一确认调用方是否需要更新为命名空间键格式
- [x] 5.2 运行 `pytest -q tests/test_spawner.py tests/test_fusion.py tests/test_phase4_session_persistence.py` 全部通过
- [x] 5.3 运行 `python scripts/check_event_schema_consistency.py` 通过（事件 schema 无变化）
- [x] 5.4 运行 `pytest -q` 全量测试通过
