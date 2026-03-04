## 1. EventType 枚举补充

- [x] 1.1 在 `src/nini/agent/events.py` 的 EventType 枚举中添加 WORKSPACE_UPDATE = "workspace_update"
- [x] 1.2 在 EventType 枚举中添加 CODE_EXECUTION = "code_execution"
- [x] 1.3 在 EventType 枚举中添加 STOPPED = "stopped"
- [x] 1.4 在 EventType 枚举中添加 SESSION = "session"
- [x] 1.5 在 EventType 枚举中添加 PONG = "pong"
- [x] 1.6 在 EventType 枚举中添加 SESSION_TITLE = "session_title"
- [x] 1.7 运行类型检查验证 EventType 枚举总数为 25 个

## 2. WebSocket 代码更新

- [x] 2.1 在 `src/nini/api/websocket.py` 顶部添加 `from nini.agent.events import EventType`
- [x] 2.2 将第 167 行的 `"workspace_update"` 替换为 `EventType.WORKSPACE_UPDATE.value`
- [x] 2.3 将第 175 行的 `"workspace_update"` 替换为 `EventType.WORKSPACE_UPDATE.value`
- [x] 2.4 将第 242 行的 `"code_execution"` 替换为 `EventType.CODE_EXECUTION.value`
- [x] 2.5 将第 291 行的 `"pong"` 替换为 `EventType.PONG.value`
- [x] 2.6 将第 303 行的 `"stopped"` 替换为 `EventType.STOPPED.value`
- [x] 2.7 将第 305 行的 `"stopped"` 替换为 `EventType.STOPPED.value`
- [x] 2.8 将第 378 行的 `"session"` 替换为 `EventType.SESSION.value`
- [x] 2.9 将第 409 行的 `"session"` 替换为 `EventType.SESSION.value`
- [x] 2.10 将第 453 行的 `"session_title"` 替换为 `EventType.SESSION_TITLE.value`
- [x] 2.11 将第 469 行的 `"pong"` 替换为 `EventType.PONG.value`
- [x] 2.12 运行 Python 语法检查验证无错误

## 3. 清理重复路由

- [x] 3.1 对比 `routes.py` 和 `session_routes.py` 中的 `/sessions` GET 端点实现
- [x] 3.2 对比 `/sessions/{session_id}` GET 端点实现
- [x] 3.3 对比 `/sessions` POST 端点实现
- [x] 3.4 对比 `/sessions/{session_id}` PATCH 端点实现
- [x] 3.5 对比 `/sessions/{session_id}/compress` POST 端点实现
- [x] 3.6 对比 `/sessions/{session_id}` DELETE 端点实现
- [x] 3.7 对比 `/sessions/{session_id}/rollback` POST 端点实现
- [x] 3.8 对比 `/sessions/{session_id}/messages` GET 端点实现
- [x] 3.9 对比 `/sessions/{session_id}/export-all` GET 端点实现
- [x] 3.10 对比 `/sessions/{session_id}/token-usage` GET 端点实现
- [x] 3.11 对比 `/sessions/{session_id}/memory-files` GET 端点实现
- [x] 3.12 对比 `/sessions/{session_id}/memory-files/{filename:path}` GET 端点实现
- [x] 3.13 对比 `/sessions/{session_id}/context-size` GET 端点实现
- [x] 3.14 从 `routes.py` 删除上述 13 个重复端点
- [x] 3.15 运行 Python 语法检查验证无错误

## 4. 更新 WSEvent 文档

- [x] 4.1 在 `src/nini/models/schemas.py` 中更新 WSEvent.type 字段注释
- [x] 4.2 添加所有 25 个事件类型的注释说明
- [x] 4.3 运行 Python 语法检查验证无错误

## 5. 验证测试

- [x] 5.1 运行 `python -c "from nini.agent.events import EventType; print(len(EventType))"` 验证枚举数量为 25
- [x] 5.2 运行 `python -m py_compile src/nini/agent/events.py` 验证语法
- [x] 5.3 运行 `python -m py_compile src/nini/api/websocket.py` 验证语法
- [x] 5.4 运行 `python -m py_compile src/nini/api/routes.py` 验证语法
- [x] 5.5 运行 `python -m py_compile src/nini/models/schemas.py` 验证语法
- [x] 5.6 启动服务并访问 `/docs` 确认会话路由正常
- [x] 5.7 使用浏览器 WebSocket 连接测试事件接收正常
- [x] 5.8 运行项目测试套件验证无回归
