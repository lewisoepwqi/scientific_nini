## ADDED Requirements

### Requirement: 系统必须为 deep task 提供端到端任务标识

系统 SHALL 为每个 deep task 分配稳定 `task_id`，并在前端事件、模型调用、工具执行、产物生成和 trace 记录中贯穿该标识。

#### Scenario: deep task 启动时分配任务标识
- **WHEN** 用户启动一个 deep task
- **THEN** 系统为该任务分配稳定 `task_id`
- **AND** 后续关键事件均可关联到该 `task_id`

#### Scenario: 产物与任务标识关联
- **WHEN** deep task 生成正式产物
- **THEN** 该产物记录包含来源 `task_id`
- **AND** 可用于后续问题定位与回放分析

### Requirement: 系统必须采集 deep task 关键运行指标

系统 SHALL 采集 deep task 的关键运行指标，至少包括总耗时、步骤耗时、失败类型、恢复次数和最终状态。

#### Scenario: deep task 结束后写入指标摘要
- **WHEN** 一次 deep task 结束，无论完成、阻塞或失败
- **THEN** 系统写入该任务的指标摘要
- **AND** 摘要包含最终状态与关键耗时信息

#### Scenario: deep task 触发恢复时记录次数
- **WHEN** 系统对 deep task 执行自动恢复或重试
- **THEN** 指标中记录恢复次数与恢复结果

### Requirement: 系统必须支持任务级预算阈值

系统 SHALL 为 deep task 支持任务级预算阈值，并在超过阈值时输出告警或降级信号。

#### Scenario: 任务达到预算阈值
- **WHEN** deep task 的 token、模型调用次数或其他预算指标超过阈值
- **THEN** 系统记录预算告警
- **AND** 告警可关联到对应 `task_id`

#### Scenario: 预算告警不影响基础 trace
- **WHEN** 系统输出预算告警
- **THEN** 任务的其他关键事件仍可正常记录与消费
