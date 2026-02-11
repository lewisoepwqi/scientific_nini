# Change: 增强 Excel 多工作表加载模式

## Why

当前系统上传 Excel 时只读取默认工作表，无法满足“数据分散在多个 sheet”的常见科研场景。  
这会导致模型看不到完整数据来源，也无法自行决定“按 sheet 分析”还是“跨 sheet 合并分析”。

## What Changes

- 扩展 `load_dataset` 技能，支持 Excel 多工作表读取参数：
  - `sheet_mode=single`：读取指定 `sheet_name`
  - `sheet_mode=all`：读取全部 sheet
  - `combine_sheets=true`：将全部 sheet 合并为一个数据集（可选保留来源列）
- 新增 Excel I/O 工具函数：列出 sheet、读取单 sheet、读取全部 sheet。
- 保持默认行为兼容：`sheet_mode=default` 时维持现有单数据集加载逻辑。
- 增加测试覆盖单 sheet、全 sheet 分开加载、全 sheet 合并加载。

## Impact

- Affected specs: `workspace`
- Affected code:
  - `src/nini/skills/data_ops.py`
  - `src/nini/utils/dataframe_io.py`
  - `tests/test_excel_sheet_modes.py`
