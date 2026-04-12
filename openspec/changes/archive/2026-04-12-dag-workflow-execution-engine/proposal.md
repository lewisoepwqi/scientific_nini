## Why

当前 `dispatch_agents` 工具只支持扁平的并行/串行派发（C1 实现后），无法表达任务之间的依赖关系（"任务 B 需要任务 A 的输出"）。对于科研数据分析中常见的流水线型工作流（数据清洗 → 统计分析 → 结果可视化），LLM 只能手动分多次调用 `dispatch_agents`，失去了统一编排的能力，也无法在 wave 间进行结果注入。此外，`TaskItem.depends_on` 字段和 `group_into_waves()` 方法虽已实现，但从未被派发路径消费，是完整的死代码。

## What Changes

- **`dispatch_agents` 工具扩展 `tasks` 参数格式**：支持对象格式 `{"task": str, "id": str, "depends_on": list[str]}`（可与旧格式 `list[str]` 向下兼容），允许 LLM 声明任务间依赖
- **`agent/dag_executor.py`（新建）**：实现 `DagExecutor` 类，接受带依赖声明的任务列表，通过拓扑排序将任务分组为执行波次（wave），同一 wave 内并行（调用 `spawn_batch()`），wave 间串行，并将前一 wave 的结果摘要注入下一 wave 的任务描述
- **连通 `TaskItem.depends_on` → `group_into_waves()` → `spawn_batch()` 链路**：`DagExecutor` 消费 `task_manager.group_into_waves()` 的结果作为并行批次
- **`ResultFusionEngine._hierarchical()` 批次并行化**：各批次之间无依赖，改为 `asyncio.gather()` 并行执行，消除不必要的串行等待
- **LLM batch routing prompt 增加依赖分析要求**：在 `_LLM_BATCH_ROUTING_PROMPT` 中要求 LLM 判断任务间是否存在依赖，依赖存在时通过 `depends_on` 字段声明

## Capabilities

### New Capabilities
- `dag-executor`：定义基于拓扑排序的 wave 执行引擎，包括任务依赖图构建、波次分组、wave 间结果注入协议

### Modified Capabilities
- `dispatch-agents-tool`：`tasks` 参数新增对象格式，支持 `id` 和 `depends_on` 字段；执行路径新增 DAG 分支（当任何任务含 `depends_on` 时走 DAG 路径，否则走 C1 的并行/串行路径）
- `result-fusion-engine`：`_hierarchical()` 各批次改为并行执行

## Impact

- **受影响代码**：
  - `src/nini/agent/dag_executor.py`（新建，~120 行）
  - `src/nini/tools/dispatch_agents.py`（`tasks` 参数解析 + DAG 路径分叉）
  - `src/nini/agent/router.py`（`_LLM_BATCH_ROUTING_PROMPT` 增加依赖分析指令）
  - `src/nini/agent/fusion.py`（`_hierarchical()` 批次并行化）
- **受影响测试**：
  - `tests/test_spawner.py`（新增 DAG 执行波次测试）
  - `tests/test_fusion.py`（hierarchical 批次并行验证）
  - 新增 `tests/test_dag_executor.py`
- **非目标**：不实现条件分支（`condition` 字段）；不实现 YAML 工作流文件（P004 中的更长期规划）；不支持循环依赖检测之外的 DAG 校验（如最大并发度限制）
- **依赖前提**：依赖 C1（fix-dispatch-parallel-serial-chain）已合并（`spawn_batch()` 和 `spawn()` 的语义已对齐）
