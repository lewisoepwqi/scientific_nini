## ADDED Requirements

### Requirement: Excel 多工作表加载模式
系统 SHALL 在 `load_dataset` 中支持多工作表读取模式，以便模型根据分析任务选择按 sheet 分析或跨 sheet 合并分析。

#### Scenario: 加载指定工作表
- **WHEN** 用户或模型调用 `load_dataset`，并指定 `sheet_mode=single` 与 `sheet_name`
- **THEN** 系统仅加载目标 sheet，并在会话中创建对应数据集

#### Scenario: 加载全部工作表并分别分析
- **WHEN** 调用 `load_dataset`，并指定 `sheet_mode=all` 且 `combine_sheets=false`
- **THEN** 系统加载全部 sheet，并在会话中为每个 sheet 创建独立数据集

#### Scenario: 加载全部工作表并合并分析
- **WHEN** 调用 `load_dataset`，并指定 `sheet_mode=all` 且 `combine_sheets=true`
- **THEN** 系统将全部 sheet 合并为一个数据集
- **AND** 可选添加来源列用于标记原始 sheet
