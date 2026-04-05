# nini sub-agent / multi-agent 迭代方案

> 生成日期：2026-04-05
> 依据：claw-code 分析（`docs/research/claw-code-analysis.md`）+ nini 现状梳理
> 范围：sub-agent 与 multi-agent 协作模块

---

## 优先级总览

| 级别 | 项目 | 改什么 | 工作量 |
|------|------|------|------|
| **P0** | 状态对象不可变化 | `spawner.py`、`registry.py`、`fusion.py` 核心 dataclass | 小 |
| **P0** | stop_reason 全路径显式化 | `spawner.py`、`dispatch_agents.py` | 小 |
| **P0** | 工具暴露前置过滤统一化 | `spawner.py` + 新增 `tool_exposure.py` | 小 |
| **P1** | SubAgentRunSnapshot 会话快照 | 新增 `agent/snapshot.py` | 中 |
| **P1** | 断路器 + 失败类型分类 | `spawner.py` | 中 |
| **P1** | 路由决策审计日志 | `router.py` | 小 |
| **P2** | 受限嵌套 Agent 支持 | `spawner.py`、`runner.py` | 中 |
| **P2** | 编排 YAML DAG | 新增 `agent/workflow.py` | 大 |
| **P2** | OpenTelemetry 链路集成 | 全链路注入 trace_id | 大 |

---

## P0：立即可落地，消除架构性隐患

### P0-1：核心状态 dataclass 改为 frozen=True

**改什么：** `agent/registry.py`、`agent/spawner.py`（SubAgentResult）、`agent/fusion.py`（FusionResult）、`agent/router.py`（RoutingDecision）

**为什么：** claw-code 所有核心状态对象全部 frozen=True（RoutedMatch、TurnResult、PermissionDenial 等）。可变 dataclass 在并发 agent 场景下存在隐式状态污染风险——`spawner.py:461` 子会话共享父会话 datasets 引用，若 SubAgentResult 可变，结果回写阶段存在写入竞争。

**怎么做：**
```python
# 将以下对象改为 frozen=True
@dataclass(frozen=True)
class SubAgentResult:
    agent_id: str
    success: bool
    summary: str
    artifacts: dict   # 改为 frozenset 或在赋值时 tuple(...)
    ...

@dataclass(frozen=True)
class RoutingDecision:
    agent_ids: tuple[str, ...]   # list → tuple
    tasks: tuple[str, ...]
    confidence: float
    parallel: bool
```
对于含 dict 的字段，改用 `MappingProxyType` 或在构造时 `tuple(items())` 传递。

**工作量：** 小（3-4 个文件，只改 dataclass 装饰器和字段类型，不改逻辑）

---

### P0-2：stop_reason 全路径显式化

**改什么：** `tools/dispatch_agents.py`、`agent/spawner.py`（spawn 返回路径）

**为什么：** claw-code 的 TurnResult 始终携带 stop_reason，调用方通过字段值分支而非异常捕获判断终止原因。nini 的 spawner 在部分路径（timeout、stopped、普通失败）通过 SubAgentResult.success=False + error 字段传递，但 dispatch_agents.py 的调用方缺少对不同 stop_reason 的分支处理，导致"超时"和"永久失败"走同一路径。

**怎么做：**
```python
# agent/spawner.py
@dataclass(frozen=True)
class SubAgentResult:
    ...
    stop_reason: str   # 'completed' | 'timeout' | 'stopped' | 'error' | 'max_retries'

# tools/dispatch_agents.py — 调用方
for result in results:
    if result.stop_reason == 'timeout':
        # 降级：记录部分结果，继续融合
    elif result.stop_reason == 'stopped':
        # 用户主动停止，不计入失败统计
    elif result.stop_reason == 'error':
        # 真正失败，触发重试或告警
```

**工作量：** 小（主要是枚举补全 + 调用方分支补充）

---

### P0-3：工具暴露前置过滤统一化

**改什么：** 新增 `agent/tool_exposure.py`，整合 `spawner.py:476` 的 create_subset 逻辑

**为什么：** claw-code 的 `get_tools(simple_mode, include_mcp, permission_context)` 把暴露面控制统一在一个入口，三个维度正交组合覆盖所有场景。nini 的子 Agent 工具限制通过 `registry.create_subset(agent_def.allowed_tools)` 实现，但没有对应的 `simple_mode`（轻量 Agent 过度暴露）和 `deny_prefixes` 机制（无法批量屏蔽某类工具）。

**怎么做：**
```python
# 新增 agent/tool_exposure.py
@dataclass(frozen=True)
class ToolExposurePolicy:
    allowed_tools: tuple[str, ...] = ()   # 空 = 无白名单限制
    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = ()
    simple_mode: bool = False             # 只暴露最小工具集

    def filter(self, registry: ToolRegistry) -> ToolRegistry:
        # 按 allowed_tools 白名单 → deny_names 黑名单 → deny_prefixes 前缀黑名单 → simple_mode 裁剪
        ...

# spawner.py:476 改为
policy = ToolExposurePolicy(allowed_tools=tuple(agent_def.allowed_tools))
subset_registry = policy.filter(self._tool_registry)
```

**工作量：** 小（新增一个小模块，spawner.py 改一处调用）

---

## P1：短期改进，补齐可观测性与可靠性

### P1-1：SubAgentRunSnapshot 会话快照

**改什么：** 新增 `agent/snapshot.py`，在 spawner 每轮 sub-agent 执行结束后生成快照

**为什么：** claw-code 的 RuntimeSession 是"执行即快照"——所有状态都在一个结构体里，`as_markdown()` 即时可读。nini 目前 sub-agent 执行结果分散在 SubAgentResult、事件流、父会话 artifacts 三处，无法在一个地方获得"这个 sub-agent 跑了什么、结果如何"的完整视图。

**怎么做：**
```python
# 新增 agent/snapshot.py
@dataclass(frozen=True)
class SubAgentRunSnapshot:
    run_id: str
    agent_id: str
    task: str
    stop_reason: str
    execution_time_ms: int
    tool_calls: tuple[str, ...]    # 调用的工具名列表
    artifact_keys: tuple[str, ...]
    summary: str
    error: str | None
    attempt: int

    def as_markdown(self) -> str:
        # 参考 claw-code RuntimeSession.as_markdown()
        ...
```

在 `spawner.spawn()` 完成时生成快照，存入 `parent_session.sub_agent_snapshots`（追加，不覆盖）。

**工作量：** 中（新增模块 + spawner 集成 + session 新字段）

---

### P1-2：断路器 + 失败类型精细分类

**改什么：** `agent/spawner.py` 的 `spawn_with_retry()`

**为什么：** claw-code 用 stop_reason 区分终止类型，使调用方能针对不同原因选择不同策略。nini 的 `spawn_with_retry()` 对所有失败一律重试（`if not result.success`），包括永久性失败（如 agent_id 不存在、工具配置错误）——这些情况重试无意义，反而浪费时间。

**怎么做：**
```python
# spawner.py — 替换 spawn_with_retry 内的重试逻辑
RETRIABLE_REASONS = {'timeout', 'rate_limit', 'transient_error'}
PERMANENT_REASONS = {'config_error', 'missing_agent', 'permission_denied'}

for attempt in range(max_retries):
    result = await self.spawn(...)
    if result.success or result.stopped:
        return result
    if result.stop_reason in PERMANENT_REASONS:
        break   # 不重试
    await asyncio.sleep(2 ** attempt)
```

同时引入简单断路器：同一 agent_id 连续失败 N 次则暂时跳过（记录到 session 级黑名单，本会话有效）。

**工作量：** 中（主要是失败分类 + 断路器状态管理）

---

### P1-3：路由决策审计日志

**改什么：** `agent/router.py` 的 `_llm_route()` 方法

**为什么：** claw-code 的 HistoryLog 在每个关键步骤（routing、execution、turn）都记录结构化日志。nini 的 LLM 路由（`_llm_route()`）解析失败时只记 warning，无法事后重现"为什么 agent X 被选中"的决策过程。

**怎么做：**
```python
# router.py — _llm_route() 中增加
routing_audit = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'prompt_tokens': len(prompt.split()),
    'rule_confidence': rule_confidence,
    'llm_triggered': True,
    'llm_raw_response': raw_response,
    'parsed_decision': decision.model_dump() if decision else None,
    'parse_error': str(e) if parse_failed else None,
}
logger.info('routing_decision', extra={'audit': routing_audit})
```

在 `RoutingDecision` 中增加 `audit_ref: str | None` 字段，存储日志 ref 供快照引用。

**工作量：** 小（在已有日志点补充结构化字段）

---

## P2：中期增强，扩展编排能力

### P2-1：受限嵌套 Agent 支持（深度 ≤ 2）

**改什么：** `agent/spawner.py`、`agent/runner.py`（工具暴露策略）

**为什么：** 当前子 Agent 被完全禁止使用 `dispatch_agents`（`runner.py:73-74`），无法进行二级任务分解。对于复杂科研任务（如"文献综述"需要子 agent 进一步拆解为"引用检索"+"方法论比较"），这是一个功能缺口。

**怎么做：**
```python
# 在 AgentDefinition 中增加
@dataclass(frozen=True)
class AgentDefinition:
    ...
    max_spawn_depth: int = 0   # 0 = 不允许派发子 Agent，1 = 允许一级嵌套

# spawner.py — 构建子 Agent 工具集时
current_depth = getattr(parent_session, 'spawn_depth', 0)
if current_depth < agent_def.max_spawn_depth:
    # 允许 dispatch_agents，但传入 depth+1
    subset_registry = policy.filter(self._tool_registry)
else:
    subset_registry = policy.filter(self._tool_registry, exclude=['dispatch_agents'])
```

硬限制：`spawn_depth > 2` 直接拒绝，防止无限递归。

**工作量：** 中（需改 AgentDefinition schema、spawner 深度传递、runner 工具暴露）

---

### P2-2：编排 YAML DAG 支持

**改什么：** 新增 `agent/workflow.py`

**为什么：** 当前 nini 只支持简单并行派发（`spawn_batch`），无法表达顺序依赖（Agent B 需要 Agent A 的输出）、条件分支（根据 Agent A 结果选择 Agent B 或 C）等复杂工作流。对于长科研任务（数据清洗 → 统计分析 → 可视化），顺序编排是刚需。

**怎么做：**

```yaml
# 工作流定义示例（agent_workflow.yaml）
name: full_analysis
steps:
  - id: clean
    agent: data_cleaner
    task: "清洗数据集 {dataset_id}"
  - id: stat
    agent: statistician
    task: "对清洗结果做统计检验"
    depends_on: [clean]
  - id: viz
    agent: viz_designer
    task: "基于统计结果生成图表"
    depends_on: [stat]
    condition: "stat.success == true"
```

```python
# agent/workflow.py
class WorkflowExecutor:
    async def execute(self, workflow: WorkflowDef, session: Any) -> WorkflowResult:
        # 拓扑排序 → 逐层并行执行 → 结果注入下游 context
        ...
```

第一期只实现顺序依赖（depends_on），不做条件分支；第二期再加 condition。

**工作量：** 大（需要 DAG 拓扑排序、依赖结果注入、YAML schema 设计）

---

### P2-3：OpenTelemetry 链路追踪集成

**改什么：** `agent/spawner.py`、`agent/router.py`、`agent/fusion.py`，注入 trace_id

**为什么：** 当前 nini 的 `run_id` 存在于事件 metadata 中，但不是标准的 W3C Trace Context 格式，无法与外部观测系统（Jaeger、Grafana Tempo）集成。claw-code 的 session_id 在所有流式事件中传播，是类似思路的简化版。

**怎么做：**
```python
# 引入 opentelemetry-api（仅 API 层，不强依赖 SDK）
from opentelemetry import trace

tracer = trace.get_tracer("nini.agent")

# spawner.spawn() 中
with tracer.start_as_current_span("sub_agent.spawn") as span:
    span.set_attribute("agent.id", agent_def.agent_id)
    span.set_attribute("agent.task", task[:200])
    span.set_attribute("parent.session_id", parent_session.id)
    ...
```

第一期只做 span 注入（不强依赖 exporter），保证 trace_id 在事件流中传播；第二期再配置 OTLP exporter。

**工作量：** 大（全链路注入工作量不小，且需协调前端事件展示）

---

## 实施建议

### 推荐顺序

```
Week 1:  P0-1 + P0-2 + P0-3（状态建模规范化）
Week 2:  P1-1 + P1-3（快照 + 审计日志）
Week 3:  P1-2（断路器）
Week 4+: P2 按需排期，P2-1 优先于 P2-2
```

P0 三项改动侵入最小（只改 dataclass 装饰器 + 新增一个小模块），但能立即提升架构稳定性和并发安全性，建议本迭代打包一起完成。

### 不推荐的方向

以下来自 claw-code 的特性**不适合**直接引入 nini：

- **全 token-based routing 替代 LLM 路由**：科研任务语义复杂度远高于命令行路由，纯关键词匹配召回率不足
- **全量 immutable session**：nini 的 session 持有 DataFrame、artifact、memory，全量不可变改造成本极高
- **简化事件协议**：nini 前端与事件类型强绑定，短期收缩事件种类代价过大
