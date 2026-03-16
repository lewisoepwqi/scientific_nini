# Capability: Agent Harness Runtime

## Purpose

定义 Agent 运行时 harness 层的核心行为，包括运行编排、完成前校验、坏循环恢复和分阶段推理预算控制。

## Requirements

### Requirement: Harness runtime orchestration

系统 SHALL 在 `AgentRunner` 外提供独立的 harness 运行编排层，用于统一管理一次会话运行的上下文准备、执行守卫和结束判定。

#### Scenario: Harness 包装既有 AgentRunner 运行

- **WHEN** 会话入口启动一次新的 Agent 运行
- **THEN** 系统 SHALL 通过 harness 编排层调用既有 `AgentRunner`
- **AND** harness SHALL 保持与现有事件流兼容的输出方式
- **AND** 不得要求调用方直接重写 `AgentRunner` 的主循环

#### Scenario: Harness 在运行前注入确定性上下文摘要

- **WHEN** harness 开始一次运行
- **THEN** 系统 SHALL 生成当前轮的运行上下文摘要
- **AND** 摘要 SHALL 包含当前数据集、已知产物、可用工具提示和关键运行约束
- **AND** 该摘要 SHALL 作为 runtime context 或等价运行时输入参与后续执行

### Requirement: Completion verification before done

系统 SHALL 在发送最终完成信号前执行结构化完成校验，并在校验失败时阻止直接完成。

#### Scenario: 未通过校验时不得直接结束

- **WHEN** 模型输出最终答案或系统准备发送 `done`
- **AND** completion verification 发现仍缺少必要动作或结果
- **THEN** 系统 SHALL 阻止当前轮直接进入完成态
- **AND** 系统 SHALL 触发一次继续执行或重规划的恢复流程

#### Scenario: 校验覆盖关键完成条件

- **WHEN** 系统执行 completion verification
- **THEN** 校验 SHALL 至少覆盖原始用户问题是否被回应、关键工具失败是否被忽略、承诺产物是否生成、以及是否仅描述下一步但未执行

#### Scenario: 承诺产物判定要求完成语义词与产物词共现

- **WHEN** 系统判断最终文本是否"承诺了产物"
- **THEN** 系统 SHALL 仅在文本中同时出现"完成语义词"（已生成、已导出、已完成、以下是、请查看、如下等）和"产物词"（图表、报告、产物、附件等）时，才将其判定为承诺产物
- **AND** 文本中仅出现产物词（如介绍系统能力时提及"图表"或"报告"）SHALL NOT 被判定为承诺产物
- **AND** 完成语义词在前时，两类词之间距离 SHALL 不超过 15 个字符（含换行）；产物词在前时距离 SHALL 不超过 8 个字符

#### Scenario: 能力描述类回答不触发产物校验失败

- **WHEN** AI 回答中包含"我可以帮你制作图表与报告"等能力介绍性文本
- **AND** 本轮未调用任何工具、未生成任何产物
- **THEN** `artifact_generated` 校验项 SHALL 判定为通过（`passed=True`）
- **AND** 系统 SHALL 不触发第二轮 AgentRunner 执行

### Requirement: Analysis loop recovery and blocking

系统 SHALL 识别科研分析场景中的坏循环，并按分级策略执行恢复或阻塞。

#### Scenario: 同类分析路径重复失败触发恢复

- **WHEN** 同一数据集或资源上重复出现同类工具失败，且近似参数路径未发生实质变化
- **THEN** 系统 SHALL 将该状态识别为坏循环
- **AND** 系统 SHALL 触发恢复提示、上下文收缩或重规划，而不是继续盲目重试

#### Scenario: 恢复失败后进入 blocked

- **WHEN** 坏循环经过有限次恢复后仍未推进计划、结论或产物状态
- **THEN** 系统 SHALL 将当前轮标记为 `blocked`
- **AND** 系统 SHALL 保留明确的阻塞原因和建议动作

### Requirement: Stage-aware reasoning budget

系统 SHALL 根据运行阶段切换 reasoning 预算，而不是对整轮运行固定使用同一档位。

#### Scenario: 规划与验证阶段提升推理预算

- **WHEN** 系统处于规划、重规划或最终验证阶段
- **THEN** 系统 SHALL 使用高于常规执行阶段的 reasoning 预算

#### Scenario: 常规执行阶段保持较低预算

- **WHEN** 系统仅在执行常规工具跟进或例行后处理
- **THEN** 系统 SHALL 使用不高于规划阶段的 reasoning 预算
- **AND** 该策略 SHALL 以减少不必要的耗时与成本为目标
