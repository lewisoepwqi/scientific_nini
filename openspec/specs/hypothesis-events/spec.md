# Capability: hypothesis-events

## Purpose

定义 Hypothesis-Driven 范式所需的事件类型枚举和 payload 构造函数，扩展 `EventType` 枚举并提供 `event_builders.py` 中的标准化事件 payload 构建接口。

## Requirements

### Requirement: EventType 枚举包含假设推理事件类型
`src/nini/agent/events.py` 的 `EventType` 枚举 SHALL 包含以下 6 个新值：
- `HYPOTHESIS_GENERATED = "hypothesis_generated"`：LLM 生成初始假设
- `EVIDENCE_COLLECTED = "evidence_collected"`：工具调用收集到证据
- `HYPOTHESIS_VALIDATED = "hypothesis_validated"`：假设被证实（confidence 达到阈值）
- `HYPOTHESIS_REFUTED = "hypothesis_refuted"`：假设被证伪（触发修正）
- `HYPOTHESIS_REVISED = "hypothesis_revised"`：假设被修正为新版本
- `PARADIGM_SWITCHED = "paradigm_switched"`：执行路径切换为 Hypothesis-Driven 范式

#### Scenario: 枚举值可通过字符串访问
- **WHEN** 访问 `EventType.HYPOTHESIS_GENERATED`
- **THEN** 其值 SHALL 为字符串 `"hypothesis_generated"`

#### Scenario: 新枚举值不与现有值冲突
- **WHEN** 初始化 `EventType` 枚举
- **THEN** 6 个新值 SHALL 与 Phase 1/2 的所有现有枚举值不重名

---

### Requirement: 假设事件 payload 结构规范
`src/nini/agent/event_builders.py` SHALL 提供以下构造函数，返回格式化的事件 payload dict：

- `build_hypothesis_generated_event(agent_id, hypotheses: list[dict])` → `{"event_type": "hypothesis_generated", "agent_id": ..., "hypotheses": [{"id": ..., "content": ..., "confidence": ...}]}`
- `build_evidence_collected_event(agent_id, hypothesis_id, evidence_type, evidence_content)` → `{"event_type": "evidence_collected", "agent_id": ..., "hypothesis_id": ..., "evidence_type": "for"|"against", "content": ...}`
- `build_hypothesis_validated_event(agent_id, hypothesis_id, confidence)` → `{"event_type": "hypothesis_validated", "agent_id": ..., "hypothesis_id": ..., "confidence": ...}`
- `build_hypothesis_refuted_event(agent_id, hypothesis_id, reason)` → `{"event_type": "hypothesis_refuted", "agent_id": ..., "hypothesis_id": ..., "reason": ...}`
- `build_paradigm_switched_event(agent_id, paradigm)` → `{"event_type": "paradigm_switched", "agent_id": ..., "paradigm": "hypothesis_driven"}`

#### Scenario: build_hypothesis_generated_event 结构合法
- **WHEN** 调用 `build_hypothesis_generated_event("literature_reading", [{"id": "h1", "content": "...", "confidence": 0.5}])`
- **THEN** 返回 dict 的 `event_type` SHALL 为 `"hypothesis_generated"`
- **AND** `hypotheses` 字段 SHALL 包含传入的假设列表

#### Scenario: build_evidence_collected_event 区分证据类型
- **WHEN** 调用 `build_evidence_collected_event("literature_reading", "h1", "against", "研究 X 未复现该结论")`
- **THEN** 返回 dict 的 `evidence_type` SHALL 为 `"against"`
- **AND** `content` 字段 SHALL 包含证据内容

#### Scenario: build_paradigm_switched_event 包含范式标识
- **WHEN** 调用 `build_paradigm_switched_event("literature_reading", "hypothesis_driven")`
- **THEN** 返回 dict 的 `paradigm` SHALL 为 `"hypothesis_driven"`
