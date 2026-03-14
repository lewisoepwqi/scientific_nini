# sandbox-import-approval Specification

## Purpose
定义 `run_code` 在沙盒扩展包审批场景下的行为边界、授权范围和执行一致性要求。

## Requirements
### Requirement: 低风险扩展包导入必须经过用户审批
系统 SHALL 在 `run_code` 检测到未授权的低风险扩展包导入时，中断本次执行并返回结构化审批需求，而不是直接当作不可恢复错误。

#### Scenario: 未授权 reviewable 包触发审批
- **WHEN** 用户代码导入 `REVIEWABLE_IMPORT_ROOTS` 中的包且该包不在本次允许集合内
- **THEN** 沙箱返回 `SandboxReviewRequired`
- **AND** `run_code` 结果中包含 `_sandbox_review_required=true`
- **AND** 结果中包含待审批包列表与风险说明

#### Scenario: 多个待审批包聚合为一次审批
- **WHEN** 同一段用户代码同时导入多个未授权的 reviewable 包
- **THEN** 系统 SHALL 聚合这些包并一次性返回审批需求
- **AND** 不得为同一次工具调用连续触发多轮审批

### Requirement: 高风险或未纳入审查范围的导入必须继续硬拒绝
系统 SHALL 对网络、系统、动态执行类模块以及未纳入 reviewable 清单的未知导入保持默认拒绝，不得通过用户确认放行。

#### Scenario: 高风险模块直接拒绝
- **WHEN** 用户代码导入 `requests`、`os`、`subprocess` 或其他硬拒绝根模块
- **THEN** 沙箱 SHALL 返回 `SandboxPolicyError`
- **AND** 工具结果不得标记 `_sandbox_review_required`

#### Scenario: 未知包默认拒绝
- **WHEN** 用户代码导入既不在自动白名单也不在 reviewable 清单中的根模块
- **THEN** 系统 SHALL 直接拒绝执行
- **AND** 不得向用户展示可授权选项

### Requirement: 授权范围必须区分一次性、会话级与永久级
系统 SHALL 支持一次性、会话级和永久级三种导入授权范围，并按最小权限原则分别生效。

#### Scenario: 仅本次允许
- **WHEN** 用户在审批中选择“仅本次允许”
- **THEN** 系统 SHALL 仅对当前工具调用的立即重试放行对应包
- **AND** 不将该包写入会话级或永久级授权存储

#### Scenario: 本会话允许
- **WHEN** 用户在审批中选择“本会话允许”
- **THEN** 系统 SHALL 将对应包写入当前会话的 `sandbox_approved_imports`
- **AND** 同一会话后续再次导入该包时不再重复询问

#### Scenario: 始终允许
- **WHEN** 用户在审批中选择“始终允许”
- **THEN** 系统 SHALL 将对应包写入永久审批存储
- **AND** 新会话加载时继续视为已授权

### Requirement: 静态校验与运行期导入校验必须保持一致
系统 SHALL 在 AST 静态校验与运行期 `_safe_import()` 中使用同一份允许导入集合，避免出现审批通过后仍无法导入的状态不一致。

#### Scenario: 审批通过后两层校验都放行
- **WHEN** 某 reviewable 包已通过一次性、会话级或永久级授权
- **THEN** `validate_code()` SHALL 允许该导入通过
- **AND** 运行期 `_safe_import()` SHALL 同样允许该导入通过

#### Scenario: 包未安装时返回正常执行失败
- **WHEN** 用户已授权某 reviewable 包但当前运行环境未安装该包
- **THEN** 系统 SHALL 返回普通执行失败或导入失败信息
- **AND** 不得把该失败重新归类为审批问题
