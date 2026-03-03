## Why

Nini 项目在 AI 对话流程中反复出现消息重复显示的问题。根本原因是**流式消息（streaming chunks）和最终消息（final message）没有明确的语义区分**，导致前端无法正确识别和处理重复内容。具体表现为：当 `generate_report` 等工具执行后，后端会再次发送完整报告内容，而前端将其视为新消息追加显示，造成用户看到重复内容。刷新页面后问题消失，因为前端状态重置并从后端持久化状态重建。

## What Changes

### 架构层面
- **引入消息ID机制**：所有流式更新共享同一消息ID，前端基于消息ID去重
- **明确消息语义**：区分 `append`（追加）、`replace`（替换）、`complete`（完成）三种消息操作类型
- **统一状态管理**：前端 `_streamingText` 与后端 `session.messages` 建立明确同步关系

### 代码修改
- **BREAKING**: 修改 `WSEvent` 类型，添加 `metadata.message_id` 和 `metadata.operation` 字段
- **后端**: `runner.py` 中为所有 TEXT 事件分配消息ID，修复 `generate_report` 重复发送问题
- **前端**: `event-handler.ts` 基于消息ID和 operation 类型处理消息，而非简单追加
- **API**: WebSocket 协议增加 `message_id` 和 `operation` 字段（向后兼容）

## Capabilities

### New Capabilities
- `message-deduplication`: 基于消息ID的去重机制，确保同一消息的多次更新不会重复显示
- `semantic-message-operations`: 消息语义操作（append/replace/complete），明确消息更新的意图

### Modified Capabilities
- `websocket-protocol`: WebSocket 事件协议扩展，增加 `metadata.message_id` 和 `metadata.operation` 字段

## Impact

### 受影响代码
- `src/nini/agent/runner.py`: Agent TEXT 事件生成逻辑
- `src/nini/models/schemas.py`: WSEvent 模型定义
- `web/src/store/event-handler.ts`: WebSocket 事件处理
- `web/src/store/types.ts`: Message 和 WSEvent 类型定义

### API 变更
- WebSocket 事件 `metadata` 字段新增 `message_id` (string) 和 `operation` ("append" | "replace" | "complete")
- 向后兼容：旧客户端无这些字段时按原逻辑处理

### 依赖
- 无新外部依赖
- 需要前后端同步部署
