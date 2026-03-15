# Capability: hypothesis-tracker-ui

## Purpose

提供前端假设推理状态管理和可视化组件，包括 Zustand store slice、事件处理器和 `HypothesisTracker` React 组件，展示假设卡片列表、置信度进度条及可折叠证据链。

## Requirements

### Requirement: 前端假设状态 Slice
`web/src/store/hypothesis-slice.ts` SHALL 维护假设推理状态，包含：
- `hypotheses: HypothesisInfo[]`：当前活跃的假设列表
- `currentPhase: string`：当前推理阶段（`generation` / `collection` / `validation` / `conclusion`）
- `iterationCount: number`：当前迭代轮次
- `activeAgentId: string | null`：正在执行假设推理的 Agent ID

`web/src/store/types.ts` SHALL 新增 `HypothesisInfo` 接口：`id`、`content`、`confidence: number`（0-1）、`status: 'pending' | 'validated' | 'refuted' | 'revised'`、`evidenceFor: string[]`、`evidenceAgainst: string[]`。

#### Scenario: 初始状态为空
- **WHEN** 应用初始化
- **THEN** `hypotheses` SHALL 为空数组
- **AND** `activeAgentId` SHALL 为 `null`

#### Scenario: hypothesis_generated 事件写入 hypotheses
- **WHEN** 接收到 `hypothesis_generated` 事件（包含 2 个假设）
- **THEN** store 中 `hypotheses` SHALL 包含 2 个 `HypothesisInfo`，`status` 均为 `"pending"`

---

### Requirement: 假设事件处理器
`web/src/store/hypothesis-event-handler.ts` SHALL 处理以下事件类型，更新对应 store 状态：
- `hypothesis_generated`：清空现有假设，写入新假设列表
- `evidence_collected`：向对应 hypothesis 的 `evidenceFor` 或 `evidenceAgainst` 追加内容
- `hypothesis_validated`：更新对应 hypothesis `status` 为 `"validated"`，更新 `confidence`
- `hypothesis_refuted`：更新对应 hypothesis `status` 为 `"refuted"`
- `paradigm_switched`：设置 `activeAgentId`，将 `currentPhase` 重置为 `"generation"`

处理器 SHALL 在 `web/src/store/event-handler.ts` 中被注册。

#### Scenario: evidence_collected 追加到正确假设
- **WHEN** 接收到 `evidence_collected` 事件，`hypothesis_id == "h1"`，`evidence_type == "for"`
- **THEN** id 为 `"h1"` 的假设的 `evidenceFor` SHALL 包含该证据内容
- **AND** 其他假设的证据列表 SHALL 不受影响

#### Scenario: hypothesis_validated 更新 confidence
- **WHEN** 接收到 `hypothesis_validated` 事件，`confidence == 0.8`
- **THEN** 对应假设的 `confidence` SHALL 更新为 0.8
- **AND** `status` SHALL 更新为 `"validated"`

---

### Requirement: HypothesisTracker 组件
`web/src/components/HypothesisTracker.tsx` SHALL 从 store 读取假设状态，渲染假设卡片列表：
- 每张卡片展示：假设内容、置信度进度条（0-1 映射为 0%-100%）、状态标签（pending/validated/refuted/revised）
- 证据链支持折叠/展开：默认折叠，点击展开显示 `evidenceFor` 和 `evidenceAgainst` 列表
- 组件 SHALL 仅在 `hypotheses.length > 0` 时渲染，否则返回 `null`
- 组件 SHALL 在 `App.tsx` 或 `ChatPanel.tsx` 中条件渲染，位于对话面板上方

#### Scenario: 空假设列表时不渲染
- **WHEN** store 中 `hypotheses` 为空数组
- **THEN** `HypothesisTracker` SHALL 返回 `null`，不渲染任何 DOM 元素

#### Scenario: 假设卡片展示置信度进度条
- **WHEN** 一个假设的 `confidence == 0.7`
- **THEN** 对应卡片的置信度进度条 SHALL 显示为 70% 宽度

#### Scenario: 证据链折叠展开
- **WHEN** 用户点击假设卡片的证据展开按钮
- **THEN** 该假设的 `evidenceFor` 和 `evidenceAgainst` 列表 SHALL 变为可见
- **AND** 再次点击 SHALL 收起证据列表

#### Scenario: 状态标签颜色区分
- **WHEN** 假设 `status == "validated"`
- **THEN** 状态标签 SHALL 使用绿色样式
- **WHEN** 假设 `status == "refuted"`
- **THEN** 状态标签 SHALL 使用红色样式
- **WHEN** 假设 `status == "pending"`
- **THEN** 状态标签 SHALL 使用灰色/蓝色样式
