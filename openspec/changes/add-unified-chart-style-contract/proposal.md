# Change: 统一发表级图表风格契约并支持双实现渲染

## Why

当前图表链路已经支持 `create_chart`（标准图）与 `run_code`（自定义图），但两条路径的风格配置与导出策略分散在不同模块：

1. 样式来源分散（模板、沙箱默认、技能内布局），难以保证长期一致。
2. 两条实现路径缺少统一“风格契约”，同一数据在不同路径下可能出现视觉差异。
3. 导出质量标准不完全对齐发表级要求（如 DPI、矢量优先、格式集合）。
4. 发表级图表技能文档未以标准 Markdown Skill 目录方式接入，无法稳定进入技能快照与提示词上下文。

为满足“同一图在两种实现方式下效果一致”的目标，需要引入单一风格契约层，并将 Plotly/Matplotlib 统一纳入该契约。

## What Changes

- 新增图表能力规范 `chart-rendering`，定义统一风格契约（字体、尺寸、线宽、配色、网格、DPI、导出格式）。
- 保持并强化双实现方式：
  - `create_chart`：声明式快速绘图；
  - `run_code`：代码式自定义绘图；
  两者必须共享同一风格契约。
- 为 `create_chart` 增加渲染引擎选择（`plotly` / `matplotlib` / `auto`），并保证默认行为可回退兼容。
- 为 `run_code` 增加图表归一化后处理：统一样式、统一导出策略、统一产物命名与元数据字段。
- 统一导出标准：至少支持 `pdf/svg/png`，默认位图导出满足 300 DPI，矢量格式优先。
- 将发表级图表技能以 `skills/*/SKILL.md` 方式纳入扫描目录，确保进入 `SKILLS_SNAPSHOT` 并参与 Agent 决策。
- 增加跨引擎一致性回归测试（样式参数断言 + 视觉相似度阈值）。

## Impact

- Affected specs:
  - `chart-rendering`（新增）
- Affected code:
  - `src/nini/skills/visualization.py`
  - `src/nini/skills/code_exec.py`
  - `src/nini/sandbox/executor.py`
  - `src/nini/skills/templates/journal_styles.py`
  - `src/nini/skills/markdown_scanner.py`（如需扩展技能目录策略）
  - `src/nini/config.py`（如需新增图表一致性配置项）
  - `docs/visualization-guide.md`
  - `tests/test_phase2_skills.py`
  - `tests/test_phase3_run_code.py`
  - `tests/test_journal_templates.py`
  - `tests/test_chart_style_consistency.py`（新增）
