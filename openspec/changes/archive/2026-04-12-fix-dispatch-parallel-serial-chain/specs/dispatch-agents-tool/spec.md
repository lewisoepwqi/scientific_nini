## MODIFIED Requirements

### Requirement: DispatchAgentsTool 工具接口
系统 SHALL 提供 `DispatchAgentsTool`，继承 `src/nini/tools/base.py:Tool`，名称为 `"dispatch_agents"`；参数：`tasks: list[str]`（必填，需要并行处理的任务描述列表）、`context: str`（可选，背景信息）；`execute(session, tasks, context="")` SHALL 依次调用 TaskRouter → SubAgentSpawner → ResultFusionEngine，返回 `ToolResult(success=True, message=fusion_result.content)`。

执行策略 SHALL 由路由层的 `RoutingDecision.parallel` 字段决定：
- `parallel=True`：调用 `SubAgentSpawner.spawn_batch()` 并行执行所有子任务
- `parallel=False`：按顺序逐一调用 `SubAgentSpawner.spawn()`（串行执行，无上下文注入——上下文注入属于 DAG 工作流特性，由后续 change 实现）

#### Scenario: parallel=True 时并行执行所有子任务
- **WHEN** `RoutingDecision.parallel` 为 `True`
- **THEN** 系统 SHALL 通过 `spawn_batch()` 并行执行所有任务
- **AND** 返回的 `ToolResult.metadata["fusion_strategy"]` SHALL 包含融合策略名称

#### Scenario: parallel=False 时串行执行
- **WHEN** `RoutingDecision.parallel` 为 `False`
- **THEN** 系统 SHALL 按任务列表顺序逐一调用 `spawn()`
- **AND** 最终返回所有任务结果的融合摘要
- **AND** 本阶段 SHALL NOT 将前一个任务的 summary 注入下一个任务描述（该特性保留给 DAG 工作流 change）

#### Scenario: tasks 为空时返回空结果
- **WHEN** 调用 `execute(session, tasks=[])`
- **THEN** 返回 `ToolResult(success=True, message="")` 或包含提示信息
- **AND** SHALL 不抛出异常
