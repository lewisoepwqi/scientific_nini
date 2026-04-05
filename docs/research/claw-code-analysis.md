# claw-code 深度分析报告

> 分析日期：2026-04-05
> 仓库：https://github.com/instructkr/claw-code
> 分析范围：sub-agent 设计、multi-agent 协作、值得借鉴的巧思
> 方法：全新独立分析，不参考历史报告

---

## 一、前置认知：claw-code 的真实定性

在开始三维分析之前，必须先厘清 claw-code 是什么：

**claw-code 是 Claude Code（原 Rust/TypeScript 实现）的 Python porting workspace / 演示镜像。**

它的 Python 端代码不是真实的 multi-agent 框架实现，而是对原始功能的"镜像描述"(mirrored shim)。`execute_tool()` 实际返回的是 `"Mirrored tool 'X' would handle payload '...'."` 这样的描述性字符串，而非真正的工具调用。

```python
# src/tools.py:61-66
def execute_tool(name: str, payload: str = '') -> ToolExecution:
    module = get_tool(name)
    if module is None:
        return ToolExecution(..., handled=False, message=f'Unknown mirrored tool: {name}')
    action = f"Mirrored tool '{module.name}' from {module.source_hint} would handle payload {payload!r}."
    return ToolExecution(name=module.name, ..., handled=True, message=action)
```

**因此，claw-code 的价值不在于"实现参考"，而在于"设计哲学示范"**——它把 Claude Code 的工程方法论用 Python 表达出来，供分析和借鉴。

---

## 二、Sub-agent 设计维度

### 2.1 Agent 的定义方式与注册机制

claw-code 没有传统的"sub-agent"注册机制。它通过两个层次定义可调用实体：

**层次 1：PortingModule（静态快照注册）**

```python
# src/models.py:13-18
@dataclass(frozen=True)
class PortingModule:
    name: str
    responsibility: str
    source_hint: str
    status: str = 'planned'
```

工具和命令均通过 JSON 快照加载，而非动态注册：

```python
# src/tools.py:10-20
SNAPSHOT_PATH = Path(__file__).resolve().parent / 'reference_data' / 'tools_snapshot.json'

@lru_cache(maxsize=1)
def load_tool_snapshot() -> tuple[PortingModule, ...]:
    raw_entries = json.loads(SNAPSHOT_PATH.read_text())
    return tuple(
        PortingModule(name=entry['name'], responsibility=entry['responsibility'],
                      source_hint=entry['source_hint'], status='mirrored')
        for entry in raw_entries
    )

PORTED_TOOLS = load_tool_snapshot()
```

**层次 2：ExecutionRegistry（运行时执行注册）**

```python
# src/execution_registry.py:29-44
@dataclass(frozen=True)
class ExecutionRegistry:
    commands: tuple[MirroredCommand, ...]
    tools: tuple[MirroredTool, ...]

    def command(self, name: str) -> MirroredCommand | None: ...
    def tool(self, name: str) -> MirroredTool | None: ...

def build_execution_registry() -> ExecutionRegistry:
    return ExecutionRegistry(
        commands=tuple(MirroredCommand(module.name, module.source_hint) for module in PORTED_COMMANDS),
        tools=tuple(MirroredTool(module.name, module.source_hint) for module in PORTED_TOOLS),
    )
```

**关键设计：** 注册表是在启动时一次性构建的不可变对象，而非运行时动态添加。

### 2.2 输入/输出契约（TurnResult）

每次 agent 执行的输入输出均用冻结 dataclass 明确建模：

```python
# src/query_engine.py:20-28
@dataclass(frozen=True)
class TurnResult:
    prompt: str
    output: str
    matched_commands: tuple[str, ...]
    matched_tools: tuple[str, ...]
    permission_denials: tuple[PermissionDenial, ...]
    usage: UsageSummary
    stop_reason: str   # 'completed' | 'max_turns_reached' | 'max_budget_reached'
```

**关键设计：** `stop_reason` 是显式字符串枚举而非异常，`permission_denials` 是一等公民而非边缘情况。

### 2.3 生命周期管理（RuntimeSession）

完整的执行上下文被封装在一个全量快照对象中：

```python
# src/runtime.py:18-38
@dataclass
class RuntimeSession:
    prompt: str
    context: PortContext
    setup: WorkspaceSetup
    setup_report: SetupReport
    system_init_message: str
    history: HistoryLog
    routed_matches: list[RoutedMatch]
    turn_result: TurnResult
    command_execution_messages: tuple[str, ...]
    tool_execution_messages: tuple[str, ...]
    stream_events: tuple[dict[str, object], ...]
    persisted_session_path: str
```

`as_markdown()` 方法直接将会话状态渲染为可读报告，这使得调试无需外部工具。

---

## 三、Multi-agent 协作维度

### 3.1 Orchestrator 调度机制（token-based routing）

`PortRuntime.route_prompt()` 用 token 集合匹配决定哪些命令/工具被选中：

```python
# src/runtime.py:70-93
def route_prompt(self, prompt: str, limit: int = 5) -> list[RoutedMatch]:
    tokens = {token.lower() for token in prompt.replace('/', ' ').replace('-', ' ').split() if token}
    by_kind = {
        'command': self._collect_matches(tokens, PORTED_COMMANDS, 'command'),
        'tool': self._collect_matches(tokens, PORTED_TOOLS, 'tool'),
    }
    # 保证每类至少一个，再按分数补齐
    selected = []
    for kind in ('command', 'tool'):
        if by_kind[kind]:
            selected.append(by_kind[kind].pop(0))
    ...

@staticmethod
def _score(tokens: set[str], module: PortingModule) -> int:
    haystacks = [module.name.lower(), module.source_hint.lower(), module.responsibility.lower()]
    return sum(1 for token in tokens if any(token in h for h in haystacks))
```

**关键设计：** 路由是纯确定性的 token 匹配，无 LLM 调用，延迟极低（< 1ms）。

### 3.2 Agent 间通信机制

**层次 1：结构化流式事件协议**

```python
# src/query_engine.py:65-89（stream_submit_message）
def stream_submit_message(self, prompt, matched_commands, matched_tools, denied_tools):
    yield {'type': 'message_start', 'session_id': self.session_id, 'prompt': prompt}
    if matched_commands:
        yield {'type': 'command_match', 'commands': matched_commands}
    if matched_tools:
        yield {'type': 'tool_match', 'tools': matched_tools}
    if denied_tools:
        yield {'type': 'permission_denial', 'denials': [d.tool_name for d in denied_tools]}
    result = self.submit_message(...)
    yield {'type': 'message_delta', 'text': result.output}
    yield {'type': 'message_stop', 'usage': {...}, 'stop_reason': result.stop_reason, ...}
```

**层次 2：TranscriptStore（对话历史共享）**

```python
# src/transcript.py
@dataclass
class TranscriptStore:
    entries: list[str] = field(default_factory=list)
    flushed: bool = False

    def compact(self, keep_last: int = 10) -> None:
        if len(self.entries) > keep_last:
            self.entries[:] = self.entries[-keep_last:]

    def replay(self) -> tuple[str, ...]:
        return tuple(self.entries)
```

`flush()` 方法在 persist_session 时调用，标记"当前历史已持久化"，区分了内存状态与持久化状态。

**层次 3：PermissionDenial 的传播**

```python
# src/runtime.py:133-138（_infer_permission_denials）
def _infer_permission_denials(self, matches: list[RoutedMatch]) -> list[PermissionDenial]:
    denials = []
    for match in matches:
        if match.kind == 'tool' and 'bash' in match.name.lower():
            denials.append(PermissionDenial(
                tool_name=match.name,
                reason='destructive shell execution remains gated in the Python port'
            ))
    return denials
```

权限拒绝不是异常，而是被传入下游每个执行层的显式参数。

### 3.3 错误处理与预算控制

```python
# src/query_engine.py:47-63（submit_message 中的预算门控）
if len(self.mutable_messages) >= self.config.max_turns:
    return TurnResult(..., stop_reason='max_turns_reached')

projected_usage = self.total_usage.add_turn(prompt, output)
stop_reason = 'completed'
if projected_usage.input_tokens + projected_usage.output_tokens > self.config.max_budget_tokens:
    stop_reason = 'max_budget_reached'
```

**关键设计：** budget 超出不抛异常，而是返回携带 `stop_reason='max_budget_reached'` 的正常结果。调用方对这种"软失败"有完整感知能力。

---

## 四、值得借鉴的巧思

### 巧思 1：全量冻结数据类作为状态容器

claw-code 几乎所有核心对象都用 `@dataclass(frozen=True)`：

```python
# RoutedMatch, TurnResult, QueryEngineConfig, StoredSession, PermissionDenial,
# UsageSummary, PortingModule, MirroredCommand, MirroredTool, ExecutionRegistry
# 全部 frozen=True
```

**为什么聪明：** 不可变对象可以安全地在 agent 间传递、序列化、diff，不存在谁在哪里改了什么的隐患。状态变更只能通过构造新对象完成，使数据流方向清晰。

### 巧思 2：ToolPermissionContext —— 过滤前置

```python
# src/permissions.py
@dataclass(frozen=True)
class ToolPermissionContext:
    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = ()

    def blocks(self, tool_name: str) -> bool:
        lowered = tool_name.lower()
        return lowered in self.deny_names or any(lowered.startswith(p) for p in self.deny_prefixes)

# src/tools.py - 调用侧
def get_tools(simple_mode=False, include_mcp=True, permission_context=None):
    tools = list(PORTED_TOOLS)
    if simple_mode:
        tools = [m for m in tools if m.name in {'BashTool', 'FileReadTool', 'FileEditTool'}]
    return filter_tools_by_permission_context(tuple(tools), permission_context)
```

**为什么聪明：** 工具暴露面的控制在"获取工具列表"这一步就已完成，而不是在"工具被调用"时才拦截。`simple_mode` + `include_mcp` + `permission_context` 三个维度的正交组合，覆盖了大多数场景。

### 巧思 3：stop_reason 枚举化，消除隐式失败

所有执行终止原因通过 `stop_reason` 字段显式传递：`'completed'`、`'max_turns_reached'`、`'max_budget_reached'`。调用方的 `run_turn_loop` 中：

```python
# src/runtime.py:116-127
for turn in range(max_turns):
    result = engine.submit_message(...)
    results.append(result)
    if result.stop_reason != 'completed':
        break  # 而不是捕获异常
```

**为什么聪明：** 分支在数据上（字段值）而非控制流上（异常），结果列表完整保留，便于事后分析每轮是如何终止的。

### 巧思 4：RuntimeSession.as_markdown() —— 调试即文档

```python
# src/runtime.py:40-65
def as_markdown(self) -> str:
    lines = ['# Runtime Session', f'Prompt: {self.prompt}',
             '## Context', render_context(self.context),
             '## Routed Matches', ...
             '## Command Execution', ...
             '## Tool Execution', ...
             '## Turn Result', self.turn_result.output, ...]
    return '\n'.join(lines)
```

**为什么聪明：** 会话状态本身就是可渲染的文档，无需额外的日志聚合工具。任何时刻调用 `as_markdown()` 即得到一份完整的执行报告。

### 巧思 5：@lru_cache + 快照加载 —— 一次加载，永久冻结

```python
@lru_cache(maxsize=1)
def load_tool_snapshot() -> tuple[PortingModule, ...]:
    ...

PORTED_TOOLS = load_tool_snapshot()
```

**为什么聪明：** 工具面定义在进程启动时确定，后续所有请求共享同一个不可变 tuple。无并发竞争，无意外变更，diff 工具面即 diff 快照文件。

---

## 五、nini 现状梳理

> 以下基于对 `src/nini/agent/` 的直接代码读取（2026-04-05），代码证据已按文件路径标注。

### 5.1 现有架构概述

nini 实现了一个功能完整的分层 multi-agent 系统，包含五个核心组件：

| 组件 | 文件 | 职责 |
|------|------|------|
| `AgentDefinition` + `AgentRegistry` | `agent/registry.py` | Agent 定义与注册（YAML 驱动） |
| `TaskRouter` | `agent/router.py` | 双轨路由（规则 + LLM 兜底） |
| `SubAgentSpawner` | `agent/spawner.py` | 并行派发 + 指数退避重试 |
| `ResultFusionEngine` | `agent/fusion.py` | 四策略融合（concat/summarize/consensus/hierarchical） |
| `DispatchAgentsTool` | `tools/dispatch_agents.py` | 主 Agent 与编排系统的接口工具 |

### 5.2 Sub-Agent 定义

```python
# src/nini/agent/registry.py:25-36
@dataclass
class AgentDefinition:
    agent_id: str
    name: str
    description: str
    system_prompt: str
    purpose: str
    allowed_tools: list[str] = field(default_factory=list)
    max_tokens: int = 8000
    timeout_seconds: int = 300
    paradigm: str = "react"   # "react" | "hypothesis_driven"
```

从 YAML 文件动态加载，支持两种推理范式。

### 5.3 通信机制（四层）

1. **数据集共享（ReadOnly引用）** — `spawner.py:461`：子会话直接引用父会话 datasets 对象
2. **事件回调中继** — `spawner.py:840-916`：子 Agent 事件通过闭包实时推送至父会话
3. **产物同步回写** — `spawner.py:424-426`：artifacts/documents 串行写回父会话
4. **停止信号级联** — `spawner.py:124-141`：asyncio.Event 实时传播父停止信号

### 5.4 与 claw-code 相比的差距清单

| 维度 | claw-code 做法 | nini 当前状态 | 差距性质 |
|------|--------------|-------------|---------|
| **状态不可变性** | 核心对象全部 `frozen=True` | 多数 dataclass 可变 | 架构风险 |
| **工具暴露前置过滤** | `ToolPermissionContext` + `simple_mode` 在 `get_tools()` 层拦截 | 白名单机制，但过滤点分散 | 维护性 |
| **stop_reason 结构化** | `TurnResult.stop_reason` 全路径显式传播 | 部分路径用异常控制流 | 可观测性 |
| **会话全量快照** | `RuntimeSession` 包含完整执行上下文 | 无单一快照对象 | 调试能力 |
| **工具面快照文件** | JSON 快照 + lru_cache | 无静态基线文件 | 回归检测 |
| **错误恢复精细度** | stop_reason 区分终止类型 | 固定重试 + 指数退避，无断路器 | 可靠性 |
| **调试渲染** | `as_markdown()` 即时渲染完整会话 | 无等效能力 | 运维成本 |
| **编排复杂度** | 简单 token 路由（刻意简单） | 双轨路由已有，但缺 DAG 支持 | 功能缺口 |
| **嵌套 Agent** | 无（porting scope 限制） | 防递归禁止，无限深度控制 | 功能缺口 |
| **链路追踪** | 结构化事件有 session_id | run_id 存在但未集成标准协议 | 可观测性 |

---

## 六、综合结论

claw-code 的核心贡献是示范了一种**"结构即文档、冻结即安全、显式即可靠"**的工程方法论：

- 把所有中间状态建模为冻结 dataclass → 可安全传递、可直接序列化
- 把所有失败路径建模为 stop_reason 字段 → 无异常控制流，调用方完整感知
- 把工具过滤前置到 get_tools() → 运行时无意外暴露
- 把会话状态渲染为 as_markdown() → 无需外部工具即可调试

nini 已有功能完整的 multi-agent 编排层，但在**状态建模规范性**、**工具暴露前置控制**、**调试可视化**和**错误类型显式化**四个维度上有明显提升空间。
