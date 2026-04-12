# cli-diagnostics Specification

## Purpose
TBD - created by archiving change improve-cli-template-doctor-observability. Update Purpose after archive.
## Requirements
### Requirement: kaleido 诊断分支可区分且可操作
系统 MUST 在 `nini doctor` 中将 kaleido + Chrome 诊断结果区分为依赖缺失、检测模块不可用、检测失败和检测成功四类，并输出可操作提示。

#### Scenario: kaleido 未安装
- **WHEN** 环境中不可导入 `kaleido`
- **THEN** doctor 输出 `kaleido 未安装` 提示
- **AND** 提供安装指引

#### Scenario: Chrome 检测模块不可用
- **WHEN** `kaleido` 可导入但 `choreographer.browsers.chromium` 不可用
- **THEN** doctor 输出 `Chrome 状态未知` 及原因
- **AND** 保留 `kaleido_get_chrome` 操作提示

#### Scenario: Chrome 检测过程异常
- **WHEN** Chrome 路径检测过程中抛出运行时异常
- **THEN** doctor 输出包含异常类型/信息的诊断提示
- **AND** 命令返回成功，不影响其他检查项输出

### Requirement: CLI 诊断必须支持运行快照摘要
系统 MUST 提供基于运行快照的 CLI 诊断入口，用于查看某个会话或轮次的摘要状态。

#### Scenario: 查看会话最新运行摘要
- **WHEN** 用户通过 CLI 请求某个会话的最新运行摘要
- **THEN** 系统 MUST 输出该会话最近一轮的 stop reason、pending actions、任务进度和关键失败摘要

#### Scenario: 查看指定轮次快照
- **WHEN** 用户通过 CLI 请求某个会话指定轮次的运行快照
- **THEN** 系统 MUST 输出对应轮次的结构化摘要
- **AND** 若轮次不存在，CLI MUST 返回明确的未找到提示

### Requirement: doctor 诊断必须支持 surface 观测
系统 MUST 提供 tools/skills/surface 的 CLI 诊断输出，用于分析当前轮或当前配置下的工具暴露面。

#### Scenario: 查看当前工具面与技能面
- **WHEN** 用户通过 `doctor --surface` 或等价入口请求 surface 诊断
- **THEN** 系统 MUST 输出当前可见工具、技能快照以及高风险工具摘要

#### Scenario: 查看策略过滤后的工具面
- **WHEN** 当前存在基于阶段、风险或授权状态的工具暴露策略
- **THEN** surface 诊断 MUST 输出过滤后的可见工具面
- **AND** MUST 说明哪些工具因策略被移除或隐藏

