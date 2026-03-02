## ADDED Requirements

### Requirement: IntentSummaryCard 默认展示简化意图概括
IntentSummaryCard 组件 SHALL 默认只展示一句话概括系统的意图理解，不展示技术细节。

#### Scenario: 用户输入时看到简化概括
- **WHEN** 用户在输入框输入内容
- **THEN** IntentSummaryCard 展示一句概括，如"系统理解您想要进行差异分析"
- **AND** 技术细节（候选能力、工具提示等）默认隐藏

### Requirement: IntentSummaryCard 提供查看详情入口
IntentSummaryCard 组件 SHALL 提供"查看详情"入口，允许用户展开查看完整技术信息。

#### Scenario: 用户点击查看完整信息
- **WHEN** 用户点击"查看详情"按钮
- **THEN** IntentSummaryCard 展开显示候选能力、推荐工具、激活技能等详细信息
- **AND** 再次点击可折叠回简化视图

### Requirement: 意图理解术语用户友好化
系统 SHALL 使用用户友好的术语替代技术术语展示意图理解结果。

#### Scenario: 用户看到友好的能力名称
- **WHEN** 系统识别到用户的差异分析意图
- **THEN** 展示"差异分析"而非"capability_candidate"
- **AND** 展示"推荐工具"而非"tool_hints"
- **AND** 不展示"规则版 v2"等技术实现标签

### Requirement: 澄清选项在置信度低时自动展开
当系统对意图理解置信度低时，IntentSummaryCard SHALL 自动展开澄清选项。

#### Scenario: 置信度低时自动展示澄清
- **WHEN** 系统识别到多个候选意图且分数接近
- **THEN** IntentSummaryCard 自动展开澄清建议区域
- **AND** 展示"您是想进行 A 分析还是 B 分析？"等澄清问题
- **AND** 提供可点击的选项按钮

### Requirement: IntentTimelineItem 展示执行阶段意图确认
IntentTimelineItem 组件 SHALL 在用户发送消息后展示系统实际采纳的意图理解结果。

#### Scenario: 用户发送消息后看到意图确认
- **WHEN** 用户发送消息
- **THEN** 在对话流中显示 IntentTimelineItem
- **AND** 展示系统确认的理解（如"系统判断您的意图是：差异分析"）
- **AND** 展示推荐工具和已激活技能
- **AND** 不展示与 IntentSummaryCard 重复的技术实现细节
