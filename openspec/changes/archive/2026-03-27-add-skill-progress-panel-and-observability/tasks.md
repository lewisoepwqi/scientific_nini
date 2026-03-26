## 1. 后端事件完善

- [x] 1.1 在 `src/nini/models/event_schemas.py` 中新增 `SkillSummaryEventData` 模型
- [x] 1.2 在 `src/nini/skills/contract_runner.py` 中，Skill 执行完成后发射 skill_summary 事件
- [x] 1.3 在 `src/nini/api/websocket.py` 中处理 review_confirm 和 review_cancel 客户端消息

## 2. 前端 store 扩展

- [x] 2.1 在 `web/src/store.ts` 中新增 skillExecution 切片和对应的 action
- [x] 2.2 在 WebSocket 事件处理器中消费 skill_step 和 skill_summary 事件

## 3. SkillProgressPanel 组件

- [x] 3.1 创建 `web/src/components/SkillProgressPanel.tsx`，展示步骤列表、状态、耗时
- [x] 3.2 实现 review_gate UI（确认/取消按钮，发送 WebSocket 消息）
- [x] 3.3 在适当位置（ChatPanel 或 AgentTurnGroup）集成 SkillProgressPanel

## 4. 输出等级标签

- [x] 4.1 在 `web/src/components/MessageBubble.tsx` 或 `AgentTurnGroup.tsx` 中添加输出等级标签展示逻辑

## 5. 测试与验证

- [x] 5.1 后端：编写 `tests/test_skill_observability.py`，验证 skill_summary 事件、review_confirm 消息处理
- [x] 5.2 前端：运行 `cd web && npm run build` 确认 TypeScript 编译通过
- [x] 5.3 后端：运行 `pytest -q` 确认全部测试通过且无回归
