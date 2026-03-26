## ADDED Requirements

### Requirement: 输出等级标签展示
消息组件 SHALL 在 Agent 回复底部展示输出等级标签，当 done 事件包含 output_level 时。

#### Scenario: O2 等级展示
- **WHEN** done 事件的 output_level 为 "o2"
- **THEN** 消息底部展示蓝色「草稿级」标签

#### Scenario: 无等级不展示
- **WHEN** done 事件的 output_level 为 null
- **THEN** 消息底部不展示等级标签

#### Scenario: 四个等级样式区分
- **WHEN** output_level 为 o1/o2/o3/o4
- **THEN** 分别展示灰色「建议级」、蓝色「草稿级」、绿色「可审阅级」、紫色「可导出级」标签
