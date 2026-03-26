# Spec: risk-grading

## Purpose

定义风险等级枚举、信任等级枚举、强制复核判定逻辑及禁止性行为清单，为 Nini Agent 的输出安全与合规提供基础数据结构与判定函数。

## Requirements

### Requirement: 风险等级枚举定义
系统 SHALL 定义 `RiskLevel` 枚举，包含四个等级：低（low）、中（medium）、高（high）、极高（critical），每个等级附带中文名称、定义和示例。

#### Scenario: 枚举值完整
- **WHEN** 导入 `RiskLevel` 枚举
- **THEN** 枚举包含 `low`、`medium`、`high`、`critical` 四个值

#### Scenario: 枚举可序列化为字符串
- **WHEN** 将 `RiskLevel.high` 序列化为 JSON
- **THEN** 输出为字符串 `"high"`

#### Scenario: 元数据可查询
- **WHEN** 查询 `RiskLevel.critical` 的元数据
- **THEN** 返回包含中文名称（「极高」）、定义和示例的字典

### Requirement: 信任等级枚举定义
系统 SHALL 定义 `TrustLevel` 枚举，包含三个等级：T1（草稿级）、T2（可审阅级）、T3（可复核级）。

#### Scenario: 枚举值完整
- **WHEN** 导入 `TrustLevel` 枚举
- **THEN** 枚举包含 `t1`、`t2`、`t3` 三个值

### Requirement: 强制人工复核场景列表
系统 SHALL 定义强制人工复核场景常量列表，包含 vision charter 第 4.3 节规定的所有场景（样本量计算、研究方案定稿、统计结论最终解释、投稿回复、期刊适配、临床/伦理建议、最终摘要/导出内容）。

#### Scenario: 场景列表完整
- **WHEN** 读取 `MANDATORY_REVIEW_SCENARIOS` 常量
- **THEN** 列表包含至少 7 个场景描述

### Requirement: 人工复核判定函数
系统 SHALL 提供 `requires_human_review(risk_level, scenario_tags)` 函数，当风险等级为高或极高，或 scenario_tags 命中强制复核场景时返回 True。

#### Scenario: 高风险触发复核
- **WHEN** 调用 `requires_human_review(RiskLevel.high, [])`
- **THEN** 返回 `True`

#### Scenario: 低风险且无场景标签不触发
- **WHEN** 调用 `requires_human_review(RiskLevel.low, [])`
- **THEN** 返回 `False`

#### Scenario: 低风险但命中复核场景触发
- **WHEN** 调用 `requires_human_review(RiskLevel.low, ["统计结论最终解释"])`
- **THEN** 返回 `True`

### Requirement: 禁止性规则清单
系统 SHALL 定义 `PROHIBITED_BEHAVIORS` 常量列表，包含 vision charter 第 4.4 节规定的 8 条禁止性行为描述。

#### Scenario: 清单完整
- **WHEN** 读取 `PROHIBITED_BEHAVIORS` 常量
- **THEN** 列表包含 8 条禁止性行为描述

### Requirement: 风险争议处理规则
当风险等级判定存在争议时，系统 SHALL 按更高等级处理（向上取整原则）。

#### Scenario: 争议时向上取整
- **WHEN** 系统需要在两个风险等级之间选择（如某操作可能是中或高风险）
- **THEN** 选择更高的等级（高风险）
