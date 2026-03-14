## ADDED Requirements

### Requirement: 基础工具必须显式返回“等待审批”的结构化结果
系统 SHALL 让基础工具在遇到可恢复的用户审批前置条件时返回结构化审批信号，便于 Agent 在统一工具循环中暂停、提问并重试。

#### Scenario: `run_code` 返回审批信号
- **WHEN** `run_code` 因未授权的 reviewable 扩展包导入而无法继续执行
- **THEN** 工具结果 SHALL 包含 `success=false`
- **AND** `data._sandbox_review_required` SHALL 为 `true`
- **AND** `data.sandbox_violations` SHALL 包含包名、风险等级与原因

#### Scenario: 不可绕过的策略错误仍然按普通失败返回
- **WHEN** `run_code` 命中不可审批的沙箱策略错误
- **THEN** 工具结果 SHALL 返回普通失败摘要
- **AND** 不包含 `_sandbox_review_required`
- **AND** 保留可解释错误信息供 Agent 与用户查看

### Requirement: 基础工具的审批型失败必须支持一次受控重试
系统 SHALL 允许 Agent 在收到结构化审批结果并获取用户授权后，对原始工具调用执行一次受控重试。

#### Scenario: 审批通过后重试原始工具调用
- **WHEN** Agent 收到 `_sandbox_review_required` 结果且用户授权继续
- **THEN** Agent SHALL 使用原始工具名与原始参数重试一次
- **AND** 重试结果继续走统一工具结果处理链路

#### Scenario: 同一次调用不得无限审批重试
- **WHEN** 某次工具调用在完成一次审批后再次返回审批需求
- **THEN** Agent SHALL 终止该次调用并返回失败
- **AND** 不得在同一次调用内再次发起新的审批循环
