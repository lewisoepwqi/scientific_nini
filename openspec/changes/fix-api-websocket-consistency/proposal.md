## Why

根据 Agent Teams 代码审查结果，发现前后端对接存在关键不一致问题：EventType 枚举缺少 6 个实际使用的事件类型、API 路由重复定义、WebSocket 文档过时。这些问题降低了代码可维护性，增加新开发者理解难度，需要立即修复以确保代码一致性和类型安全。

## What Changes

- **补充 EventType 枚举**: 在 `events.py` 中添加 6 个缺失的 WebSocket 事件类型（WORKSPACE_UPDATE, CODE_EXECUTION, STOPPED, SESSION, PONG, SESSION_TITLE）
- **WebSocket 代码使用枚举**: 将 `websocket.py` 中的硬编码字符串替换为 EventType 枚举值
- **清理重复路由**: 从 `routes.py` 删除与 `session_routes.py` 重复的会话管理端点
- **更新 WSEvent 文档**: 在 `schemas.py` 中更新事件类型注释，包含所有实际使用的事件类型

## Capabilities

### New Capabilities
<!-- 无新增功能规格，本变更为代码维护性修复 -->

### Modified Capabilities
<!-- 无规格级别变更，本变更为纯实现层面的修复 -->

## Impact

**受影响文件**:
- `src/nini/agent/events.py` - 添加 EventType 枚举值
- `src/nini/api/websocket.py` - 使用枚举替换字符串
- `src/nini/api/routes.py` - 删除重复路由
- `src/nini/models/schemas.py` - 更新文档注释

**向后兼容性**: 完全兼容，所有事件类型的字符串值保持不变

**验证方式**: Python 类型检查、语法验证、服务启动测试、WebSocket 连接测试
