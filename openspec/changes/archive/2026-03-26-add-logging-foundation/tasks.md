## 1. 日志初始化与配置入口

- [x] 1.1 新增 `src/nini/logging_config.py`，实现统一日志初始化函数并支持控制台与文件 handler。
- [x] 1.2 修改 `src/nini/app.py`，将生命周期中的日志初始化切换到统一入口。
- [x] 1.3 修改 `src/nini/config.py`，补充日志目录、日志级别或相关基础配置项。

## 2. 级别对齐与上下文传播

- [x] 2.1 修改 `src/nini/__main__.py`，让 `--log-level` 同时影响应用日志与 Uvicorn 日志。
- [x] 2.2 修改 `src/nini/app.py` HTTP 中间件，在请求作用域内绑定并清理 `request_id` 上下文。
- [x] 2.3 修改 `src/nini/api/websocket.py`，在建连作用域绑定 `connection_id`，在消息处理作用域绑定并清理 `session_id`。

## 3. 测试与验证

- [x] 3.1 新增或更新测试，覆盖日志文件生成、轮转基础行为和现有 stdlib logger 兼容性。
- [x] 3.2 新增或更新测试，覆盖 HTTP `request_id` 与 WebSocket `connection_id` / `session_id` 的上下文传播。
- [x] 3.3 运行 `pytest -q` 验证后端测试通过，并检查 `tests/test_phase7_cli.py` 是否需要补充 CLI 日志级别相关断言。
