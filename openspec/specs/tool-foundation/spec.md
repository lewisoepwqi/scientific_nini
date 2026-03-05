# tool-foundation Specification

## Purpose
TBD - created by archiving change consolidate-tool-foundation. Update Purpose after archive.
## Requirements
### Requirement: 模型可见工具必须收敛为基础工具层
系统 SHALL 将模型可见工具限制为少量基础工具，并将复合分析能力实现为内部编排层而非同级暴露接口。

#### Scenario: 构建模型工具清单
- **WHEN** Agent 为新一轮对话构建可调用工具定义
- **THEN** 返回的工具集合仅包含基础工具层定义
- **AND** 不包含完整比较、完整 ANOVA、相关分析、回归分析等内部编排工具

#### Scenario: 内部编排复用基础工具
- **WHEN** 系统执行复合分析流程
- **THEN** 复合流程通过基础工具组合完成
- **AND** 每一步可追踪到具体基础工具调用

### Requirement: 会话资源必须使用统一资源标识
系统 SHALL 为数据集、统计结果、图表规格、报告、脚本和工作区文件分配统一资源标识，并支持后续操作通过资源标识引用。

#### Scenario: 基础工具创建新资源
- **WHEN** 任一基础工具创建新的数据集、图表、报告、脚本或统计结果
- **THEN** 返回值包含 `resource_id`、`resource_type` 和展示名称

#### Scenario: 后续操作引用已有资源
- **WHEN** 用户或编排层继续操作前一步创建的资源
- **THEN** 系统优先通过 `resource_id` 解析目标资源
- **AND** 不依赖“最近一次结果”或纯文本名称匹配

### Requirement: 基础工具结果必须返回统一摘要契约
系统 SHALL 为基础工具输出提供统一的结果摘要结构，至少包含执行是否成功、用户可读消息、资源摘要和可供编排层复用的结构化数据。

#### Scenario: 基础工具执行成功
- **WHEN** 任一基础工具成功完成
- **THEN** 返回结构中包含 `success=true`
- **AND** 包含 `message`
- **AND** 在创建或更新资源时包含资源摘要

#### Scenario: 基础工具执行失败
- **WHEN** 任一基础工具失败
- **THEN** 返回结构中包含 `success=false`
- **AND** 包含可解释错误信息
- **AND** 在可恢复场景下包含失败位置或恢复线索

