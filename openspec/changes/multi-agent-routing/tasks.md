## 1. TaskRouter（src/nini/agent/router.py）

- [x] 1.1 创建 `RoutingDecision` 数据类，字段：`agent_ids: list[str]`、`tasks: list[str]`、`confidence: float`、`strategy: str`、`parallel: bool = True`
- [x] 1.2 实现 `TaskRouter.__init__(model_resolver, enable_llm_fallback=True)`，初始化内置关键词规则表（6 条规则，frozenset → agent_id）
- [x] 1.3 实现 `TaskRouter._rule_route(intent: str) -> RoutingDecision`，关键词集合匹配 + 置信度线性计算（< 5ms）
- [x] 1.4 实现 `TaskRouter._llm_route(intent: str, context: dict) -> RoutingDecision`，调用 `model_resolver.chat(purpose="planning")`，输出 JSON 格式路由决策，失败时返回规则路由结果
- [x] 1.5 实现 `TaskRouter.route(intent: str, context: dict = {}) -> RoutingDecision`，规则路由 confidence < 0.7 时触发 LLM 兜底
- [x] 1.6 实现 `TaskRouter.route_batch(tasks: list[str]) -> list[RoutingDecision]`，一次 LLM 调用批量分析，保序返回，空列表返回空列表

## 2. ResultFusionEngine（src/nini/agent/fusion.py）

- [x] 2.1 创建 `FusionResult` 数据类，字段：`content: str`、`strategy: str`、`conflicts: list[dict] = field(default_factory=list)`、`sources: list[str] = field(default_factory=list)`
- [x] 2.2 实现 `ResultFusionEngine.__init__(model_resolver)`
- [x] 2.3 实现 `_concatenate(results) -> FusionResult`，拼接各 `SubAgentResult.summary`，换行分隔，不调用 LLM
- [x] 2.4 实现 `_summarize(results) -> FusionResult`，调用 `model_resolver.chat(purpose="analysis")` 生成整合摘要；超时 60s 降级为 concatenate
- [x] 2.5 实现 `_hierarchical(results) -> FusionResult`，分批（每批 ≤4 个）summarize 后再汇总
- [x] 2.6 实现冲突检测（私有方法），在 summarize/consensus 策略下对结论做简单比对，追加到 `FusionResult.conflicts`，不修改 content
- [x] 2.7 实现 `ResultFusionEngine.fuse(results, strategy="auto") -> FusionResult`，auto 分档逻辑（0→空、1→concat、2-4→summarize、>4→hierarchical）；不支持的策略名降级为 concatenate 并记录 WARNING

## 3. DispatchAgentsTool（src/nini/tools/dispatch_agents.py）

- [x] 3.1 创建 `DispatchAgentsTool`，继承 `tools/base.py:Skill`，`name = "dispatch_agents"`，参数 `tasks: list[str]`（必填）和 `context: str`（可选，默认空字符串）
- [x] 3.2 实现构造函数注入：`__init__(agent_registry, spawner, fusion_engine)`，任意依赖为 None 时 execute() 返回 `SkillResult(success=False, content="dispatch_agents 未正确初始化")` 而不抛出异常
- [x] 3.3 实现 `execute(session, tasks, context="") -> SkillResult`：tasks 为空时返回 `SkillResult(content="")`；否则调用 spawner.spawn_batch() 并行执行，再调用 fusion_engine.fuse()，返回 `SkillResult(content=fusion_result.content)`

## 4. 注册 DispatchAgentsTool（src/nini/tools/registry.py）

- [x] 4.1 在 `create_default_tool_registry()` 中实例化并注册 `DispatchAgentsTool`（依赖注入 AgentRegistry、SubAgentSpawner、ResultFusionEngine）
- [x] 4.2 确认 `"dispatch_agents"` 不在 `LLM_EXPOSED_BASE_TOOL_NAMES` 中（仅通过 Orchestrator 路径暴露给主 Agent）

## 5. Orchestrator 钩子（src/nini/agent/runner.py）

- [x] 5.1 在 runner.py 顶部添加 `ORCHESTRATOR_TOOL_NAMES = {"dispatch_agents"}` 常量
- [x] 5.2 修改 `_get_tool_definitions()`：非 SubSession 时额外暴露 `ORCHESTRATOR_TOOL_NAMES` 中的工具（通过 `isinstance(session, SubSession)` 判断）
- [x] 5.3 在 `for tc in tool_calls:` 循环之前插入 Orchestrator 钩子：检测 `dispatch_agents` 工具调用，若存在则调用 `_handle_dispatch_agents()` 并 `continue`
- [x] 5.4 实现私有方法 `_handle_dispatch_agents(dispatch_tc, session, turn_id)`：解析参数、调用 DispatchAgentsTool.execute()、将融合结果以 `tool_result` 消息注入 session，通过 yield 推送 `agent_start/complete/error` 事件

## 6. 前端 WorkflowTopology（web/src/components/WorkflowTopology.tsx）

- [x] 6.1 创建 `WorkflowTopology` 组件，订阅 store 的 `activeAgents`（Record）和 `completedAgents`（数组）
- [x] 6.2 实现节点渲染：running→蓝色、completed→绿色、error→红色，显示 agent_name 和状态文字
- [x] 6.3 实现条件渲染：Agent 总数 < 2 时返回 null
- [x] 6.4 在 `App.tsx`（或 `ChatPanel.tsx`）中引入 `WorkflowTopology`，位于对话面板上方条件渲染

## 7. MessageBubble 子 Agent 来源标签（web/src/components/MessageBubble.tsx）

- [x] 7.1 读取消息事件 payload 中的 `agent_id` 字段，通过 `completedAgents` 查找对应 `agentName`
- [x] 7.2 在消息气泡顶部条件渲染来源 badge `[{agentName}]`（仅 agent_id 非空且能找到对应记录时显示）

## 8. 测试

- [x] 8.1 `tests/test_router.py`：规则路由高置信度命中、多关键词同时命中多 Agent、无关键词命中（confidence < 0.7）、route_batch 保序、LLM 路由失败降级
- [x] 8.2 `tests/test_fusion.py`：空结果集、单结果无 LLM 调用、多结果触发 summarize、concatenate 策略拼接、summarize 超时降级、冲突标注不影响 content
- [x] 8.3 `tests/test_dispatch_agents.py`：正常执行返回 SkillResult、tasks 为空返回空结果、依赖未注入返回错误结果
- [x] 8.4 `tests/test_orchestrator_mode.py`：dispatch_agents 调用被拦截（不进入通用工具循环）、子 Agent 不暴露 dispatch_agents 工具定义、事件链完整（agent_start + agent_complete + tool_result）
