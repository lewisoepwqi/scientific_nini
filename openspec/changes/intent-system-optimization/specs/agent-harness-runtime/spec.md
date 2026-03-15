## MODIFIED Requirements

### Requirement: Completion verification before done

系统 SHALL 在发送最终完成信号前执行结构化完成校验，并在校验失败时阻止直接完成。

#### Scenario: 未通过校验时不得直接结束

- **WHEN** 模型输出最终答案或系统准备发送 `done`
- **AND** completion verification 发现仍缺少必要动作或结果
- **THEN** 系统 SHALL 阻止当前轮直接进入完成态
- **AND** 系统 SHALL 触发一次继续执行或重规划的恢复流程

#### Scenario: 校验覆盖关键完成条件

- **WHEN** 系统执行 completion verification
- **THEN** 校验 SHALL 至少覆盖以下四项：原始用户问题是否被回应、关键工具失败是否被忽略、承诺产物是否生成、以及是否仅描述下一步但未执行

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
