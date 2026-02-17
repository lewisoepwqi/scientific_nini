# 任务清单：分析计划任务列表可见性优化

## 1. 事件契约与状态适配

- [x] 1.1 扩展分析流程事件契约，补充 `plan_progress` 事件与 `current_step_index`、`total_steps`、`step_title`、`step_status`、`next_hint` 字段（向后兼容可选）。
- [x] 1.2 在会话状态层新增计划状态适配器，将后端原始字段统一映射为 `not_started | in_progress | done | blocked | failed`。
- [x] 1.3 增加乱序保护策略（基于时间戳或序号）并验证步骤状态不会回退覆盖新状态。

## 2. 顶部任务列表组件与布局接入

- [x] 2.1 在会话页实现 `AnalysisPlanHeader`，固定放置于对话区上方并接入现有会话数据流。
- [x] 2.2 实现步骤列表渲染与当前步骤高亮，展示 `step x/y` 进度、步骤标题与状态样式。
- [x] 2.3 在无活动计划时隐藏组件，避免空白占位影响对话阅读。
- [x] 2.4 通过特性开关 `analysis_plan_header_v2` 控制新头部启用与回退。

## 3. 引导文案与移动端交互

- [x] 3.1 增加“当前步骤说明 + 下一步提示”展示区域，覆盖进行中与完成态文案。
- [x] 3.2 为 `blocked` 与 `failed` 状态增加原因摘要与恢复建议文案展示。
- [x] 3.3 实现移动端紧凑摘要与展开/收起交互，确保不遮挡输入区。
- [x] 3.4 为超长文案实现精简降级策略，详细信息仅在展开态展示。

## 4. 可观测性、测试与验收

- [x] 4.1 新增埋点事件（如 `plan_header_rendered`、`plan_step_changed`、`plan_expand_toggled`、`plan_blocked_exposed`）。
- [x] 4.2 增加前端单测与状态适配测试，覆盖状态映射、步骤切换、异常状态文案与移动端折叠逻辑。
- [x] 4.3 增加端到端回归用例，验证顶部任务列表在分析全流程中的可见性与实时更新。
- [x] 4.4 完成最小回归验证：`pytest -q` 与 `cd web && npm run build`，并记录风险与回滚步骤。

## 验证记录

- [x] `pytest -q`（539 passed，5 skipped）
- [x] `cd web && npm run build`（通过）
- [x] `cd web && npx playwright test e2e/analysis-plan-header.spec.ts`（2 passed）

## 风险与回滚

- 风险：`analysis_plan_header_v2` 开启后，老会话中结构化计划事件缺失时可能只显示简化状态。
- 风险：`plan_progress` 事件若由第三方扩展发送非标准状态，前端会降级为 `not_started`。
- 回滚：将 `localStorage` 的 `nini_feature_analysis_plan_header_v2` 设为 `false`（或 URL 参数 `analysisPlanHeaderV2=0`）即可恢复旧展示路径。
