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

系统 SHALL 在发送最终完成信号前执行基于结构化证据的完成校验，并在校验失败时阻止直接完成。

#### Scenario: 未通过校验时不得直接结束

- **WHEN** 模型输出最终答案或系统准备发送 `done`
- **AND** completion verification 发现仍缺少必要动作或结果
- **THEN** 系统 SHALL 阻止当前轮直接进入完成态
- **AND** 系统 SHALL 触发一次继续执行或重规划的恢复流程

#### Scenario: 校验覆盖关键完成条件

- **WHEN** 系统执行 completion verification
- **THEN** 校验 SHALL 至少覆盖原始用户问题是否被回应、关键工具失败是否被忽略、承诺产物是否生成、是否仅描述下一步但未执行、以及是否仍存在未解决的 `pending_actions`

#### Scenario: 校验基于结构化证据生成

- **WHEN** 系统执行 completion verification
- **THEN** 系统 SHALL 先构建结构化 completion evidence
- **AND** 再由该 evidence 映射为具体校验项与恢复提示
- **AND** SHALL NOT 仅依赖关键词匹配或单条文本提示作为唯一判断依据

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

系统 SHALL 识别科研分析场景中的坏循环，并基于结构化错误码执行分级恢复；当错误属于“调度语义误用”时，系统 MUST 优先切换执行路径或收紧错误工具形态，而不是仅依赖重复计数后阻断。

#### Scenario: 调度语义错误优先触发路径纠偏

- **WHEN** 同一恢复链路中连续出现 `dispatch_agents` 的调度上下文错误或等价误用错误
- **THEN** 系统 SHALL 先注入恢复提示并收紧错误工具路径
- **AND** SHALL 优先引导模型切换到推荐的直接工具路径
- **AND** 不得在第一次恢复前就仅以通用坏循环处理

#### Scenario: 路径切换后仍无推进才进入 blocked

- **WHEN** 系统已经对调度误用执行过路径收紧或切换
- **AND** 后续运行仍未推进任务、结论或产物状态
- **THEN** 系统 SHALL 将当前轮标记为 `blocked`
- **AND** 阻塞原因 SHALL 明确指出已尝试的恢复动作和仍未解决的原因

### Requirement: Stage-aware reasoning budget

系统 SHALL 根据运行阶段切换 reasoning 预算，而不是对整轮运行固定使用同一档位。

#### Scenario: 规划与验证阶段提升推理预算

- **WHEN** 系统处于规划、重规划或最终验证阶段
- **THEN** 系统 SHALL 使用高于常规执行阶段的 reasoning 预算

#### Scenario: 常规执行阶段保持较低预算

- **WHEN** 系统仅在执行常规工具跟进或例行后处理
- **THEN** 系统 SHALL 使用不高于规划阶段的 reasoning 预算
- **AND** 该策略 SHALL 以减少不必要的耗时与成本为目标

### Requirement: Harness 运行时必须支持外部依赖的分级重试与超时策略

系统 SHALL 对模型调用、网络检索、导出作业或其他外部依赖采用分级超时与有限次重试策略，并记录每次尝试。

#### Scenario: 可恢复外部依赖失败触发重试

- **WHEN** 某个外部依赖调用返回可恢复失败
- **THEN** 系统按预定义策略触发有限次重试
- **AND** 为每次尝试记录尝试序号与结果

#### Scenario: 达到超时上限后停止重试

- **WHEN** 某个外部依赖持续超时并达到上限
- **THEN** 系统停止继续重试
- **AND** 将失败结果写入当前运行诊断

#### Scenario: 超时失败登记为待处理动作

- **WHEN** 某个分析步骤因超时而未完成
- **THEN** 系统 SHALL 将该失败登记为未解决的 `pending_actions`
- **AND** 后续 completion verification SHALL 将其视为待处理状态，直到被重试成功或被明确说明影响

### Requirement: Harness runtime 必须维护统一的 pending_actions 账本

系统 SHALL 在运行时维护统一的 `pending_actions` 账本，用于显式追踪未完成动作、失败恢复线索和待确认状态；对于同一逻辑调度错误，系统 SHALL 进行归并，避免在压缩和恢复轮次中无限累积重复项。

#### Scenario: 同一逻辑调度错误只保留一条规范化待处理动作

- **WHEN** 同一恢复链路中多次出现语义等价的 `dispatch_agents` 误用
- **THEN** 系统 SHALL 将其归并为一条规范化的 `pending_action`
- **AND** 该条目 SHALL 保留最近一次错误摘要、来源工具和恢复建议

#### Scenario: 恢复动作生效后更新待处理动作状态

- **WHEN** 调度误用已被路径切换、显式放弃或成功恢复
- **THEN** 系统 SHALL 更新对应 `pending_action` 的状态或将其清理
- **AND** 不得将已过时错误继续作为当前阻塞动作注入后续上下文

### Requirement: Harness runtime 摘要必须包含 pending_actions

系统 SHALL 在当前轮的 runtime context 或等价运行时摘要中注入 `pending_actions` 的精简摘要，以支持跨压缩和跨恢复链路保持状态连续性；对于调度类错误，摘要 SHALL 同时包含当前执行任务与推荐恢复动作。

#### Scenario: 调度类待处理动作摘要包含上下文字段

- **WHEN** 当前轮存在与任务调度相关的未解决 `pending_actions`
- **THEN** 摘要 SHALL 包含当前 `in_progress` 任务或当前 `pending wave` 的关键上下文
- **AND** SHALL 包含推荐恢复动作
- **AND** SHALL 避免只保留无法指导恢复的通用报错文案

#### Scenario: 无待处理动作时不注入冗余摘要

- **WHEN** 当前轮不存在 `pending_actions`
- **THEN** 系统 SHALL 不注入空的待处理动作摘要

### Requirement: Harness recovery 必须基于错误码收紧错误路径
系统 SHALL 为可识别的工具误用错误维护恢复策略表，并根据错误码生成恢复建议、推荐工具与阻塞判定依据；涉及 turn 级工具拦截时，harness SHALL 通过结构化恢复结果驱动 runner 更新护栏，而不得维护第二套独立拦截状态。

#### Scenario: 非法 agent 错误触发定向收紧
- **WHEN** 运行中出现非法 `agent_id` 的结构化错误
- **THEN** harness SHALL 将其识别为可恢复的路径误用
- **AND** SHALL 生成“收紧相同错误形态”的结构化恢复建议并驱动 runner 执行

#### Scenario: 调度上下文错误触发直接工具推荐
- **WHEN** 运行中出现“当前任务应直接执行而非继续派发”的结构化错误
- **THEN** harness SHALL 在后续恢复链路中推荐直接执行工具
- **AND** SHALL 将该推荐写入运行时上下文或等价约束中

### Requirement: Harness 运行时必须支持幂等恢复

系统 SHALL 在重试或恢复过程中避免重复提交同一逻辑动作，确保同一 deep task 的关键副作用具备幂等保护。

#### Scenario: 同一导出作业恢复时不重复登记

- **WHEN** 导出作业因可恢复错误被重新执行
- **THEN** 系统不会重复登记同一逻辑导出结果
- **AND** 诊断信息中可追踪原始尝试与恢复尝试

#### Scenario: 重复工具结果可被关联

- **WHEN** 同一逻辑动作发生多次尝试
- **THEN** 系统可区分原始尝试与恢复尝试
- **AND** 不要求用户手工清理重复记录
