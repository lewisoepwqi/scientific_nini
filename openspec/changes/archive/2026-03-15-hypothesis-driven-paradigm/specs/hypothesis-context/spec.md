## ADDED Requirements

### Requirement: Hypothesis 数据类
系统 SHALL 提供 `Hypothesis` 数据类，字段包括：`id: str`（唯一标识）、`content: str`（假设内容）、`confidence: float`（置信度，初始值 0.5，范围 [0.0, 1.0]）、`evidence_for: list[str]`（支持证据列表）、`evidence_against: list[str]`（反驳证据列表）、`status: str`（状态，取值 `pending` / `validated` / `refuted` / `revised`）。

#### Scenario: 创建有效的 Hypothesis 实例
- **WHEN** 以合法字段实例化 `Hypothesis`
- **THEN** 所有字段 SHALL 可通过属性访问
- **AND** `confidence` 未传入时 SHALL 默认为 0.5
- **AND** `status` 未传入时 SHALL 默认为 `"pending"`

#### Scenario: evidence 列表默认为空
- **WHEN** 实例化 `Hypothesis` 时不传入 `evidence_for` 和 `evidence_against`
- **THEN** 两者 SHALL 默认为空列表 `[]`，不共享同一对象引用

---

### Requirement: HypothesisContext 数据类
系统 SHALL 提供 `HypothesisContext` 数据类，字段包括：`hypotheses: list[Hypothesis]`（假设列表）、`current_phase: str`（当前阶段，取值 `generation` / `collection` / `validation` / `conclusion`，默认 `"generation"`）、`iteration_count: int`（当前迭代轮次，默认 0）、`max_iterations: int`（最大迭代上限，默认 3）、`_prev_confidences: list[float]`（上一轮置信度快照，用于贝叶斯收敛判断）。

#### Scenario: 默认初始化状态
- **WHEN** 不传参数实例化 `HypothesisContext`
- **THEN** `hypotheses` SHALL 为空列表
- **AND** `current_phase` SHALL 为 `"generation"`
- **AND** `iteration_count` SHALL 为 0
- **AND** `max_iterations` SHALL 为 3

---

### Requirement: HypothesisContext 三条件收敛判断
`HypothesisContext.should_conclude()` SHALL 在满足以下任一条件时返回 `True`：
1. `iteration_count >= max_iterations`（硬上限）
2. 所有假设的 `status` 均为 `"validated"` 或 `"refuted"`（无 `pending` 状态）
3. `_prev_confidences` 与当前 `hypotheses` 数量相同，且相邻两轮最大置信度变化 `Δ < 0.05`（贝叶斯收敛）

#### Scenario: 达到迭代上限时收敛
- **WHEN** `iteration_count == max_iterations`
- **THEN** `should_conclude()` SHALL 返回 `True`

#### Scenario: 所有假设已定论时收敛
- **WHEN** 所有 `Hypothesis.status` 均为 `"validated"` 或 `"refuted"`
- **THEN** `should_conclude()` SHALL 返回 `True`，即使 `iteration_count < max_iterations`

#### Scenario: 贝叶斯收敛时停止
- **WHEN** `_prev_confidences` 与当前假设数量相同，且所有假设置信度变化均 < 0.05
- **THEN** `should_conclude()` SHALL 返回 `True`

#### Scenario: 条件均不满足时继续迭代
- **WHEN** `iteration_count < max_iterations` 且存在 `status == "pending"` 的假设，且置信度变化 >= 0.05
- **THEN** `should_conclude()` SHALL 返回 `False`

---

### Requirement: HypothesisContext 置信度更新
`HypothesisContext` SHALL 提供 `update_confidence(hypothesis_id, evidence_type)` 方法：
- `evidence_type == "for"`：`confidence = min(1.0, confidence + 0.15)`
- `evidence_type == "against"`：`confidence = max(0.0, confidence - 0.20)`
- 更新前 SHALL 将当前置信度快照保存到 `_prev_confidences`

#### Scenario: 支持证据提升置信度
- **WHEN** 调用 `update_confidence(id, "for")` 且当前 `confidence == 0.5`
- **THEN** 该假设 `confidence` SHALL 变为 0.65

#### Scenario: 反驳证据降低置信度且权重更高
- **WHEN** 调用 `update_confidence(id, "against")` 且当前 `confidence == 0.5`
- **THEN** 该假设 `confidence` SHALL 变为 0.30

#### Scenario: 置信度不超出 [0.0, 1.0] 边界
- **WHEN** 调用 `update_confidence(id, "for")` 且当前 `confidence == 0.95`
- **THEN** 该假设 `confidence` SHALL 为 1.0，不超出上限
