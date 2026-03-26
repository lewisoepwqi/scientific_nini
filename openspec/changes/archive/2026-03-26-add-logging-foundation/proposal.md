## Why

当前 Nini 的日志仍停留在“能打印”阶段：应用层只通过 `basicConfig()` 输出到控制台，历史日志不会持久化，HTTP `request_id` 也没有进入日志上下文。同时，CLI `--log-level` 与应用内部日志级别分离，导致运行时行为不一致。维护阶段要做稳定性和可观测性优化，必须先补齐日志基础设施。

这个 change 聚焦日志基础设施最小闭环，先解决统一初始化、文件持久化和核心上下文字段传播，为后续异常治理与耗时日志提供稳定底座。

## What Changes

- 新增统一日志配置入口，替代 `app.py` 中分散且极简的 `basicConfig()` 初始化。
- 为应用日志增加文件持久化与基础轮转策略，同时保留控制台输出。
- 对齐 CLI `--log-level` 与应用日志级别，避免 Uvicorn 与应用日志配置分裂。
- 为 HTTP 请求、WebSocket 连接和会话处理链路补齐最小上下文传播能力。
- 新增日志基础设施测试，验证初始化、文件输出和上下文绑定行为。
- 明确非目标：本 change 不引入日志查看 CLI、不做日志采样、不接入外部可观测性平台，也不要求一次性切换到 structlog。

## Capabilities

### New Capabilities

- `logging-foundation`: 定义 Nini 的统一日志初始化、文件持久化、级别对齐与最小上下文传播行为。

### Modified Capabilities

- 无

## Impact

- 受影响代码主要位于 `src/nini/app.py`、`src/nini/__main__.py`、`src/nini/api/websocket.py`、`src/nini/config.py`。
- 预计新增 `src/nini/logging_config.py` 作为集中配置入口。
- 受影响系统包括 FastAPI 生命周期、WebSocket 会话处理和本地文件系统日志目录。
- 不引入外部平台依赖；如需新增第三方日志库，应在后续 change 单独评估。
- 验证重点为 `pytest -q` 下的日志初始化与上下文传播测试，必要时补充 CLI 相关测试。
