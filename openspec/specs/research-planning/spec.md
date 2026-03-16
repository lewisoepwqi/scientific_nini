# research-planning Specification

## Purpose
定义研究规划能力在意图层的识别规则、同义词覆盖范围，以及研究设计、实验方案和样本量估计类请求的稳定路由要求，确保相关问题能够一致地命中规划能力。

## Requirements

### Requirement: research_planning Capability 在意图层可被识别

系统 SHALL 在 `create_default_capabilities()` 中注册 `research_planning` Capability，使用户的研究设计/规划请求能路由到 `research_planner` Agent。

#### Scenario: 用户请求制定研究方案时意图层推荐 research_planning

- **WHEN** 用户输入含"研究规划"、"实验设计"、"研究方案"等关键词的请求
- **THEN** `capability_candidates` 中包含 `research_planning`

### Requirement: research_planning 同义词覆盖研究设计相关术语

`config/intent_synonyms.yaml` 中 SHALL 包含 `research_planning` 条目，覆盖研究设计、样本量计算、实验方案、研究思路等词汇。

#### Scenario: 同义词匹配样本量计算请求

- **WHEN** 用户输入"我需要多少样本量"
- **THEN** 意图候选中包含 `research_planning`

#### Scenario: 同义词匹配实验设计请求

- **WHEN** 用户输入"帮我设计一个随机对照实验"
- **THEN** 意图候选中包含 `research_planning`
