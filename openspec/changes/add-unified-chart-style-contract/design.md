## Context

Nini 现有图表能力分为两条主链路：

1. `create_chart`：快速生成标准图（当前主要输出 Plotly）。
2. `run_code`：在沙箱执行 Matplotlib/Seaborn/Plotly 代码，自动收集并导出产物。

两条链路功能互补，但风格配置与导出规范存在多源定义，导致“同一语义图在不同路径下观感不一致”的风险。目标是通过统一契约实现“能力双轨 + 视觉一致”。

## Goals / Non-Goals

### Goals

- 提供单一图表风格契约，作为所有渲染路径的唯一样式来源。
- 明确支持两种实现方式（声明式/代码式），并保持输出一致。
- 标准化发表级导出策略（矢量优先 + 300 DPI 位图）。
- 将发表级图表技能纳入标准技能扫描路径，进入提示词上下文。

### Non-Goals

- 不在本次变更中新增大量新图表类型。
- 不引入第三套前端图形库。
- 不改变现有会话消息协议的核心结构。

## Decisions

### 决策 1：引入 `ChartStyleSpec` 作为单一风格契约

- 做法：定义统一字段（字体、字号、线宽、坐标轴、网格、配色、尺寸、DPI、导出格式）。
- 原因：将“样式定义”与“渲染实现”解耦，避免配置漂移。

### 决策 2：采用“单契约 + 双渲染器”模型

- 做法：
  - Plotly 适配器将契约映射到 `layout/template`。
  - Matplotlib 适配器将契约映射到 `rcParams/savefig`。
- 原因：保留两种实现方式的优势，同时统一视觉结果。

### 决策 3：`create_chart` 支持显式渲染引擎选择

- 做法：新增 `render_engine=auto|plotly|matplotlib`。
- 原因：兼顾默认易用与高级可控，便于 A/B 与回归比较。

### 决策 4：`run_code` 统一后处理而非干预用户绘图语句

- 做法：在图表捕获后执行标准化（字体链补齐、布局归一、导出归一）。
- 原因：减少对用户代码的侵入，避免破坏自定义逻辑。

### 决策 5：导出策略统一为“矢量优先 + 位图兜底”

- 做法：默认产出 `pdf/svg/png`，其中 PNG 默认 300 DPI。
- 原因：满足期刊投稿与 Web 预览双场景。

## Architecture

### 1) 逻辑分层

- `style_contract`：定义契约模型与模板映射。
- `renderers/plotly`：Plotly 适配器。
- `renderers/matplotlib`：Matplotlib 适配器。
- `skills/visualization`：声明式图表入口（选择渲染器）。
- `skills/code_exec + sandbox/executor`：代码式图表入口（采集后归一化与导出）。

### 2) 数据流

1. 用户指定 `journal_style`（可选 `render_engine`）。
2. 系统加载 `ChartStyleSpec`。
3. 根据实现路径进入 Plotly 或 Matplotlib 渲染/归一化。
4. 输出统一产物结构与统一元数据。

### 3) 技能注入路径

- 将发表级技能文件置于 `skills/<skill_name>/SKILL.md`。
- 由 Markdown 技能扫描器纳入 `SKILLS_SNAPSHOT`。
- Prompt 中可稳定感知“发表级图表规范”。

## Risks / Trade-offs

- 风险 1：双渲染器天然存在像素级差异。
  - 缓解：使用“参数一致 + 视觉阈值一致”双重验收，而非强制像素全等。

- 风险 2：导出链路依赖（kaleido/Chrome）导致不稳定。
  - 缓解：保留 HTML/JSON 降级路径，并输出明确告警信息。

- 风险 3：风格契约过于严格可能限制高级自定义。
  - 缓解：允许 `run_code` 局部覆盖，但默认遵循契约。

## Migration Plan

1. 先引入契约层与模板映射，不改外部 API。
2. 为 `create_chart` 增加渲染引擎参数并保持默认兼容。
3. 在 `run_code` 链路增加后处理归一化与导出统一。
4. 接入技能扫描目录并更新文档。
5. 增加一致性测试后再切换为默认严格策略。

## Rollback Plan

- 可通过配置开关回退到现有单路径行为：
  - 关闭 `create_chart` 的 `matplotlib` 渲染器。
  - 关闭 `run_code` 图表后处理归一化。
- 保留已生成产物与历史模板，不做破坏性迁移。

## Open Questions

- 视觉一致性阈值最终采用 SSIM 还是多指标组合（SSIM + 感知哈希）？
- `render_engine=auto` 的决策规则是否需要暴露给前端配置？
- 是否需要对“统计标注组件”（显著性括号、p 值文本）单独做跨引擎标准件？
