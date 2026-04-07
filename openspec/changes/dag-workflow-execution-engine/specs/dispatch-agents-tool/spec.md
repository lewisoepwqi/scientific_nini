## MODIFIED Requirements

### Requirement: DispatchAgentsTool 工具接口
系统 SHALL 提供 `DispatchAgentsTool`，`tasks` 参数 SHALL 支持两种格式（可混用）：
1. 字符串格式（旧格式）：`"任务描述"`，系统自动分配 `id`（`t1`、`t2`...），`depends_on=[]`
2. 对象格式（新格式）：`{"task": "任务描述", "id": "my_id", "depends_on": ["other_id"]}`

执行路径 SHALL 按以下逻辑分叉：
- 所有任务 `depends_on` 均为空 → 走 C1 的并行/串行路径（`RoutingDecision.parallel` 决定）
- 任意任务含非空 `depends_on` → 走 DAG 路径（`DagExecutor` 拓扑波次执行）

#### Scenario: 旧格式字符串兼容
- **WHEN** LLM 传入 `tasks=["清洗数据", "统计分析"]`（纯字符串列表）
- **THEN** 系统 SHALL 按 C1 的并行/串行逻辑执行（无 DAG 路径）
- **AND** 行为 SHALL 与 C1 实现后完全一致

#### Scenario: 对象格式触发 DAG 执行
- **WHEN** LLM 传入 `tasks=[{"task":"清洗数据","id":"clean"},{"task":"统计分析","id":"stat","depends_on":["clean"]}]`
- **THEN** 系统 SHALL 通过 `DagExecutor` 执行：先执行 "clean"，完成后再执行 "stat"
- **AND** "stat" 的任务描述 SHALL 包含 "clean" 任务的结果摘要

#### Scenario: 无效 depends_on 引用时降级
- **WHEN** 任务声明 `depends_on: ["nonexistent_id"]`
- **THEN** 系统 SHALL 记录 WARNING 并忽略无效依赖，按无依赖处理该任务
- **AND** SHALL 不抛出异常
