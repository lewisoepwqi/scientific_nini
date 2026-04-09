## REMOVED Requirements

### Requirement: FusionResult 数据结构
**Reason**: ResultFusionEngine 及其 FusionResult 数据类随融合层一起移除。融合将子 Agent 输出降维为单一文本，主 Agent 失去对各子 Agent 原始输出的独立判断能力。子 Agent 原始输出直接拼接返回，主 Agent 自行综合质量更高。
**Migration**: dispatch_agents 返回带 agent_id 标签的拼接文本，主 Agent 在下一轮直接综合各子 Agent 输出。

### Requirement: ResultFusionEngine 自动策略选择（strategy="auto"）
**Reason**: auto 策略在 summarize / hierarchical 分支下额外触发一次或多次 LLM 调用，增加延迟和成本，且对主 Agent 的综合推理无额外价值。
**Migration**: 无替代，直接拼接替代所有 fusion 策略。

### Requirement: ResultFusionEngine summarize 策略
**Reason**: 由主 Agent 综合替代，无需独立 summarize 调用。
**Migration**: 无替代。

### Requirement: ResultFusionEngine consensus 策略
**Reason**: 共识提取与冲突标注由主 Agent 在综合阶段自行判断，无需独立 consensus 调用。
**Migration**: 无替代。

### Requirement: ResultFusionEngine hierarchical 策略
**Reason**: 分批 summarize 的复杂度与维护成本不匹配其实际价值，主 Agent 可直接处理多个子 Agent 的原始输出。
**Migration**: 无替代；子 Agent 并发上限（默认 4）限制了单次派发规模，避免输出过长。
