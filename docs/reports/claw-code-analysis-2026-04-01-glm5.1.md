# claw-code 分析报告

> 日期：2026-04-01
> 外部参考：https://github.com/instructkr/claw-code
> 本地参考：docs/reports/agent-robustness-analysis-20260401.md

---

## 1. claw-code 设计理念

### 1.1 Harness-First 架构（Shim 模式）

**核心理念**：项目定位为 "Better Harness Tools"——研究 agent 系统的组装模式（如何连接工具、编排任务、管理上下文），而非构建可运行的 agent 运行时。

**代码依据**：`tools.py` 和 `commands.py` 中的 `execute_tool()` / `execute_command()` 均为 shim（垫片），返回描述性消息而非执行真实操作：

```python
# tools.py — shim 执行模式
def execute_tool(tool_name: str, payload: dict) -> str:
    """不执行真实操作，返回描述性消息"""
    # 例："工具 X 将在此执行 payload Y"
```

**意义**：将 harness 关注点（路由、权限、编排、事件流）与执行关注点彻底分离。这使得编排逻辑可以独立测试、独立演进。

### 1.2 不可变数据模型（Frozen Dataclass）

**核心理念**：全系统数据模型使用 `@dataclass(frozen=True)`，强制"创建新对象而非修改"的数据流。

**代码依据**：`models.py` 中所有模型均为 frozen：

```python
# models.py
@dataclass(frozen=True)
class UsageSummary:       # token 用量统计
    input_tokens: int
    output_tokens: int
    def add_turn(self, ...) -> UsageSummary:  # 返回新实例

@dataclass(frozen=True)
class PermissionDenial:   # 权限拒绝记录
@dataclass(frozen=True)
class PortingBacklog:     # 移植待办列表
@dataclass(frozen=True)
class Subsystem:          # 子系统描述
```

**意义**：天然线程安全、可哈希（可作为 dict key）、防止意外状态变异。在 async agent 场景下，不可变性消除了并发修改的整类 bug。

### 1.3 显式资源约束与预算门控

**核心理念**：在多个层面实施硬性资源控制，不依赖 LLM 自我约束。

**代码依据**：`query_engine.py` 的配置常量：

```python
# query_engine.py
max_turns = 8                    # 最大迭代次数
max_budget_tokens = 2000         # token 消耗上限
compact_after_turns = 12         # 压缩阈值
structured_retry_limit = 2       # 结构化输出重试上限
```

`submit_message()` 在每轮检查预算并返回 `stop_reason: 'max_budget_reached'`：

```python
# query_engine.py — 提前退出
if usage.output_tokens >= self.max_budget_tokens:
    return TurnResult(stop_reason='max_budget_reached', ...)
```

**意义**：系统行为有可预测的上界，不会因模型陷入循环而无限消耗资源。

### 1.4 Token-Based 轻量路由

**核心理念**：不依赖 LLM 调用进行工具/命令选择，而是通过 token 匹配实现零成本路由。

**代码依据**：`runtime.py` 的 `route_prompt()`：

```python
# runtime.py — Token-based 路由
def route_prompt(self, prompt: str) -> list:
    tokens = prompt.split()
    # 对每个命令/工具的 name、source_hint、responsibility 字段评分
    scored = [(self._score(t, tokens), t) for t in all_candidates]
    scored.sort(reverse=True)
    # 交替取命令和工具的最优匹配（interleaving）
```

**意义**：常见模式的工具选择无需 LLM 介入，既节省 token 又降低延迟。仅在复杂意图时才需要 LLM 判断。

### 1.5 严格有序事件协议

**核心理念**：定义了严格的事件发射顺序，消费者可增量处理且行为可预测。

**代码依据**：`query_engine.py` 的 `stream_submit_message()` 事件序列：

```
message_start → [command_match]* → [tool_match]* → [permission_denial]* → [message_delta]+ → message_stop
```

**意义**：前端消费者可基于事件类型实现确定性渲染逻辑，无需处理乱序事件。

### 1.6 关注点分离（模块边界清晰）

**代码依据**：核心模块职责划分：

| 模块 | 唯一职责 |
|------|---------|
| `query_engine.py` | 编排（turn 循环、流式事件、消息压缩） |
| `runtime.py` | 路由与会话生命周期 |
| `permissions.py` | 工具权限门控 |
| `execution_registry.py` | 统一命令/工具查找 |
| `session_store.py` | 会话持久化 |
| `setup.py` | 工作区初始化 |

每个模块文件控制在 200-400 行，单一职责明确。

---

## 2. 架构优势（对比 nini）

### 2.1 编排与执行的清晰分离

| 维度 | claw-code | nini |
|------|-----------|------|
| 编排层 | `query_engine.py`（~300 行） | `agent/runner.py`（4000+ 行） |
| 执行层 | `tools.py`（shim，独立） | 嵌入 runner.py 中的 `_execute_tool()` |
| 事件层 | 6 种有序事件 | 49 种事件类型 |

**claw-code 优势**：runner.py 的 4000+ 行体量使维护困难，bug 定位成本高。claw-code 将编排、路由、权限、持久化拆为独立模块，每个模块可独立测试和理解。

**对 nini 的启示**：现有优化方案（A-K）均在 runner.py 内部修补。长期来看，应考虑将 runner.py 拆分为独立模块。

### 2.2 不可变状态 vs 可变状态

| 维度 | claw-code | nini |
|------|-----------|------|
| 数据模型 | `frozen=True` dataclass | Pydantic v2（默认可变） |
| 状态变更 | 返回新实例 | 原地修改 session 属性 |
| 并发安全 | 天然安全 | 依赖 asyncio 单线程保证 |

**nini 风险**：session 对象在多个异步协程间共享（WebSocket handler、agent runner、compression），虽然 asyncio 单线程模型降低了竞态风险，但代码中 `session.xxx = yyy` 的原地修改模式使状态推理困难。

**典型问题**：`agent-robustness-analysis` 报告中的"pending_script_ids"优化 B，本质就是需要从"消息历史中的隐式状态"变为"session 上的显式结构化字段"。如果 session 是不可变的，这类状态遗漏在设计阶段就会被发现。

### 2.3 零成本路由 vs 全量 LLM 路由

| 维度 | claw-code | nini |
|------|-----------|------|
| 工具选择 | Token-based 评分（零 LLM 开销） | 每轮 LLM 决定工具调用 |
| 意图识别 | 路由层轻量判断 | `intent/` 模块（可能涉及 LLM） |

**nini 劣势**：弱模型（如 GLM-5）在工具选择上反复出错（如 create_script 后不调 run_script），根本原因是工具选择完全依赖 LLM 判断。claw-code 的 token-based 路由为常见模式提供了结构化保障。

### 2.4 显式预算 vs 隐式限制

| 维度 | claw-code | nini |
|------|-----------|------|
| Turn 限制 | `max_turns=8`，硬性 | `max_iter` 参数，可配置 |
| Token 预算 | `max_budget_tokens=2000`，硬性 | budget_warning（警告，非硬限制） |
| 压缩策略 | `compact_after_turns=12`，固定阈值 | 动态（基于 context 占比） |

**nini 劣势**：`budget_warning` 仅发出警告事件，不强制终止。弱模型可能在预算警告后继续无效循环，直到达到 `max_iter`。

### 2.5 精细权限控制

| 维度 | claw-code | nini |
|------|-----------|------|
| 权限粒度 | 精确名匹配 + 前缀匹配 | sandbox import 白名单 + allowed-tools 策略 |
| 权限决策 | 静态（deny_names/deny_prefixes） | 混合（静态 + 动态审批流） |

**claw-code 优势**：`ToolPermissionContext` 的两层拒绝机制（精确 + 前缀）简单、可预测、零运行时开销。nini 的动态审批流（`ask_user_question`）虽然更灵活，但增加了 LLM 交互复杂度。

---

## 3. nini 现有方案评价

### 3.1 方案有效性评价

| 优化 | 有效性 | 评价 |
|------|--------|------|
| A: auto_run | ★★★★★ | 将 create→run 两步 API 合并为一步，从根本上消除遗漏问题。符合 claw-code 的"减少 LLM 决策点"理念。 |
| B: pending_scripts context | ★★★★☆ | 结构化状态注入，不受压缩影响。与 claw-code 的不可变状态理念一致，但实现为可变 session 字段。 |
| C: noop→success:false | ★★★★☆ | 利用弱模型对 `success` 字段的信任。但属于"以毒攻毒"——理想方案应是消除 noop 场景本身。 |
| D: tool_failures context | ★★★★☆ | 结构化失败状态注入，价值明确。 |
| E: 沙箱超时按 purpose | ★★★☆☆ | 实用但治标不治本，purpose 分类依赖 LLM 正确标注。 |
| F: Recovery 按类型定制 | ★★★★☆ | 提高恢复提示的可操作性。但仍是软约束，依赖模型服从。 |
| G: ignored_tool_failures 结构化 | ★★★★☆ | 从关键词匹配升级为行为证据检测，方向正确。 |
| H: TRANSITIONAL_TEXT_RE | ★★★☆☆ | 修复正则锚定 bug，必要但影响力有限。 |
| I: task summary 字段 | ★★★☆☆ | 增加信息密度，但需要 schema 变更和向前兼容处理。 |
| J: 数据量提示 | ★★☆☆☆ | 工具描述层提示，效果最弱——等同已证明失败的"文本干预"路线。 |
| K: 日志指标 | ★★☆☆☆ | 可观测性改善，不直接影响模型行为。 |

### 3.2 局限性分析

#### 局限 1：修补式优化 vs 结构性重构

现有方案 A-K 均在 `runner.py` 内部添加逻辑。随着优化累积，runner.py 的复杂度将继续增长（已 4000+ 行）。claw-code 的模块拆分理念提供了更可持续的方向。

#### 局限 2：缺少不可变性保障

所有优化方案都向 session 添加新的可变字段（`pending_script_ids`、`current_turn_tool_failures`），但没有引入状态一致性校验。例如：
- `pending_script_ids` 在 `run_script` 成功后移除——但如果 session 被压缩/恢复，这个列表是否可靠？
- `current_turn_tool_failures` 每轮重置——但"轮"的边界在流式执行中并不总是清晰的。

#### 局限 3：仍依赖 LLM 理解 runtime context

优化 B 和 D 本质上是"更高质量的提示词注入"。虽然不受压缩影响是进步，但弱模型是否真的会注意到并遵守 runtime context 中的 `pending_scripts` 块？这与 claw-code 的"减少 LLM 决策点"理念相悖。

#### 局限 4：缺少工具级别的权限/预算控制

claw-code 的 `ToolPermissionContext` 提供了工具粒度的 deny 控制。nini 的 circuit breaker 是按工具+参数签名的，但没有全局的"某些工具在特定模式下禁止使用"的能力。

### 3.3 遗漏点

1. **runner.py 模块化拆分**：4000+ 行是所有维护困难的根源，但现有方案未涉及。
2. **不可变状态快照**：每次工具执行后可生成 session 的不可变快照，用于回滚和校验。
3. **轻量路由层**：对常见工具调用模式（create→run、profile→analyze）可预编码路由，无需 LLM 判断。
4. **结构化输出重试**：claw-code 的 `_render_structured_output()` 带 `structured_retry_limit=2` 的重试机制，nini 的工具结果序列化缺少类似保障。
5. **事件协议简化**：49 种事件类型增加了前端和后端的契约维护成本。

---

## 4. 优化建议（P0/P1/P2）

### P0：结构性改进

#### 建议 1：拆分 runner.py 为独立模块

**claw-code 依据**：query_engine.py（编排）、runtime.py（路由）、permissions.py（权限）的清晰分离。

**具体方案**：

```
agent/runner.py (4000+ 行)
    → agent/orchestrator.py    # 主循环、事件发射（~800 行）
    → agent/tool_executor.py   # 工具调度、circuit breaker、loop guard（~600 行）
    → agent/context_manager.py # 上下文构建、压缩触发（~500 行）
    → agent/recovery.py        # transitional 检测、completion check、recovery prompt（~400 行）
    → agent/turn_budget.py     # 预算管理、turn 计数、提前退出（~200 行）
```

**落地路径**：先提取 `turn_budget.py`（最小风险），再逐步提取其他模块。每步保证测试全部通过。

---

#### 建议 2：引入 Session State Snapshot（不可变快照）

**claw-code 依据**：全系统使用 `frozen=True` dataclass，状态变更通过创建新实例。

**具体方案**：

```python
# agent/state_snapshot.py
@dataclass(frozen=True)
class TurnSnapshot:
    """每轮工具执行后的不可变状态快照"""
    turn_id: int
    pending_script_ids: tuple[str, ...]    # 不可变
    tool_failures: tuple[ToolFailure, ...]  # 不可变
    completed_task_ids: tuple[str, ...]
    timestamp: str

class SessionState:
    """管理状态快照序列"""
    _snapshots: list[TurnSnapshot]

    def record(self, session) -> TurnSnapshot:
        """从当前 session 状态生成不可变快照"""
        snap = TurnSnapshot(
            turn_id=self._current_turn,
            pending_script_ids=tuple(session.pending_script_ids),
            ...
        )
        self._snapshots.append(snap)
        return snap

    def latest(self) -> TurnSnapshot | None:
        """获取最新快照，用于 context 注入"""
        return self._snapshots[-1] if self._snapshots else None
```

**意义**：
- context 注入的数据源是不可变快照，不受后续 session 修改影响
- 可用于回滚（恢复到上一个一致性状态）
- 可用于 harness completion check（对比预期快照 vs 实际快照）

---

### P1：工具链优化

#### 建议 3：引入常见模式的预编码工具链（Toolchain）

**claw-code 依据**：`route_prompt()` 的 token-based 路由——常见模式不需要 LLM 决策。

**具体方案**：

```python
# agent/toolchains.py
class Toolchain(Protocol):
    """预编码的工具调用序列"""
    async def execute(self, session, first_call_result) -> AsyncIterator[Event]: ...

class CreateAndRunScript(Toolchain):
    """create_script → run_script 自动链"""
    async def execute(self, session, first_call_result):
        # first_call_result 是 create_script 的结果
        script_id = first_call_result.data["script_id"]
        yield from run_script(session, script_id=script_id)

# 在 tool_executor.py 中注册
TOOLCHAINS: dict[str, Toolchain] = {
    "create_script": CreateAndRunScript(),  # 自动链接到 run_script
}
```

**意义**：优化 A（auto_run）的升级版——不是在 create_script 内部加 auto_run 参数，而是通过 toolchain 机制将两步 API 在系统层自动链接。LLM 只需调用 create_script，系统自动完成后续步骤。

---

#### 建议 4：添加 Turn Budget 硬限制

**claw-code 依据**：`max_budget_tokens=2000` 的硬性预算门控。

**具体方案**：

```python
# agent/turn_budget.py
@dataclass
class TurnBudget:
    max_turns: int = 20              # 硬性上限
    max_tool_calls: int = 50         # 单次会话工具调用上限
    max_consecutive_no_progress: int = 3  # 连续无进展上限
    warning_threshold: float = 0.8   # 80% 时发出警告

    def should_stop(self, turn: int, tool_calls: int, no_progress: int) -> tuple[bool, str]:
        if tool_calls >= self.max_tool_calls:
            return True, "工具调用次数已达上限"
        if no_progress >= self.max_consecutive_no_progress:
            return True, "连续无进展次数已达上限"
        return False, ""

    def should_warn(self, turn: int, tool_calls: int) -> bool:
        return tool_calls >= self.max_tool_calls * self.warning_threshold
```

**与现有 budget_warning 的区别**：现有 budget_warning 仅发出事件，不强制终止。TurnBudget 在 `should_stop()` 返回 True 时直接结束 agent 循环。

---

#### 建议 5：Harness Completion Check 升级为结构化校验

**claw-code 依据**：`_render_structured_output()` 的结构化输出 + 重试模式。

**具体方案**：

将现有的 5 个 CompletionCheckItem 从"关键词匹配 + 文本分析"升级为"行为证据链"：

```python
# harness/completion_verifier.py
@dataclass(frozen=True)
class CompletionEvidence:
    """不可变的完成证据"""
    has_tool_failures: bool
    has_post_failure_success: bool     # 失败后有成功的重试
    has_artifact_events: bool          # 有 CHART/ARTIFACT 事件
    has_explicit_acknowledgment: bool  # 文本中明确承认失败
    completed_task_ratio: float        # 已完成任务比例
    total_tool_calls: int

    def to_check_items(self) -> list[CompletionCheckItem]:
        items = []
        if self.has_tool_failures and not (self.has_post_failure_success or self.has_explicit_acknowledgment):
            items.append(CompletionCheckItem(key="ignored_tool_failures", passed=False))
        ...
        return items
```

**意义**：将 HC-1（关键词匹配）、HC-2（Recovery 提示不区分类型）合并为基于不可变证据的结构化校验。优化 F 和优化 G 可整合进此框架。

---

### P2：长期架构优化

#### 建议 6：事件协议分层简化

**claw-code 依据**：6 种有序事件（message_start → command_match → tool_match → permission_denial → message_delta → message_stop）的简洁设计。

**具体方案**：

将 49 种事件类型按语义分层：

```python
# 事件分层
CORE_EVENTS = {TEXT, TOOL_CALL, TOOL_RESULT, DONE, ERROR}        # 必须保证
ANALYSIS_EVENTS = {ANALYSIS_PLAN, PLAN_STEP_UPDATE, ...}         # PDCA/分析专用
CONTENT_EVENTS = {CHART, DATA, ARTIFACT, IMAGE}                  # 内容产出
SYSTEM_EVENTS = {TOKEN_USAGE, CONTEXT_COMPRESSED, ...}           # 系统状态
INTERACTION_EVENTS = {ASK_USER_QUESTION}                          # 用户交互
```

前端按层订阅，核心层事件必须保证有序且不丢，分析层和内容层允许最终一致。

---

#### 建议 7：工具级别的静态权限策略

**claw-code 依据**：`ToolPermissionContext` 的精确名 + 前缀两层拒绝。

**具体方案**：

```python
# tools/permissions.py
@dataclass(frozen=True)
class ToolPermissionPolicy:
    deny_tools: frozenset[str]           # 禁止的工具（精确匹配）
    deny_prefixes: tuple[str, ...]       # 禁止的前缀
    require_approval: frozenset[str]     # 需要用户审批的工具
    max_calls_per_session: dict[str, int]  # 单工具调用上限

    def check(self, tool_name: str, call_count: int) -> PermissionDecision:
        if tool_name in self.deny_tools or any(tool_name.startswith(p) for p in self.deny_prefixes):
            return PermissionDecision.DENY
        if call_count >= self.max_calls_per_session.get(tool_name, float('inf')):
            return PermissionDecision.DENY
        if tool_name in self.require_approval:
            return PermissionDecision.REQUIRE_APPROVAL
        return PermissionDecision.ALLOW
```

**与现有 circuit breaker 的区别**：circuit breaker 是被动的（检测到失败后才阻止），ToolPermissionPolicy 是主动的（基于策略预判）。

---

#### 建议 8：Shim 模式用于 Harness 逻辑测试

**claw-code 依据**：MirroredTool / MirroredCommand 的 shim 执行模式——测试编排逻辑不需要真实工具。

**具体方案**：

```python
# tests/harness/shim_tools.py
class ShimTool(Tool):
    """测试用 shim，返回预设结果"""
    def __init__(self, name: str, response: ToolResult):
        self.name = name
        self._response = response

    async def execute(self, session, **kwargs) -> ToolResult:
        return self._response

# 测试编排逻辑
def test_loop_guard_triggers_on_repetition():
    registry = ToolRegistry()
    registry.register(ShimTool("run_code", ToolResult(success=True, message="ok")))
    runner = AgentRunner(registry=registry, ...)
    # 无需真实沙箱，纯编排逻辑测试
```

**意义**：nini 的 1975 个测试中有大量 mock，但 mock 粒度不够统一。shim 模式提供了一种标准化的测试替身，使 harness 逻辑测试（完成校验、循环检测、预算管理）完全独立于工具实现。

---

## 5. 参考资料

### claw-code 源码

| 文件 | 核心模式 |
|------|---------|
| `src/models.py` | Frozen dataclass 不可变模型 |
| `src/query_engine.py` | 编排层、turn 循环、流式事件、消息压缩 |
| `src/runtime.py` | Token-based 路由、会话生命周期 |
| `src/permissions.py` | 精确名 + 前缀两层权限拒绝 |
| `src/execution_registry.py` | 统一命令/工具查找接口 |
| `src/tools.py` | Shim 执行模式、权限过滤 |
| `src/session_store.py` | JSON 会话持久化 |

### nini 内部文档

| 文档 | 内容 |
|------|------|
| `docs/reports/agent-robustness-analysis-20260401.md` | Agent 鲁棒性分析与优化报告（问题清单、修复状态、优化 A-K） |
| `src/nini/agent/runner.py` | 4000+ 行的 ReAct agent 主循环 |
| `src/nini/harness/runner.py` | Harness 层（完成校验、恢复循环、预算警告） |
| `src/nini/agent/session.py` | Session 管理（可变状态、压缩、持久化） |
| `src/nini/tools/registry.py` | 35+ 工具注册 |
| `src/nini/api/websocket.py` | WebSocket 事件流 |

### 关键洞察

> claw-code 的核心贡献不是某个具体技术，而是**架构决策**：通过不可变状态、模块分离、显式预算、零成本路由，将 agent 系统中"依赖 LLM 判断"的部分压缩到最小。nini 当前方案的优化 A-K 是在正确方向上的修补，但长期可持续性需要借鉴 claw-code 的结构性分离理念。
