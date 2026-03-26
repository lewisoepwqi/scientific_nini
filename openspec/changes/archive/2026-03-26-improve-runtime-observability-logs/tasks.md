## 1. 关键异常路径增强

- [x] 1.1 梳理 `runner.py`、`model_resolver.py`、`websocket.py`、`tools/registry.py` 中缺少 traceback 的关键错误日志，并为意外失败路径补充 `exc_info=True`。
- [x] 1.2 审核高风险业务路径中的 `except Exception: pass`，将首批目标改为 warning、error 或 debug 日志记录。
- [x] 1.3 保持预期降级、拒绝和兼容分支的现有级别语义，不将所有分支统一升级为 error。

## 2. 关键耗时与薄弱模块日志

- [x] 2.1 在 `agent/runner.py`、`agent/model_resolver.py`、`tools/registry.py`、`knowledge/` 和 `sandbox/` 的关键链路补充统一耗时日志。
- [x] 2.2 在 `workspace/manager.py` 补充基础操作日志，并在 `api/routes.py` 中补充关键文件或会话操作失败日志。
- [x] 2.3 统一新增耗时日志的字段语义与表达方式，优先使用 `duration_ms`。

## 3. 测试与验证

- [x] 3.1 新增或更新测试，验证关键异常路径日志包含 traceback 或等效异常上下文。
- [x] 3.2 新增或更新测试，验证首批高风险静默吞错路径不再完全无日志。
- [x] 3.3 新增或更新测试，验证关键链路耗时日志可被捕获，并运行 `pytest -q` 完成回归验证。
