# Capability: task-dispatch-coordination

## Purpose

定义任务执行语义、初始化依赖规范化和统一 dispatch context，为任务板推进、`dispatch_agents` 校验和恢复决策提供一致的运行时契约。

## Requirements

### Requirement: 任务执行语义必须分离主任务、当前执行上下文与子派发单元
系统 SHALL 将用户可见的计划任务、当前主 Agent 执行上下文和 `dispatch_agents` 子派发单元视为不同语义层，而不得要求同一个主任务 `task_id` 同时承担“进行中任务”和“待派发 wave 项”的双重角色。

#### Scenario: 当前任务进入执行态后仍可继续在主 Agent 内推进
- **WHEN** 某个计划任务已被标记为 `in_progress`
- **THEN** 系统 SHALL 将其视为当前执行任务
- **AND** 后续直接工具调用 SHALL 继续关联到该任务
- **AND** 系统 SHALL NOT 要求该任务重新回到 `pending` 才能继续执行

#### Scenario: 当前执行任务的内部子派发不复用 pending wave 语义
- **WHEN** 主 Agent 需要为当前 `in_progress` 任务发起 specialist 辅助子任务
- **THEN** 系统 SHALL 允许使用显式的父任务上下文标识该子派发
- **AND** 系统 SHALL NOT 要求该子派发必须属于当前 `pending wave`

### Requirement: 任务初始化必须规范化顺序与依赖
系统 SHALL 在任务初始化时校验任务顺序和依赖声明；当多步骤流程满足内建且高置信的线性流水线规则而模型未提供有效 `depends_on` 时，系统 MUST 将其规范化为安全的顺序依赖，并保留主任务顺序稳定；当仅检测到疑似顺序风险而无法高置信判定时，系统 SHALL 返回结构化 warning，而不得静默重写任务图。

这里的高置信规则 SHALL 来自显式、可枚举且可测试的内建模板、白名单工具链或等价确定性规则，而不得仅基于自由文本启发式做自动改写。

#### Scenario: 串行分析流程自动补齐依赖
- **WHEN** 初始化任务列表包含“读取数据 → 预处理 → 聚合 → 绘图”这类明显串行步骤
- **AND** 这些任务符合系统支持的高置信线性流水线判定规则
- **AND** 这些任务未声明依赖或依赖不完整
- **THEN** 系统 SHALL 自动补齐前后依赖关系
- **AND** 后续 wave 计算 SHALL 基于规范化后的依赖而不是原始空依赖

#### Scenario: 低置信顺序风险仅返回 warning
- **WHEN** 初始化任务列表存在疑似串行关系
- **AND** 系统无法基于内建规则高置信确定安全依赖
- **THEN** 系统 SHALL 保留原始任务依赖
- **AND** SHALL 返回结构化 warning 供后续恢复与诊断使用

#### Scenario: 显式并行任务保留并行
- **WHEN** 初始化任务列表中存在明确声明为彼此独立的任务
- **AND** 这些任务不存在依赖和读写冲突
- **THEN** 系统 SHALL 保留它们的并行资格
- **AND** 不得因全局顺序规范化而强行串行化

### Requirement: 系统必须暴露统一的 dispatch context
系统 SHALL 为运行时提供统一的 dispatch context，至少包含当前 `in_progress` 任务、当前 `pending wave`、允许的派发模式和推荐直接执行工具，用于 `dispatch_agents` 校验、恢复器决策和上下文注入。

#### Scenario: 存在进行中任务时返回当前执行上下文
- **WHEN** 会话存在一个 `in_progress` 任务
- **THEN** dispatch context SHALL 标识该任务为当前执行任务
- **AND** SHALL 同时返回当前 `pending wave` 的任务列表
- **AND** SHALL 指示当前轮是否允许直接执行、内部子派发或 pending wave 派发

#### Scenario: 无进行中任务时返回待开始波次
- **WHEN** 会话不存在 `in_progress` 任务
- **AND** 任务板中仍有 `pending` 任务
- **THEN** dispatch context SHALL 将首个可启动 wave 视为当前可派发波次
- **AND** SHALL 为主 Agent 提供下一步推荐动作
