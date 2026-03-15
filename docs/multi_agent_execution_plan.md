# Scientific Nini 多Agent架构可执行规划

> 版本：1.1（审查修订）
> 日期：2026-03-15
> 依据：multi_agent_architecture_plan.md (v1.0) + multi_agent_architecture_plan_v2.md (v2.1)
> 修订说明：修复工具名幻觉、ModelResolver接口错误、前端store架构偏差及7项中等/轻微问题

---

## 一、代码现状基线（已实现，勿重复建设）

### 1.1 已实现的基础设施

| 组件 | 文件 | 说明 |
|------|------|------|
| ReAct 主循环 | `src/nini/agent/runner.py` | 单 Agent 思考-行动循环，完整实现 |
| 会话管理 | `src/nini/agent/session.py` | `Session` 含 `artifacts/datasets/documents`，`SessionManager` 全局单例 |
| 多模型路由 | `src/nini/agent/model_resolver.py` | `ModelResolver` 对外暴露 `chat(messages, tools, *, purpose, ...)` 异步生成器接口 |
| 上下文构建 | `src/nini/agent/components/context_builder.py` | `ContextBuilder` 组装 system prompt，知识库检索是其内部逻辑 |
| 推理追踪 | `src/nini/agent/components/reasoning_tracker.py` | `ReasoningChainTracker` |
| 任务规划 | `src/nini/agent/planner.py` + `task_manager.py` | 结构化任务列表，支持中断恢复 |
| 工具注册 | `src/nini/tools/registry.py` | `ToolRegistry`，LLM 可调用工具见下表 |
| WebSocket 事件流 | `src/nini/api/websocket.py` | 现有事件类型见 `agent/events.py:EventType` |
| 沙箱执行 | `src/nini/sandbox/` | AST 静态分析 + 受限 builtins + `multiprocessing` 进程隔离 |
| 知识库检索 | `src/nini/knowledge/` + `src/nini/memory/` | 层次化 RAG，作为 `ContextBuilder` 内部逻辑，**不**作为 LLM 可调用工具暴露 |
| 前端状态管理 | `web/src/store/` | 已按 slices 模式重构，入口 `store/index.ts`，类型 `store/types.ts`，事件处理 `store/event-handler.ts` + `event-handler-extended.ts` |

### 1.2 LLM 可调用工具（实际注册名，以下为完整白名单）

```
# 核心基础工具（LLM_EXPOSED_BASE_TOOL_NAMES）
task_state          dataset_catalog     dataset_transform
stat_test           stat_model          stat_interpret
chart_session       report_session      workspace_session
code_session        analysis_memory

# 其他已注册工具
task_write          load_dataset        data_summary
t_test              mann_whitney        anova             kruskal_wallis
run_code            run_r_code（可选）  fetch_url
export_chart        export_document     generate_report
export_report       organize_workspace  edit_file
analysis_memory     update_profile_notes
# 复合模板工具
complete_comparison  complete_anova  correlation_analysis  regression_analysis
```

> **注意**：`knowledge_search`、`preview_data`、`clean_data`、`data_quality`、`create_chart`、`image_analysis` 均**不存在**于注册表，文献中如有引用须替换为上表中的实际工具名。

### 1.3 ModelResolver 对外接口

```python
# 正确调用方式（异步生成器）
async for chunk in model_resolver.chat(
    messages=messages,
    tools=tool_defs,
    purpose="analysis",   # analysis / coding / vision / planning / default
    temperature=0.7,
    max_tokens=4000,
):
    ...

# 支持的 purpose 键
# analysis / coding / vision / embedding / planning / verification / default
```

> **不存在** `get_client_for_purpose()` 方法。`SubAgentSpawner` 必须通过 `model_resolver.chat(purpose=...)` 调用，不能先取客户端再调用。

### 1.4 尚未实现（本规划要建设的）

- `AgentDefinition`：Agent 声明数据类
- `AgentRegistry`：Agent 注册中心
- `SubSession`：子 Agent 独立上下文（需继承 `Session` 并覆盖 `__post_init__`）
- `SubAgentSpawner`：子 Agent 动态派生器
- `ToolRegistry.create_subset()`：受限工具注册表构造方法（需新增）
- `TaskRouter`：任务智能路由
- `ResultFusionEngine`：结果聚合引擎
- `HypothesisContext`：假设驱动范式上下文（Phase 3）
- 前端 agent slice 及相关组件

---

## 二、整体架构目标

```
用户消息
  ↓
WebSocket /ws
  ↓
AgentRunner（已有，增加 Orchestrator 模式入口）
  ↓ 意图分解
TaskRouter（新建）── 规则路由（<1ms）
  │                └── LLM路由（purpose="planning"，~500ms）
  ↓ 路由决策
SubAgentSpawner（新建）
  ├── SubAgent: data_cleaner    ──┐
  ├── SubAgent: statistician    ──┤ 并行执行（最多 4 个）
  └── SubAgent: viz_designer    ──┘
  ↓ 结果收集
ResultFusionEngine（新建）
  ↓
Orchestrator 汇总输出
  ↓
WebSocket 事件流 → 前端
```

### 范式说明

| 范式 | 适用场景 | Phase |
|------|----------|-------|
| **ReAct**（默认） | 工具密集型：数据清洗、代码执行、图表生成 | 现有 + Phase 1 扩展 |
| **Hypothesis-Driven**（显式启用） | 推理密集型：文献综述、实验设计、结论验证 | Phase 3 引入 |

---

## 三、Phase 1：多Agent基础设施（预计 3-4 周）

**目标**：建立 Agent 注册、上下文隔离、动态派生三件套。

> 工作量说明：SubSession 接口适配是本阶段技术难度最高的部分（详见 3.2 节），2-3 周估算过于乐观，修正为 3-4 周。

### 3.1 后端 - AgentDefinition + AgentRegistry

**新建文件**：`src/nini/agent/registry.py`

```python
@dataclass
class AgentDefinition:
    agent_id: str            # 唯一标识，如 "data_cleaner"
    name: str                # 显示名称，如 "数据清洗专家"
    description: str         # 能力描述，用于路由匹配
    system_prompt: str       # 系统提示词
    purpose: str             # 用途路由：analysis / planning / default
    allowed_tools: list[str] # 只能包含 1.2 节白名单中的工具名
    max_tokens: int = 8000
    timeout_seconds: int = 300
    paradigm: str = "react"  # "react" 或 "hypothesis_driven"（Phase 3 启用）

class AgentRegistry:
    # 加载内置 Agent 定义（见 3.5 节）
    # 从 src/nini/agent/prompts/agents/*.yaml 加载自定义 Agent
    # 方法：register / get / list_agents / match_for_task
```

**关键约束**：
- `AgentRegistry` 加载自定义配置的路径是 `src/nini/agent/prompts/agents/`，与 Claude Code 工具链的 `.claude/agents/` **完全无关**
- `paradigm` 字段默认 `"react"`，Phase 3 前不生效

---

### 3.2 后端 - SubSession

**新建文件**：`src/nini/agent/sub_session.py`

**设计要点**：`AgentRunner` 对 `Session` 有深度依赖（持久化方法、`conversation_memory`、`knowledge_memory`、`task_manager`、`event_callback` 等十余个字段），duck typing 实现代价极高。正确方案是**继承 `Session` 并覆盖 `__post_init__`** 跳过磁盘初始化。

```python
@dataclass
class SubSession(Session):
    """子 Agent 独立会话上下文，继承 Session 但跳过磁盘持久化。

    使用场景：SubAgentSpawner 为每个子 Agent 创建独立的 SubSession，
    执行完毕后通过 SubAgentResult 将产物回写到父会话。
    """
    parent_session_id: str = ""  # 父会话 ID，用于回写产物

    def __post_init__(self) -> None:
        # 覆盖父类：不初始化 ConversationMemory（避免写磁盘）
        # 不初始化 KnowledgeMemory、TaskManager
        # 保留 datasets / artifacts / documents 字段供 AgentRunner 使用
        from nini.agent.task_manager import TaskManager
        self.task_manager = TaskManager()
        # conversation_memory 使用内存版（不落盘）
        from nini.memory.conversation import InMemoryConversationMemory
        self.conversation_memory = InMemoryConversationMemory()
        self.knowledge_memory = None  # 子 Agent 不独立维护知识库
```

**任务分解**（单独列出，不包含在 spawner 任务中）：
1. 实现 `InMemoryConversationMemory`（仅在内存操作，不落盘）或确认现有 `ConversationMemory` 支持内存模式
2. 实现 `SubSession.__post_init__` 覆盖
3. 补全 `AgentRunner` 要求但 `SubSession` 未覆盖的所有方法/字段（通过实际运行报错定位）

**字段说明**：
- `datasets`：只读共享，从父会话 `session.datasets` 浅拷贝引用
- `documents`：**需要包含**，文献类 Agent（`literature_search`/`literature_reading`）的核心产物是文档，需通过 `SubAgentResult.documents` 回写到父会话 `session.documents`
- `artifacts`：子 Agent 产物，执行完毕后回写到父会话 `session.artifacts`
- `messages`：独立，不污染父会话历史

---

### 3.3 后端 - ToolRegistry.create_subset()

**修改文件**：`src/nini/tools/registry.py`（`ToolRegistry` 类增加方法）

```python
def create_subset(self, allowed_tool_names: list[str]) -> "ToolRegistry":
    """创建受限工具注册表，仅包含 allowed_tool_names 中指定的工具。

    用于 SubAgentSpawner 为子 Agent 创建隔离的工具视图。
    allowed_tool_names 必须是 1.2 节白名单的子集，传入不存在的名称会记录警告。
    """
    subset = ToolRegistry()
    for name in allowed_tool_names:
        skill = self.get(name)
        if skill:
            subset.register(skill)
        else:
            logger.warning("create_subset: 工具 %r 不存在于注册表，已跳过", name)
    return subset
```

> 此方法是 SubAgentSpawner 的前置依赖，Phase 1 必须先实现。

---

### 3.4 后端 - SubAgentSpawner

**新建文件**：`src/nini/agent/spawner.py`

核心调用方式（修正 ModelResolver 接口）：

```python
class SubAgentSpawner:
    def __init__(
        self,
        registry: AgentRegistry,
        tool_registry: ToolRegistry,   # 全量工具注册表（用于 create_subset）
    ):
        self.registry = registry
        self.tool_registry = tool_registry

    async def _execute_agent(
        self,
        agent_def: AgentDefinition,
        task: str,
        sub_session: SubSession,
    ) -> SubAgentResult:
        # 构建受限工具注册表
        restricted_registry = self.tool_registry.create_subset(agent_def.allowed_tools)

        # 构建消息
        messages = [{"role": "user", "content": task}]

        # 通过 model_resolver.chat(purpose=...) 调用 LLM（不使用 get_client_for_purpose）
        # AgentRunner 内部已处理此调用，只需传入 purpose
        runner = AgentRunner(
            tool_registry=restricted_registry,
            session=sub_session,
            purpose=agent_def.purpose,
        )
        return await runner.run(messages)

    async def spawn(self, agent_id, task, session, timeout_seconds=300) -> SubAgentResult: ...
    async def spawn_with_retry(self, ..., max_retries=3) -> SubAgentResult: ...
    async def spawn_batch(self, tasks, session, max_concurrency=4) -> list[SubAgentResult]: ...
```

**失败策略**：
- 子 Agent 失败 → `SubAgentResult(success=False, summary="...")`，由 Orchestrator 决定降级处理
- 超时 → `asyncio.wait_for` + `TimeoutError` 捕获，同上

---

### 3.5 后端 - WebSocket 新增事件类型

**修改文件**：`src/nini/agent/events.py`

在 `EventType(str, Enum)` 中追加（保持 `UPPER = "lower_snake"` 命名风格）：

```python
# Phase 1 新增：多 Agent 协作事件
AGENT_START    = "agent_start"      # 子 Agent 开始执行
AGENT_PROGRESS = "agent_progress"   # 子 Agent 进度更新
AGENT_COMPLETE = "agent_complete"   # 子 Agent 完成（含摘要结果）
AGENT_ERROR    = "agent_error"      # 子 Agent 失败
WORKFLOW_STATUS = "workflow_status" # 整体工作流状态
```

事件 payload 结构：
```json
{
  "event_type": "agent_start",
  "agent_id": "data_cleaner",
  "agent_name": "数据清洗专家",
  "task": "清洗上传的 CSV 数据，处理缺失值"
}
```

---

### 3.6 内置 Agent 定义（9 个 Specialist）

**新建目录**：`src/nini/agent/prompts/agents/`（每个 Agent 一个 `.yaml` 配置文件）

| AgentID | 名称 | purpose | allowed_tools（均为注册表实际存在的工具） |
|---------|------|---------|----------------------------------------|
| `literature_search` | 文献检索专家 | `analysis` | `fetch_url`, `task_write`, `analysis_memory` |
| `literature_reading` | 文献精读专家 | `analysis` | `fetch_url`, `task_write`, `analysis_memory` |
| `data_cleaner` | 数据清洗专家 | `analysis` | `load_dataset`, `dataset_catalog`, `dataset_transform`, `task_write` |
| `statistician` | 统计分析专家 | `analysis` | `stat_test`, `stat_model`, `stat_interpret`, `t_test`, `mann_whitney`, `anova`, `kruskal_wallis`, `task_write` |
| `viz_designer` | 可视化设计师 | `analysis` | `chart_session`, `export_chart`, `task_write` |
| `writing_assistant` | 学术写作助手 | `analysis` | `report_session`, `generate_report`, `export_report`, `task_write` |
| `research_planner` | 研究规划师 | `planning` | `task_write`, `analysis_memory` |
| `citation_manager` | 引用管理专家 | `default` | `fetch_url`, `task_write` |
| `review_assistant` | 审稿助手 | `default` | `task_write`, `analysis_memory` |

> **设计约束**：
> - `run_code` / `run_r_code` **不**放入任何子 Agent 的 `allowed_tools`，代码执行保留在 Orchestrator（主 Agent）层
> - 知识库检索（RAG）通过 `ContextBuilder` 在每次 LLM 调用时自动注入，无需工具调用

---

### 3.7 前端 - Agent 状态管理

**新建文件**：`web/src/store/agent-slice.ts`（融入现有 slices 架构）

```typescript
// web/src/store/types.ts 中新增类型
interface AgentInfo {
  agentId: string
  agentName: string
  status: 'running' | 'completed' | 'error'
  task: string
  startTime: number
  summary?: string
}

interface AgentSlice {
  activeAgents: Record<string, AgentInfo>
  completedAgents: AgentInfo[]
}
```

**修改文件**：`web/src/store/event-handler.ts` 或新建 `agent-event-handler.ts`
- 处理 `agent_start`：写入 `activeAgents`
- 处理 `agent_progress`：更新对应 agentId 状态
- 处理 `agent_complete` / `agent_error`：移出 `activeAgents`，写入 `completedAgents`

**新建组件**：`web/src/components/AgentExecutionPanel.tsx`
- 展示并行运行中的 Agent 列表（名称、任务、状态、耗时）
- 完成后显示摘要结果

### 3.8 Phase 1 验证标准

```bash
# 后端单元测试
pytest tests/test_agent_registry.py -q
pytest tests/test_sub_session.py -q          # 重点：SubSession 继承 Session 后 AgentRunner 是否正常工作
pytest tests/test_tool_registry_subset.py -q # create_subset 方法
pytest tests/test_spawner.py -q

# 集成验证
# 1. 发送"帮我清洗这份数据并做统计分析"
# 2. 收到 agent_start(data_cleaner) + agent_start(statistician) 两个事件
# 3. 子 Agent 产物正确回写到父会话 session.artifacts
# 4. 子 Agent 失败时，主 Agent 自动降级处理，不中断会话
# 5. 前端 AgentExecutionPanel 展示两个并行 Agent 状态
```

---

## 四、Phase 2：智能路由与并行执行（预计 2-3 周）

**前置条件**：Phase 1 全部验证通过

### 4.1 后端 - TaskRouter

**新建文件**：`src/nini/agent/router.py`

路由策略（双轨制）：
1. **规则路由**（约 <1ms）：关键词匹配，置信度 > 0.9 时直接使用
2. **LLM 路由**（约 500ms）：规则置信度不足时启用，使用 `purpose="planning"`

```python
class TaskRouter:
    async def route(user_intent: str, context: dict) -> RoutingDecision:
        # 先尝试规则路由；置信度不足时调用 model_resolver.chat(purpose="planning")
        ...

    async def route_batch(tasks: list[str]) -> list[RoutingDecision]:
        # 一次 LLM 调用（purpose="planning"）分析所有任务的依赖关系，优化并行度
        ...
```

> LLM 路由使用 `purpose="planning"` 而非 `"default"`，避免与主 Agent 竞争同一路由配置；`planning` 已在 `ModelResolver` 中预留。

默认关键词规则：

| 关键词 | 路由目标 |
|--------|----------|
| 文献、论文、引用、期刊、搜索 | `literature_search` |
| 精读、批注、阅读、理解图表 | `literature_reading` |
| 数据清洗、缺失值、异常值、预处理 | `data_cleaner` |
| 统计、检验、p值、显著性、回归、方差 | `statistician` |
| 图表、可视化、画图、箱线图、散点图 | `viz_designer` |
| 写作、润色、摘要、引言、讨论 | `writing_assistant` |

---

### 4.2 后端 - ResultFusionEngine

**新建文件**：`src/nini/agent/fusion.py`

融合策略：

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `concatenate` | 简单拼接 | 独立任务结果 |
| `summarize` | LLM 摘要（`purpose="analysis"`） | 需整合的结果 |
| `consensus` | 辩论共识 | 结论有分歧 |
| `hierarchical` | 层次化融合 | 结果数量 > 4 |

**冲突检测**：
- 数值型：方差超阈值 → 标注 `numeric_discrepancy`（仅标注，不影响输出）
- 分类型：结论不一致 → 标注 `categorical_discrepancy`

---

### 4.3 后端 - Orchestrator 改造

**修改文件**：`src/nini/agent/runner.py`

在现有 ReAct 循环内增加"是否需要子 Agent 派发"判断点：

```
ReAct 主循环（不改变现有逻辑）
  ↓ 在 tool_call 解析后
  ├── 普通工具调用 → 原有执行路径（不变）
  └── 复杂任务判断 → TaskRouter.route() → SubAgentSpawner.spawn_batch() → ResultFusionEngine.fuse()
```

**不破坏现有行为**：Orchestrator 模式仅在 `TaskRouter` 返回多 Agent 决策时触发，单 Agent 场景退化为现有逻辑。

---

### 4.4 前端 - 工作流可视化

**新建组件**：`web/src/components/WorkflowTopology.tsx`
- 简化 DAG 可视化（非图形库，纯 CSS flexbox）
- 实时着色：等待（灰）/ 运行（蓝）/ 完成（绿）/ 失败（红）

**修改组件**：`web/src/components/MessageBubble.tsx`
- 子 Agent 来源消息增加来源标签，如 `[统计分析专家]`

### 4.5 Phase 2 验证标准

```bash
pytest tests/test_router.py -q
pytest tests/test_fusion.py -q

# 集成验证
# 1. 发送"请帮我分析这份数据：清洗、统计和可视化"
# 2. 3 个子 Agent 并行启动（data_cleaner + statistician + viz_designer）
# 3. 结果被正确融合，最终报告包含三部分
# 4. 前端 WorkflowTopology 展示 DAG 执行过程
# 5. 统计结论有分歧时，冲突被标注在报告中
```

---

## 五、Phase 3：Hypothesis-Driven 范式（预计 2-3 周）

**前置条件**：Phase 2 全部验证通过

**核心价值**：科研场景的文献综述、实验设计等任务，其推理模式是"提出假设 → 收集证据 → 验证修正 → 得出结论"，比纯 ReAct 的工具链式触发更能产出高质量结论。

### 5.1 范式触发条件

| 触发场景 | 判断依据 |
|----------|----------|
| 文献综述 | 意图含"综述/review/系统分析/meta分析" |
| 实验设计 | 意图含"实验设计/样本量/随机化/对照组" |
| 结论验证 | 意图含"验证/检验假设/反驳/证伪" |
| 显式声明 | 用户输入包含"假设：..." |

默认：未触发时继续使用 ReAct 范式。

---

### 5.2 后端 - HypothesisContext

**新建文件**：`src/nini/agent/hypothesis_context.py`

```python
@dataclass
class Hypothesis:
    id: str
    content: str
    confidence: float               # 置信度（贝叶斯更新）
    evidence_for: list[str]
    evidence_against: list[str]
    status: str                     # pending / validated / refuted / revised

@dataclass
class HypothesisContext:
    """存储于 SubSession.artifacts["_hypothesis_context"]，不修改主 Session 结构。"""
    hypotheses: list[Hypothesis] = field(default_factory=list)
    current_phase: str = "generation"  # generation / collection / validation / conclusion
    iteration_count: int = 0
    max_iterations: int = 3

    def should_conclude(self) -> bool:
        """收敛判断（三条件，满足任一即收敛）：
        1. iteration_count >= max_iterations（硬上限）
        2. 所有假设状态均为 validated 或 refuted（无 pending）
        3. 相邻两轮最大置信度变化 < 0.05（贝叶斯收敛）
        """
        ...
```

> 存储位置：`SubSession.artifacts["_hypothesis_context"]`，不修改 `Session` 主结构。

---

### 5.3 后端 - registry.py 增加 paradigm 字段

Phase 1 已包含 `paradigm` 字段，Phase 3 在此基础上：
- 将 `literature_reading` 和 `research_planner` 的 `paradigm` 改为 `"hypothesis_driven"`
- 其余 7 个保持 `paradigm = "react"`

---

### 5.4 后端 - spawner.py 增加范式分支

**修改文件**：`src/nini/agent/spawner.py`

```python
async def spawn(self, agent_id, task, session, timeout_seconds=300):
    agent_def = self.registry.get(agent_id)

    if agent_def.paradigm == "hypothesis_driven":
        return await self._spawn_hypothesis_driven(agent_def, task, session)
    else:
        return await self._spawn_react(agent_def, task, session)

async def _spawn_hypothesis_driven(self, agent_def, task, session):
    # 1. 创建 SubSession，注入 HypothesisContext
    # 2. 循环：生成假设 → 调用工具收集证据 → 更新置信度
    # 3. 直到 HypothesisContext.should_conclude() 为 True
    # 4. 返回 SubAgentResult（detailed_output 包含假设链）
```

---

### 5.5 后端 - 新增范式事件类型

**修改文件**：`src/nini/agent/events.py`（Phase 1 基础上追加）

```python
# Phase 3 新增
HYPOTHESIS_GENERATED  = "hypothesis_generated"   # 生成假设
EVIDENCE_COLLECTED    = "evidence_collected"      # 收集到证据
HYPOTHESIS_VALIDATED  = "hypothesis_validated"    # 假设已验证
HYPOTHESIS_REFUTED    = "hypothesis_refuted"      # 假设被证伪（触发修正）
PARADIGM_SWITCHED     = "paradigm_switched"       # 范式切换通知
```

---

### 5.6 前端 - 假设推理可视化

**新建组件**：`web/src/components/HypothesisTracker.tsx`
- 假设列表：内容 + 置信度进度条 + 状态标签
- 证据链折叠展开
- 接收 `hypothesis_generated` / `evidence_collected` / `hypothesis_validated` / `hypothesis_refuted` 事件实时更新

### 5.7 Phase 3 验证标准

```bash
pytest tests/test_hypothesis_context.py -q   # 重点：should_conclude 三条件
pytest tests/test_spawner_hypothesis.py -q

# 集成验证
# 1. 发送"请综述近5年XXX领域的研究进展"
# 2. 触发 Hypothesis-Driven 范式（收到 paradigm_switched 事件）
# 3. 收到 hypothesis_generated 事件（2-4 个初始假设）
# 4. 收到 evidence_collected 事件（使用 fetch_url / analysis_memory）
# 5. 至少一轮 hypothesis_validated 或 hypothesis_refuted
# 6. 迭代不超过 max_iterations=3 轮
# 7. 最终结论包含置信度说明
# 8. 前端 HypothesisTracker 展示完整假设链
```

---

## 六、文件改动汇总

### 新建文件

```
src/nini/agent/
├── registry.py                   # Phase 1：AgentDefinition + AgentRegistry
├── sub_session.py                # Phase 1：SubSession（继承 Session，跳过磁盘初始化）
├── spawner.py                    # Phase 1 + Phase 3：SubAgentSpawner（含范式分支）
├── router.py                     # Phase 2：TaskRouter（双轨制路由）
├── fusion.py                     # Phase 2：ResultFusionEngine
├── hypothesis_context.py         # Phase 3：HypothesisContext（三条件收敛）
└── prompts/agents/               # Phase 1：9个 Agent 系统提示词（.yaml 格式）
    ├── literature_search.yaml
    ├── literature_reading.yaml
    ├── data_cleaner.yaml
    ├── statistician.yaml
    ├── viz_designer.yaml
    ├── writing_assistant.yaml
    ├── research_planner.yaml
    ├── citation_manager.yaml
    └── review_assistant.yaml

tests/
├── test_agent_registry.py        # Phase 1
├── test_sub_session.py           # Phase 1（含 AgentRunner 兼容性测试）
├── test_tool_registry_subset.py  # Phase 1（create_subset 方法）
├── test_spawner.py               # Phase 1
├── test_router.py                # Phase 2
├── test_fusion.py                # Phase 2
├── test_hypothesis_context.py    # Phase 3（should_conclude 三条件）
└── test_spawner_hypothesis.py    # Phase 3

web/src/
├── store/agent-slice.ts          # Phase 1：AgentSlice 状态
├── store/agent-event-handler.ts  # Phase 1：处理多 Agent 事件
├── components/AgentExecutionPanel.tsx  # Phase 1
├── components/WorkflowTopology.tsx     # Phase 2
└── components/HypothesisTracker.tsx    # Phase 3
```

### 修改文件

```
src/nini/tools/registry.py        # Phase 1：ToolRegistry 增加 create_subset() 方法
src/nini/agent/events.py          # Phase 1 + Phase 3：追加事件类型
src/nini/agent/runner.py          # Phase 2：增加 Orchestrator 模式入口
src/nini/agent/registry.py        # Phase 3：literature_reading/research_planner 的 paradigm 字段
src/nini/agent/spawner.py         # Phase 3：增加 Hypothesis-Driven 执行分支
web/src/store/types.ts            # Phase 1：增加 AgentInfo/AgentSlice 类型
web/src/store/event-handler.ts    # Phase 1：注册 agent_start/progress/complete/error 处理器
web/src/components/MessageBubble.tsx  # Phase 2：增加子 Agent 来源标签
```

---

## 七、向后兼容性保证

- 现有 `AgentRunner` ReAct 循环**不被修改**，Orchestrator 模式作为新代码路径叠加
- 现有 `Session` 结构**不被修改**，`SubSession` 继承 `Session` 但覆盖 `__post_init__`
- 现有 `EventType` 枚举**只追加**，不删除、不重命名
- 现有 30+ 工具**不受影响**，`create_subset()` 仅构造只读视图
- 未配置多 Agent 时，系统退化为当前单 Agent ReAct 模式

---

## 八、风险与缓解

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| SubSession 继承 Session 接口适配不完整 | 高 | 先跑通 AgentRunner + SubSession 的最小集成测试，再接 Spawner |
| `spawn_batch` 并发沙箱进程数膨胀 | 高 | `run_code`/`run_r_code` 不放入子 Agent allowed_tools；主 Agent 保留代码执行能力 |
| ModelResolver chat() 流式接口在子 Agent 中的事件回调设计 | 中 | SubSession.event_callback 指向父会话的 callback，子 Agent 事件通过父会话推送 |
| TaskRouter LLM 路由（`planning` purpose）占用额外 Token | 中 | 常见场景规则路由命中（置信度 > 0.9），LLM 路由仅作兜底 |
| Hypothesis-Driven 多轮迭代延迟增加 | 中 | `max_iterations=3` 硬上限；前端增加"深度分析中（预计 30-90 秒）"提示 |
| ResultFusionEngine 冲突误判 | 低 | 冲突仅作标注，不干预输出；数值方差阈值可配置 |

---

## 九、成本预估

| Phase | 额外 LLM 调用 | 预估延迟增加 | 备注 |
|-------|-------------|------------|------|
| Phase 1 | 子 Agent 各 1 次主循环 | +5-15s/子 Agent | 并行执行，不串行累加 |
| Phase 2 | TaskRouter LLM 路由 1 次（可选） | +0-1s | 规则命中时为 0 |
| Phase 3 | Hypothesis 每轮迭代 2-4 次 LLM 调用 | +15-60s | 仅文献综述类任务触发 |
