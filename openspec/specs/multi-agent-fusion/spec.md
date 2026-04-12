# Capability: Multi-Agent Fusion

## Purpose

记录 ResultFusionEngine 融合层的移除决策。子 Agent 原始输出直接以 agent_id 标签拼接返回，主 Agent 在下一轮自行综合，质量高于预先融合。

## Requirements

_此 capability 所有要求已移除，见下方移除记录。_

## Removed Requirements

### Removed: FusionResult 数据结构
**原因**: ResultFusionEngine 及其 FusionResult 数据类随融合层一起移除。融合将子 Agent 输出降维为单一文本，主 Agent 失去对各子 Agent 原始输出的独立判断能力。子 Agent 原始输出直接拼接返回，主 Agent 自行综合质量更高。
**迁移**: dispatch_agents 返回带 agent_id 标签的拼接文本，主 Agent 在下一轮直接综合各子 Agent 输出。

### Removed: ResultFusionEngine 自动策略选择（strategy="auto"）
**原因**: auto 策略在 summarize / hierarchical 分支下额外触发一次或多次 LLM 调用，增加延迟和成本，且对主 Agent 的综合推理无额外价值。
**迁移**: 无替代，直接拼接替代所有 fusion 策略。

### Removed: ResultFusionEngine summarize 策略
**原因**: 由主 Agent 综合替代，无需独立 summarize 调用。
**迁移**: 无替代。

### Removed: ResultFusionEngine consensus 策略
**原因**: 共识提取与冲突标注由主 Agent 在综合阶段自行判断，无需独立 consensus 调用。
**迁移**: 无替代。

### Removed: ResultFusionEngine hierarchical 策略
**原因**: 分批 summarize 的复杂度与维护成本不匹配其实际价值，主 Agent 可直接处理多个子 Agent 的原始输出。
**迁移**: 无替代；子 Agent 并发上限（默认 4）限制了单次派发规模，避免输出过长。
