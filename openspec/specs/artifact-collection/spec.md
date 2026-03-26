## Purpose

定义会话分析产物到写作素材包的收集能力，为论文或报告写作提供结构化输入。

## Requirements

### Requirement: collect_artifacts 工具定义
系统 SHALL 提供 `collect_artifacts` 工具，继承 Tool 基类，从当前会话中收集分析产物并生成结构化写作素材包。

#### Scenario: 收集统计结果
- **WHEN** 会话中有已执行的统计检验
- **THEN** 素材包包含每个检验的方法名、关键统计量、p 值、效应量

#### Scenario: 收集图表
- **WHEN** 会话中有已生成的图表
- **THEN** 素材包包含每个图表的标题、类型和文件路径

#### Scenario: 收集方法记录
- **WHEN** 会话中有 MethodsLedgerEntry 记录
- **THEN** 素材包包含方法使用的完整记录

#### Scenario: 空会话返回空素材包
- **WHEN** 会话中无分析产物
- **THEN** 返回结构完整但内容为空的素材包 JSON

### Requirement: 素材包结构
collect_artifacts 返回的素材包 SHALL 为 JSON 格式，包含以下顶级字段：statistical_results、charts、methods、datasets、summary。

#### Scenario: JSON 结构完整
- **WHEN** 调用 collect_artifacts
- **THEN** 返回 JSON 包含所有顶级字段，缺失内容以空数组或 null 填充

### Requirement: 工具注册
collect_artifacts SHALL 在 `tools/registry.py` 中注册。

#### Scenario: 工具可查询
- **WHEN** 从 ToolRegistry 中查询 "collect_artifacts"
- **THEN** 返回对应的 Tool 实例
