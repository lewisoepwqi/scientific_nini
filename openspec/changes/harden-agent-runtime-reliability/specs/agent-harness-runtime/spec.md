## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Harness runtime 必须维护统一的 pending_actions 账本
系统 SHALL 在运行时维护统一的 `pending_actions` 账本，用于显式追踪未完成动作、失败恢复线索和待确认状态。

#### Scenario: 运行中登记未解决动作
- **WHEN** 某个关键动作未完成、失败后待恢复，或需要用户确认后才能继续
- **THEN** 系统 SHALL 向 `pending_actions` 账本登记对应动作
- **AND** 该动作 SHALL 至少包含类型、唯一键、状态、简要说明和来源工具

#### Scenario: 动作完成后清理账本
- **WHEN** 某个待处理动作被成功执行、被显式放弃，或其影响已在最终结论中明确说明
- **THEN** 系统 SHALL 更新或移除对应的 `pending_actions` 条目

### Requirement: Harness runtime 摘要必须包含 pending_actions
系统 SHALL 在当前轮的 runtime context 或等价运行时摘要中注入 `pending_actions` 的精简摘要，以支持跨压缩和跨恢复链路保持状态连续性。

#### Scenario: 运行摘要展示未解决动作
- **WHEN** 当前轮存在未解决的 `pending_actions`
- **THEN** 系统 SHALL 在运行时摘要中展示这些动作的精简列表
- **AND** SHALL 优先提示影响继续执行或最终完成判定的动作

#### Scenario: 无待处理动作时不注入冗余摘要
- **WHEN** 当前轮不存在 `pending_actions`
- **THEN** 系统 SHALL 不注入空的待处理动作摘要
