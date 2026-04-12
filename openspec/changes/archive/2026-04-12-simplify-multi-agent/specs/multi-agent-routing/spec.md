## REMOVED Requirements

### Requirement: RoutingDecision 数据结构
**Reason**: TaskRouter 及其 RoutingDecision 数据类随路由层一起移除。主 Agent LLM 在调用 dispatch_agents 时直接声明 agent_id，不再需要中间路由推理层。
**Migration**: 在 dispatch_agents 的 `agents` 参数中直接指定 `agent_id`，主 Agent system prompt 中提供可用 agent_id 列表及其适用场景说明。

### Requirement: TaskRouter 规则路由
**Reason**: 规则路由基于关键词集合匹配，需要持续维护关键词列表，且其做的推理与主 Agent LLM 重复，带来双重不确定性。
**Migration**: 主 Agent LLM 直接在 dispatch_agents 参数中声明目标 agent_id，不再经过路由层。

### Requirement: TaskRouter LLM 兜底路由
**Reason**: LLM 兜底路由在规则路由置信度不足时额外发起一次 API 调用（约 +500ms），增加延迟和 token 消耗，且其决策结果不可控。
**Migration**: 同上，主 Agent 直接声明 agent_id，无需兜底机制。

### Requirement: 批量路由（route_batch）
**Reason**: 批量路由 API 随 TaskRouter 整体移除。
**Migration**: 无替代，dispatch_agents 参数中直接列出所有 agents。

### Requirement: 多意图检测与拆分
**Reason**: 多意图检测（detect_multi_intent）与路由层耦合，随路由层一起移除。
**Migration**: 主 Agent 自行在 dispatch_agents 调用中拆分任务，每个 agent 对应一个独立 task 描述。
