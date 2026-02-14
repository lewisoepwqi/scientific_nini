# chart-rendering Specification

## Purpose
TBD - created by archiving change add-unified-chart-style-contract. Update Purpose after archive.
## Requirements
### Requirement: 统一图表风格契约
系统 SHALL 提供单一的图表风格契约，统一定义字体链、字号、线宽、配色、画布尺寸、网格样式、DPI 与导出格式，作为所有图表实现路径的唯一样式来源。

#### Scenario: 加载期刊模板并生成契约
- **WHEN** 用户指定 `journal_style`（如 `nature` 或 `science`）
- **THEN** 系统生成对应 `ChartStyleSpec`，且后续渲染仅从该契约读取样式参数

#### Scenario: 模板缺失时回退
- **WHEN** 用户指定不存在的 `journal_style`
- **THEN** 系统回退到 `default` 契约并记录可观测告警

### Requirement: 双实现方式必须同时支持
系统 SHALL 同时支持声明式绘图（`create_chart`）与代码式绘图（`run_code`）两种实现方式，并允许在声明式路径中显式选择渲染引擎（`auto|plotly|matplotlib`）。

#### Scenario: 声明式绘图选择 Plotly
- **WHEN** 用户调用 `create_chart` 且 `render_engine=plotly`
- **THEN** 系统使用 Plotly 渲染并应用统一风格契约

#### Scenario: 声明式绘图选择 Matplotlib
- **WHEN** 用户调用 `create_chart` 且 `render_engine=matplotlib`
- **THEN** 系统使用 Matplotlib 渲染并应用统一风格契约

#### Scenario: 代码式绘图自动归一化
- **WHEN** 用户通过 `run_code` 生成 Plotly 或 Matplotlib 图表
- **THEN** 系统在采集后执行统一样式归一化并输出标准化产物

### Requirement: 跨引擎图表效果一致性
系统 SHALL 对同一输入数据与同一模板下的 Plotly 与 Matplotlib 输出建立一致性约束，至少保证关键视觉参数一致，并通过自动化回归测试验证视觉相似度。

#### Scenario: 参数一致性校验
- **WHEN** 同一图表分别通过 Plotly 与 Matplotlib 渲染
- **THEN** 字体、字号、线宽、配色、尺寸、坐标轴样式与网格参数一致

#### Scenario: 视觉回归校验
- **WHEN** 持续集成执行图表回归测试
- **THEN** 同图跨引擎输出满足预设视觉相似度阈值（如 SSIM 阈值）

### Requirement: 发表级导出标准统一
系统 SHALL 统一图表导出规则，默认支持 `pdf/svg/png`，并确保位图导出默认不低于 300 DPI，矢量格式优先用于高质量发布。

#### Scenario: 默认导出集合
- **WHEN** 图表生成完成并进入产物保存流程
- **THEN** 系统至少产出 `pdf`、`svg`、`png` 三种格式或给出可解释降级结果

#### Scenario: 位图分辨率
- **WHEN** 系统导出 PNG
- **THEN** 默认导出 DPI 不低于 300

### Requirement: 发表级技能纳入标准技能扫描
系统 SHALL 通过标准 Markdown Skill 目录（`skills/*/SKILL.md`）接入发表级图表技能，并将其写入技能快照供 Agent 提示词使用。

#### Scenario: 技能被扫描并进入快照
- **WHEN** 系统刷新 Markdown 技能目录
- **THEN** 发表级图表技能出现在 `SKILLS_SNAPSHOT` 中

#### Scenario: Agent 可见技能规范
- **WHEN** Agent 构建系统提示词
- **THEN** 提示词中包含发表级图表技能摘要，支持图表决策时引用该规范

