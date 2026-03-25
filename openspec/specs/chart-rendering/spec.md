# chart-rendering Specification

## Purpose
TBD - created by archiving change add-unified-chart-style-contract. Update Purpose after archive.
## Requirements
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

### Requirement: 图表默认配置降级可观测
系统 MUST 在图表默认样式配置发生异常时记录可观测日志，并继续执行后续流程。

#### Scenario: Matplotlib 默认配置异常时记录日志并降级
- **WHEN** Matplotlib 默认样式设置阶段抛出异常
- **THEN** 系统记录包含异常信息的降级日志
- **AND** 不中断后续代码执行

#### Scenario: Plotly 默认配置异常时记录日志并降级
- **WHEN** Plotly 默认样式设置阶段抛出异常
- **THEN** 系统记录包含异常信息的降级日志
- **AND** 不中断后续代码执行

### Requirement: 图表必须通过图表会话资源管理
系统 SHALL 将图表创建、更新和导出统一纳入图表会话资源生命周期，而不是将“生成图表”和“导出图表”视为相互独立且依赖隐式状态的操作。

#### Scenario: 创建图表会话
- **WHEN** 用户或编排层请求创建图表
- **THEN** 系统创建图表资源
- **AND** 返回图表 `resource_id`
- **AND** 保存图表规格与渲染参数

#### Scenario: 更新已有图表会话
- **WHEN** 用户或编排层针对已有图表资源修改标题、列映射或导出参数
- **THEN** 系统更新同一图表资源
- **AND** 不要求重新依赖“最近一次图表”

### Requirement: 图表导出必须基于图表资源执行
系统 SHALL 基于指定图表资源执行导出，并将导出结果登记为受管产物。

#### Scenario: 导出指定图表资源
- **WHEN** 用户或编排层请求导出某个图表资源
- **THEN** 系统基于该资源当前规格导出目标格式
- **AND** 将导出文件登记为工作区产物

#### Scenario: 缺少图表资源时拒绝隐式导出
- **WHEN** 请求导出图表但未指定有效图表资源
- **THEN** 系统返回可解释错误
- **AND** 不再回退到“最近一次图表”的隐式行为
