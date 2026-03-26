# Spec: phase-aware-capability

## Purpose

扩展 `Capability` 数据类，使其能够标注所属研究阶段（`ResearchPhase`）、风险等级（`RiskLevel`）和最高输出等级（`OutputLevel`），并定义 `ResearchPhase` 枚举覆盖八大研究阶段，从而支持按阶段路由能力、进行合规性校验和向 API 消费者暴露能力元数据。

## Requirements

### Requirement: ResearchPhase 枚举定义
系统 SHALL 定义 `ResearchPhase` 枚举，包含八大研究阶段：选题（topic_selection）、文献调研（literature_review）、实验设计（experiment_design）、数据采集（data_collection）、数据分析（data_analysis）、论文写作（paper_writing）、投稿发表（submission）、传播转化（dissemination）。

#### Scenario: 枚举值完整
- **WHEN** 导入 `ResearchPhase` 枚举
- **THEN** 枚举包含 8 个值，与纲领定义的八大研究阶段一一对应

#### Scenario: 枚举可序列化为字符串
- **WHEN** 将 `ResearchPhase.data_analysis` 序列化为 JSON
- **THEN** 输出为字符串 `"data_analysis"`

### Requirement: Capability 阶段字段
`Capability` dataclass SHALL 新增可选字段 `phase: ResearchPhase | None`，默认为 None，表示该能力所属的研究阶段。None 表示通用能力（跨阶段）。

#### Scenario: 字段存在且默认为 None
- **WHEN** 创建 Capability 不传 phase
- **THEN** 实例的 phase 为 None

#### Scenario: 字段可赋值
- **WHEN** 创建 Capability(phase=ResearchPhase.data_analysis, ...)
- **THEN** 实例的 phase 为 `ResearchPhase.data_analysis`

### Requirement: Capability 风险等级字段
`Capability` dataclass SHALL 新增可选字段 `risk_level: RiskLevel | None`，默认为 None，表示该能力的默认风险等级。

#### Scenario: 字段存在且默认为 None
- **WHEN** 创建 Capability 不传 risk_level
- **THEN** 实例的 risk_level 为 None

#### Scenario: 字段可赋值
- **WHEN** 创建 Capability(risk_level=RiskLevel.high, ...)
- **THEN** 实例的 risk_level 为 `RiskLevel.high`

### Requirement: Capability 最高输出等级字段
`Capability` dataclass SHALL 新增可选字段 `max_output_level: OutputLevel | None`，默认为 None，表示该能力可达到的最高输出等级。

#### Scenario: 字段存在且默认为 None
- **WHEN** 创建 Capability 不传 max_output_level
- **THEN** 实例的 max_output_level 为 None

#### Scenario: 受 trust-ceiling 约束
- **WHEN** 一个能力的 trust 等级为 T1
- **THEN** 其 max_output_level SHALL NOT 超过 O2

### Requirement: 现有 Capability 标注完整
`defaults.py` 中的全部 11 个 Capability 实例 SHALL 标注 phase、risk_level 和 max_output_level 属性。

#### Scenario: 数据分析类 Capability 标注正确
- **WHEN** 读取 difference_analysis Capability
- **THEN** phase 为 data_analysis，risk_level 不为 None，max_output_level 不为 None

#### Scenario: 通用 Capability 标注正确
- **WHEN** 读取 visualization Capability
- **THEN** phase 为 None（表示跨阶段通用）

#### Scenario: 新阶段 Capability 标注正确
- **WHEN** 读取 research_planning Capability
- **THEN** phase 为 experiment_design，risk_level 为 high，max_output_level 为 o2

### Requirement: to_dict 包含新字段
`Capability.to_dict()` 的返回值 SHALL 包含 phase、risk_level 和 max_output_level 字段。

#### Scenario: API 响应包含新字段
- **WHEN** 调用 Capability 实例的 to_dict()
- **THEN** 返回字典中包含 `"phase"`、`"risk_level"`、`"max_output_level"` 键

#### Scenario: None 值正确序列化
- **WHEN** 调用 phase 为 None 的 Capability 的 to_dict()
- **THEN** 返回字典中 `"phase"` 值为 None
