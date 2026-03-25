# TradingAgents × Scientific Nini · 借鉴优化方向报告

> 生成日期：2026-03-25
> TradingAgents 版本：`589b351f2ab55a8a37d846848479cebc810a5a36`（2026-03-22）
> Scientific Nini 版本：`bd33b80f50c7e253dd1bb259e09924eeae0ea629`

---

## 执行摘要

TradingAgents 的核心优势不在“智能体数量多”，而在于它把角色边界、共享状态、阶段顺序和辩论回合都做成了显式工作流，因此系统行为更可预测、更易解释。Scientific Nini 当前已经在工具体系、记忆体系、容错和工程化上明显强于 TradingAgents，但主聊天链路仍以单主 Agent 的 ReAct 循环为核心，`Intent → Capability → Skill Runtime` 主要在 MCP 入口更完整，在 WebSocket 主链路里没有同样强的一致性。最值得借鉴的不是 TradingAgents 的金融角色本身，而是“有类型的阶段状态 + 角色输出契约 + 受控编排图”。如果 Nini 引入这三点，预期可降低复杂任务漂移、提升多专家协作质量，并让现有的 Memory、Harness、WebSocket 观测能力真正服务于多智能体编排。

---

## 一、TradingAgents 项目概览

### 1.1 项目定位与背景

TradingAgents 是一个面向金融交易研究的多智能体框架，目标是模拟真实交易公司中的分析、研究、交易、风控和组合管理流程。官方 README、zdoc 文档和 Tauric Research 研究页都把它描述为“用专业角色拆分复杂交易决策”的系统，而不是通用 Agent 平台。

基于 2026-03-25 可验证的公开信息：

| 指标 | 数值 |
|------|------|
| GitHub 仓库 | `TauricResearch/TradingAgents` |
| Star | 40,829 |
| Fork | 7,519 |
| Issues | 162 |
| Pull requests | 98 |
| 默认分支 | `main` |
| 最近推送 | 2026-03-22T23:51:27Z |
| PyPI/包版本 | `0.2.2` |
| 最近主分支提交数 | GitHub 页面显示 114 commits |

### 1.2 整体架构

官方文档把系统分成 5 个连续阶段：分析师团队、研究辩论、交易员、风险管理、组合经理。源码中这一点并不是 README 口号，而是直接编排为 LangGraph 状态图。

```text
用户输入（ticker + date + LLM/provider 配置）
  ↓
TradingAgentsGraph
  ↓
LangGraph StateGraph(AgentState)
  ├── Analyst Team
  │   ├── Market Analyst
  │   ├── Social Analyst
  │   ├── News Analyst
  │   └── Fundamentals Analyst
  ├── Research Debate
  │   ├── Bull Researcher
  │   ├── Bear Researcher
  │   └── Research Manager
  ├── Trader
  ├── Risk Debate
  │   ├── Aggressive Analyst
  │   ├── Conservative Analyst
  │   └── Neutral Analyst
  └── Portfolio Manager
  ↓
共享状态 AgentState / DebateState
  ↓
最终交易结论 + 落盘报告
```

关键代码证据：

- `tradingagents/graph/trading_graph.py:43-135` 负责装配 LLM、memory、tool nodes 和 graph setup。
- `tradingagents/graph/setup.py:108-202` 用 `StateGraph(AgentState)` 明确注册节点与边。
- `tradingagents/agents/utils/agent_states.py:10-76` 定义全局共享状态与两个辩论子状态。

代表性代码片段：

```python
workflow = StateGraph(AgentState)
workflow.add_node("Bull Researcher", bull_researcher_node)
workflow.add_node("Trader", trader_node)
workflow.add_conditional_edges(
    "Bull Researcher",
    self.conditional_logic.should_continue_debate,
    {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
)
```

### 1.3 技术栈

| 层次 | 技术选型 | 版本/证据 |
|------|----------|-----------|
| Agent 编排 | LangGraph | `pyproject.toml` 依赖 `langgraph>=0.4.8` |
| LLM 接入 | LangChain provider clients + 自定义 factory | `tradingagents/llm_clients/factory.py` |
| 数据接入 | `yfinance` / `Alpha Vantage` 双供应商路由 | `tradingagents/dataflows/interface.py` |
| Memory | 每角色一份 BM25 记忆 + reflection | `tradingagents/agents/utils/memory.py`、`tradingagents/graph/reflection.py` |
| 交互入口 | Typer CLI + Rich TUI | `cli/main.py` |
| 持久化 | 本地结果目录、data cache | `tradingagents/default_config.py` |

### 1.4 工程实践观察

1. 架构表达非常强。README、研究页、源码三者一致，都围绕“固定角色图 + 共享状态”。
2. 编排层清晰，但测试明显偏弱。目录树显示 `tests/` 下仅 1 个测试文件 `tests/test_ticker_symbol_handling.py`。
3. 可扩展性主要体现在“换模型、换数据源、调回合数”，而不是面向通用业务的插件式生态。
4. 社区热度很高，但工程可维护性更像“研究框架向产品化演进中”，不是成熟平台内核。

---

## 二、Scientific Nini 当前状态

### 2.1 当前架构的实际落地

从本地代码看，Scientific Nini 的实际运行主链路更接近：

```text
Web UI
  ↓
FastAPI / WebSocket
  ↓
HarnessRunner
  ↓
AgentRunner（单主 Agent ReAct）
  ├── ToolRegistry（Function Tools + Markdown Skills）
  ├── KnowledgeLoader（BM25 / vector / hybrid）
  ├── Session（messages / datasets / artifacts / approvals）
  ├── ConversationMemory / LongTermMemory
  └── 可选 dispatch_agents 多专家派发
  ↓
事件流（text / reasoning / tool_call / tool_result / chart / done）
```

而 `Intent → Capability → Skill Runtime` 这一层次目前最完整的落点在 MCP Server：

- `src/nini/mcp/server.py:1-64` 明确宣称 Nini 2.0 架构是 `Intent Layer → Capability Layer → Skill Runtime`。
- `src/nini/mcp/server.py:121-170` 暴露架构层工具 `analyze_intent`、`list_capabilities`、`execute_capability` 加底层 Function Skills。
- 但 WebSocket 主入口 `src/nini/api/websocket.py:153-214` 仍然直接实例化 `AgentRunner(tool_registry=_tool_registry)`。
- `src/nini/agent/runner.py:1-78` 表明主循环核心仍是“构建上下文 → 调 LLM → 执行工具 → 循环”。

结论：Nini 已经具备三层架构元素，但主产品路径尚未完全以三层架构驱动。

### 2.2 已实现能力

结合 README、源码和测试，可确认已落地的核心能力：

| 能力 | 代码证据 |
|------|----------|
| 短期会话记忆（STM） | `src/nini/memory/conversation.py:131-260` |
| 长期记忆（LTM） | `src/nini/memory/long_term_memory.py:91-280` |
| 对话压缩 | `src/nini/memory/compression.py` |
| RAG / 本地检索 / hybrid retrieval | `src/nini/knowledge/loader.py:56-211` |
| Function Skills 注册与执行 | `src/nini/tools/registry.py:269-345` |
| Markdown Skills 扫描与启停 | `src/nini/tools/registry.py:146-153,343-344` |
| 多模型路由与故障转移 | `src/nini/agent/model_resolver.py:540-737` |
| Ollama 支持 | `src/nini/__main__.py:30-33`、`src/nini/agent/providers/ollama_provider.py` |
| MCP Gateway | `src/nini/mcp/server.py:99-340` |
| 多专家基础设施（可选） | `src/nini/tools/dispatch_agents.py:17-146`、`src/nini/agent/spawner.py` |

### 2.3 明显薄弱点

以下问题都能从代码直接归纳，不是凭空猜测：

1. 架构叙事与主链路存在分叉。MCP 已按 `Intent → Capability → Skill Runtime` 暴露，但 WebSocket 主链路仍主要依赖单主 Agent + ToolRegistry；Capability 层没有成为默认入口。
2. 多智能体仍是“外挂能力”，不是默认编排内核。`dispatch_agents` 由 `AgentRunner` 特殊拦截，且 `TaskRouter` 在默认注册时关闭了 LLM fallback（`src/nini/tools/registry.py:327-333`）。
3. 会话状态过于集中。`Session` 同时承载消息、数据集、产物、授权、压缩片段、偏好和任务管理（`src/nini/agent/session.py:25-51`），复杂任务更适合再引入 typed substate。
4. Capability 直接执行覆盖还不完整。`data_exploration`、`article_draft`、`report_generation`、`citation_management`、`peer_review`、`research_planning` 仍是不可直接执行能力（`src/nini/capabilities/defaults.py:119-239`）。
5. Specialist Agent 输出缺少统一结构契约。当前 `dispatch_agents` 主要依赖自由文本 `summary` 和后置融合，不像 TradingAgents 那样天然写回固定槽位状态。

### 2.4 项目阶段判断

我对 Scientific Nini 的判断不是“早期探索”也不是“完全稳定平台”，而是：

**稳定迭代期，且处于发布后维护与架构收敛阶段。**

依据：

- 仓库说明已完成 `Phase 1 ~ Phase 7`，进入发布后维护。
- 本地版本已是 `0.1.1`，具备 CLI、WebSocket、MCP、打包、Harness。
- 测试规模较大，`tests/` 下有 127 个测试文件。
- 但多智能体、Capability 主链路化、角色状态建模仍在扩展和收敛中。

---

## 三、对标分析（8 维度）

### 3.1 Agent 角色设计

**TradingAgents 的做法**

TradingAgents 使用固定职责的专职角色，而不是“一个通用 Agent + 一堆工具”。角色分为四类：分析师、研究辩论、交易员、风险辩论/组合经理。角色输出直接落到共享状态中的专用字段，如 `market_report`、`investment_plan`、`final_trade_decision`。

代码证据：

```python
class AgentState(MessagesState):
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    investment_debate_state: Annotated[InvestDebateState, ...]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]
```

来源：`tradingagents/agents/utils/agent_states.py:50-76`

**Scientific Nini 现状**

Nini 主链路仍是通用型 `AgentRunner`。虽然已具备 YAML Specialist Agent 注册、任务路由、子会话派发能力（`src/nini/agent/registry.py:23-125`、`src/nini/agent/router.py:22-96`、`src/nini/agent/spawner.py:31-223`），但这些角色并不是默认工作模式，而是通过 `dispatch_agents` 按需启用。

**可借鉴性**：⭐⭐⭐⭐⭐

**借鉴要点**：最值得借鉴的是“角色对应明确交付物”，不是 TradingAgents 的金融角色名。Nini 适合沉淀出 `data_cleaner / statistician / viz_designer / writer / reviewer` 这类科研专职角色，并为每种角色定义固定输出槽位。

---

### 3.2 Orchestration 模式

**TradingAgents 的做法**

TradingAgents 是非常典型的“中心编排 + 显式状态图”。主入口 `TradingAgentsGraph` 负责组装依赖，`GraphSetup` 负责创建 `StateGraph(AgentState)`，每个阶段的下一步都由条件边控制。

代码证据：

```python
workflow = StateGraph(AgentState)
workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")
workflow.add_edge("Research Manager", "Trader")
workflow.add_edge("Trader", "Aggressive Analyst")
workflow.add_edge("Portfolio Manager", END)
```

来源：`tradingagents/graph/setup.py:108-202`

**Scientific Nini 现状**

Nini 的主编排器是 `AgentRunner` 的 ReAct 循环，不是显式图。`dispatch_agents` 是在工具调用阶段被 `AgentRunner` 特判拦截（`src/nini/agent/runner.py:3172-3287`），因此多专家协作属于局部增强，而不是全局 orchestration 模式。

**可借鉴性**：⭐⭐⭐⭐⭐

**借鉴要点**：对于 Nini 中“差异分析、回归分析、文章初稿、同行评审”这类高价值复合任务，应引入显式编排模板或轻量状态图，而不是全部押给自由 ReAct。

---

### 3.3 状态流转

**TradingAgents 的做法**

TradingAgents 的状态流转非常直接：所有角色共享一个 `AgentState`，辩论阶段再通过 `InvestDebateState` / `RiskDebateState` 管理历史、当前发言者、轮次计数。分析师阶段结束后还会清空 `messages`，避免对下游阶段形成噪声累积。

代码证据：

```python
def should_continue_market(self, state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools_market"
    return "Msg Clear Market"
```

来源：`tradingagents/graph/conditional_logic.py:14-44`

**Scientific Nini 现状**

Nini 的状态比 TradingAgents 丰富得多。`Session` 不仅有消息，还挂载数据集、产物、授权、压缩上下文和任务管理；会话消息会被 canonicalize，按事件类型落盘；大 payload 会引用化存储（`src/nini/agent/session.py:25-51`、`src/nini/memory/conversation.py:43-260`）。

**可借鉴性**：⭐⭐⭐☆☆

**借鉴要点**：TradingAgents 的 typed state 适合借给 Nini 的“复杂工作流层”，但不适合直接替换 Nini 现有 `Session`。正确做法是保留 `Session` 作为运行容器，再补一个针对复合任务的 typed substate。

---

### 3.4 工具 / 技能注册

**TradingAgents 的做法**

TradingAgents 的工具体系是“静态工具 + 供应商路由”。工具通过 LangChain `@tool` 装饰器声明，再由 `ToolNode` 挂到 analyst 节点上；真正的数据源切换在 `route_to_vendor()` 层完成，并支持 category/tool-level vendor 覆盖。

代码证据：

```python
VENDOR_METHODS = {
    "get_stock_data": {"alpha_vantage": get_alpha_vantage_stock, "yfinance": get_YFin_data_online},
}
def route_to_vendor(method: str, *args, **kwargs):
    ...
```

来源：`tradingagents/dataflows/interface.py:68-160`

**Scientific Nini 现状**

Nini 在这一维其实更强。`ToolRegistry` 同时管理 Function Tools、Markdown Skills、catalog、guardrail、fallback、subset registry，还能为子 Agent 构造受限工具子集（`src/nini/tools/registry.py:74-239,269-345`）。

**可借鉴性**：⭐⭐☆☆☆

**借鉴要点**：可借鉴的是“外部数据连接器的 vendor adapter 设计”，不建议在工具注册能力上向 TradingAgents 靠拢。Nini 应继续坚持自己的注册中心体系。

---

### 3.5 Memory 策略

**TradingAgents 的做法**

TradingAgents 采用“按角色隔离的轻量记忆”。Bull、Bear、Trader、Manager 各自持有 `FinancialSituationMemory`，底层是 BM25；reflection 模块在事后分析对错，并把“情境 -> 建议”写回角色记忆。

代码证据：

```python
self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
...
result = self._reflect_on_component(...)
bull_memory.add_situations([(situation, result)])
```

来源：`tradingagents/graph/trading_graph.py:97-105`、`tradingagents/graph/reflection.py:73-121`

**Scientific Nini 现状**

Nini 已经实现了远强于 TradingAgents 的 Memory 体系：会话 JSONL、压缩摘要、长期记忆、向量索引、冲突去重、大 payload 引用化、知识检索注入（`src/nini/memory/conversation.py`、`src/nini/memory/long_term_memory.py`、`src/nini/knowledge/loader.py`）。

**可借鉴性**：⭐⭐☆☆☆

**借鉴要点**：不建议照搬 BM25-only memory。真正值得借鉴的是“按角色隔离经验库”的思想，例如给 Nini 的 `statistician`、`viz_designer`、`writing_assistant` 各自维护轻量 episodic memory namespace。

---

### 3.6 错误处理与容错

**TradingAgents 的做法**

TradingAgents 的容错主要体现在两处：

1. 数据供应商 fallback，仅在 Alpha Vantage 限流时切换到其他 vendor。
2. 工作流回合数强约束，通过 `max_debate_rounds`、`max_risk_discuss_rounds` 限制辩论长度。

代码证据：

```python
for vendor in fallback_vendors:
    try:
        return impl_func(*args, **kwargs)
    except AlphaVantageRateLimitError:
        continue
```

来源：`tradingagents/dataflows/interface.py:134-160`

**Scientific Nini 现状**

Nini 在这一维明显更成熟：LLM 多供应商 fallback（`src/nini/agent/model_resolver.py:544-737`）、子 Agent retry（`src/nini/agent/spawner.py:152-190`）、fusion timeout fallback（`src/nini/agent/fusion.py`，测试见 `tests/test_fusion.py:126-137`）、工具授权与导入审批（`src/nini/agent/runner.py:207-240`）。

**可借鉴性**：⭐⭐☆☆☆

**借鉴要点**：只建议借 TradingAgents 的“回合预算”与“阶段 timebox”思路，把多专家工作流限制在更可控的 token/cost 上界内。

---

### 3.7 可观测性

**TradingAgents 的做法**

TradingAgents 的可观测性偏向 CLI 人机界面。`cli/main.py` 中 `MessageBuffer` 维护 agent 状态、报告分段和工具调用，`run_analysis()` 绑定 `StatsCallbackHandler` 追踪 LLM/tool 调用并把结果落盘。

代码证据：

```python
stats_handler = StatsCallbackHandler()
graph = TradingAgentsGraph(..., callbacks=[stats_handler])
message_buffer.init_for_analysis(selected_analyst_keys)
```

来源：`cli/main.py` 中 `run_analysis()` 调用链

**Scientific Nini 现状**

Nini 的可观测性更偏产品与测试平台：WebSocket 事件流、Harness、event schema contract、conversation observability、sandbox observability 等覆盖较全（`src/nini/api/websocket.py:56-220`，以及 `tests/test_conversation_observability.py`、`tests/test_event_schema_contract.py`、`tests/test_harness_runner.py`）。

**可借鉴性**：⭐⭐⭐☆☆

**借鉴要点**：TradingAgents 的“按阶段展示协作进度”和“报告分段完成度”很适合借给 Nini 前端，尤其是多专家协作 UI；但底层观测基础设施不必退回到它的实现方式。

---

### 3.8 扩展性

**TradingAgents 的做法**

TradingAgents 的扩展是“强架构、弱插件”。新增一个固定角色通常要同步修改：

1. `AgentState` 字段；
2. `GraphSetup` 节点注册；
3. `ConditionalLogic` 路由；
4. 可能的 tool node 和 CLI 展示。

这让架构一致性很强，但角色增长成本并不低。

**Scientific Nini 现状**

Nini 在工具和轻量 specialist 扩展上更灵活：工具可直接注册，Markdown Skills 可扫描发现，Specialist Agent 可由 YAML 驱动（`src/nini/agent/registry.py:23-125`）。但复杂任务要从“灵活”走向“稳定”，还缺统一 workflow 模板层。

**可借鉴性**：⭐⭐⭐☆☆

**借鉴要点**：不建议复制 TradingAgents 的硬编码角色图，但建议复制其“新增一类任务时必须显式声明状态、边界和输出槽位”的设计纪律。

---

## 四、核心借鉴点总结

### 4.1 强烈推荐引入（高价值 + 低改造成本）

#### 借鉴点 A：角色输出契约与报告槽位

**来源**：TradingAgents `tradingagents/agents/utils/agent_states.py`、`tradingagents/graph/setup.py`

**核心思路**：

TradingAgents 的每个核心角色都不是“自由发挥后把文本丢回聊天记录”，而是写入固定状态槽位。这样下游节点不必重新理解上游自由文本的全部上下文，只需要消费特定报告字段。

**在 scientific_nini 的应用场景**：

为 `dispatch_agents` 里的科研专职角色定义标准输出契约，例如：

- `data_cleaner`: 数据问题摘要、修复动作、变更后的数据集名
- `statistician`: 方法选择、前提检验、主要数值结果
- `viz_designer`: 图表类型、映射字段、导出产物
- `writer`: 章节草稿、待补证据

**改造成本**：低

**预期收益**：显著降低多专家协作中的信息丢失；让融合器和前端能稳定展示阶段性成果。

#### 借鉴点 B：显式编排模板

**来源**：TradingAgents `tradingagents/graph/setup.py`、`tradingagents/graph/conditional_logic.py`

**核心思路**：

对高价值复合任务，用显式图而非自由 ReAct。节点、条件边和终止条件全都先定义，运行期只填充状态。

**在 scientific_nini 的应用场景**：

先从 2 到 3 个高频任务做模板：

- 差异分析工作流
- 回归分析工作流
- 论文初稿工作流

这些模板可复用现有 `TaskManager`、`Harness` 和 `WebSocket` 事件机制。

**改造成本**：中

**预期收益**：复杂任务成功率和可复现性提升，调试成本下降，用户对“系统下一步在做什么”更容易形成稳定预期。

#### 借鉴点 C：角色级经验记忆

**来源**：TradingAgents `tradingagents/agents/utils/memory.py`、`tradingagents/graph/reflection.py`

**核心思路**：

不是所有记忆都进入一个全局池，而是先按角色维护“这个角色以前在哪类情境下犯过什么错、学到了什么”。

**在 scientific_nini 的应用场景**：

在现有 LTM 之上增加 `role_namespace`，让统计、作图、写作、审稿等专家拥有独立经验库；完成任务后写入轻量反思。

**改造成本**：中

**预期收益**：子 Agent 输出风格更稳定；长期看能减少重复错误和不必要的提示词膨胀。

### 4.2 选择性借鉴（有价值，但需评估改造成本）

#### 借鉴点 D：阶段化多专家前端展示

**来源**：TradingAgents `cli/main.py`

**核心思路**：

把“谁在执行、哪些报告完成了、当前卡在哪一段”显式展示给用户。

**在 scientific_nini 的应用场景**：

给 Web 端 `AgentExecutionPanel` 增加阶段泳道、角色状态和报告槽位完成度，而不是仅展示事件流。

**改造成本**：中

**预期收益**：多智能体模式的可解释性更强，用户不会误以为系统“卡住”。

#### 借鉴点 E：外部数据源 adapter 分层

**来源**：TradingAgents `tradingagents/dataflows/interface.py`

**核心思路**：

将“工具语义”与“供应商实现”分开，工具永远叫同一个名字，底层 vendor 可切换。

**在 scientific_nini 的应用场景**：

未来若 Nini 要扩展学术检索、文献数据库、云存储或实验数据平台，这种 adapter 层会很有价值。

**改造成本**：中

**预期收益**：减少外部集成对上层 prompt / tool schema 的影响。

### 4.3 不建议照搬（原因分析）

| TradingAgents 的做法 | 不适用原因 | Scientific Nini 更合适的替代方案 |
|---------------------|-----------|----------------------------------|
| 固定金融角色图 | 场景差异太大，科研任务的角色组合比金融更异构 | 用“任务类型专职角色 + 动态编排模板”替代 |
| 单一全局 `AgentState` 承载全部阶段字段 | Nini 的数据集、产物、审批、文件编辑、图表导出复杂度更高 | 保留 `Session` 作为运行容器，补 typed substate |
| BM25-only 角色记忆 | 对科研任务的结构化上下文与多模态证据不够 | 保持 Nini 的 STM/LTM/hybrid retrieval，只增加 role namespace |
| 工具体系以静态 ToolNode 为中心 | Nini 已有更强的 Function + Markdown + guardrail 体系 | 保持 ToolRegistry，中间再加 workflow adapter |

---

## 五、优化迭代路线图

基于上面的借鉴点，建议按以下顺序推进：

### 迭代 R1：多专家输出契约化（工作量：M，建议优先级：P0）

**目标**：让 `dispatch_agents` 从“自由文本并行执行”升级为“结构化子结果 + 可稳定融合”的协作模式。

**核心改动**：

- [ ] 参考 TradingAgents `tradingagents/agents/utils/agent_states.py` 的状态槽位思路，为 Nini 专家角色定义标准输出 schema
- [ ] 改造 `src/nini/agent/spawner.py` 和 `src/nini/tools/dispatch_agents.py`，让子结果包含 `summary / evidence / artifacts / next_action`
- [ ] 改造前端 agent execution 面板，显示结构化阶段结果

**验收标准**：同一复合任务重复执行时，子 Agent 结果字段稳定，可直接被融合器和 UI 消费。

**风险**：需要控制 schema 复杂度，避免把子 Agent 再做成一层难以维护的微服务协议。

### 迭代 R2：高频能力模板化编排（工作量：M，建议优先级：P0）

**目标**：让高频复合任务从“纯 ReAct”变成“ReAct + 显式阶段模板”的混合模式。

**核心改动**：

- [ ] 参考 TradingAgents `tradingagents/graph/setup.py` 的显式节点/边模式，为 `difference_analysis`、`regression_analysis` 建立轻量 workflow 模板
- [ ] 在 `AgentRunner` 之前增加模板选择层，优先命中 capability-driven workflow
- [ ] 把阶段状态映射到现有 WebSocket 事件和 Harness trace

**验收标准**：差异分析和回归分析在回放中能看到固定阶段序列，且失败可定位到具体阶段。

**风险**：模板过多会与现有通用 Agent 分叉；首批应只做 2 到 3 个高频场景。

### 迭代 R3：角色级记忆与反思沉淀（工作量：M，建议优先级：P1）

**目标**：让 Specialist Agent 真正“学到自己的经验”，而不是只共享一个全局记忆池。

**核心改动**：

- [ ] 参考 TradingAgents `tradingagents/graph/reflection.py` 的 post-task reflection 思路，在 Nini 完成复合任务后写入角色经验
- [ ] 为现有 `LongTermMemoryEntry.metadata` 增加 `role_namespace`
- [ ] 在子 Agent 上下文构建时优先检索同角色经验，再回退全局 LTM

**验收标准**：同类任务多次执行后，统计专家/写作专家在方法选择和输出稳定性上出现可观改善。

**风险**：如果检索预算不受控，可能造成上下文重复注入和 token 浪费。

### 迭代 R4：统一主链路与 MCP 架构语义（工作量：M，建议优先级：P1）

**目标**：消除“主链路是 ReAct，MCP 才是 Intent/Capability/Skill Runtime”的语义分叉。

**核心改动**：

- [ ] 将 `src/nini/mcp/server.py` 已有的 `analyze_intent / execute_capability` 设计抽象为主链路可复用组件
- [ ] 让 WebSocket 主入口优先走 Capability 命中，再决定是否退回自由 ReAct
- [ ] 统一前端、MCP、CLI 的能力目录与执行语义

**验收标准**：同一条用户请求在 WebSocket 和 MCP 两个入口上得到一致的 capability 决策。

**风险**：需要审慎处理兼容性，避免破坏当前已稳定的聊天体验。

---

## 六、附录

### A. TradingAgents 关键文件索引

| 文件路径 | 核心作用 | 参考价值 |
|----------|----------|----------|
| `tradingagents/graph/trading_graph.py` | 顶层装配器，初始化 LLM、memory、tool nodes、graph | ⭐⭐⭐⭐⭐ |
| `tradingagents/graph/setup.py` | 显式 LangGraph 工作流定义 | ⭐⭐⭐⭐⭐ |
| `tradingagents/agents/utils/agent_states.py` | 全局共享状态与辩论子状态 | ⭐⭐⭐⭐⭐ |
| `tradingagents/graph/conditional_logic.py` | 阶段推进与回合控制 | ⭐⭐⭐⭐☆ |
| `tradingagents/dataflows/interface.py` | 数据源 vendor 路由与 fallback | ⭐⭐⭐⭐☆ |
| `tradingagents/agents/utils/memory.py` | 轻量角色记忆 | ⭐⭐⭐☆☆ |
| `tradingagents/graph/reflection.py` | 事后反思与经验沉淀 | ⭐⭐⭐⭐☆ |
| `cli/main.py` | 交互式 CLI 与执行进度可视化 | ⭐⭐⭐☆☆ |
| `tradingagents/default_config.py` | 模型、回合、数据 vendor 配置 | ⭐⭐⭐☆☆ |
| `tests/test_ticker_symbol_handling.py` | 当前可见测试覆盖样本 | ⭐⭐☆☆☆ |

### B. 参考资料

- TradingAgents GitHub: https://github.com/TauricResearch/TradingAgents
- TradingAgents 文档: https://www.zdoc.app/zh/TauricResearch/TradingAgents
- TradingAgents 研究页: https://tauric.ai/research/tradingagents/
- TradingAgents commit metadata API: https://api.github.com/repos/TauricResearch/TradingAgents/commits/main
- TradingAgents tree API: https://api.github.com/repos/TauricResearch/TradingAgents/git/trees/HEAD?recursive=1
- Scientific Nini GitHub: https://github.com/lewisoepwqi/scientific_nini
- Scientific Nini tree API: https://api.github.com/repos/lewisoepwqi/scientific_nini/git/trees/HEAD?recursive=1

补充说明：

- 已执行 WebSearch，但未检索到 TradingAgents 官方对 AutoGen / CrewAI 的直接对标文章，因此报告中的判断以官方 README、官方研究页、目录树和源码为主。
- TradingAgents 的“Communication Protocol”公开描述主要来自研究页；源码侧并不存在单独的 protocol schema 文件，实际落地方式是“共享状态 + 结构化报告字段 + 辩论文本历史”。
