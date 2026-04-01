## ADDED Requirements

### Requirement: HarnessSessionSnapshot 持久化每轮运行摘要
系统 SHALL 在每轮 harness 运行结束后生成一个不可变的 `HarnessSessionSnapshot` 摘要对象，并将其持久化为可加载的诊断记录。

#### Scenario: 运行结束后生成快照
- **WHEN** 一轮 harness 运行进入 `done`、`blocked`、`error` 或等价终止状态
- **THEN** 系统 SHALL 生成一条 `HarnessSessionSnapshot`
- **AND** 快照 SHALL 包含 `session_id`、`turn_id`、`stop_reason`、`pending_actions`、`task_progress`、`selected_tools`、`tool_failures`、`token_usage` 和 `trace_ref`

#### Scenario: 快照不复制大对象
- **WHEN** 系统生成 `HarnessSessionSnapshot`
- **THEN** 快照 SHALL 仅保存摘要字段和引用信息
- **AND** SHALL NOT 直接复制 DataFrame、完整 artifact 内容或完整消息历史

### Requirement: 运行快照必须支持按会话与按轮次查询
系统 SHALL 提供基于会话和轮次查询 `HarnessSessionSnapshot` 的诊断能力，用于后续 CLI 或调试入口复用。

#### Scenario: 按会话加载最近快照
- **WHEN** 调试入口请求查看某个 `session_id` 的最新运行摘要
- **THEN** 系统 SHALL 返回该会话最近一轮的 `HarnessSessionSnapshot`

#### Scenario: 按轮次加载指定快照
- **WHEN** 调试入口请求查看某个 `session_id` 下指定 `turn_id` 的快照
- **THEN** 系统 SHALL 返回对应轮次的 `HarnessSessionSnapshot`
- **AND** 若该轮次不存在，系统 SHALL 返回明确的未找到结果而不是隐式回退到其他轮次

### Requirement: 运行快照必须作为调试摘要的数据源
系统 SHALL 让运行快照成为 `debug summary`、`debug snapshot`、`debug load-session` 或等价诊断入口的统一摘要数据源，而不是要求诊断逻辑直接重新解析完整消息历史。

#### Scenario: 调试摘要优先读取快照
- **WHEN** 用户请求查看某个会话的运行摘要
- **THEN** 系统 SHALL 优先从 `HarnessSessionSnapshot` 构建摘要输出
- **AND** SHALL NOT 依赖重新扫描全部消息历史作为唯一数据源

#### Scenario: 快照可关联 trace 与运行时状态
- **WHEN** 调试入口输出某轮运行摘要
- **THEN** 输出 SHALL 能关联该轮的 `trace_ref` 或等价运行诊断引用
- **AND** SHALL 能显示该轮剩余 `pending_actions` 和关键失败摘要
