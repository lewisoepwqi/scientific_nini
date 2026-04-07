## 1. DagExecutor 核心实现

- [x] 1.1 新建 `src/nini/agent/dag_executor.py`：定义 `DagTask` dataclass（`task: str`、`id: str`、`depends_on: list[str]`、`agent_id: str`）和 `DagExecutor` 类
- [x] 1.2 实现 `DagExecutor.build_waves(tasks: list[DagTask]) -> list[list[DagTask]]`：将 `DagTask` 列表转换为 `TaskItem` 后调用已有的 `TaskManager.group_into_waves()`（Kahn 算法，`task_manager.py:81`）；若返回的 wave 数量小于任务数（循环依赖），记录 ERROR 并返回所有任务为单一波次（串行降级）
- [x] 1.3 实现 `DagExecutor.execute(waves, session, spawner, router) -> list[SubAgentResult]`：逐 wave 调用 `spawn_batch()`，wave 间注入前序摘要（截断 200 字符）
- [x] 1.4 新建 `tests/test_dag_executor.py`：覆盖链式依赖、扇出、扇入、菱形拓扑、循环依赖回退、无依赖等场景

## 2. dispatch_agents 工具扩展

- [x] 2.1 修改 `dispatch_agents.py`：解析 `tasks` 参数，支持字符串和字典混合格式；字符串自动补充 `id` 和 `depends_on=[]`
- [x] 2.2 在 `execute()` 中实现路径分叉：有 `depends_on` 时实例化 `DagExecutor` 执行；无 `depends_on` 时走 C1 的并行/串行路径
- [x] 2.3 在 `execute()` 内直接实例化 `DagExecutor`（无需构造函数注入——`DagExecutor` 是纯计算类，不持有状态，也不需要 mock）
- [x] 2.4 补充测试：验证旧格式字符串兼容、对象格式触发 DAG、无效 `depends_on` 引用的 WARNING 降级

## 3. 路由层 prompt 更新

- [x] 3.1 修改 `router.py:_LLM_BATCH_ROUTING_PROMPT`：在末尾追加依赖分析指令（"如果某任务需要其他任务的输出，请在路由结果中添加 depends_on 字段"）
- [x] 3.2 验证 prompt 变更不破坏现有路由单元测试

## 4. fusion.py 批次并行化

- [x] 4.1 修改 `fusion.py:_hierarchical()`：将 `for batch in batches: batch_fusion = await self._summarize(batch)` 改为 `batch_results = list(await asyncio.gather(*(self._summarize(b) for b in batches)))`
- [x] 4.2 更新 `tests/test_fusion.py`：验证 hierarchical 策略中多批次并发执行（可通过 mock 检测 `asyncio.gather` 被调用）

## 5. 集成验证

- [x] 5.1 端到端测试：3 个任务含链式依赖，验证执行顺序和摘要注入
- [x] 5.2 运行 `pytest -q tests/test_dag_executor.py tests/test_spawner.py tests/test_fusion.py` 全部通过
- [x] 5.3 运行 `python scripts/check_event_schema_consistency.py` 通过
- [x] 5.4 运行 `pytest -q` 全量测试通过（3 个预存失败 test_intent_phase2.py 与本次变更无关）
