## Context

前端使用 React 18 + Zustand + Tailwind。WebSocket 事件通过 `store.ts` 中的事件处理器消费，更新 Zustand store 后 React 自动重渲染。现有组件如 `AnalysisTasksPanel` 已展示任务进度（task_write 事件），可参考其模式。后端 C4/C11 的 ContractRunner 发射 `skill_step` 事件。C2 在 `DoneEventData` 中新增了 `output_level` 字段。

## Goals / Non-Goals

**Goals:**
- 实现 Skill 进度面板
- 实现 review_gate 前端交互
- 展示输出等级标签
- 完善 observability 事件

**Non-Goals:**
- 不实现证据链可视化
- 不实现步骤编辑

## Decisions

### D1: SkillProgressPanel 组件设计

**选择**：新建 `SkillProgressPanel.tsx` 组件，参考 `AnalysisTasksPanel` 的模式：

```
┌─────────────────────────────────────┐
│ 🔬 实验设计引导                      │
│ ─────────────────────────────────── │
│ ✅ 问题定义          0.8s           │
│ ✅ 设计选择          1.2s           │
│ 🔄 参数计算          ...            │
│ ⏳ 方案生成（需人工确认）            │
│ ─────────────────────────────────── │
│ 信任等级: T1 | 输出等级: O2          │
└─────────────────────────────────────┘
```

**理由**：与现有任务面板风格一致。步骤状态图标：✅ completed、🔄 in_progress、⏳ pending、⚠️ review_required、❌ failed、⏭️ skipped。

### D2: review_gate UI

**选择**：当收到 `skill_step` 事件且 status="review_required" 时，在面板中展示确认按钮。用户点击后发送 `review_confirm` WebSocket 消息到后端。

后端 `websocket.py` 接收 `review_confirm` 消息后，通知 ContractRunner 的 asyncio.Event。

**理由**：最简交互。无需弹窗或独立页面。

### D3: 输出等级标签

**选择**：在 `MessageBubble` 或 `AgentTurnGroup` 组件中，当 done 事件包含 `output_level` 时，在消息底部展示等级标签。

标签样式：
- O1: 灰色标签「建议级」
- O2: 蓝色标签「草稿级」
- O3: 绿色标签「可审阅级」
- O4: 紫色标签「可导出级」

**理由**：非侵入式展示，不干扰阅读。颜色区分等级。

### D4: Zustand store 扩展

**选择**：在 store 中新增 `skillExecution` 切片：

```typescript
interface SkillExecutionState {
  activeSkill: string | null
  steps: SkillStepInfo[]
  trustCeiling: string | null
  outputLevel: string | null
}
```

WebSocket 事件处理器在收到 `skill_step` 事件时更新此切片。

### D5: skill_summary 事件

**选择**：ContractRunner 在 Skill 执行完成后发射 `skill_summary` 事件，包含 skill_name、total_steps、completed_steps、skipped_steps、failed_steps、total_duration_ms、overall_status。

**理由**：前端可据此切换面板状态（从进行中→已完成），也可用于后续的执行历史记录。

## Risks / Trade-offs

- **[风险] review_gate 的前后端同步** → 使用 WebSocket 双向通信，后端等待事件，前端发送确认。超时机制在后端已有（C4）。
- **[风险] 前端组件增加包体积** → SkillProgressPanel 是轻量组件（~200 行 TSX），影响极小。
- **[回滚]** 删除新建组件 + revert store 和 MessageBubble 即可恢复。
