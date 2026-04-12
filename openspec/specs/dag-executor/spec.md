# Capability: dag-executor

## Purpose

_已移除。_ `DagExecutor` 随 `simplify-multi-agent` 变更一起废弃（commit: "移除多 Agent 过度设计层"）。拓扑排序分 wave 执行、波次间结果注入等机制因从未被实际触发而移除。有序执行需求由主 Agent 多次调用 `dispatch_agents` 实现。详见 `multi-agent-dag` capability 的移除记录。

> 注：本 spec 中的需求由 `dag-workflow-execution-engine` 变更引入，随即被 `simplify-multi-agent` 变更全部移除。此 spec 保留为历史记录。

## Requirements

_所有要求已移除。此 spec 保留为历史记录。_

<!--

### Requirement: DagExecutor 拓扑波次执行
`DagExecutor` SHALL 接受带依赖声明的任务列表，通过拓扑排序（Kahn 算法）将任务分组为执行波次（wave），同一 wave 内的任务相互独立可并行执行，wave 间按依赖顺序串行推进。

#### Scenario: 链式依赖分为多个波次
- **WHEN** 任务列表为 `[{id:"A"}, {id:"B", depends_on:["A"]}, {id:"C", depends_on:["B"]}]`
- **THEN** `DagExecutor` SHALL 产生 3 个波次：wave1=[A]，wave2=[B]，wave3=[C]
- **AND** wave2 SHALL 在 wave1 完成后才开始执行

#### Scenario: 扇出依赖同一 wave 并行
- **WHEN** 任务列表为 `[{id:"A"}, {id:"B", depends_on:["A"]}, {id:"C", depends_on:["A"]}]`
- **THEN** `DagExecutor` SHALL 产生 2 个波次：wave1=[A]，wave2=[B, C]
- **AND** wave2 中的 B 和 C SHALL 并行执行

---

### Requirement: wave 间结果注入
`DagExecutor` 在执行下一 wave 前，SHALL 将前一 wave 所有成功任务的摘要注入下一 wave 各任务的描述前缀（格式：`前序 Agent 结果摘要：\n[agent_id] summary\n\n原始任务描述`）。单个摘要截断为 200 字符。

#### Scenario: 成功任务的摘要注入下一 wave
- **WHEN** wave1 中 Agent A 成功完成并产生摘要 "清洗完成，删除 3 行异常值"
- **THEN** wave2 的任务描述 SHALL 包含前缀 "前序 Agent 结果摘要：\n[agent_a] 清洗完成，删除 3 行异常值\n\n"

#### Scenario: 失败任务的摘要不注入
- **WHEN** wave1 中 Agent A 失败（`success=False`）
- **THEN** wave2 的任务描述 SHALL NOT 包含 Agent A 的摘要

---

### Requirement: 循环依赖检测与回退
`DagExecutor` SHALL 检测任务列表中的循环依赖；检测到循环时，SHALL 记录 ERROR 日志并回退到按原始顺序串行执行所有任务，在执行结果元数据中标注 `"dag_error": "circular_dependency"`。

#### Scenario: 循环依赖时串行执行并标注错误
- **WHEN** 任务列表包含循环依赖（A depends_on B，B depends_on A）
- **THEN** 系统 SHALL 记录包含任务 ID 的 ERROR 日志
- **AND** 所有任务 SHALL 按原始顺序串行执行（不中断）
- **AND** 返回的元数据 SHALL 包含 `"dag_error": "circular_dependency"`

-->
