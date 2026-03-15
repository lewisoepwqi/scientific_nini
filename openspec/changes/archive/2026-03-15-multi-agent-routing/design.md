## Context

Phase 1 已交付 `AgentRegistry`、`SubSession`、`SubAgentSpawner` 三个基础组件，以及 `ToolRegistry.create_subset()`。主 Agent（`AgentRunner`）的 ReAct 循环仍作为单 Agent 运行，复杂任务由主 Agent 串行处理。

Phase 2 在不修改现有 ReAct 逻辑的前提下，通过插入 Orchestrator 钩子实现多 Agent 并行分发。关键约束：
- `AgentRunner.__init__` 参数：`resolver, skill_registry, knowledge_loader, ask_user_question_handler`（无 purpose 参数）
- `model_resolver.chat()` 是唯一 LLM 调用接口，`purpose` 通过参数传入
- runner.py 工具调用循环在 `for tc in tool_calls:` 处（~line 1140），Orchestrator 钩子在此之前插入
- 前端 store 已有 `activeAgents / completedAgents` 状态（Phase 1 agent-slice.ts）

## Goals / Non-Goals

**Goals:**
1. `TaskRouter` 能在 <1ms（规则）或 <1s（LLM）内将用户意图映射到一组 Specialist Agent
2. `ResultFusionEngine` 能将多个 `SubAgentResult` 融合为一段结构化文本，支持 4 种策略
3. `dispatch_agents` 工具将 Router + Spawner + Fusion 封装为单一 LLM 调用接口
4. runner.py Orchestrator 钩子拦截 `dispatch_agents` 调用，不影响其他工具的现有执行路径
5. 前端 WorkflowTopology 在 ≥2 个并行 Agent 时展示执行拓扑

**Non-Goals:**
- 修改 AgentRunner 的 purpose 路由机制（Phase 2 子 Agent 沿用 Phase 1 的默认路由）
- Hypothesis-Driven 范式（Phase 3）
- TaskRouter 的持久化或配置管理 UI
- `dispatch_agents` 工具的权限控制（子 Agent 已通过 `create_subset` 限制工具集）

## Decisions

### Decision 1：dispatch_agents 作为普通工具而非 runner.py 内置触发

**选择**：`dispatch_agents` 实现为继承 `Skill` 的普通工具，注册到 `ToolRegistry`；runner.py 在 `for tc in tool_calls:` 之前检测是否有 `dispatch_agents` 调用，如有则走 Orchestrator 路径，并跳过原有工具执行。

**理由**：LLM 通过工具调用形式触发多 Agent 派发，语义清晰，主 Agent 完全控制何时触发。工具参数（`tasks list`）天然承载了任务分解结果，无需额外的意图解析层。

**替代方案**：在 runner.py 首轮迭代前调用 TaskRouter 自动判断 → 问题是所有请求都付出路由开销，且可能与主 Agent 的规划步骤冲突。

**实现要点**：`dispatch_agents` 工具的 `execute()` 仅做组合调用（Router → Spawner → Fusion），实际 async 派发由 Spawner 处理；但工具 `execute()` 是 async 方法，可直接 `await spawner.spawn_batch()`。

---

### Decision 2：TaskRouter 规则路由采用关键词集合匹配，不使用正则

**选择**：每条规则为 `(frozenset[str], str)` 元组（关键词集合 → agent_id），用 `any(kw in intent_lower for kw in keywords)` 匹配；置信度由匹配关键词数 / 规则关键词数线性计算。

**理由**：规则路由的核心诉求是 <1ms 延迟和零依赖，关键词集合匹配满足要求且易于扩展（添加规则不需要修改核心逻辑）。正则在性能上接近但可读性更差，且无法自然计算置信度。

**LLM 路由触发条件**：规则路由 `confidence < 0.7`（可配置），使用 `model_resolver.chat(purpose="planning")`，输入用户意图和规则描述，要求 LLM 输出 JSON 格式路由决策。

---

### Decision 3：ResultFusionEngine strategy="auto" 分档逻辑

**选择**：
- 1 个结果 → `concatenate`（直接返回，零开销）
- 2-4 个结果 → `summarize`（一次 LLM 调用 `purpose="analysis"` 生成整合摘要）
- >4 个结果 → `hierarchical`（分批 summarize 后再汇总）

**理由**：`summarize` 策略需要 LLM 调用，仅在真正有多个独立结果时触发，单 Agent 场景零额外开销。`hierarchical` 防止超过 4 个结果时单次 LLM 上下文过长。

**冲突检测**：在 `summarize`/`consensus` 策略下，对结果中的数值结论做简单方差检测，标注到 `FusionResult.conflicts`（不修改内容，仅附加元数据）。

---

### Decision 4：Orchestrator 钩子插入位置

**选择**：在 runner.py 的 `tool_calls` 收集完成后、`for tc in tool_calls:` 循环前，添加：

```python
# Orchestrator 钩子：检测 dispatch_agents 工具调用
dispatch_tc = next((tc for tc in tool_calls if tc["function"]["name"] == "dispatch_agents"), None)
if dispatch_tc is not None:
    async for evt in self._handle_dispatch_agents(dispatch_tc, session, turn_id):
        yield evt
    # dispatch_agents 处理完成后继续循环（Fusion 结果已注入 session）
    iteration += 1
    continue
```

`_handle_dispatch_agents()` 是 runner.py 新增的私有方法，接收工具调用参数，执行 Router → Spawner → Fusion，将融合结果以 `tool_result` 消息形式注入 session，然后 yield 相关事件。

**理由**：最小侵入，不影响 1140 行后的现有工具执行代码，只在 `dispatch_agents` 出现时走新路径。`continue` 让主循环再次进入下一迭代（LLM 收到 Fusion 结果后决定下一步）。

---

### Decision 5：dispatch_agents 不加入 LLM_EXPOSED_BASE_TOOL_NAMES

**选择**：`dispatch_agents` 通过 `ToolRegistry.register()` 注册但不加入 `LLM_EXPOSED_BASE_TOOL_NAMES`；在主 Agent 的 system prompt 或 agents.md 文件中说明该工具的使用时机。

**理由**：`LLM_EXPOSED_BASE_TOOL_NAMES` 是子 Agent 的工具白名单基础，`dispatch_agents` 不应递归出现在子 Agent 中（子 Agent 不能再派发孙 Agent）。主 Agent 通过 runner.py 的 `get_tool_definitions()` 方法可以显式控制暴露哪些工具。

实际上，`dispatch_agents` 需要在主 Agent 中可被 LLM 调用，但不在子 Agent 中。runner.py 的 `_get_tool_definitions()` 方法根据 `_llm_exposed_function_tools` 白名单过滤，需要为 `dispatch_agents` 单独添加到主 Agent 的暴露工具集，而不是全局白名单。

**实现要点**：在 runner.py 中维护一个 `ORCHESTRATOR_TOOL_NAMES = {"dispatch_agents"}` 集合，`_get_tool_definitions()` 对主 Agent（非 SubSession）额外暴露这些工具。判断方式：`isinstance(session, SubSession)` 时不暴露。

## Risks / Trade-offs

**[风险] dispatch_agents 工具的 execute() 是同步接口但需要 await async 操作**
→ 缓解：`Skill.execute()` 实际上是 `async def execute()`（查看 tools/base.py 确认），可直接 await；若为同步，则通过 `asyncio.get_event_loop().run_until_complete()` 包装（但会阻塞），首选确认 base.py 接口。

**[风险] TaskRouter LLM 路由增加首次响应延迟**
→ 缓解：规则路由命中（confidence > 0.7）时不调用 LLM；LLM 路由仅在规则不确定时兜底，且 `purpose="planning"` 使用轻量模型。

**[风险] ResultFusionEngine summarize 策略的 LLM 调用可能超时**
→ 缓解：summarize 调用使用独立的 `asyncio.wait_for(timeout=60)` 超时控制；超时时降级为 `concatenate`。

**[风险] runner.py Orchestrator 钩子与现有计划任务管理（task_manager）的交互**
→ 缓解：`dispatch_agents` 调用期间不触发 `TASK_ATTEMPT` 事件逻辑（通过 func_name 判断跳过），避免与现有任务状态机冲突。

**[风险] WorkflowTopology 的 startTime 计算误差（客户端时钟）**
→ 缓解：仅用于 UI 展示，精度不关键；不影响后端状态。

## Open Questions（已解决）

1. **Skill.execute() 是否为 async？** → 需读 `src/nini/tools/base.py` 确认（任务 0 完成前确认）。
2. **runner.py 的 _get_tool_definitions() 如何过滤工具？** → 通过 `_llm_exposed_function_tools` set 过滤，SubSession 判断使用 `isinstance(session, SubSession)` 区分主/子 Agent 上下文。
