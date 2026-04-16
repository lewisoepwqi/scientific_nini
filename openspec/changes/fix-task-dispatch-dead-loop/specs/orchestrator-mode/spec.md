## MODIFIED Requirements

### Requirement: Orchestrator 钩子拦截 dispatch_agents 调用
`AgentRunner` 在解析 `tool_calls` 后、进入通用工具执行循环前 SHALL 检测是否存在 `dispatch_agents` 调用；若存在，SHALL 通过 `_handle_dispatch_agents()` 执行调度流程，并根据调度返回的结构化错误决定继续派发、切回主 Agent 直接执行路径或进入恢复流程，而不是一律继续暴露原始派发路径。

#### Scenario: 合法派发请求继续走 Orchestrator 路径
- **WHEN** `tool_calls` 中包含合法的 `dispatch_agents` 调用
- **AND** 调度上下文允许该请求执行
- **THEN** runner SHALL 通过 `_handle_dispatch_agents()` 处理该调用
- **AND** 多 Agent 结果 SHALL 以 `tool_result` 注入 session
- **AND** 主循环 SHALL 继续进入下一轮决策

#### Scenario: 调度上下文错误触发路径切换
- **WHEN** `dispatch_agents` 返回表明“当前任务应直接执行”或等价恢复动作的结构化错误
- **THEN** runner SHALL 将该错误写入当前轮运行时上下文
- **AND** SHALL 在后续决策中限制重复的错误派发形态
- **AND** SHALL 引导主 Agent 切换到推荐的直接工具路径

## ADDED Requirements

### Requirement: Orchestrator 必须支持 turn 级调度护栏
系统 SHALL 在 `AgentRunner` 内为单个 turn 维护调度护栏，用于记录当前轮已判定无效的 `dispatch_agents` 形态，并在同一恢复链路中阻止模型继续重复相同误用；该护栏 SHALL 作为唯一执行期拦截来源，避免 runner 与 harness 维护重复状态。

#### Scenario: 非法 agent 在当前轮被禁用
- **WHEN** 当前轮某次 `dispatch_agents` 调用因非法 `agent_id` 失败
- **THEN** 系统 SHALL 在该 turn 的后续恢复链路中禁止重复使用该非法 agent
- **AND** 若模型再次尝试同类调用，系统 SHALL 直接返回受控错误而不是再次进入真实派发流程

#### Scenario: 当前任务错误派发在当前轮被收紧
- **WHEN** 当前轮某次 `dispatch_agents` 调用因“将 `in_progress` 任务误当成 pending wave 派发项”而失败
- **THEN** 系统 SHALL 在该 turn 内收紧对应的 `dispatch_agents` 使用形态
- **AND** 后续恢复链路 SHALL 优先保留推荐的直接执行工具
