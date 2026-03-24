## 1. 核心模块实现

- [x] 1.1 新建 `src/nini/agent/loop_guard.py`，定义 `LoopGuardDecision` 枚举（NORMAL / WARN / FORCE_STOP）
- [x] 1.2 实现 `_hash_tool_calls(tool_calls)` 函数：排序后 JSON 序列化取 md5 前 12 位
- [x] 1.3 实现 `LoopGuard` 类：`__init__(warn_threshold=3, hard_limit=5, window_size=20, max_sessions=100)`
- [x] 1.4 实现 `LoopGuard.check(tool_calls, session_id) -> LoopGuardDecision`：滑动窗口计数逻辑
- [x] 1.5 实现 LRU 缓存：用 `OrderedDict` 维护最多 `max_sessions` 个 session 状态

## 2. Runner 集成

- [x] 2.1 在 `AgentRunner.__init__` 中初始化 `self._loop_guard = LoopGuard()`
- [x] 2.2 在 ReAct 循环 tool_calls 处理段（`if func_name == ...` 前）插入 `LoopGuard.check()` 调用
- [x] 2.3 处理 `WARN` 决策：构建警告 SystemMessage 并在下一轮 LLM 请求消息列表中注入
- [x] 2.4 处理 `FORCE_STOP` 决策：跳过工具执行，推送说明性 text 事件，`break` 退出循环

## 3. 测试

- [x] 3.1 新建 `tests/test_loop_guard.py`
- [x] 3.2 测试 `_hash_tool_calls`：相同调用不同顺序 → 相同哈希；不同参数 → 不同哈希
- [x] 3.3 测试 NORMAL 路径：fingerprint 出现 1-2 次返回 NORMAL
- [x] 3.4 测试 WARN 路径：fingerprint 出现第 3 次返回 WARN
- [x] 3.5 测试 FORCE_STOP 路径：fingerprint 出现第 5 次返回 FORCE_STOP
- [x] 3.6 测试 session 隔离：session A 的计数不影响 session B
- [x] 3.7 测试 LRU 淘汰：超过 max_sessions 时最旧 session 被淘汰
- [x] 3.8 集成测试：mock AgentRunner，验证 WARN 决策导致下一轮 LLM 消息列表中包含循环警告 SystemMessage
- [x] 3.9 集成测试：mock AgentRunner，验证 FORCE_STOP 决策导致推送 text 事件且不执行任何工具
- [x] 3.10 运行 `pytest tests/test_loop_guard.py -q` 全部通过

## 4. 验收

- [x] 4.1 运行 `pytest -q` 确认全量测试无回归
- [x] 4.2 运行 `black --check src/nini/agent/loop_guard.py tests/test_loop_guard.py`
- [x] 4.3 运行 `mypy src/nini/agent/loop_guard.py` 无类型错误
