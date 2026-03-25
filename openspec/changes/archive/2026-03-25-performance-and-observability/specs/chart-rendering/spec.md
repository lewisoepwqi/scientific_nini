## MODIFIED Requirements

### Requirement: 统一图表风格契约
系统 SHALL 提供单一的图表风格契约，统一定义字体链、字号、线宽、配色、画布尺寸、网格样式、DPI 与导出格式，作为所有图表实现路径的唯一样式来源。DPI 值 SHALL 限制在 `[300, 600]` 范围内。

#### Scenario: 加载期刊模板并生成契约
- **WHEN** 用户指定 `journal_style`（如 `nature` 或 `science`）
- **THEN** 系统生成对应 `ChartStyleSpec`，且后续渲染仅从该契约读取样式参数

#### Scenario: 模板缺失时回退
- **WHEN** 用户指定不存在的 `journal_style`
- **THEN** 系统回退到 `default` 契约并记录可观测告警

#### Scenario: DPI 超出范围时截断
- **WHEN** 配置或参数中的 DPI 值小于 300 或大于 600
- **THEN** 系统 SHALL 将 DPI 截断到 `[300, 600]` 范围
- **AND** SHALL 记录 warning 日志说明截断行为
