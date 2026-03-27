:
# 学习记录: Agent 核心模块全景

| 字段 | 值 |
|------|-----|
| 日期 | 2026-03-24 |
| 阶段 | 第二阶段 |
| 模块 | tools/base.py, agent/session.py, sandbox/executor.py, agent/runner.py, api/websocket.py, web/src/store.ts |
| 对话轮数 | ~1 轮（系统性总结）|

---

## 📝 本次摘要

本次学习系统性地梳理了 scientific_nini 项目的核心架构模块，从底层的 Tool 基类与注册机制，到会话状态管理、沙箱安全执行、ReAct 循环核心、WebSocket 实时通信，再到前端 Zustand 状态管理。理解了 Agent 从接收用户消息到执行工具并返回结果的完整数据流，以及各模块之间的协作关系。

---

## 🧠 核心知识点

### 1. Tool 基类与注册机制（tools/base.py + registry.py）

**概念理解**
- **@dataclass**: Python 装饰器，自动生成 `__init__`、`__repr__` 等方法，简化类定义 — 在项目中的作用: 所有 Tool 类都使用 dataclass 定义，减少样板代码
- **@abstractmethod**: 抽象方法装饰器，强制子类必须实现 — 在项目中的作用: `Tool.execute()` 是抽象方法，每个具体 Tool 必须实现
- **ToolRegistry**: 工具注册中心，管理所有可用工具 — 在项目中的作用: 统一暴露工具给 LLM，支持动态注册

**关键代码片段**
```python
# tools/base.py - Tool 基类定义
@dataclass
class Tool(ABC):
    """工具基类，所有具体工具继承此类"""
    name: str
    description: str
    parameters: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, session: Session, **kwargs) -> ToolResult:
        """执行工具，必须由子类实现"""
        pass
```

```python
# tools/registry.py - 工具注册
class ToolRegistry:
    """工具注册中心"""
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def get_tool_schemas(self) -> list[dict]:
        """获取所有工具的 JSON Schema，供 LLM 调用"""
        return [tool.to_schema() for tool in self._tools.values()]
```

### 2. 会话状态管理（agent/session.py）

**概念理解**
- **field(default_factory)**: dataclass 字段，使用工厂函数创建默认值 — 在项目中的作用: 避免可变对象（如 list、dict）在实例间共享
- **会话持久化**: 会话数据保存到磁盘，支持恢复 — 在项目中的作用: 用户可随时回到之前的对话

**关键代码片段**
```python
# agent/session.py - Session 类
@dataclass
class Session:
    """会话状态管理"""
    session_id: str
    messages: list[Message] = field(default_factory=list)  # 消息历史
    dataframes: dict[str, pd.DataFrame] = field(default_factory=dict)  # 已加载数据
    artifacts: list[Artifact] = field(default_factory=list)  # 产物列表

    def persist(self) -> None:
        """持久化到 data/sessions/{session_id}/"""
        # 保存 meta.json, memory.jsonl, workspace/
```

### 3. 沙箱安全执行（sandbox/executor.py）

**概念理解**
- **AST 静态分析**: 解析代码语法树，检查危险操作 — 在项目中的作用: 执行前拦截恶意代码
- **multiprocessing**: 进程隔离，防止代码影响主进程 — 在项目中的作用: 用户代码在独立进程中运行，崩溃不影响主程序
- **async/await**: 异步编程，避免阻塞 — 在项目中的作用: 沙箱执行是 I/O 密集型操作，使用异步提高效率

**关键代码片段**
```python
# sandbox/executor.py - 沙箱执行器
async def run_code_sandbox(code: str, session: Session) -> ExecutionResult:
    """在沙箱中异步执行代码"""
    # 1. AST 静态检查
    if not policy.check_code(code):
        return ExecutionResult(error="代码包含危险操作")

    # 2. 创建进程池执行
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,  # 使用默认 executor
        _execute_in_process,  # 在独立进程中执行
        code,
        session
    )
    return result

def _execute_in_process(code: str, session: Session) -> ExecutionResult:
    """在子进程中执行代码（隔离环境）"""
    # 限制 builtins，只允许安全操作
    safe_builtins = {
        'len': len,
        'range': range,
        # ... 其他安全内置函数
    }
    exec(code, {"__builtins__": safe_builtins}, {})
```

### 4. ReAct 循环核心（agent/runner.py）

**概念理解**
- **ReAct 循环**: Reasoning + Acting，LLM 思考后执行工具 — 在项目中的作用: Agent 的核心决策循环
- **流式响应**: 逐步返回结果，提升用户体验 — 在项目中的作用: 用户可实时看到思考过程和工具调用

**关键代码片段**
```python
# agent/runner.py - AgentRunner
class AgentRunner:
    """Agent 运行器，实现 ReAct 循环"""

    async def run(self, session: Session, user_message: str) -> AsyncIterator[Event]:
        """运行 ReAct 循环，流式返回事件"""
        # 1. 构建上下文（system prompt + 历史 + 知识库）
        context = self._build_context(session)

        # 2. 调用 LLM，流式获取响应
        async for chunk in self.model_resolver.chat(context):
            # 3. 解析 tool_calls
            if chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    # 4. 执行工具
                    result = await self._execute_tool(tool_call, session)
                    # 5. 通过 callback 推送事件
                    yield ToolResultEvent(tool=tool_call.name, result=result)
            else:
                # 普通文本响应
                yield TextEvent(content=chunk.content)
```

### 5. WebSocket 实时通信（api/websocket.py + agent/events.py）

**概念理解**
- **WebSocket**: 全双工通信协议，支持服务器主动推送 — 在项目中的作用: 实时推送 Agent 事件到前端
- **Event 系统**: 统一的事件模型，解耦 Agent 与传输层 — 在项目中的作用: Agent 无需关心如何发送，只需 yield 事件

**关键代码片段**
```python
# agent/events.py - 事件定义
@dataclass
class Event:
    """基础事件类"""
    type: str
    timestamp: datetime

@dataclass
class TextEvent(Event):
    """文本事件"""
    content: str

@dataclass
class ToolCallEvent(Event):
    """工具调用事件"""
    tool: str
    arguments: dict
```

```python
# api/websocket.py - WebSocket 端点
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = Session()

    async for event in agent_runner.run(session, user_message):
        # 将事件序列化为 JSON 发送给前端
        await websocket.send_json(event.to_dict())
```

### 6. 前端状态管理（web/src/store.ts）

**概念理解**
- **Zustand**: 轻量级 React 状态管理库 — 在项目中的作用: 单一 store 管理整个前端状态
- **单一数据源**: 所有组件从同一 store 获取状态 — 在项目中的作用: 避免状态不一致，简化数据流

**关键代码片段**
```typescript
// web/src/store.ts - Zustand Store
import { create } from 'zustand'

interface AppState {
  messages: Message[]
  artifacts: Artifact[]
  currentSession: Session | null

  // Actions
  addMessage: (msg: Message) => void
  updateArtifact: (id: string, artifact: Artifact) => void
  setSession: (session: Session) => void
}

export const useAppStore = create<AppState>((set) => ({
  messages: [],
  artifacts: [],
  currentSession: null,

  addMessage: (msg) => set((state) => ({
    messages: [...state.messages, msg]
  })),

  updateArtifact: (id, artifact) => set((state) => ({
    artifacts: state.artifacts.map(a =>
      a.id === id ? artifact : a
    )
  }))
}))
```

---

## ⚡ 语法收获

| 语法点 | 一句话解释 | 项目中位置 |
|--------|-----------|-----------|
| @dataclass | 自动生成类方法，简化数据类定义 | tools/base.py |
| @abstractmethod | 强制子类实现，定义接口契约 | tools/base.py |
| field(default_factory) | 使用工厂函数创建可变字段默认值 | agent/session.py |
| async/await | 异步编程，非阻塞 I/O 操作 | sandbox/executor.py, agent/runner.py |
| AsyncIterator | 异步迭代器，支持流式数据 | agent/runner.py |
| yield | 生成器，逐步返回结果 | agent/runner.py |
| multiprocessing | 进程隔离，安全执行用户代码 | sandbox/executor.py |
| Zustand create | 创建 React 全局状态 store | web/src/store.ts |

---

## 🧪 实验记录

- **实验**: 梳理 Agent 完整数据流
- **结果**: 理解了从用户输入到工具执行再到前端展示的完整链路
- **理解**: ✅ 正确

---

## ❓ 遗留问题

- [ ] 知识库检索（knowledge/）的具体实现机制
- [ ] 任务规划系统（agent/planner.py）如何分解复杂任务
- [ ] 多模型路由（agent/model_resolver.py）的降级策略细节
- [ ] 图表渲染（charts/）的扩展机制

---

## 🔗 关联

- **前置知识**: Python 异步编程、React 基础、FastAPI WebSocket
- **后续模块**:
  - knowledge/ - RAG 向量检索
  - agent/planner.py - 任务规划
  - agent/model_resolver.py - 多模型路由
  - charts/ - 图表渲染
- **上一条记录**: 无（本次为系统性总结）

---
*Generated by @learning-record*
