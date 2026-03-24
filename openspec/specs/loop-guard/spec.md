### Requirement: 工具调用哈希 Fingerprint 生成
系统 SHALL 对每轮 LLM 返回的 `tool_calls` 列表计算顺序无关的 md5 哈希 fingerprint（取前 12 位）。哈希计算 SHALL 先按 `(name, json(args, sort_keys=True))` 对调用列表排序，再序列化为 JSON 字符串后取 md5，确保相同工具调用的不同排列产生相同 fingerprint。

#### Scenario: 相同调用不同顺序产生相同 fingerprint
- **WHEN** 两轮 tool_calls 包含完全相同的工具名和参数，但顺序不同
- **THEN** 两次计算得到的 fingerprint 完全相同

#### Scenario: 不同参数产生不同 fingerprint
- **WHEN** 两轮 tool_calls 中同一工具的参数值不同
- **THEN** 两次计算得到的 fingerprint 不同

### Requirement: 三级循环检测响应
`LoopGuard` SHALL 维护每个 session 最近 20 次 tool_call 组的 fingerprint 滑动窗口，并按以下规则返回决策：
- 同一 fingerprint 在窗口内出现次数 < 3：返回 `NORMAL`
- 出现次数 ≥ 3 且 < 5：返回 `WARN`
- 出现次数 ≥ 5：返回 `FORCE_STOP`

#### Scenario: 正常调用返回 NORMAL
- **WHEN** 当前 fingerprint 在滑动窗口内出现次数少于 3 次
- **THEN** `LoopGuard.check()` 返回 `LoopGuardDecision.NORMAL`

#### Scenario: 重复 3 次触发 WARN
- **WHEN** 当前 fingerprint 在滑动窗口内累计出现第 3 次
- **THEN** `LoopGuard.check()` 返回 `LoopGuardDecision.WARN`

#### Scenario: 重复 5 次触发 FORCE_STOP
- **WHEN** 当前 fingerprint 在滑动窗口内累计出现第 5 次
- **THEN** `LoopGuard.check()` 返回 `LoopGuardDecision.FORCE_STOP`

### Requirement: WARN 阶段警告消息注入
当 `LoopGuard` 返回 `WARN` 时，runner SHALL 在下一轮 LLM 请求的消息列表中注入一条 SystemMessage，内容提示 LLM 检测到重复调用模式，要求其尝试不同方法或直接给出结论。

#### Scenario: WARN 决策触发警告注入
- **WHEN** `LoopGuard.check()` 返回 `WARN`
- **THEN** runner 在下一轮 LLM 请求中包含循环警告 SystemMessage
- **THEN** 当前轮工具调用正常继续执行，不中断

### Requirement: FORCE_STOP 强制终止循环
当 `LoopGuard` 返回 `FORCE_STOP` 时，runner SHALL 跳过工具执行，直接终止当前 ReAct 循环并向用户推送包含说明的最终回复。

#### Scenario: FORCE_STOP 决策终止循环
- **WHEN** `LoopGuard.check()` 返回 `FORCE_STOP`
- **THEN** runner 不执行当前轮的任何工具调用
- **THEN** runner 向 WebSocket 推送 text 事件，内容说明因检测到循环而终止
- **THEN** 当前 turn 正常结束，不抛出异常

### Requirement: Session 隔离与 LRU 内存管理
`LoopGuard` SHALL 按 `session_id` 独立维护滑动窗口状态，不同 session 的检测状态互不干扰。内部缓存 SHALL 使用 LRU 策略，最多保留 100 个 session 的状态，超出时自动淘汰最久未访问的条目。

#### Scenario: 不同 session 状态互不影响
- **WHEN** session A 中某 fingerprint 出现 4 次（WARN 状态）
- **THEN** session B 中相同 fingerprint 首次出现时仍返回 `NORMAL`

#### Scenario: LRU 淘汰超出限制的 session
- **WHEN** `LoopGuard` 已缓存 100 个 session 状态，第 101 个 session 发起检测
- **THEN** 最久未访问的 session 状态被自动淘汰，新 session 正常初始化
