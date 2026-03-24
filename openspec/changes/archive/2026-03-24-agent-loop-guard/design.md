## Context

`agent/runner.py` 实现了完整的 ReAct 循环（接收消息 → 调用 LLM → 解析 tool_calls → 执行工具 → 继续循环）。当前循环没有任何重复检测机制，LLM 在遇到工具执行失败、数据加载异常等情况时可能持续重复相同的工具调用，直到上下文窗口耗尽（消耗大量 token）或触发超时。

已有类似解决方案可参考：deer-flow 的 `loop_detection_middleware.py` 使用 md5 哈希 + 滑动窗口实现了该机制，算法自包含，无外部依赖，可直接移植思路。

## Goals / Non-Goals

**Goals:**
- 检测同一组 tool_calls 的重复调用（顺序无关）
- 三级响应策略：正常 → 警告注入 → 强制终止
- 按 session 独立隔离检测状态，避免跨会话干扰
- 零外部依赖，不影响现有 WebSocket 协议和前端

**Non-Goals:**
- 不检测"语义相似但参数略有不同"的循环（仅做哈希精确匹配）
- 不持久化循环检测状态（重启后重置，跨轮次循环不纳入）
- 不引入中间件链架构重构（直接在 runner.py 现有结构中集成）

## Decisions

### 决策 1：哈希算法选择 md5 而非内容比较
内容比较需要序列化整个 tool_calls 列表做字符串相等判断，而哈希可以做到：排序后哈希 → 同一组调用的不同排列产生相同 fingerprint（顺序无关）。md5 在此场景无安全需求，计算速度快，输出长度固定。

### 决策 2：阈值设计（warn=3, force=5）
- warn=3：第 3 次出现时发出警告，给 LLM 一次"意识到循环"的机会
- force=5：第 5 次出现时强制终止，兜底保证最终收敛
- 阈值通过 `LoopGuard.__init__` 参数暴露，可在 runner 实例化时按需调整，无需改配置文件

### 决策 3：FORCE_STOP 实现方式——直接 break + 推送 text 事件
检测到 FORCE_STOP 时，runner 跳过本轮所有工具执行，直接推送一条说明性 text 事件（"检测到工具调用死循环，已自动终止"），然后 `break` 退出 ReAct 循环。不再发起额外的 LLM 调用——若让 LLM 再产出一轮文字答案，有再次陷入循环的风险，且增加了不必要的延迟和 token 消耗。

### 决策 4：LRU 缓存控制内存
`LoopGuard` 用 `OrderedDict` 实现简单 LRU，最多缓存 100 个 session 的状态。session 结束时不需要显式清理，LRU 自动淘汰。

## Risks / Trade-offs

- **[风险] 误判正常的重复调用** → 缓解：阈值为 5 次，正常科研流程中极少出现同组工具被调用 5 次完全相同参数的情况；WARN 阶段 LLM 有机会调整行为
- **[风险] 哈希碰撞导致误触发** → 缓解：md5 12 位哈希碰撞概率极低（1/2^48），在此场景可以接受
- **[权衡] 滑动窗口 vs 全历史计数**：全历史计数在长会话中可能误判（早期调用的合理重复被统计进来）；滑动窗口（最近 20 次 tool_call 组）更精确，但实现略复杂。本次采用滑动窗口方案

## Migration Plan

- 纯新增逻辑，`runner.py` 中以 `if decision == FORCE_STOP` 分支接入，不修改现有执行路径
- 线上灰度：可通过将 `warn_threshold` 设为极大值（如 999）来"禁用"检测，实现热切换
- 回滚：删除 `loop_guard.py` 并移除 runner.py 中的 3 处调用点即可完全回滚

## Open Questions

（无，所有决策已明确）

> 已决定：WARN 阶段注入 SystemMessage（不用 ToolMessage），理由是 ToolMessage 必须关联一个 tool_call_id，强行构造会污染工具调用历史，导致后续 LLM 上下文错乱。
