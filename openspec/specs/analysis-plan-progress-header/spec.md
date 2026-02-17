# analysis-plan-progress-header Specification

## Purpose
确保分析计划在对话区主路径持续可见，并以一致状态表达帮助用户实时掌握流程进度。

## Requirements
### Requirement: 对话区上方持续可见计划进度头部
系统 SHALL 在会话页对话区上方渲染分析计划进度头部，保证用户在阅读回复与等待执行期间可持续看到当前流程位置。

#### Scenario: 桌面端显示计划头部
- **WHEN** 当前会话存在分析计划且屏幕宽度大于等于 768px
- **THEN** 对话区上方必须显示计划进度头部
- **AND** 头部显示步骤总数与当前步骤序号

#### Scenario: 无活动计划时不显示冗余头部
- **WHEN** 当前会话不存在活动分析计划
- **THEN** 系统不显示空计划进度头部

### Requirement: 计划步骤状态表达一致
系统 SHALL 为每个步骤提供统一状态表达，至少覆盖 `not_started`、`in_progress`、`done`、`blocked`、`failed`，并保持状态颜色/图标/文案的一致映射。

#### Scenario: 当前步骤高亮
- **WHEN** 计划中某步骤状态为 `in_progress`
- **THEN** 该步骤在头部中以当前态高亮显示
- **AND** 其他步骤按其状态显示对应样式

#### Scenario: 步骤完成后进度更新
- **WHEN** 当前步骤从 `in_progress` 变为 `done`
- **THEN** 系统更新 `step x/y` 进度
- **AND** 下一步骤自动进入可见的待执行或进行中状态

### Requirement: 移动端紧凑展示与展开查看
系统 SHALL 在移动端提供紧凑摘要展示，并支持展开查看完整步骤列表，以兼顾可见性与内容空间。

#### Scenario: 移动端默认紧凑摘要
- **WHEN** 屏幕宽度小于 768px 且存在活动计划
- **THEN** 默认显示单行摘要（当前步骤与总体进度）
- **AND** 不遮挡输入区域

#### Scenario: 用户展开后查看完整步骤
- **WHEN** 用户点击计划摘要的展开控件
- **THEN** 系统显示完整步骤列表与状态
- **AND** 用户可再次收起回到紧凑摘要态
