## ADDED Requirements

### Requirement: Local trace persistence
系统 SHALL 将一次 harness 运行的关键轨迹持久化到本地存储，以支持后续回放、分析和问题复现。

#### Scenario: 运行结束后保存结构化 trace
- **WHEN** 一次 harness 运行结束，无论结果为完成、停止或阻塞
- **THEN** 系统 SHALL 保存该次运行的结构化 trace
- **AND** trace SHALL 包含关键事件序列、模型调用摘要、工具调用结果、completion check 结果和最终状态

#### Scenario: Trace 与索引可关联
- **WHEN** 系统写入一次新的运行 trace
- **THEN** 系统 SHALL 同步保存可检索的摘要索引
- **AND** 索引 SHALL 能关联回对应的 trace 明细记录

### Requirement: Replayable harness evaluation
系统 SHALL 提供基于本地 trace 的回放与评测能力，供维护者验证 harness 行为与回归风险。

#### Scenario: 维护者可以回放单次运行
- **WHEN** 维护者选择一条历史运行记录进行回放
- **THEN** 系统 SHALL 能重建该次运行的关键轨迹和结果摘要
- **AND** 回放过程 SHALL 可用于定位 completion、loop recovery 或协议层行为问题

#### Scenario: 评测结果可比较
- **WHEN** 维护者对多次运行执行 harness 评测
- **THEN** 系统 SHALL 输出可比较的结果摘要
- **AND** 摘要 SHALL 至少包含运行结果、失败类别、耗时和成本相关指标

### Requirement: Failure classification and aggregation
系统 SHALL 对 harness 运行失败进行统一分类，并支持聚合分析。

#### Scenario: 失败被归类到标准标签
- **WHEN** 一次运行以失败、阻塞或未通过验证结束
- **THEN** 系统 SHALL 为其分配标准化失败标签
- **AND** 标签 SHALL 能区分至少验证缺失、坏循环、方法选择错误、产物缺失或上下文过载等主要类型

#### Scenario: 聚合分析输出失败分布
- **WHEN** 维护者对一组运行记录执行聚合分析
- **THEN** 系统 SHALL 输出失败标签分布和对应样本计数
- **AND** 结果 SHALL 可用于指导后续 harness 调优
