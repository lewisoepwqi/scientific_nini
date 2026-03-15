## Context

Phase 1/2 已建立 AgentRegistry + SubSession + SubAgentSpawner + TaskRouter + ResultFusionEngine 基础设施。当前所有子 Agent 均使用 ReAct 范式（工具链式触发），对"提出假设 → 收集证据 → 验证修正 → 得出结论"这类科研推理任务缺乏结构化支持，导致：
- 假设在对话中隐式游移，缺乏可追踪性
- 证据堆砌而非服务于假设，输出冗长
- 无收敛机制，可能无限轮次调用工具

Phase 3 在不修改主循环的前提下，为 `SubAgentSpawner` 引入 Hypothesis-Driven 执行路径，使 `literature_reading` 和 `research_planner` 两类 Agent 获得结构化推理能力。

## Goals / Non-Goals

**Goals:**
- `HypothesisContext` 完整生命周期：生成 → 收集证据 → 置信度更新 → 三条件收敛
- `SubAgentSpawner` 支持两条执行路径（ReAct / Hypothesis-Driven），通过 `paradigm` 字段路由
- 5 个新 WebSocket 事件类型，前端实时可视化假设链状态
- 向后兼容：未触发 Hypothesis-Driven 时行为与 Phase 1/2 完全相同

**Non-Goals:**
- 不修改主 Agent（Orchestrator）的 ReAct 主循环
- 不支持用户手动切换范式（由 AgentDefinition.paradigm 静态决定）
- 不实现跨会话假设持久化（假设链存活于 SubSession，随会话结束销毁）
- 不将 `run_code` / `run_r_code` 引入假设驱动 Agent 的 allowed_tools

## Decisions

### D1：HypothesisContext 存储位置 —— SubSession.artifacts["_hypothesis_context"]

**决策**：将 `HypothesisContext` 实例序列化后存入 `sub_session.artifacts["_hypothesis_context"]`，而非新增 `SubSession` 字段。

**理由**：`Session.artifacts` 是 `dict[str, Any]`，对象级存储无需修改数据类定义，SubSession 与父会话的字段契约不变。以下划线前缀表示内部状态，防止与业务产物命名冲突。

**备选方案**：在 `SubSession` 新增 `hypothesis_context: HypothesisContext | None` 字段。

**否决理由**：需同步更新 `SubSession.__post_init__` 和所有测试的初始化断言，侵入性过高。

---

### D2：收敛判断 —— 三条件"满足任一即收敛"

```python
def should_conclude(self) -> bool:
    # 条件 1：硬上限（防止无限循环）
    if self.iteration_count >= self.max_iterations:
        return True
    # 条件 2：所有假设已定论（无 pending 状态）
    if all(h.status in {"validated", "refuted"} for h in self.hypotheses):
        return True
    # 条件 3：贝叶斯收敛（相邻两轮最大置信度变化 < 5%）
    if len(self._prev_confidences) == len(self.hypotheses):
        delta = max(
            abs(h.confidence - prev)
            for h, prev in zip(self.hypotheses, self._prev_confidences)
        )
        if delta < 0.05:
            return True
    return False
```

**理由**：三条件覆盖三类终止场景：(1) 防御性上限、(2) 逻辑完备性、(3) 数值收敛。单一条件会在边缘情况下失效。

---

### D3：置信度更新 —— 简化贝叶斯（不引入概率论库）

置信度初始值 `0.5`，每轮更新规则：
- 发现支持证据：`confidence = min(1.0, confidence + 0.15)`
- 发现反驳证据：`confidence = max(0.0, confidence - 0.20)`（反驳权重略高于支持，模拟科学保守性）
- 无新证据：`confidence` 不变

**理由**：无需引入 `scipy` 或 `numpy`，规则清晰可测试，与项目现有依赖零冲突。标准贝叶斯更新需要先验分布假设，在没有历史数据的冷启动场景下意义有限。

---

### D4：范式分支触发 —— AgentDefinition.paradigm 静态决定，不做运行时推断

`SubAgentSpawner.spawn()` 检查 `agent_def.paradigm`：

```python
if agent_def.paradigm == "hypothesis_driven":
    return await self._spawn_hypothesis_driven(agent_def, task, session, timeout_seconds)
else:
    return await self._spawn_react(agent_def, task, session, timeout_seconds)
```

**理由**：运行时意图推断（如 LLM 判断"这条任务是否需要假设推理"）增加约 500ms 延迟，且与 TaskRouter 的路由职责重叠。将范式绑定到 Agent 定义，路由决策在 AgentRegistry 层完成，职责清晰。

---

### D5：假设循环架构 —— 使用现有 AgentRunner，不新建执行引擎

`_spawn_hypothesis_driven()` 不另起一个推理引擎，而是复用 `AgentRunner` 运行单轮 ReAct（`max_iterations=1`），在外层 Python 循环控制假设迭代：

```
while not hypothesis_context.should_conclude():
    # 单轮 ReAct：LLM 生成假设更新 + 工具调用（fetch_url / analysis_memory）
    round_result = await _run_single_react_turn(runner, sub_session, hypothesis_context)
    # 更新置信度、记录证据
    _update_hypothesis_context(hypothesis_context, round_result)
    hypothesis_context.iteration_count += 1
    await _emit_hypothesis_events(session.event_callback, hypothesis_context)
```

**理由**：无需维护第二套工具执行路径，AgentRunner 的 tool_call 解析、重试、事件推送等逻辑直接复用。

---

### D6：前端假设状态 —— 独立 hypothesis-slice，不合并到 agent-slice

新建 `web/src/store/hypothesis-slice.ts`，管理：
```typescript
interface HypothesisInfo {
  id: string
  content: string
  confidence: number       // 0-1
  status: 'pending' | 'validated' | 'refuted' | 'revised'
  evidenceFor: string[]
  evidenceAgainst: string[]
}
interface HypothesisSlice {
  hypotheses: HypothesisInfo[]
  currentPhase: string
  iterationCount: number
  activeSessionId: string | null
}
```

**理由**：假设链与 Agent 执行状态是两个正交维度，合并会使 AgentSlice 膨胀且难以独立测试。

## Risks / Trade-offs

- **假设循环超时风险**：max_iterations=3 + 每轮单次 ReAct，理论最大 3 × AgentRunner 超时 = 900s。缓解：`_spawn_hypothesis_driven` 外层套 `asyncio.wait_for(timeout=agent_def.timeout_seconds)`，与 ReAct 路径一致。

- **AgentRunner max_iterations 接口兼容性**：当前 `AgentRunner` 不暴露 `max_iterations` 参数。缓解：通过在 system_prompt 中追加"本轮只执行一次工具调用后立即返回结论"来软性约束单轮行为，无需修改 AgentRunner 接口。

- **HypothesisContext 序列化**：存入 `artifacts["_hypothesis_context"]` 时为 Python 对象引用，不做 JSON 序列化（子 Agent 生命周期内）。缓解：仅在 SubSession 内存中存活，随 SubSession 销毁，不涉及持久化边界。

- **前端事件与 AgentSlice 事件乱序**：`agent_start` 和 `hypothesis_generated` 可能在同一 Agent 生命周期内交替触发。缓解：两个 slice 独立订阅各自事件类型，互不干扰。

## Migration Plan

1. 后端：新建 `hypothesis_context.py`，修改 `spawner.py`（范式分支），修改 `events.py` + `event_builders.py`，更新两个 YAML 配置（`literature_reading`、`research_planner`）
2. 前端：新建 `hypothesis-slice.ts`、`hypothesis-event-handler.ts`、`HypothesisTracker.tsx`，注册事件处理器
3. 测试：`test_hypothesis_context.py`（三条件收敛单元测试）+ `test_spawner_hypothesis.py`（范式分支集成测试）
4. 回滚：恢复两个 YAML 的 `paradigm: react`，删除新建文件，前端移除 HypothesisTracker 渲染点

## Open Questions

- `_run_single_react_turn` 的 system_prompt 追加方式是否足够可靠来约束"单轮工具调用"行为，还是需要在 AgentRunner 层增加 `max_tool_calls` 参数？（建议先用 prompt 软约束，若集成测试失败再扩展接口）
- `HypothesisTracker` 是否需要在 `AgentExecutionPanel` 内嵌入，还是独立展示区域？（建议独立：假设链属于内容输出，Agent 状态属于进度监控，位置语义不同）
