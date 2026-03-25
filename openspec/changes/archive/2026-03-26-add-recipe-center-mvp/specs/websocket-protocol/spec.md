## ADDED Requirements

### Requirement: WebSocket 协议必须支持 Recipe 生命周期事件

系统 SHALL 在 WebSocket 通道中表达 Recipe 启动、任务分类与生命周期状态变化，使前端能够稳定展示模板任务执行过程。

#### Scenario: Recipe 启动后推送任务初始化事件
- **WHEN** 用户通过 Recipe Center 或接受推荐启动模板任务
- **THEN** 服务端推送包含 `recipe_id`、任务类型与初始状态的事件
- **AND** 前端可据此切换到 deep task 展示模式

#### Scenario: deep task 状态变化时推送生命周期事件
- **WHEN** deep task 状态在 `queued`、`running`、`retrying`、`blocked`、`completed`、`failed` 之间变化
- **THEN** 服务端推送对应状态事件
- **AND** 事件中包含任务标识、当前步骤与原因摘要

### Requirement: WebSocket 协议必须支持 Recipe 步骤进度事件

系统 SHALL 提供可增量消费的 Recipe 步骤进度事件，表达总步骤数、当前步骤、步骤状态与下一步提示。

#### Scenario: deep task 进入某一步骤
- **WHEN** 系统开始执行某个 Recipe 步骤
- **THEN** 服务端推送步骤进度事件
- **AND** 事件中包含步骤索引、步骤标题、步骤状态与总步骤数

#### Scenario: deep task 进入重试
- **WHEN** 当前步骤因可恢复错误进入重试
- **THEN** 服务端推送步骤进度事件
- **AND** 事件中包含 `retrying` 状态与失败原因摘要
