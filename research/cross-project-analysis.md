# 跨项目学习分析报告

> 分析对象：deer-flow 2.0 (ByteDance) · OpenGenerativeUI (CopilotKit) · scientific_nini
> 报告日期：2026-03-24

---

## 执行摘要

本报告对三个 AI Agent 系统进行了深度横向对比。deer-flow 2.0 是目前工程成熟度最高的开源 Super Agent Harness，其 **中间件链（Middleware Chain）** 与 **子 Agent 并发执行** 体系是最值得借鉴的设计；OpenGenerativeUI 在 **Generative UI**（AI 直接输出可交互 HTML 组件渲染进 iframe）方向提供了极具启发性的前端 AI 协同范式；scientific_nini 在科研垂直领域深耕，拥有成熟的多模型路由、沙箱安全体系和领域工具集，但在 Agent 架构健壮性（循环检测、中间件、Guardrails）与 UI 表达力（Generative UI）上存在明显差距。可在保留现有领域优势的前提下，分三个阶段引入这两个项目的核心设计。

---

## 一、deer-flow 深度解析

### 1.1 架构设计亮点

deer-flow 2.0 是对 1.x Deep Research 框架的彻底重写，定位为 **Super Agent Harness**——将多个 sub-agent、memory、sandbox 与可扩展的 skills 组合起来，完成复杂任务。

**整体分层架构：**

```
app/gateway/         ← FastAPI 路由层（REST + WebSocket）
app/channels/        ← IM 渠道适配（Slack / Feishu / Telegram）
packages/harness/
  deerflow/
    agents/          ← lead_agent + middleware chain
    subagents/       ← 子 Agent 注册与执行引擎
    tools/           ← 内置工具（task_tool / clarification / sandbox 等）
    skills/          ← Markdown 文件形式的 Skill 定义
    sandbox/         ← 本地 + 远程双模沙箱
    memory/          ← 长期记忆（JSON 结构化存储 + LLM 更新）
    guardrails/      ← 工具调用安全防护
    mcp/             ← MCP 工具协议集成
    config/          ← 细粒度配置模块（独立文件）
```

**核心特点：**

1. **LangGraph + langchain.agents.create_agent** 作为 Agent Runtime，充分利用 LangGraph 的状态图调度能力
2. **独立的 packages/harness 内包**，与 app 层（gateway/channels）完全解耦，可独立被第三方使用
3. **细粒度配置模块化**：每个关注点（memory、sandbox、subagents、summarization 等）有独立配置类，便于单独调优

### 1.2 技术实现细节（代码级）

#### ⭐ 中间件链（Middleware Chain）

这是 deer-flow 最精髓的设计。Agent 执行过程中，各功能模块以**中间件**形式串联在 LangGraph runtime 上，每个中间件只关注单一职责：

```python
# 中间件装配顺序（顺序即优先级）
middlewares = build_lead_runtime_middlewares(lazy_init=True)   # 工具错误处理
+ SummarizationMiddleware(...)                                  # 上下文摘要压缩
+ TodoMiddleware(...)                                           # Plan Mode 任务列表
+ TitleMiddleware()                                             # 自动生成会话标题
+ MemoryMiddleware(agent_name=agent_name)                       # 异步记忆更新队列
+ ViewImageMiddleware()                                         # 多模态图片注入
+ DeferredToolFilterMiddleware()                                # 延迟工具过滤
+ SubagentLimitMiddleware(max_concurrent=N)                     # 并发子 Agent 限流
+ LoopDetectionMiddleware()                                     # 循环检测
+ ClarificationMiddleware()                                     # 用户澄清中断（必须最后）
```

每个中间件实现 `AgentMiddleware` 的 `after_model()` 和 `aafter_model()` 钩子，以**纯声明式**方式修改 Agent 状态，无侵入性：

```python
class LoopDetectionMiddleware(AgentMiddleware[AgentState]):
    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._apply(state, runtime)
```

#### ⭐ 循环检测（LoopDetectionMiddleware）

基于 **工具调用哈希 + 滑动窗口** 的循环检测：
- 对 tool_calls 做 `md5(sorted(name+args))`，构成 12 位 fingerprint
- 同一 fingerprint 出现 ≥ 3 次：注入 SystemMessage 警告
- 同一 fingerprint 出现 ≥ 5 次：**强制剥除 tool_calls**，迫使 LLM 产出最终文字答案
- LRU 缓存最近 100 个线程的历史，节省内存

```python
# 硬停止：直接篡改 AIMessage，去掉 tool_calls
stripped_msg = last_msg.model_copy(update={
    "tool_calls": [],
    "content": (last_msg.content or "") + f"\n\n{_HARD_STOP_MSG}",
})
```

#### ⭐ 子 Agent 并发执行引擎（SubagentExecutor）

- 双线程池：`_scheduler_pool`（3 workers 调度）+ `_execution_pool`（3 workers 执行）
- 支持同步 `execute()` 和异步 `execute_async()` 两种调用模式
- 异步模式通过全局 `_background_tasks: dict[str, SubagentResult]` 跟踪状态
- 子 Agent 直接继承父 Agent 的 `sandbox_state` 和 `thread_data`，共享文件系统上下文
- 通过 `config.model == "inherit"` 支持模型继承

#### ⭐ 延迟工具发现（DeferredToolRegistry / tool_search）

大量 MCP 工具不在初始 context 中展示，仅暴露工具名列表；agent 通过 `tool_search` 工具按需获取完整 schema，规避 context 膨胀：

```python
@tool
def tool_search(query: str) -> str:
    """支持三种查询形式：
      - "select:name1,name2"  精确匹配
      - "+keyword rest"       名称必须含 keyword
      - "regex query"         全文正则
    """
```

这个设计直接来源于 Claude Code 的工具发现机制（CLAUDE.md 中的 ToolSearch 描述与此完全相同）。

#### Guardrails 防护层

`GuardrailMiddleware` 在工具执行前调用 provider 链（可扩展）：

```python
class AllowlistProvider:
    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        if request.tool_name in self._denied:
            return GuardrailDecision(allow=False, ...)
```

### 1.3 可复用的设计模式

| 模式 | 文件路径 | 核心价值 |
|------|----------|----------|
| 中间件链装配 | `agents/lead_agent/agent.py` | 各功能模块零侵入、可插拔 |
| 循环检测中间件 | `agents/middlewares/loop_detection_middleware.py` | P0 安全防护，防止无限 tool_call |
| 澄清中断 | `agents/middlewares/clarification_middleware.py` | 主动向用户提问而非猜测 |
| 延迟工具注册 | `tools/builtins/tool_search.py` | 按需加载减少 token 消耗 |
| 子 Agent 背景执行 | `subagents/executor.py` | 真正的并发任务处理 |
| 上下文摘要压缩 | `SummarizationMiddleware` (langchain 内置) | 自动管理长对话 context |
| 结构化长期记忆 | `agents/memory/updater.py` | JSON + LLM 提取 + mtime 缓存 |

### 1.4 创意与差异化特性

- **Coding Plan 模式**：通过 `is_plan_mode` 开关和 `TodoMiddleware` 实现任务分解执行，TODO 列表实时同步到前端
- **Bootstrap Agent**：专用于创建自定义 Agent 的特殊引导模式，system prompt 精简，工具集极小
- **IM 渠道集成**：通过 `app/channels/` 支持 Slack/Feishu/Telegram 接入，与核心 harness 完全解耦
- **per-Agent 记忆**：每个自定义 Agent 拥有独立的记忆文件（`agent_name` 作为 key），不混入全局记忆
- **上传文件脱敏**：记忆更新时自动用正则去除文件上传相关句子，防止下次会话试图访问不存在的文件

---

## 二、OpenGenerativeUI 深度解析

### 2.1 架构设计亮点

OpenGenerativeUI 是 CopilotKit + LangGraph 的展示项目，核心命题是：**AI 不只产出文本，而是直接生成可交互的 UI 组件**（Generative UI）。

**整体架构极简：**
```
apps/
  agent/          ← LangGraph Python Agent（tools + skills + main.py）
  app/            ← Next.js 前端（CopilotKit hooks + 渲染组件）
  mcp/            ← 独立 MCP Server（技能文档 + HTML 组装器）
```

**关键设计决策：**
- Agent 只定义了 3 个工具（`query_data`, `todo_tools`, `generate_form`）
- 真正的复杂性在 system prompt 中注入的 skills 文档
- 前端不是"展示 AI 文本"，而是"渲染 AI 生成的 React 组件"

### 2.2 UI-AI 协同机制

#### ⭐ Generative UI 核心流程

```
Agent 调用 widgetRenderer(title, description, html)
    ↓
CopilotKit 前端捕获 tool_call
    ↓
WidgetRenderer 组件接收 html 参数
    ↓
assembleDocument(html) 注入主题 CSS + 桥接 JS
    ↓
iframe.srcdoc 命令式写入（绕过 React 重渲染）
    ↓
iframe 内 JS 通过 postMessage 上报高度
    ↓
宿主组件响应式调整 iframe 高度
```

#### ⭐ iframe 沙箱渲染技术

`WidgetRenderer` 组件的核心技巧是**命令式写入 iframe，不用 React 的 srcDoc prop**：

```typescript
// 关键：绕过 React 协调，只在 html 内容真正变化时重载 iframe
useEffect(() => {
    if (html === committedHtmlRef.current) return;
    committedHtmlRef.current = html;
    // 命令式写入，而非声明式 prop
    iframeRef.current!.srcdoc = assembleDocument(html);
}, [html]);
```

这样即使父组件因 CopilotKit 流式更新而频繁重渲染，iframe 内部的 JS 状态（Three.js 场景、动画帧等）也不会被重置。

#### CSP 安全策略

```html
<meta http-equiv="Content-Security-Policy" content="
    script-src 'unsafe-inline' 'unsafe-eval'
      https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com;
    connect-src 'self';
">
```

允许主流 CDN 引入库（Chart.js/Three.js/D3 等），拒绝其他外联。

#### ⭐ 双向通信桥接（Bridge JS）

注入到每个 iframe 的 Bridge JS 实现了宿主-沙箱双向通信：

```javascript
// iframe → 宿主：触发新提问
window.sendPrompt = function(text) {
    window.parent.postMessage({ type: 'send-prompt', text }, '*');
};

// iframe → 宿主：报告内容高度（自适应）
var ro = new ResizeObserver(reportHeight);
ro.observe(document.getElementById('content') || document.body);
```

#### ⭐ Design System 注入

每个 iframe 被注入完整的主题 CSS（支持 light/dark mode）、预制 SVG 颜色类（`.c-purple`, `.c-teal` 等）和表单样式，使 AI 生成的 HTML 开箱即用：

```css
:root {
  --color-background-primary: #ffffff;
  --color-text-primary: #1a1a1a;
  /* ... 完整 design token ... */
}
@media (prefers-color-scheme: dark) { /* ... */ }
```

### 2.3 可复用的设计模式

| 模式 | 文件路径 | 核心价值 |
|------|----------|----------|
| Generative UI（iframe 渲染） | `components/generative-ui/widget-renderer.tsx` | AI 直接生成可交互 UI |
| 命令式 iframe 写入 | `WidgetRenderer` useEffect | 防止流式更新中 iframe 状态重置 |
| Design System CSS 注入 | `THEME_CSS / SVG_CLASSES_CSS` | AI 生成 HTML 自动主题化 |
| Bridge JS 双向通信 | `BRIDGE_JS` | iframe 与宿主消息互通 |
| Skills 文件即 Prompt | `apps/agent/skills/*.txt` | 技能文档直接注入 system prompt |
| MCP 服务器化 Skills | `apps/mcp/src/` | 技能文档可通过 MCP 协议消费 |

### 2.4 创意与差异化特性

- **3-Layer Response Pattern（钩子 → 视觉 → 叙述）**：`master-agent-playbook.txt` 中定义了完整的"卓越回答"哲学，用 Decision Tree 指导 AI 何时用图、何时用文字
- **Progressive Reveal Animation**：CSS 动画使 iframe 内容元素逐个淡入，增强视觉感知
- **自适应高度 iframe**：ResizeObserver + postMessage 实时上报高度，完全自适应内容
- **A2UI（Agent to UI）工具注入**：`a2ui: { injectA2UITool: true }` 让 CopilotKit runtime 自动向 Agent 注入 UI 渲染工具
- **MCP Server 对外暴露 Skills**：任何 MCP 兼容的客户端（Claude Desktop、Cursor 等）都可访问同一套 Skills 文档

---

## 三、与 scientific_nini 的对比分析

### 3.1 能力差距矩阵

| 能力维度 | deer-flow | OpenGenerativeUI | scientific_nini | 差距等级 |
|---------|-----------|-----------------|-----------------|---------|
| Agent 循环安全（防死循环） | LoopDetectionMiddleware | N/A | 无专门机制 | **P0 缺失** |
| 中间件/插件化架构 | 10+ 中间件链 | CopilotKitMiddleware | 无（嵌入 runner.py） | 高 |
| 子 Agent 并发 | SubagentExecutor + 双线程池 | N/A | dispatch_agents（基础） | 中 |
| 延迟工具发现 | DeferredToolRegistry | N/A | 无 | 中 |
| Guardrails | AllowlistProvider + 扩展点 | N/A | 无 | 中 |
| 用户澄清类型化 | `clarification_type` 枚举（5种）+ `context` 字段 | N/A | `ask_user_question`（已有，但无类型区分） | **低**（增强而非新建） |
| 长期记忆 | 结构化 JSON + LLM 更新 + 上传脱敏 | N/A | compression + profile（有） | 低 |
| Generative UI | N/A | WidgetRenderer + iframe 沙箱 | Plotly 图表（固定） | **高差距** |
| Design System 注入 | N/A | 主题 CSS + SVG 类库 | 无 | 高 |
| 沙箱安全 | 本地 shell + 可选远程 | N/A | multiprocessing + AST 分析（强） | 反向优势 |
| 多模型路由 | config.yaml 配置 + 按 Agent 指定 | OpenAI only | 7+ 提供商 + 自动降级（强） | 反向优势 |
| 科研领域工具 | 无 | 无 | 30+ 专业工具（独有优势） | 反向优势 |
| MCP 集成 | 完整 MCP 客户端 + OAuth | 作为 MCP 服务器对外 | 有（基础） | 低 |
| 自动摘要压缩 | SummarizationMiddleware | N/A | compress_session_history_with_llm（有） | 低 |
| IM 渠道接入 | Slack/Feishu/Telegram | N/A | 无 | 低优先级 |

### 3.2 scientific_nini 的现有优势

1. **科研领域工具集**：30+ 专业工具（统计检验、回归、可视化、代码执行、报告生成），在同类系统中无对手
2. **多模型路由与故障转移**：支持 OpenAI / Anthropic / DeepSeek / Zhipu / DashScope / Moonshot / MiniMax / Ollama，7+ 提供商自动降级，远超 deer-flow 的配置文件方案
3. **三重沙箱安全**：AST 静态分析（`sandbox/policy.py`）+ 受限 builtins + multiprocessing spawn 进程隔离，安全性高于 deer-flow 的 shell 执行方案
4. **Research Profile 记忆体系**：`memory/research_profile.py` 维护用户科研背景画像，是领域特化的亮点
5. **会话持久化与工作区管理**：完整的文件系统工作区（datasets/artifacts/notes），对科研数据管理友好

### 3.3 可直接借鉴的设计（Quick Wins）

以下设计可在不重构主干的情况下快速引入：

**Quick Win 1：循环检测中间件**
- 来源：`deer-flow/agents/middlewares/loop_detection_middleware.py`
- 实现位置：`src/nini/agent/runner.py` 中 ReAct 循环的 tool_call 处理段
- 工作量：约 1-2 天，核心算法不到 100 行
- 价值：解决 P0 安全漏洞，防止无限循环消耗 token

**Quick Win 2：`ask_user_question` 类型化增强**
- 来源：`deer-flow/tools/builtins/clarification_tool.py` 的 `clarification_type` 设计
- 背景分析：两者**不是重复轮子**。deer-flow 的 `ask_clarification` 只覆盖"LLM 主动发起提问"这一场景；nini 的 `ask_user_question` 是一个伪工具（pseudo-tool，不注册到 ToolRegistry），同时承担 4 个不同触发场景：
  1. 意图预分析澄清（LLM 尚未参与，由意图系统自动触发）
  2. LLM 在 ReAct 循环中主动调用
  3. LLM 生成纯文本但未调用工具时的 confirmation_fallback
  4. 高风险操作前的人工确认
- 真正可借鉴的是 deer-flow 的**类型枚举**和 **`context` 字段**设计，将其融入现有 `ask_user_question` 协议：
  - 在问题对象中增加可选 `question_type` 字段（`missing_info` / `ambiguous_requirement` / `approach_choice` / `risk_confirmation` / `suggestion`）
  - 增加可选 `context` 字段（说明为何需要澄清）
- 实现位置：
  - `src/nini/models/event_schemas.py` — `ask_user_question` 事件 schema 加字段
  - `src/nini/agent/prompts/builder.py` — system prompt 中补充 `question_type` 使用说明
  - `web/src/` 前端根据 `question_type` 渲染差异化样式（`risk_confirmation` → 红色警告框）
- 工作量：约 1-2 天（纯增量，无破坏性改动）
- 价值：前端可差异化渲染澄清类型；LLM 调用更精准；零迁移成本

**Quick Win 3：Guardrails 层**
- 来源：`deer-flow/guardrails/`
- 实现位置：在 `tools/registry.py` 的工具调用路径中插入
- 工作量：约 1-2 天
- 价值：工具调用安全防护，支持 allowlist/denylist

**Quick Win 4：Generative UI iframe 组件**
- 来源：`OpenGenerativeUI/apps/app/src/components/generative-ui/widget-renderer.tsx`
- 实现位置：`web/src/components/` 中新增 `WidgetRenderer` 组件
- 工作量：约 3-5 天（含设计系统 CSS 迁移）
- 价值：解锁 AI 直接生成可交互可视化的能力

**Quick Win 5：Design System 注入到沙箱输出**
- 来源：`OpenGenerativeUI` 的 theme CSS + bridge JS 方案
- 实现位置：科研报告/HTML 导出功能
- 工作量：约 2 天
- 价值：AI 生成 HTML 报告自动适配深色/浅色模式

### 3.4 需要重新设计的部分

**1. runner.py 中间件化重构**

当前 `agent/runner.py` 是一个大型单文件 ReAct 循环，各功能（循环检测、记忆更新、plan 解析）混在循环体内。deer-flow 的中间件链模式更优雅，但迁移成本较高（需要引入 LangGraph 或自研类似的 hooks 机制）。

**2. 子 Agent 调度机制升级**

当前 `dispatch_agents` 工具实现基础，缺乏：
- 超时控制
- 并发限流（SubagentLimitMiddleware 思路）
- 结果实时流式推送给前端
- 子 Agent 状态独立追踪

**3. 延迟工具注册**

随着工具数量增长（目前 30+），全量工具 schema 注入 context 会消耗大量 token。需要参考 deer-flow 的 `DeferredToolRegistry` 实现按需工具发现。

---

## 四、优化迭代规划

### 4.1 规划原则与优先级框架

- **P0（稳定性）**：修复可能导致系统崩溃或无限消耗的问题
- **P1（体验）**：用户可直接感知的能力提升
- **P2（架构）**：内部架构优化，减少技术债
- **领域优先**：所有引入的外部设计必须服务于科研场景，不引入无关通用功能

### 4.2 路线图概览

```
Phase 1（2-4周）：基础增强
  ├── P0: 循环检测保护
  ├── P1: 用户澄清工具
  └── P1: Guardrails 层

Phase 2（4-8周）：核心能力升级
  ├── P1: Generative UI（科研图表 + 交互可视化）
  ├── P1: 子 Agent 并发升级
  └── P2: 延迟工具注册

Phase 3（持续迭代）：差异化与创新
  ├── 科研专属 Generative UI 组件库
  ├── 中间件链架构重构
  └── 科研多 Agent 协作流程
```

---

## 五、详细实施方案

### Phase 1：基础增强（建议 2-4 周）

**目标**：解决 P0 稳定性问题，补充常见安全机制

#### 任务 1.1：实现循环检测保护

**参考来源**：`/tmp/deer-flow/backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py`

**实施位置**：`src/nini/agent/runner.py` 中 ReAct 循环的 tool_call 处理逻辑

**实现方案**：
```python
# 在 src/nini/agent/loop_guard.py 中新建
class LoopGuard:
    """基于工具调用哈希的循环检测。"""
    def __init__(self, warn_threshold=3, hard_limit=5, window_size=20):
        self._history: dict[str, list[str]] = {}

    def check(self, tool_calls: list[dict], session_id: str) -> LoopGuardDecision:
        call_hash = _hash_tool_calls(tool_calls)
        # 返回 NORMAL / WARN / FORCE_STOP 三种决策
        ...
```

在 `runner.py` 的 ReAct 主循环中：
```python
# 每次收到 tool_calls 后调用
decision = self._loop_guard.check(tool_calls, session.id)
if decision == LoopGuardDecision.FORCE_STOP:
    # 清空 tool_calls，触发最终回答
    ...
elif decision == LoopGuardDecision.WARN:
    # 在下一轮消息中注入警告
    ...
```

**验收标准**：
- `pytest tests/test_loop_guard.py` 全部通过
- 手动触发重复工具调用，5 次后自动停止

#### 任务 1.2：为 `ask_user_question` 增加类型化字段

**背景**：nini 已有完整的 `ask_user_question` 机制（4 个触发场景），deer-flow 的 `ask_clarification` 仅对应其中一个场景（LLM 主动提问）。两者不应合并，但 deer-flow 的 `clarification_type` 枚举设计值得引入。

**参考来源**：`deer-flow/tools/builtins/clarification_tool.py` 的类型枚举定义

**实施位置（纯增量，无破坏性改动）**：

1. `src/nini/models/event_schemas.py` — 在问题对象 schema 中增加可选字段：
```python
# 在 ask_user_question 事件的单个问题对象中新增
"question_type": {
    "type": "string",
    "enum": ["missing_info", "ambiguous_requirement", "approach_choice", "risk_confirmation", "suggestion"],
    "description": "澄清类型，指导前端渲染差异化 UI"
},
"context": {
    "type": "string",
    "description": "可选背景说明，帮助用户理解为何需要回答此问题"
}
```

2. `src/nini/agent/prompts/builder.py` — 在 system prompt 的 `ask_user_question` 使用说明中补充类型描述：
```
- missing_info：缺少必要信息（文件路径、参数等）
- ambiguous_requirement：需求存在多种合理解释
- approach_choice：存在多种有效实现方案需用户选择
- risk_confirmation：即将执行破坏性/不可逆操作
- suggestion：有推荐方案但需用户确认
```

3. `web/src/` 前端 `AskUserQuestionCard` 组件 — 根据 `question_type` 渲染差异化样式：
   - `risk_confirmation` → 红色边框 + 警告图标
   - `approach_choice` / `ambiguous_requirement` → 蓝色选项按钮组
   - `missing_info` / `suggestion` → 默认样式

**验收标准**：
- 现有 4 种触发场景均不受影响（字段为可选）
- LLM 在 system prompt 引导下能正确传入 `question_type`
- 前端 `risk_confirmation` 类型问题以红色警告样式显示

#### 任务 1.3：实现 Guardrails 层

**参考来源**：`deer-flow/packages/harness/deerflow/guardrails/`

**实施位置**：`src/nini/tools/registry.py` 的 `invoke()` 方法中插入

```python
# 在 tools/guardrails.py 中新建
class ToolGuardrail(ABC):
    @abstractmethod
    def evaluate(self, tool_name: str, kwargs: dict) -> GuardrailDecision: ...

class DangerousOperationGuardrail(ToolGuardrail):
    """防止在科研数据上做破坏性操作（如覆盖原始数据集）。"""
    DANGEROUS_PATTERNS = {...}
    def evaluate(self, tool_name, kwargs):
        ...
```

**验收标准**：
- 危险操作被拦截并返回用户友好的错误信息
- `pytest tests/test_guardrails.py` 通过

---

### Phase 2：核心能力升级（建议 4-8 周）

**目标**：大幅提升用户体验，解锁 Generative UI 能力

#### 任务 2.1：实现 Generative UI 组件

**参考来源**：`/tmp/open-generative-ui/apps/app/src/components/generative-ui/widget-renderer.tsx`

**实施位置**：`web/src/components/WidgetRenderer.tsx`

**核心实现要点**：

1. **命令式 iframe 写入**（防止 React 重渲染重置 iframe）：
```typescript
useEffect(() => {
    if (html === committedHtmlRef.current) return;
    committedHtmlRef.current = html;
    // 命令式：通过 ref 写入，而非 React prop
    iframeRef.current!.srcdoc = assembleDocument(html);
}, [html]);
```

2. **科研主题 Design System**：在 OpenGenerativeUI 的主题 CSS 基础上，增加科研场景专用变量：
```css
:root {
  --color-significance: #d62728;    /* p < 0.05 高亮 */
  --color-not-significant: #aec7e8; /* 不显著 */
  --color-positive-effect: #2ca02c; /* 正效应 */
  --color-negative-effect: #d62728; /* 负效应 */
}
```

3. **Bridge JS 扩展**：支持从 iframe 内触发数据加载、更新图表参数：
```javascript
window.requestData = function(datasetId, columns) {
    window.parent.postMessage({ type: 'request-data', datasetId, columns }, '*');
};
```

4. **后端新增 generate_widget 工具**：
```python
class GenerateWidgetTool(Tool):
    name = "generate_widget"
    description = "生成可交互的 HTML 可视化组件，在聊天界面内嵌展示。"
    parameters = {
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "html": {"type": "string", "description": "自包含 HTML 片段，支持内联 CSS/JS"}
        },
        "required": ["title", "html"]
    }
```

**验收标准**：
- Agent 可生成展示统计结果的交互式 HTML 组件
- iframe 支持 light/dark mode 自动切换
- 科研专属颜色系统生效

#### 任务 2.2：子 Agent 并发升级

**参考来源**：`deer-flow/subagents/executor.py`

**实施位置**：`src/nini/tools/dispatch_agents.py` + 新建 `src/nini/agent/subagent_executor.py`

**改进点**：
- 引入 `ThreadPoolExecutor` 双池模式（调度 + 执行分离）
- 添加超时控制（`config.timeout_seconds`）
- 子 Agent 状态从 `pending → running → completed/failed/timed_out` 全程追踪
- 通过 WebSocket 推送子 Agent 进度事件到前端

**验收标准**：
- 多子 Agent 并发执行不阻塞主 Agent
- 超时后优雅降级，返回已收集的结果

#### 任务 2.3：延迟工具注册

**参考来源**：`deer-flow/tools/builtins/tool_search.py`

**实施位置**：`src/nini/tools/registry.py`

**实现方案**：
- 将非核心工具（如统计类、R 代码等）标记为 `expose_to_llm = False`（`Tool.expose_to_llm` 属性已存在）
- 新建 `SearchToolsTool` 提供工具搜索能力
- `ToolRegistry` 增加 `get_deferred_tools()` 方法返回未暴露工具的名称+描述

**验收标准**：
- LLM 收到的工具列表 token 数量减少 > 30%
- Agent 通过 `search_tools` 仍可发现并调用所有工具

---

### Phase 3：差异化与创新（建议持续迭代）

**目标**：构建 scientific_nini 的独特竞争力

#### 探索方向 1：科研专属 Generative UI 组件库

基于 Phase 2 的 `WidgetRenderer`，为常见科研场景预制组件：
- 统计结果展示卡（p 值高亮、效应量可视化）
- 相关矩阵热图（可点击查看单变量分布）
- 回归系数瀑布图（交互式）
- 数据质量报告（可折叠分组）
- 多组比较图（带置信区间的动态可视化）

**参考 OpenGenerativeUI 的 Skills 体系**：将这些组件的"如何生成优质 HTML"写成 Skill 文档注入 system prompt，让 LLM 学会生成高质量的科研可视化。

#### 探索方向 2：中间件链架构重构

将 `runner.py` 中的内联逻辑提取为可插拔中间件：
- `LoopGuardMiddleware`
- `ContextCompressionMiddleware`
- `ResearchProfileMiddleware`（注入用户科研背景）
- `ArtifactIndexingMiddleware`（自动索引生成的产物）

这需要设计一套简单的 `Middleware` 协议，不必引入 LangGraph，用责任链模式即可。

#### 探索方向 3：科研多 Agent 协作

借鉴 deer-flow 的 sub-agents 体系，设计科研专属的多 Agent 协作流程：
- **数据清洗 Agent**：专职数据预处理
- **统计分析 Agent**：执行统计检验
- **可视化 Agent**：生成图表和 HTML 组件
- **报告撰写 Agent**：整合结果生成研究报告

主 Agent 作为 Orchestrator 调度各专职 Agent，类似 deer-flow 的 lead_agent + subagents 模型。

#### 风险与权衡

| 风险 | 说明 | 缓解方案 |
|------|------|----------|
| Generative UI 安全性 | AI 生成 HTML 可能包含恶意脚本 | CSP 严格白名单 + 仅允许特定 CDN，通过 iframe sandbox 属性隔离 |
| iframe 性能 | 大量 iframe 导致内存占用 | 懒加载 + 超出视口时卸载 |
| 中间件链复杂度 | 调试困难 | 每个中间件有独立单测 + 结构化日志 |
| 子 Agent token 消耗 | 并发 Agent 倍增 LLM 调用 | 限制并发数 + 快速失败策略 |

---

## 六、关键技术决策建议

### 决策 1：是否引入 LangGraph？

**结论：短期不引入，中期可选。**

deer-flow 深度依赖 LangGraph，获得了状态图调度、检查点持久化等能力，但也带来了依赖复杂度。scientific_nini 的 ReAct 循环已经相当成熟，短期内在 runner.py 中直接实现循环检测、澄清中断等机制更务实。中期如果需要真正的多 Agent 状态图调度，再评估 LangGraph 引入成本。

### 决策 2：Generative UI 使用 iframe 还是其他方案？

**结论：优先使用 iframe 沙箱方案。**

OpenGenerativeUI 的 iframe 方案比直接内联 HTML（需要完全信任内容）更安全，且不受宿主 React 版本约束。AI 生成 HTML 的内容是不可信的，必须隔离。`sandbox="allow-scripts"` + CSP 白名单是正确的安全边界。所有数据通过 `postMessage` 通信，避免跨域问题。

### 决策 3：工具数量管理策略？

**结论：短期保持全量工具暴露，引入 `expose_to_llm` 分层。**

Tool 基类已有 `expose_to_llm` 属性，可以立即利用：将使用频率低的工具（如 `r_code_exec`、`organize_workspace`）设为 `expose_to_llm = False`，通过 `search_tools` 工具按需激活。这比全量延迟注册风险低，可逐步推进。

### 决策 4：长期记忆架构是否需要对齐 deer-flow？

**结论：当前方案已足够，关注上传文件脱敏问题。**

scientific_nini 的记忆体系（`compression.py` + `research_profile.py`）已经比 deer-flow 的 JSON 结构更领域化。但 deer-flow 中**上传文件提及自动脱敏**的处理（`_strip_upload_mentions_from_memory`）是值得立即借鉴的：防止用户下次会话时 Agent 找不到之前上传的临时文件。

### 决策 5：Guardrails 是否引入外部评估模型？

**结论：先实现规则型 Guardrails，不引入额外 LLM 调用。**

deer-flow 的 `AllowlistProvider` 是纯规则型的，无需 LLM。对 scientific_nini 而言，科研数据安全的核心是：防止覆写原始数据、防止访问系统目录、防止 R 代码执行恶意命令。这些都可以用规则型 Guardrails 实现，无需引入成本高昂的 LLM 评估。

---

## 附录：参考代码片段

### A1. deer-flow 循环检测核心算法（最值得直接移植）

```python
# 来源: deer-flow/agents/middlewares/loop_detection_middleware.py
def _hash_tool_calls(tool_calls: list[dict]) -> str:
    """工具调用的顺序无关哈希（同一组调用的不同排列产生相同哈希）。"""
    normalized = [
        {"name": tc.get("name", ""), "args": tc.get("args", {})}
        for tc in tool_calls
    ]
    normalized.sort(
        key=lambda tc: (tc["name"], json.dumps(tc["args"], sort_keys=True, default=str))
    )
    blob = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]

# 硬停止：去掉 tool_calls 迫使 LLM 产出文字答案
stripped_msg = last_msg.model_copy(update={
    "tool_calls": [],
    "content": (last_msg.content or "") + f"\n\n{_HARD_STOP_MSG}",
})
```

**借鉴价值**：直接解决 scientific_nini 的 P0 稳定性问题，算法自包含，无外部依赖。

---

### A2. OpenGenerativeUI iframe 命令式写入（防止 React 重渲染破坏 iframe 状态）

```typescript
// 来源: OpenGenerativeUI/apps/app/src/components/generative-ui/widget-renderer.tsx
const committedHtmlRef = useRef("");

useEffect(() => {
    if (!html || !iframeRef.current) return;
    if (html === committedHtmlRef.current) return;  // 只在内容真正变化时重载
    committedHtmlRef.current = html;
    // 命令式写入 srcdoc，绕过 React 属性协调
    iframeRef.current.srcdoc = assembleDocument(html);
    setLoaded(false);
    setHeight(0);
}, [html]);
```

**借鉴价值**：CopilotKit 流式更新会高频触发 React 重渲染，若通过 React prop 设置 iframe src，每次 re-render 都会重新加载 iframe，导致 Three.js 场景/动画被重置。命令式写入 + ref 追踪是解决此类问题的正确模式。

---

### A3. deer-flow 上传文件脱敏（防止记忆污染）

```python
# 来源: deer-flow/agents/memory/updater.py
_UPLOAD_SENTENCE_RE = re.compile(
    r"[^.!?]*\b(?:upload(?:ed|ing)?(?:\s+\w+){0,3}\s+(?:file|files?))[^.!?]*[.!?]?\s*",
    re.IGNORECASE,
)

def _strip_upload_mentions_from_memory(memory_data):
    """上传文件是会话级临时资产，不应出现在跨会话长期记忆中。"""
    for section in ("user", "history"):
        for _key, val in memory_data.get(section, {}).items():
            if isinstance(val, dict) and "summary" in val:
                val["summary"] = _UPLOAD_SENTENCE_RE.sub("", val["summary"]).strip()
    memory_data["facts"] = [
        f for f in memory_data.get("facts", [])
        if not _UPLOAD_SENTENCE_RE.search(f.get("content", ""))
    ]
    return memory_data
```

**借鉴价值**：scientific_nini 的记忆体系同样面临此问题——用户上传的数据集路径被记入长期记忆，下次会话时 Agent 尝试访问已不存在的文件。此正则过滤方案可直接移植到 `src/nini/memory/compression.py`。

---

### A4. OpenGenerativeUI 科研 Design System 扩展方案

```css
/* 科研专属 Design Token，补充到基础主题之上 */
:root {
  /* 统计显著性颜色 */
  --color-significant: #d62728;       /* p < 0.05 */
  --color-marginal: #ff7f0e;          /* 0.05 <= p < 0.10 */
  --color-not-significant: #aec7e8;   /* p >= 0.10 */

  /* 效应方向 */
  --color-positive-effect: #2ca02c;
  --color-negative-effect: #d62728;
  --color-neutral: #7f7f7f;

  /* 数据类型 */
  --color-continuous: #1f77b4;        /* 连续变量 */
  --color-categorical: #ff7f0e;       /* 分类变量 */
}

/* 统计结果徽章 */
.stat-sig-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}
.stat-sig-badge.significant { background: var(--color-significant); color: white; }
.stat-sig-badge.not-significant { background: var(--color-not-significant); color: #333; }
```

**借鉴价值**：将 OpenGenerativeUI 的通用 Design System 扩展为科研专属主题，使 Agent 生成的 HTML 可视化自动符合学术规范（如 APA/AMA 颜色惯例）。

---

### A5. deer-flow 延迟工具发现（减少 Context Token）

```python
# 来源: deer-flow/tools/builtins/tool_search.py
@tool
def tool_search(query: str) -> str:
    """按需获取工具完整 Schema，三种查询形式：
      - "select:stat_test,r_code_exec" -- 精确按名获取
      - "+stat regression"              -- 名称含 stat，按 regression 排序
      - "time series analysis"          -- 全文正则搜索
    """
    registry = get_deferred_registry()
    matched_tools = registry.search(query)
    tool_defs = [convert_to_openai_function(t) for t in matched_tools[:5]]
    return json.dumps(tool_defs, indent=2, ensure_ascii=False)
```

**借鉴价值**：scientific_nini 工具数量已达 30+，全量 schema 注入约消耗 3000-5000 token/次。延迟工具注册可使 context 减少 30-40%，对长对话尤为重要。`Tool.expose_to_llm` 属性已存在，可直接作为"哪些工具进延迟注册"的分类依据。

---

*报告生成时间：2026-03-24*
*参考代码版本：deer-flow@main (depth=1), OpenGenerativeUI@main (depth=1)*
