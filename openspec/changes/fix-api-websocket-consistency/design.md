## Context

当前代码审查发现以下不一致问题：

1. **EventType 枚举不完整**: `src/nini/agent/events.py` 定义了 19 个事件类型，但 `websocket.py` 实际使用 25 个类型，其中 6 个类型（workspace_update, code_execution, stopped, session, pong, session_title）使用硬编码字符串而非枚举

2. **API 路由重复**: `routes.py` 和 `session_routes.py` 都定义了相同的 `/api/sessions/*` 端点，导致代码冗余

3. **WebSocket 文档过时**: `WSEvent.type` 字段的注释未包含所有实际使用的事件类型

## Goals / Non-Goals

**Goals:**
- 补充 EventType 枚举，包含所有实际使用的事件类型
- 将 WebSocket 代码中的硬编码字符串替换为枚举值
- 清理重复的路由定义
- 更新 WSEvent 文档注释

**Non-Goals:**
- 不修改事件类型的字符串值（保持向后兼容）
- 不改变任何 API 行为或响应格式
- 不引入新的功能

## Decisions

### Decision 1: 直接在 EventType 枚举中添加新事件

**选择**: 在 `EventType` 枚举中添加 6 个缺失的事件类型，而不是创建新的枚举类

**理由**:
- 这些事件虽然主要用于 WebSocket，但本质上是 Agent 事件系统的一部分
- 统一使用一个枚举类简化代码理解和维护
- 避免引入新的枚举类造成混淆

**替代方案**: 创建 `WebSocketEventType` 单独枚举 - 被拒绝，因为会增加复杂性

### Decision 2: 使用 `.value` 访问枚举值

**选择**: 在 `websocket.py` 中使用 `EventType.EVENT_NAME.value` 而不是直接比较枚举

**理由**:
- `_send_event()` 函数接受 `str` 类型的 `event_type` 参数
- 保持与现有代码风格一致
- 避免修改函数签名（减少变更范围）

### Decision 3: 从 routes.py 删除重复路由

**选择**: 删除 `routes.py` 中的会话管理路由，保留 `session_routes.py` 中的定义

**理由**:
- `session_routes.py` 更专注，职责更清晰
- `routes.py` 已经非常庞大（66+ 端点），需要减负
- `session_routes.py` 已经包含所有必需功能

**风险**: 确保两个文件的实现完全一致，避免功能丢失

### Decision 4: 不修改 WSEvent 的类型定义

**选择**: 只更新注释，不改变 `type: str` 的类型定义

**理由**:
- FastAPI/Pydantic 需要字符串类型来处理动态事件类型
- 前端也使用字符串比较，修改类型定义无实际收益
- 注释更新已足够提供开发指导

## Risks / Trade-offs

**[风险] 删除路由可能导致功能丢失**
→ **缓解**: 逐行对比 `routes.py` 和 `session_routes.py` 的实现，确保功能完全一致后再删除

**[风险] WebSocket 使用枚举可能引入运行时错误**
→ **缓解**: 所有枚举值的字符串与当前硬编码值完全一致，启动后进行 WebSocket 连接测试

**[风险] 修改 events.py 可能影响其他模块**
→ **缓解**: 只添加新枚举值，不修改现有值；运行完整测试套件验证

## Migration Plan

本变更无需迁移，因为：
- 所有事件类型的字符串值保持不变
- API 路径和响应格式不变
- 无数据库变更

**部署步骤**:
1. 修改 `events.py` - 添加枚举值
2. 修改 `websocket.py` - 使用枚举
3. 修改 `routes.py` - 删除重复路由
4. 修改 `schemas.py` - 更新注释
5. 运行类型检查和测试
6. 部署并验证

**回滚策略**: 直接回滚到上一版本，无数据影响

## Open Questions

无
