# deep-task-workflow Specification

## Purpose
定义 quick task / deep task 分类、deep task 状态机与最小恢复约束，作为模板任务执行的基础契约。

## Requirements

### Requirement: 系统必须区分 quick task 与 deep task

系统 SHALL 在任务启动前将请求分类为 `quick task` 或 `deep task`，并对 deep task 启用项目工作区、步骤进度与恢复策略。MVP 阶段 SHALL 采用确定性规则优先分类，显式启动的 Recipe 不得依赖模型兜底判定。

#### Scenario: 轻量请求按 quick task 执行
- **WHEN** 用户请求属于单轮即可完成的轻量问题
- **THEN** 系统按 `quick task` 执行
- **AND** 不强制创建项目工作区或多步进度状态

#### Scenario: 模板任务按 deep task 执行
- **WHEN** 用户通过 Recipe Center 启动模板任务
- **THEN** 系统将该请求标记为 `deep task`
- **AND** 启用项目工作区与步骤进度跟踪

#### Scenario: MVP 分类采用规则优先
- **WHEN** 系统在 MVP 阶段处理未显式选择 Recipe 的请求
- **THEN** 系统优先依据预定义规则进行 `quick task` / `deep task` 分类
- **AND** 不要求模型参与必选分类路径

### Requirement: Deep task 必须遵循统一执行状态机

系统 SHALL 为 deep task 提供统一执行状态机，至少包含 `queued`、`running`、`retrying`、`blocked`、`completed`、`failed` 状态，并记录当前步骤与下一步提示。

#### Scenario: deep task 启动后进入运行态
- **WHEN** deep task 创建成功且准备进入执行
- **THEN** 任务状态变为 `running`
- **AND** 系统记录当前步骤索引与步骤标题

#### Scenario: 步骤失败后触发自动重试
- **WHEN** 某一步骤命中可恢复失败
- **THEN** 任务状态变为 `retrying`
- **AND** 系统记录失败原因与重试次数
- **AND** 成功恢复后返回 `running`

#### Scenario: 不可恢复失败进入阻塞或失败
- **WHEN** 某一步骤无法自动恢复
- **THEN** 系统将任务标记为 `blocked` 或 `failed`
- **AND** 向前端提供建议动作或失败原因

### Requirement: Deep task 必须初始化项目工作区

系统 SHALL 在 deep task 启动时创建与当前会话绑定的项目工作区，并将 Recipe 输入、步骤中间产物与最终产物归档到该工作区。

#### Scenario: deep task 创建项目工作区
- **WHEN** Recipe 成功创建新 deep task
- **THEN** 系统创建与当前会话绑定的项目工作区
- **AND** 工作区记录 `recipe_id` 与任务标识

#### Scenario: 步骤产物写入项目工作区
- **WHEN** deep task 生成中间文件或最终产物
- **THEN** 系统将文件归档到项目工作区
- **AND** 产物可被后续步骤复用

### Requirement: Deep task 必须声明默认输出与最小恢复策略

每个 Recipe SHALL 声明默认输出类型与最小恢复策略，确保系统在失败时有一致的补救行为。

#### Scenario: Recipe 定义默认输出
- **WHEN** 系统读取 Recipe 元数据
- **THEN** 可确定该 Recipe 的默认最终输出类型
- **AND** 前端可据此展示预期产物说明

#### Scenario: Recipe 定义失败回退规则
- **WHEN** 某步骤失败且存在声明的回退动作
- **THEN** 系统执行该回退动作
- **AND** 记录该次恢复尝试
