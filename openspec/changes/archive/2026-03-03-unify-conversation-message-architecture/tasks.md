## 1. 后端消息模型收敛

- [x] 1.1 扩展 `src/nini/agent/session.py` 的消息写入方法，为 assistant / reasoning / tool 可见消息写入 `message_id`、`turn_id`、`event_type`、`operation` 等统一字段
- [x] 1.2 更新 `src/nini/memory/conversation.py` 的持久化与读取逻辑，确保 canonical message metadata 可落盘且兼容旧记录
- [x] 1.3 为后端消息记录结构补充单元测试，覆盖普通文本、reasoning、tool replace/complete 等路径

## 2. 历史消息接口统一

- [x] 2.1 收敛 `src/nini/api/routes.py` 与 `src/nini/api/session_routes.py` 中重复的消息历史路由，明确唯一对外契约
- [x] 2.2 更新历史接口返回结构，补齐 `message_id`、`turn_id`、reasoning / tool 关联字段及兼容旧记录的填充逻辑
- [x] 2.3 补充 API 测试，验证内存会话、磁盘恢复会话与旧历史记录都返回同一消息 schema

## 3. 前端消息归并统一

- [x] 3.1 抽取统一的消息 normalizer，使实时事件与历史恢复共用同一归并规则
- [x] 3.2 更新 `web/src/store/event-handler.ts`、`web/src/store/api-actions.ts`、`web/src/store/types.ts`，让 `message_id` / `turn_id` / lifecycle metadata 成为一等字段
- [x] 3.3 为前端归并逻辑补充测试，覆盖 append、replace、complete、reasoning merge 与刷新恢复一致性

## 4. 重连与重试对账

- [x] 4.1 在前端连接管理中加入 WebSocket 重连后的 session reconcile 流程，清理过期 buffer 并拉取 canonical history
- [x] 4.2 调整 stop / retry 逻辑，确保基于 `turn_id` 精确清理受影响回合而不是按内容猜测
- [x] 4.3 增加集成测试，覆盖断线重连、停止中断、重试上一轮后的消息一致性

## 5. 架构清理与收口

- [x] 5.1 识别并清理未接线或重复的前端 store 实现，明确唯一消息写入与事件处理入口
- [x] 5.2 清理与旧消息推断模型相关的死代码、兼容分支和注释，保留必要的历史兼容层
- [x] 5.3 更新相关文档，说明 canonical history schema、重连恢复策略和迁移边界

## 6. 回归验证

- [x] 6.1 运行后端回归：`pytest -q`
- [x] 6.2 运行前端验证：`cd web && npm test` 与 `cd web && npm run build`
- [x] 6.3 人工验证关键场景：工具触发的首轮文本、报告替换、刷新恢复、断线重连、reasoning 合并
