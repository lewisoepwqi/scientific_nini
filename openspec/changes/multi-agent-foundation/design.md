## Context

当前 `AgentRunner` 实现了完整的单 Agent ReAct 循环，所有复杂请求由一个 Agent 串行处理。`Session` 是重量级数据类，`__post_init__` 会初始化 `ConversationMemory`（写磁盘）、`KnowledgeMemory`、`TaskManager`，并通过 `_append_entry()` 持久化每条消息。`ToolRegistry` 将全部 30+ 工具暴露给 LLM，无隔离机制。`ModelResolver` 对外接口是 `chat(messages, tools, *, purpose, ...)` 异步生成器，不提供获取底层客户端的方法。

本 change 在不修改现有 ReAct 主循环的前提下，新增三个组件：AgentRegistry（注册中心）、SubSession（隔离上下文）、SubAgentSpawner（动态派生器），以及一个新方法 `ToolRegistry.create_subset()`。

## Goals / Non-Goals

**Goals:**
1. 可在运行时通过 `AgentRegistry` 查询和匹配 Specialist Agent 定义
2. 子 Agent 可通过 `SubSession` 独立执行，不污染父会话的消息历史和持久化存储
3. `SubAgentSpawner` 可并行派生最多 4 个子 Agent，支持重试和超时
4. 子 Agent 只能访问其声明的 `allowed_tools`，代码执行能力保留在主 Agent
5. 主 Agent 可通过 WebSocket 事件（agent_start/progress/complete/error）向前端实时报告子 Agent 状态

**Non-Goals:**
- 任务智能路由（TaskRouter）：Phase 2 实现
- 结果聚合引擎（ResultFusionEngine）：Phase 2 实现
- Orchestrator 模式接入 runner.py：Phase 2 实现
- Hypothesis-Driven 范式：Phase 3 实现
- 自定义 Agent 的 UI 管理界面：暂不规划

## Decisions

### Decision 1：SubSession 使用继承而非 duck typing

**选择**：`SubSession` 继承 `Session`，覆盖 `__post_init__` 跳过磁盘初始化。

**理由**：`AgentRunner` 对 `Session` 有深度依赖（`add_message`、`add_tool_result`、`add_tool_call` 等 10+ 持久化方法，以及 `conversation_memory`、`task_manager`、`event_callback`、`tool_approval_grants` 等字段）。duck typing 需要在 `SubSession` 中完整复制这些接口，维护成本极高且容易遗漏。继承 + 覆盖 `__post_init__` 是最小改动路径：子类只替换磁盘写入部分，其余方法原样继承。

**替代方案**：Protocol/ABC — 需要抽取 `Session` 的接口为抽象类，涉及对现有代码的大量重构，超出本 change 范围。

**实现要点**：
- `SubSession.__post_init__` 使用 `InMemoryConversationMemory`（内存模式，不落盘）替代默认的 `ConversationMemory`
- `knowledge_memory` 设为 `None`（子 Agent 不独立维护知识库，通过父会话的 `ContextBuilder` 获取知识）
- 保留 `datasets`、`artifacts`、`documents` 字段，供 AgentRunner 工具调用使用

---

### Decision 2：SubSession 包含 documents 字段

**选择**：`SubSession` 从父会话复制 `documents` 的只读引用，执行完毕后通过 `SubAgentResult.documents` 回写。

**理由**：`literature_search` 和 `literature_reading` 两个 Specialist Agent 的核心产物是文档（PDF 内容、文献摘要），需要写入 `documents` 字段。若 `SubSession` 缺少该字段，这两个 Agent 无法正常工作。

---

### Decision 3：SubAgentSpawner 通过 AgentRunner 执行子 Agent

**选择**：`SubAgentSpawner._execute_agent()` 实例化 `AgentRunner`，传入受限工具注册表（`skill_registry=subset_registry`）和 `SubSession`；调用 `AgentRunner.run(sub_session, task)` 执行 ReAct 循环。

**理由**：`ModelResolver` 不提供 `get_client_for_purpose()` 方法，其唯一对外接口是 `chat()` 异步生成器。`AgentRunner` 已经封装了正确的调用方式（工具解析、错误处理、事件推送），复用比绕过更安全。

**关于 purpose 路由**：`AgentRunner.__init__` 无 `purpose` 参数，内部 `_resolve_model_purpose()` 根据迭代次数和 `stage_override` 自动选择 `planning`/`verification`/`chat`。Phase 1 的子 Agent 复用这一默认路由；若需为特定子 Agent 强制指定模型（如 `vision` Agent），可在 `run()` 调用时传入 `stage_override`。该机制当前只支持 `planning`/`verification` 两个覆盖值，足够 Phase 1 使用。Phase 2 如需真正的 per-agent 模型配置，可为 `AgentRunner.__init__` 增加 `purpose_override` 参数。

**替代方案**：直接在 `SubAgentSpawner` 中调用 `model_resolver.chat()` 实现简化版循环 — 会导致逻辑重复，且失去 `AgentRunner` 已有的工具解析、错误处理、事件推送能力。

---

### Decision 4：ToolRegistry.create_subset() 返回新实例

**选择**：`create_subset()` 创建新的 `ToolRegistry` 实例，仅注册 `allowed_tool_names` 中指定的工具；不存在的工具名记录 warning 并跳过。

**理由**：返回独立实例而非修改原实例，确保主 Agent 的 `ToolRegistry` 不受影响。`ToolRegistry` 内部有 `_llm_exposed_function_tools` 白名单机制，新实例从零构建更简洁，无需处理白名单同步问题。

---

### Decision 5：run_code / run_r_code 不进入任何子 Agent 的 allowed_tools

**选择**：代码执行工具保留在 Orchestrator（主 Agent）层，所有 Specialist Agent 的 `allowed_tools` 均不包含 `run_code` 和 `run_r_code`。

**理由**：沙箱执行通过 `multiprocessing.Process` 进程隔离，每次 `run_code` 调用 spawn 子进程。若 4 个并行子 Agent 各自触发代码执行，并发进程数可能超过系统限制并影响稳定性。Specialist Agent 的职责是分析、规划、可视化（通过 `chart_session`），不需要直接执行任意代码。

---

### Decision 6：子 Agent 事件通过父会话 event_callback 推送

**选择**：`SubSession.event_callback` 初始化时绑定父会话的 `event_callback`，子 Agent 产生的 WebSocket 事件（含 `agent_id` 标识）通过同一 callback 推送。

**理由**：前端通过单一 WebSocket 连接接收所有事件，无需建立新的通信信道。`agent_id` 字段使前端能区分事件来源。

---

### Decision 7：并发上限设为 4

**选择**：`spawn_batch()` 默认 `max_concurrency=4`，通过 `asyncio.Semaphore` 控制。

**理由**：每个子 Agent 在 ReAct 循环中可能多次调用 LLM。4 个并发子 Agent 同时运行时，LLM 调用的实际并发数可达 4 × 平均工具轮数（通常 3-6 轮），总请求数在一次分析任务中不会触发典型 API tier 的速率限制。同时，沙箱进程隔离（multiprocessing.spawn）在 4 个并发下资源开销可控；若超过 8 个，进程切换开销会影响吞吐量。此值可通过参数覆盖。

## Risks / Trade-offs

**[风险] SubSession 继承 Session 后，Session 的未来改动可能破坏 SubSession**
→ 缓解：在 `test_sub_session.py` 中添加集成测试，验证 `AgentRunner` + `SubSession` 的完整执行路径；Session 的重大改动需检查 SubSession 兼容性。

**[风险] InMemoryConversationMemory 需要新实现或现有 ConversationMemory 不支持内存模式**
→ 缓解：Phase 1 第一步验证 `ConversationMemory` 是否有内存模式参数；若无，新建最小实现（仅需实现 `append`、`load_messages`、`clear` 三个方法）。

**[风险] 9 个 Specialist Agent 的 allowed_tools 若引用不存在的工具名，create_subset() 会静默跳过导致 Agent 能力缺失**
→ 缓解：`create_subset()` 对不存在工具名记录 WARNING 级别日志；单元测试验证每个 Agent 的 allowed_tools 均在注册表白名单内。

**[风险] SubAgentResult 回写 artifacts/documents 到父会话时的并发写入冲突**
→ 缓解：`spawn_batch()` 使用 `asyncio.gather()` 等待所有子 Agent 完成后，由 Spawner 统一串行回写结果，不在子 Agent 执行期间并发修改父会话。

## Migration Plan

1. 本 change 全部为新增代码，无破坏性变更，无需迁移
2. 现有单 Agent 会话不受影响，`AgentRunner` 主循环逻辑不变
3. 新增 WebSocket 事件类型（追加枚举值）向前兼容，旧前端客户端会忽略未知事件类型

## Open Questions（已解决）

1. ~~`ConversationMemory` 是否已有内存模式？~~ **已确认**：`ConversationMemory.__init__` 总绑定到磁盘路径，无内存模式参数。需新建 `InMemoryConversationMemory`，最小接口为：`append(entry: dict)`、`load_all() -> list[dict]`（`ConversationMemory` 基类方法，不可漏实现）、`load_messages() -> list[dict]`、`clear()`。
2. ~~`AgentRunner` 构造函数是否支持 `purpose` 参数？~~ **已确认**：`AgentRunner.__init__` 无 `purpose` 参数，工具注册表通过 `skill_registry` 传入。purpose 路由由 `_resolve_model_purpose()` 内部处理，Phase 1 复用默认路由即可（见 Decision 3）。
