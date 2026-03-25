## ADDED Requirements

### Requirement: 引用详情必须展示验证状态

系统 SHALL 在引用详情或来源列表中展示与结论相关的验证状态，使用户能够区分已验证、待验证和冲突状态。

#### Scenario: 用户查看已验证引用
- **WHEN** 引用关联的结论状态为 `verified`
- **THEN** 系统在引用详情中展示“已验证”状态

#### Scenario: 用户查看待验证引用
- **WHEN** 引用关联的结论状态为 `pending_verification`
- **THEN** 系统在引用详情中展示“待验证”状态
- **AND** 可见缺口原因摘要

#### Scenario: 用户查看冲突引用
- **WHEN** 引用关联的结论状态为 `conflicted`
- **THEN** 系统在引用详情中展示“证据冲突”状态
- **AND** 可见冲突摘要
