## Why

`agent/runner.py` 的 ReAct 循环目前没有任何循环检测机制：当 LLM 陷入重复调用同一组工具的死循环时，系统会持续消耗 token 直到上下文窗口耗尽或用户手动中断。这是 P0 稳定性风险，在复杂科研任务中（数据加载失败、工具返回意外结果）尤其容易触发。

## What Changes

- 新增 `src/nini/agent/loop_guard.py`：实现 `LoopGuard` 类，基于工具调用哈希 + 滑动窗口检测重复模式
  - 对每轮 `tool_calls` 计算 `md5(sorted(name+args))` 生成 fingerprint
  - 同一 fingerprint 出现 ≥ 3 次：返回 `WARN` 决策，在下一轮 system 消息中注入警告
  - 同一 fingerprint 出现 ≥ 5 次：返回 `FORCE_STOP` 决策，强制清空 `tool_calls` 迫使 LLM 输出最终答案
  - 按 session_id 独立维护检测状态，LRU 缓存控制内存占用
- 修改 `src/nini/agent/runner.py`：在 ReAct 循环的 tool_call 处理段接入 `LoopGuard.check()`
- 新增 `tests/test_loop_guard.py`：覆盖 NORMAL / WARN / FORCE_STOP 三条路径及边界条件

## Capabilities

### New Capabilities

- `loop-guard`：Agent ReAct 循环的重复工具调用检测与强制终止能力

### Modified Capabilities

（无现有规格变更）

## Impact

- **修改文件**：`src/nini/agent/runner.py`（工具调用处理段）
- **新增文件**：`src/nini/agent/loop_guard.py`、`tests/test_loop_guard.py`
- **无 API 变更**：对 WebSocket 协议、前端、外部接口零影响
- **无新依赖**：仅使用标准库 `hashlib`、`json`、`collections`
