## Context

Nini 当前是单体应用，所有功能直接编码在 `src/nini/` 中。`tools/` 中的 `fetch_url` 是唯一涉及外部网络的工具，但它是硬编码的，没有可用性检测或降级机制。V1 纲领决定联网功能以可选插件形式存在（见 `docs/nini-vision-charter.md`），需要一个轻量级的插件框架。

## Goals / Non-Goals

**Goals:**
- 定义简洁的 Plugin 接口
- 实现 PluginRegistry 管理插件生命周期
- 实现可用性检测和降级通知
- 提供 NetworkPlugin 作为第一个插件骨架

**Non-Goals:**
- 不实现热加载/卸载
- 不实现第三方插件分发
- 不迁移现有工具

## Decisions

### D1: 插件接口设计

**选择**：抽象基类 + Protocol 模式：

```python
class Plugin(ABC):
    name: str
    version: str
    description: str

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...

    def get_degradation_info(self) -> DegradationInfo | None: ...
```

**理由**：ABC 提供明确的接口约束。`is_available()` 是核心方法——每个插件定义自己的可用性检测逻辑。`get_degradation_info()` 在不可用时返回结构化的降级信息。

### D2: PluginRegistry 设计

**选择**：应用级单例，在 `create_app()` 中初始化：

```python
class PluginRegistry:
    def register(self, plugin: Plugin) -> None: ...
    def get(self, name: str) -> Plugin | None: ...
    def list_available(self) -> list[Plugin]: ...
    def list_unavailable(self) -> list[tuple[Plugin, DegradationInfo]]: ...
    async def initialize_all(self) -> None: ...
    async def shutdown_all(self) -> None: ...
```

**理由**：与现有 `ToolRegistry` 模式一致（注册表模式）。启动时调用 `initialize_all()`，每个插件的初始化失败不阻断其他插件和应用启动。

### D3: DegradationInfo 模型

**选择**：

```python
class DegradationInfo(BaseModel):
    plugin_name: str
    reason: str                    # 不可用原因
    impact: str                    # 对用户的影响描述
    alternatives: list[str] = []   # 替代建议
```

**理由**：结构化的降级信息，可被 Agent 提示词和前端 UI 消费。Agent 在运行时通过 PluginRegistry 查询降级信息，在回复中向用户说明。

### D4: NetworkPlugin 骨架

**选择**：

```python
class NetworkPlugin(Plugin):
    name = "network"
    version = "1.0"
    description = "提供网络请求能力，支持文献检索等联网功能"

    async def is_available(self) -> bool:
        # 检查网络连通性（尝试访问一个可靠端点）
        # 检查是否配置了必要的 API key
        ...

    async def initialize(self) -> None:
        # 初始化 HTTP 客户端
        ...
```

**理由**：作为第一个插件示例，NetworkPlugin 验证整个框架是否可用。V1 仅做网络可用性检测，具体的文献检索等功能在 C7 中以 NetworkPlugin 的扩展或子插件形式实现。

### D5: 与应用启动的集成

**选择**：在 `app.py` 的 `create_app()` 中，在 lifespan 事件中调用 `plugin_registry.initialize_all()`。PluginRegistry 实例存储在 `app.state.plugin_registry` 中。

**理由**：与 FastAPI 的 lifespan 模式一致，确保插件在应用启动时初始化、关闭时清理。存储在 app.state 中便于路由和 Agent 访问。

## Risks / Trade-offs

- **[风险] 插件初始化失败可能拖慢启动** → 每个插件设 5 秒初始化超时，超时视为不可用。
- **[风险] 过度抽象** → V1 仅有一个 NetworkPlugin，框架保持最简。不引入事件总线、依赖注入等重型机制。
- **[回滚]** 删除 plugins 模块 + revert app.py 即可恢复。
