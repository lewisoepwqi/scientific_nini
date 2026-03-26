## Why

C4/C11 的 ContractRunner 在执行 Skill 步骤时发射 `skill_step` 事件，但前端目前没有消费这些事件。用户无法看到 Skill 执行的进度、当前步骤、信任等级和证据链。本 change 在前端实现 Skill 进度面板，消费 `skill_step` 事件并展示实时进度，同时完善后端的 observability 事件格式。

## What Changes

- **前端 Skill 进度面板**：在 `web/src/components/` 中新增 `SkillProgressPanel` 组件，实时展示 Skill 执行进度（步骤列表、当前步骤高亮、状态标记、耗时）。
- **前端 review_gate UI**：在进度面板中展示 review_gate 提示，用户可确认或取消。
- **前端输出等级标签**：在消息气泡中展示输出等级标签（O1/O2/O3/O4），消费 DoneEventData 中的 output_level 字段。
- **后端事件完善**：确保 SkillStepEventData 的字段在各场景下正确填充，新增 `skill_summary` 事件（Skill 执行完成后的摘要事件）。
- **Zustand store 扩展**：在前端 store 中新增 skill 执行状态管理。

## Non-Goals

- 不实现证据链的可视化（仅展示进度和输出等级）。
- 不实现 Skill 步骤的编辑或自定义。
- 不实现历史 Skill 执行记录的回放。

## Capabilities

### New Capabilities

- `skill-progress-ui`: Skill 进度面板——涵盖前端组件、事件消费、review_gate UI
- `output-level-display`: 输出等级展示——涵盖消息气泡的等级标签
- `skill-observability-events`: Skill 可观测性事件——涵盖事件格式完善和摘要事件

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`web/src/components/SkillProgressPanel.tsx`（新建）、`web/src/store.ts`（扩展）、`web/src/components/MessageBubble.tsx`（输出等级标签）、`src/nini/models/event_schemas.py`（摘要事件）、`src/nini/api/websocket.py`（review_gate 确认消息处理）
- **影响范围**：前端组件新增，现有组件小幅扩展
- **API / 依赖**：WebSocket 消息新增 `skill_step` 和 `skill_summary` 事件类型、新增 `review_confirm` 客户端消息类型
- **风险**：前端组件新增不影响现有功能；review_gate UI 需要与后端 asyncio.Event 配合
- **回滚**：删除新建前端组件 + revert store 和 MessageBubble 的扩展即可恢复
- **验证方式**：前端构建验证（`npm run build`）；E2E 测试验证进度面板渲染；后端 pytest 验证事件格式
