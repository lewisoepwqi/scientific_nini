## Why

Nini 当前的对话链路同时存在“实时事件模型”和“历史消息模型”两套表达，导致同一条助手消息在流式显示、工具执行、刷新恢复、断线重连时缺乏统一身份。重复气泡只是表象，更深层的问题是消息语义没有贯穿 WebSocket、Session 持久化和前端状态恢复，导致同类缺陷反复出现且难以一次性修复。

当前仓库还存在重复的消息历史路由与并行的前端 store 实现，进一步放大了架构漂移风险。现在进入维护阶段，继续在局部打补丁的成本已经高于统一消息架构的成本，因此需要发起一次收敛式迭代。

## What Changes

- 建立统一的对话消息生命周期模型，为助手文本、推理、工具产出定义稳定的消息身份与操作语义。
- 将 `message_id`、`turn_id`、消息类型和必要元数据纳入 Session 持久化与历史接口，确保刷新恢复与实时流使用同一语义模型。
- 新增会话状态对账能力，覆盖页面刷新、WebSocket 重连、重试上一轮和工具中断后的状态恢复。
- 收敛重复的消息历史 API 与前端 store 实现，明确单一读写路径和唯一的消息归并入口。
- **BREAKING**：统一历史消息接口与前端消息模型，历史读取结果将补充稳定身份字段与事件元数据，旧的“仅按内容推断消息关系”的实现视为废弃。

## Capabilities

### New Capabilities
- `conversation-message-lifecycle`: 定义消息身份、生命周期操作和实时流到持久化的一致性契约。
- `conversation-session-reconciliation`: 定义刷新、重连、重试等场景下的会话状态重建与对账行为。

### Modified Capabilities
- `conversation`: 从仅关注 token usage 扩展为要求对话事件流具备可恢复、可对账的消息语义。
- `explainability-enhancement`: 推理消息需要具备稳定身份，并在流式展示、最终完成和刷新恢复后保持一致的合并关系。

## Impact

- 受影响后端：`src/nini/agent/runner.py`、`src/nini/agent/session.py`、`src/nini/memory/conversation.py`、`src/nini/api/websocket.py`、`src/nini/api/routes.py`、`src/nini/api/session_routes.py`
- 受影响前端：`web/src/store.ts`、`web/src/store/event-handler.ts`、`web/src/store/api-actions.ts`、`web/src/store/types.ts` 以及未接线的 slice 文件
- 受影响协议：WebSocket `text/reasoning/tool_*` 事件元数据、`/api/sessions/{id}/messages` 历史返回格式
- 依赖影响：无新增第三方依赖，需同步更新测试、OpenSpec capability 和前后端回归用例
