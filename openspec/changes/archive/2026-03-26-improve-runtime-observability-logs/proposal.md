## Why

在日志基础设施落地后，Nini 仍然会面临“日志存在但难以定位问题”的情况：关键异常路径中仍有不少 `logger.error()` 不带堆栈，代码里也存在较多 `except Exception: pass`，而模型调用、工具执行、检索和沙箱运行等关键链路缺少统一耗时信号。维护阶段要做稳定性和性能优化，这部分可观测性需要单独治理。

这个 change 聚焦运行期日志质量，而不是日志底座本身。目标是优先补齐高价值失败路径和关键耗时日志，让日志从“可保存”提升到“可用于排障与性能定位”。

## What Changes

- 为关键失败路径补充带 `exc_info=True` 的错误日志，提升异常可诊断性。
- 按风险分层治理静默吞错，优先修复业务失败路径中的 `except Exception: pass`。
- 为模型调用、工具执行、检索、沙箱和 Agent 单轮执行补充统一的耗时日志。
- 为当前缺少基础操作日志的关键模块补齐开始/结束/失败日志，优先覆盖 `workspace/manager.py` 等薄弱区域。
- 增加针对异常日志与耗时日志的测试或断言，确保新增日志语义可验证。
- 明确非目标：本 change 不扩展 `doctor`、不引入日志采样、不接入外部平台，也不要求对所有低风险清理路径一轮清零。

## Capabilities

### New Capabilities

- `runtime-observability-logs`: 定义关键异常日志、静默吞错治理和关键链路耗时日志的运行期可观测性要求。

### Modified Capabilities

- 无

## Impact

- 受影响代码主要位于 `src/nini/agent/runner.py`、`src/nini/agent/model_resolver.py`、`src/nini/tools/registry.py`、`src/nini/api/websocket.py`、`src/nini/api/routes.py`、`src/nini/workspace/manager.py`、`src/nini/sandbox/` 和 `src/nini/knowledge/`。
- 受影响行为主要是日志内容增强，不涉及对外 API 协议变更。
- 预计需要补充或更新日志相关测试，并执行 `pytest -q` 验证。
- 该 change 依赖 `add-logging-foundation` 提供的统一日志初始化与基础上下文能力，但不依赖新的第三方日志库。
