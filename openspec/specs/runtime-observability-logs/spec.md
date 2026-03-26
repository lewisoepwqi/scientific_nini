# runtime-observability-logs Specification

## Purpose
TBD - created by archiving change improve-runtime-observability-logs. Update Purpose after archive.
## Requirements
### Requirement: 系统必须为关键意外失败路径输出可诊断错误日志

系统 MUST 在关键运行链路的意外失败路径中输出可诊断错误日志，使维护者能够从日志中定位异常来源。

#### Scenario: 关键异常日志包含 traceback
- **WHEN** Agent 执行、模型调用、工具执行、WebSocket 消息处理或其他关键运行链路发生未预期异常
- **THEN** 系统输出错误日志
- **AND** 该日志包含 traceback 或等效异常上下文

#### Scenario: 预期业务分支不强制升级为错误
- **WHEN** 系统进入已定义的降级、拒绝或兼容分支
- **THEN** 系统可以输出 info 或 warning 日志
- **AND** 不得要求所有这类分支统一升级为 error

### Requirement: 系统必须减少高风险业务路径中的静默吞错

系统 MUST 在高风险业务路径中避免无日志的静默吞错，并至少记录可消费的 warning、error 或 debug 信息。

#### Scenario: 业务失败路径不再静默吞错
- **WHEN** 高风险业务路径捕获到异常并继续执行
- **THEN** 系统至少输出一条与该异常相关的日志
- **AND** 不得继续完全无日志地吞掉异常

#### Scenario: 清理路径允许保守降级记录
- **WHEN** 文件关闭、资源释放或清理路径捕获到异常
- **THEN** 系统可以使用 debug 级别记录该异常
- **AND** 不要求将所有清理路径统一升级为 warning 或 error

### Requirement: 系统必须为关键执行链路输出统一耗时信号

系统 MUST 为关键执行链路输出统一耗时日志，以支撑性能定位和回归比较。

#### Scenario: 模型调用输出耗时
- **WHEN** 一次模型调用结束，无论成功或失败
- **THEN** 系统输出该次调用的耗时日志
- **AND** 日志使用统一的耗时语义，例如 `duration_ms`

#### Scenario: 工具与执行链路输出耗时
- **WHEN** 工具执行、检索、沙箱执行或 Agent 单轮执行结束
- **THEN** 系统输出对应耗时日志
- **AND** 不要求调用外部平台才能获得这些耗时信息

### Requirement: 薄弱模块必须具备最小基础操作日志

系统 MUST 为当前日志薄弱的关键模块补齐最小基础操作日志，至少覆盖开始、失败或完成中的关键状态变化。

#### Scenario: 工作区关键操作可从日志追踪
- **WHEN** 系统执行关键工作区操作，例如文件组织、移动、删除或资源写入
- **THEN** 相关模块输出可用于追踪该操作的基础日志

#### Scenario: 关键 API 操作失败可被日志定位
- **WHEN** 文件、会话或关键资源相关 API 操作失败
- **THEN** 系统输出与该失败相关的日志
- **AND** 维护者可据此定位失败发生的模块或操作阶段

