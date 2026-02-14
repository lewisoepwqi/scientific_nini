## ADDED Requirements
### Requirement: 图表输出统一契约
系统 SHALL 对所有 `has_chart=true` 的技能输出使用统一图表载荷结构，顶层必须包含 `data`（数组）与可选 `layout`、`config`，可被前端直接交给 Plotly 渲染。

#### Scenario: 复合统计技能输出统一载荷
- **WHEN** `correlation_analysis`、`complete_anova`、`complete_comparison` 返回图表
- **THEN** 返回值中的 `chart_data` 顶层包含 `data` 字段
- **AND** 不再仅返回 `{"figure": ...}` 包装结构

#### Scenario: 图表消息可被直接渲染
- **WHEN** Agent 发送 `chart` 事件给前端
- **THEN** 前端无需二次推断字段映射即可渲染图表

### Requirement: 图表载荷历史兼容
系统 SHALL 在图表渲染链路中兼容历史图表格式，确保历史会话和旧技能输出不会因为字段结构差异而显示“图表数据为空”。

#### Scenario: 兼容旧版 `figure` 包装
- **WHEN** 输入图表载荷为 `{"figure": {...}}`
- **THEN** 系统在渲染前将其转换为标准顶层结构
- **AND** 图表正常展示

#### Scenario: 非法图表载荷降级
- **WHEN** 图表载荷既不满足新契约也无法从旧契约转换
- **THEN** 系统返回可解释错误信息
- **AND** 不影响同轮其他消息展示

### Requirement: 图表契约版本标识
系统 SHALL 为图表载荷提供契约版本标识，用于后续演进和跨版本兼容。

#### Scenario: 生成新版图表载荷
- **WHEN** 技能输出图表数据
- **THEN** 载荷包含 `schema_version`
- **AND** 版本值符合系统定义的可比较格式
