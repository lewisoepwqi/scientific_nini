## ADDED Requirements

### Requirement: Harness 评测必须覆盖核心 Recipe 基准集

系统 SHALL 为核心 Recipe 建立基准集，并支持在发布前对这些样本执行自动回放评测。

#### Scenario: 运行核心 Recipe 回放
- **WHEN** 维护者触发发布前回归
- **THEN** 系统对核心 Recipe 基准集执行自动回放评测
- **AND** 输出每条样本的结果摘要

#### Scenario: 基准集覆盖多个失败类型
- **WHEN** 维护者维护核心 Recipe 基准集
- **THEN** 样本覆盖正常完成、阻塞、失败恢复与产物缺失等主要场景

### Requirement: Harness 评测必须支持发布门禁阈值

系统 SHALL 为核心 Recipe 回放评测定义发布门禁阈值，并在不满足阈值时阻止视为通过。

#### Scenario: 回归结果达到阈值
- **WHEN** 核心 Recipe 回放结果满足预设阈值
- **THEN** 系统将该轮回归标记为通过

#### Scenario: 回归结果低于阈值
- **WHEN** 核心 Recipe 回放结果低于预设阈值
- **THEN** 系统将该轮回归标记为未通过
- **AND** 输出主要失败类型摘要
