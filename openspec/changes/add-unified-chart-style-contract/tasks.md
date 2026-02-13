# 任务清单：统一发表级图表风格契约（双实现一致）

## 1. 契约与配置（P0）

- [x] 1.1 新增图表风格契约模块，定义统一参数模型（字体链、尺寸、线宽、配色、DPI、导出格式）。
- [x] 1.2 将现有期刊模板（default/nature/science/cell/nejm/lancet）映射到统一契约，消除重复配置源。
- [x] 1.3 增加配置项与默认值，明确“发表级默认策略”和降级策略（缺字体/缺 kaleido）。

## 2. `create_chart` 双引擎化（P0）

- [x] 2.1 扩展 `create_chart` 参数，支持 `render_engine=auto|plotly|matplotlib`。
- [x] 2.2 实现 Plotly 渲染器与 Matplotlib 渲染器对同一契约的适配。
- [x] 2.3 确保 `create_chart` 返回结构与历史兼容（`has_chart/chart_data/artifacts`）。

## 3. `run_code` 归一化后处理（P0）

- [x] 3.1 在沙箱图表采集后增加统一样式归一化（两库一致）。
- [x] 3.2 统一导出策略：至少 `pdf/svg/png`，位图默认 300 DPI。
- [x] 3.3 统一产物元数据字段，保证 `export_chart` 与工作区画廊可复用。

## 4. 技能接入与提示词上下文（P1）

- [x] 4.1 将发表级图表技能文档迁移至 `skills/<name>/SKILL.md` 目录结构。
- [x] 4.2 验证技能扫描与 `SKILLS_SNAPSHOT` 包含该技能。
- [x] 4.3 更新 Agent 策略文案，明确“简单图优先 create_chart，复杂图优先 run_code”。

## 5. 测试与验收（P0）

- [x] 5.1 新增契约单测：模板参数映射、默认值、降级行为。
- [x] 5.2 新增双引擎一致性测试：相同输入下样式参数一致。
- [x] 5.3 新增视觉回归测试：同图 SSIM 不低于阈值（建议 ≥ 0.96）。
- [x] 5.4 回归现有测试：`pytest -q` 与 `cd web && npm run build`。

## 6. 文档与迁移说明（P1）

- [x] 6.1 更新 `docs/visualization-guide.md`，补充双引擎选择与一致性保证说明。
- [x] 6.2 提供迁移说明：历史图表参数与新契约字段对照表。
