# 科研Nini Agent架构优化调研报告

**调研日期：** 2026年2月10日
**调研员：** 调研员Agent
**项目位置：** /home/lewis/coding/scientific_nini

---

## 执行摘要

本报告深度调研了业内先进的Agent项目架构，包括LangGraph、Model Context Protocol (MCP)、Agent Protocol、SuperAGI等项目，提取了核心架构模式和设计理念，并为科研Nini项目提供了可执行的优化建议。

**核心发现：**
1. **状态驱动架构**成为主流，LangGraph的Channel系统最为完善
2. **协议标准化**是趋势，MCP和Agent Protocol定义了Agent通信标准
3. **多层次记忆系统**是先进Agent的核心竞争力
4. **Runtime上下文注入**模式显著提升开发体验
5. **工具生态系统**的开放性和可扩展性至关重要

---

## 一、调研项目概览

### 1.1 已调研项目列表

| 项目 | GitHub地址 | 核心特点 | 架构亮点 |
|------|-----------|---------|---------|
| **LangGraph** | langchain-ai/langgraph | 状态图架构，Pregel算法 | Channel系统、Checkpoint持久化、Runtime注入 |
| **MCP Servers** | modelcontextprotocol/servers | 统一工具协议 | 标准化工具定义、Prompt模板、双向通信 |
| **Agent Protocol** | AI-Engineer-Foundation/agent-protocol | Agent通信标准 | REST API规范、任务/步骤模型 |
| **SuperAGI** | TransformerOptimus/SuperAGI | 企业级Agent平台 | 工具市场、工作流编排 |
| **Anthropic SDK** | anthropic/anthropic-sdk-typescript | 官方SDK | 流式响应、工具调用标准化 |

### 1.2 当前科研Nini项目架构分析

**现有架构组件：**

```
科研Nini
├── Agent核心
│   ├── runner.py          - ReAct主循环
│   ├── session.py         - 会话管理
│   ├── model_resolver.py  - 多模型路由
│   └── title_generator.py - 标题生成
├── 技能系统
│   ├── base.py            - Skill基类
│   ├── registry.py        - 技能注册中心
│   └── [18个具体技能]
├── 记忆系统
│   ├── conversation.py    - JSONL会话记忆
│   ├── knowledge.py       - 知识记忆
│   └── compression.py     - 上下文压缩
├── 知识系统
│   ├── loader.py          - 混合检索加载器
│   └── vector_store.py    - 向量索引
└── 工作空间
    └── manager.py         - 工件管理
```

**现有优势：**
- 完整的ReAct循环实现
- 多模型故障转移机制
- 混合检索（向量+关键词）
- 工作空间产物管理
- 流式响应支持

**待优化点：**
- 缺少状态驱动的Channel系统
- 记忆系统相对简单
- 技能系统缺少标准化协议
- 缺少Checkpoint持久化机制
- 协作能力有限

---

## 二、核心架构模式深度分析

### 2.1 LangGraph的Channel系统（状态管理）

**核心理念：** Agent的状态变化通过一组Channel进行管理和同步。

**关键设计：**

```python
# BaseChannel接口（简化版）
class BaseChannel(Generic[Value, Update, Checkpoint], ABC):
    @abstractmethod
    def get(self) -> Value:
        """获取当前值"""

    @abstractmethod
    def update(self, values: Sequence[Update]) -> bool:
        """批量更新状态"""

    @abstractmethod
    def checkpoint(self) -> Checkpoint | Any:
        """创建检查点"""

    @abstractmethod
    def from_checkpoint(self, checkpoint: Checkpoint) -> Self:
        """从检查点恢复"""
```

**Channel类型体系：**

| Channel类型 | 用途 | 更新策略 |
|------------|------|---------|
| `LastValue` | 最新值覆盖 | 替换 |
| `BinaryOperatorAggregate` | 累积值 | 通过reducer函数合并 |
| `NamedBarrierValue` | 同步屏障 | 等待所有依赖更新 |
| `Topic` | 发布订阅 | 多消费者模式 |
| `EphemeralValue` | 临时值 | 不持久化 |

**科研Nini应用建议：**

```python
# 建议引入的Channel类型
from typing import Annotated

def reducer_append(a: list, b: list) -> list:
    return a + b

class AnalysisState(TypedDict):
    # 对话历史 - 累积式
    messages: Annotated[list[dict], reducer_append]

    # 当前数据集 - 覆盖式
    datasets: dict[str, pd.DataFrame]

    # 图表产物 - 累积式
    artifacts: Annotated[list[Artifact], reducer_append]

    # 分析进度 - 最新值
    progress: float

    # 用户偏好 - 覆盖式
    user_preferences: dict
```

### 2.2 LangGraph的Runtime系统（上下文注入）

**核心理念：** 将运行时上下文（如user_id、store、stream_writer）作为依赖注入到节点函数中。

**关键实现：**

```python
@dataclass
class Runtime(Generic[ContextT]):
    """运行时上下文容器"""
    context: ContextT               # 用户定义的上下文
    store: BaseStore | None        # 持久化存储
    stream_writer: StreamWriter    # 流式输出
    previous: Any                  # 上次运行的返回值

# 使用示例
def personalized_node(state: State, runtime: Runtime[Context]) -> State:
    user_id = runtime.context.user_id
    memory = runtime.store.get(("users", user_id))
    # ... 使用上下文数据
    return updated_state
```

**科研Nini应用建议：**

```python
# 定义科研上下文
@dataclass
class ResearchContext:
    user_id: str
    experiment_id: str | None = None
    workspace_path: str | None = None
    preferences: dict = field(default_factory=dict)

# 修改AgentRunner以支持Runtime注入
class AgentRunner:
    def __init__(self):
        self._runtime: Runtime[ResearchContext] | None = None

    async def run_with_context(
        self,
        session: Session,
        user_message: str,
        context: ResearchContext,
    ):
        # 将context注入到所有技能调用中
        for skill_call in tool_calls:
            result = await skill.execute(
                session=session,
                runtime=Runtime(context=context),  # 注入上下文
                **args
            )
```

### 2.3 LangGraph的Checkpoint系统（持久化）

**核心理念：** 将整个Agent状态序列化为checkpoint，支持暂停和恢复。

**关键设计：**

```python
class BaseCheckpointSaver(ABC):
    @abstractmethod
    async def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
    ) -> None:
        """保存检查点"""

    @abstractmethod
    async def get(
        self,
        config: RunnableConfig,
    ) -> Checkpoint | None:
        """获取检查点"""

    @abstractmethod
    def list(
        self,
        config: RunnableConfig,
        before: datetime | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        """列出检查点历史"""
```

**科研Nini应用建议：**

```python
# 实现科研Nini的CheckpointSaver
class ResearchCheckpointSaver:
    """科研分析检查点保存器"""

    def __init__(self, sessions_dir: Path):
        self._dir = sessions_dir

    async def save_analysis_checkpoint(
        self,
        session_id: str,
        step_id: str,
        state: AnalysisState,
    ):
        """保存分析步骤的状态"""
        checkpoint_path = (
            self._dir / session_id / "checkpoints" / f"{step_id}.json"
        )
        checkpoint = {
            "step_id": step_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self._serialize_state(state),
            "messages": state["messages"][-10:],  # 保留最近消息
        }
        checkpoint_path.write_text(
            json.dumps(checkpoint, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    async def load_analysis_checkpoint(
        self,
        session_id: str,
        step_id: str,
    ) -> AnalysisState | None:
        """加载分析步骤的状态"""
        checkpoint_path = (
            self._dir / session_id / "checkpoints" / f"{step_id}.json"
        )
        if not checkpoint_path.exists():
            return None

        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return self._deserialize_state(data["state"])
```

### 2.4 MCP的工具定义标准

**核心理念：** 标准化工具定义，使工具可在不同Agent系统间互操作。

**MCP工具Schema：**

```typescript
interface Tool {
    name: string;
    description: string;
    inputSchema: JSONSchema;  // JSON Schema格式
}

interface ToolCallResult {
    content: TextContent | ImageContent | EmbeddedResource;
    isError?: boolean;
}
```

**科研Nini应用建议：**

```python
# 统一技能定义标准
class StandardizedSkill(Skill):
    """符合MCP标准的技能"""

    def to_mcp_tool(self) -> dict:
        """转换为MCP工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            }
        }

    def execute_mcp(
        self,
        arguments: dict,
    ) -> list[TextContent | ImageContent]:
        """MCP标准执行接口"""
        result = await self.execute(session=MockSession(), **arguments)

        contents = []
        if result.message:
            contents.append(TextContent(
                type="text",
                text=result.message
            ))
        if result.has_chart:
            contents.append(ImageContent(
                type="image",
                data=result.chart_data,
                mimeType="application/vnd.plotly+json"
            ))
        return contents
```

### 2.5 Agent Protocol的任务/步骤模型

**核心理念：** 将Agent工作分解为Task和Step，支持可观测性和重试。

**API端点：**

```
POST /ap/v1/agent/tasks        # 创建任务
GET  /ap/v1/agent/tasks        # 列出任务
POST /ap/v1/agent/tasks/{id}/steps  # 执行步骤
GET  /ap/v1/agent/tasks/{id}/steps  # 列出步骤
```

**科研Nini应用建议：**

```python
# 引入任务/步骤模型
@dataclass
class AnalysisTask:
    """分析任务"""
    task_id: str
    objective: str              # 用户目标
    status: str                 # pending/running/completed/failed
    created_at: str
    steps: list[AnalysisStep]

@dataclass
class AnalysisStep:
    """分析步骤"""
    step_id: str
    name: str                   # 如"load_data", "t_test"
    input: dict
    output: dict | None
    status: str
    error: str | None
    artifacts: list[str]

class TaskManager:
    """任务管理器"""

    async def create_task(
        self,
        objective: str,
        session_id: str,
    ) -> AnalysisTask:
        """创建新的分析任务"""
        task = AnalysisTask(
            task_id=uuid.uuid4().hex[:12],
            objective=objective,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            steps=[],
        )
        await self._save_task(task, session_id)
        return task

    async def add_step(
        self,
        task_id: str,
        name: str,
        input: dict,
    ) -> AnalysisStep:
        """添加执行步骤"""
        step = AnalysisStep(
            step_id=uuid.uuid4().hex[:12],
            name=name,
            input=input,
            output=None,
            status="running",
            error=None,
            artifacts=[],
        )
        # ... 更新任务
        return step
```

---

## 三、架构对比分析

### 3.1 状态管理对比

| 特性 | 科研Nini（当前） | LangGraph | SuperAGI |
|------|----------------|-----------|----------|
| 状态类型 | 内存dict | Channel系统 | 数据库模型 |
| 更新策略 | 直接赋值 | Reducer函数 | ORM操作 |
| 持久化 | JSONL | Checkpoint | PostgreSQL |
| 恢复能力 | 弱 | 强（检查点） | 中等 |
| 类型安全 | 部分 | 强（TypedDict） | 强（Pydantic） |

**建议：** 引入Channel系统，增加类型安全性和状态可追溯性。

### 3.2 工具系统对比

| 特性 | 科研Nini（当前） | MCP | Agent Protocol |
|------|----------------|-----|----------------|
| 定义格式 | 自定义 | OpenAI Function + JSON Schema | OpenAPI |
| 执行模式 | 异步函数 | 可同步/异步 | REST调用 |
| 结果格式 | SkillResult | TextContent/ImageContent | JSON |
| 标准化 | 无 | MCP协议 | Agent协议 |

**建议：** 技能系统向MCP标准靠拢，增强互操作性。

### 3.3 记忆系统对比

| 特性 | 科研Nini（当前） | LangGraph | SuperAGI |
|------|----------------|-----------|----------|
| 会话记忆 | JSONL | Checkpoint + Store | PostgreSQL |
| 知识记忆 | 混合检索 | BaseStore | Vector DB |
| 长期记忆 | 无 | 支持 | Qdrant/Weaviate |
| 记忆压缩 | 简单摘要 | 智能合并 | 未实现 |

**建议：** 引入BaseStore概念，支持分层记忆架构。

### 3.4 协作能力对比

| 特性 | 科研Nini（当前） | LangGraph | MCP |
|------|----------------|-----------|-----|
| 多Agent | 无 | Pregel（多节点） | Server-Client |
| 通信协议 | 无 | Channel更新 | JSON-RPC |
| 工具共享 | 本地注册 | 远程工具 | stdio/SSE |
| 协作模式 | 单Agent | 图编排 | 微服务 |

**建议：** 考虑引入多Agent协作能力，支持复杂分析任务。

---

## 四、可执行优化建议

### 4.1 短期优化（1-2周）

#### 建议1：引入Channel系统

**优先级：** 高
**工作量：** 3-5天

```python
# 新增文件：src/nini/channels/__init__.py

from abc import ABC, abstractmethod
from typing import Any, Sequence, Generic, TypeVar

Value = TypeVar("Value")
Update = TypeVar("Update")

class BaseChannel(Generic[Value, Update], ABC):
    """Channel基类"""

    @abstractmethod
    def get(self) -> Value:
        """获取当前值"""

    @abstractmethod
    def update(self, values: Sequence[Update]) -> bool:
        """更新值"""

    @property
    def is_available(self) -> bool:
        """是否有值"""
        try:
            self.get()
            return True
        except:
            return False

class LastValue(BaseChannel[Value, Value]):
    """最新值Channel"""

    def __init__(self, default: Value | None = None):
        self._value: Value | None = default

    def get(self) -> Value:
        if self._value is None:
            raise ValueError("Channel is empty")
        return self._value

    def update(self, values: Sequence[Update]) -> bool:
        if not values:
            return False
        self._value = values[-1]  # 取最后一个值
        return True

class AppendChannel(BaseChannel[list, list]):
    """追加列表Channel"""

    def __init__(self):
        self._value: list = []

    def get(self) -> list:
        return list(self._value)

    def update(self, values: Sequence[list]) -> bool:
        for v in values:
            self._value.extend(v)
        return True
```

**应用方式：**

```python
# 修改Session类
class Session:
    def __init__(self):
        # 使用Channel替代直接dict
        self._channels = {
            "messages": AppendChannel(),
            "datasets": LastValue(default={}),
            "artifacts": AppendChannel(),
        }

    def get_state(self) -> dict:
        """获取当前状态"""
        return {
            "messages": self._channels["messages"].get(),
            "datasets": self._channels["datasets"].get(),
            "artifacts": self._channels["artifacts"].get(),
        }
```

#### 建议2：实现Checkpoint持久化

**优先级：** 高
**工作量：** 2-3天

```python
# 新增文件：src/nini/checkpoint/__init__.py

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

@dataclass
class Checkpoint:
    """检查点数据"""
    checkpoint_id: str
    session_id: str
    timestamp: str
    state: dict[str, Any]
    metadata: dict[str, Any]

class CheckpointSaver:
    """检查点保存器"""

    def __init__(self, sessions_dir: Path):
        self._dir = sessions_dir / "checkpoints"
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        session_id: str,
        state: dict,
        metadata: dict | None = None,
    ) -> str:
        """保存检查点"""
        checkpoint_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            state=state,
            metadata=metadata or {},
        )

        path = self._dir / session_id / f"{checkpoint_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(checkpoint.__dict__, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        return checkpoint_id

    async def load(
        self,
        session_id: str,
        checkpoint_id: str,
    ) -> Checkpoint | None:
        """加载检查点"""
        path = self._dir / session_id / f"{checkpoint_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(**data)

    async def list_checkpoints(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[Checkpoint]:
        """列出检查点"""
        session_dir = self._dir / session_id
        if not session_dir.exists():
            return []

        checkpoints = []
        for path in sorted(session_dir.glob("*.json"), reverse=True)[:limit]:
            data = json.loads(path.read_text(encoding="utf-8"))
            checkpoints.append(Checkpoint(**data))
        return checkpoints
```

**集成到AgentRunner：**

```python
class AgentRunner:
    def __init__(
        self,
        checkpoint_saver: CheckpointSaver | None = None,
    ):
        self._checkpoint_saver = checkpoint_saver

    async def run(
        self,
        session: Session,
        user_message: str,
        enable_checkpoint: bool = True,
    ) -> AsyncGenerator[AgentEvent, None]:
        # ... 在关键步骤保存检查点
        if enable_checkpoint and self._checkpoint_saver:
            await self._checkpoint_saver.save(
                session_id=session.id,
                state=session.get_state(),
                metadata={"step": "before_llm"},
            )
```

#### 建议3：技能系统标准化

**优先级：** 中
**工作量：** 1-2天

```python
# 新增文件：src/nini/skills/standard.py

from typing import Any
from pydantic import BaseModel, Field

class StandardSkillSchema(BaseModel):
    """标准化技能Schema"""
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_function(self) -> dict:
        """转换为OpenAI Function格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_mcp_tool(self) -> dict:
        """转换为MCP Tool格式"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }
```

### 4.2 中期优化（2-4周）

#### 建议4：引入Runtime上下文注入

**优先级：** 中
**工作量：** 3-5天

参考LangGraph的Runtime设计，实现科研Nini的上下文注入系统。

#### 建议5：实现任务/步骤模型

**优先级：** 中
**工作量：** 5-7天

参考Agent Protocol，实现AnalysisTask和AnalysisStep。

#### 建议6：增强记忆压缩

**优先级：** 中
**工作量：** 3-4天

引入智能摘要和关键信息提取，改进现有的简单压缩机制。

### 4.3 长期优化（1-2月）

#### 建议7：多Agent协作

**优先级：** 低
**工作量：** 10-15天

实现基于Pregel的多节点Agent系统，支持并行分析。

#### 建议8：工具生态系统

**优先级：** 低
**工作量：** 15-20天

实现符合MCP标准的工具服务器，支持外部工具集成。

---

## 五、架构演进路线图

```
阶段1：状态管理优化（Week 1-2）
├── 引入Channel系统
├── 实现Checkpoint持久化
└── 改进Session类

阶段2：技能系统标准化（Week 3-4）
├── 定义标准技能Schema
├── 实现MCP兼容接口
└── 技能注册中心升级

阶段3：上下文与可观测性（Week 5-6）
├── 实现Runtime注入
├── 任务/步骤模型
└── 增强日志和追踪

阶段4：高级特性（Week 7-10）
├── 多Agent协作
├── 工具生态系统
└── 智能记忆压缩
```

---

## 六、关键技术代码片段

### 6.1 LangGraph StateGraph核心代码

```python
class StateGraph(Generic[StateT, ContextT, InputT, OutputT]):
    """状态图构建器"""

    def add_node(
        self,
        node_name: str,
        node: Callable[..., StateUpdate | Output],
    ) -> Self:
        """添加节点"""
        self.nodes[node_name] = StateNode(node)
        return self

    def add_edge(self, start: str, end: str) -> Self:
        """添加边"""
        self.edges.add((start, end))
        return self

    def set_entry_point(self, node: str) -> Self:
        """设置入口"""
        self.entry_point = node
        return self

    def set_finish_point(self, node: str) -> Self:
        """设置出口"""
        self.finish_point = node
        return self

    def compile(
        self,
        checkpointer: Checkpointer | None = None,
    ) -> CompiledStateGraph:
        """编译为可执行图"""
        return CompiledStateGraph(
            self,
            checkpointer=checkpointer,
        )
```

### 6.2 MCP工具执行示例

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """MCP标准工具调用"""
    if name == "fetch":
        args = Fetch(**arguments)
        content, prefix = await fetch_url(str(args.url))
        return [TextContent(
            type="text",
            text=f"{prefix}Contents of {args.url}:\n{content}"
        )]

    raise McpError(ErrorData(
        code=INVALID_PARAMS,
        message=f"Unknown tool: {name}"
    ))
```

### 6.3 Agent Protocol步骤执行

```python
POST /ap/v1/agent/tasks/{task_id}/steps
{
    "input": "分析数据集data.csv的统计特征",
    "additional_input": {
        "dataset_path": "data.csv",
        "analysis_type": "descriptive"
    }
}

# 响应
{
    "task_id": "abc123",
    "step_id": "step_1",
    "output": "分析完成：均值=5.2, 标准差=1.8...",
    "artifacts": [
        {"artifact_id": "chart_1", "relative_path": "output/chart.png"}
    ],
    "status": "completed"
}
```

---

## 七、风险评估与缓解策略

| 风险 | 影响 | 概率 | 缓解策略 |
|------|------|------|---------|
| 架构变更导致现有功能失效 | 高 | 中 | 逐步迁移，保持向后兼容 |
| 性能下降（Channel开销） | 中 | 低 | 实现缓存和优化路径 |
| 开发周期延长 | 中 | 中 | 分阶段实施，优先高价值功能 |
| 协议限制影响灵活性 | 中 | 低 | 扩展协议，保留自定义能力 |

---

## 八、总结与建议

### 8.1 核心建议

1. **优先实施：** Channel系统和Checkpoint持久化
2. **逐步迁移：** 保持现有功能，增量添加新特性
3. **标准化：** 向MCP和Agent Protocol标准靠拢
4. **可观测性：** 增强日志、追踪和检查点功能

### 8.2 关键指标

成功标准：
- Checkpoint恢复时间 < 1秒
- Channel操作开销 < 5%
- 技能定义符合MCP标准
- 支持多Agent协作（长期）

### 8.3 后续行动

1. 审查本报告，确定优先级
2. 创建详细实施计划
3. 开始第一阶段开发
4. 定期回顾和调整

---

**报告完成日期：** 2026年2月10日
**下次审查建议：** 实施第一阶段后（约2周）
