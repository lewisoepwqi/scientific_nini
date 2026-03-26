## Context

当前日志初始化集中在 `src/nini/app.py` 的 `logging.basicConfig()`，只能输出到控制台，且日志级别由 `settings.debug` 决定。CLI `nini start --log-level` 只影响 `uvicorn.run()`，导致应用日志和 Uvicorn 日志存在双轨配置。HTTP 中间件已生成 `X-Request-ID`，但没有进入日志上下文；WebSocket 在连接建立阶段也没有连接级标识。

这次设计是一个跨模块变更，涉及 `app.py`、`__main__.py`、`api/websocket.py`、`config.py` 和新增的日志配置模块，因此需要先明确统一入口、字段绑定层级和回滚策略。

## Goals / Non-Goals

**Goals:**

- 建立统一日志初始化入口，替代 `app.py` 内的裸 `basicConfig()`
- 同时支持控制台输出和本地文件持久化
- 对齐 CLI `--log-level` 与应用层日志级别
- 为 HTTP / WebSocket / 会话处理链路提供最小可用的上下文绑定能力
- 保持现有 `logging.getLogger(__name__)` 调用方式兼容

**Non-Goals:**

- 不在本 change 中引入日志查看命令或 `doctor` 日志巡检
- 不在本 change 中引入日志采样、外部日志平台或告警系统
- 不要求将现有日志全部改为结构化 JSON
- 不引入 `user_id` 作为基础日志字段
- 不在本 change 中系统性治理全部 `except Exception: pass`

## Decisions

### 决策 1：Phase 1 继续基于 stdlib logging，而不是立即引入 structlog

原因：

- 现有代码广泛使用 stdlib logger，兼容性最好
- 当前最急迫的问题是统一入口、持久化和上下文关联，而不是日志库替换
- 直接引入 structlog 容易把“零迁移”和“新调用风格”混在一起，增加实现风险

备选方案：

- 方案 A：立即引入 structlog
  - 优点：后续结构化能力更强
  - 缺点：需要额外桥接和兼容性验证，不适合本阶段最小闭环
- 方案 B：仅保留现状 `basicConfig()`
  - 优点：改动最少
  - 缺点：无法解决持久化、级别分裂和上下文传播问题

结论：先以 stdlib logging 完成基础设施，后续再评估结构化增强。

### 决策 2：新增集中式 `logging_config.py`

在 `src/nini/logging_config.py` 中集中提供初始化函数，例如 `setup_logging()`，负责：

- 创建控制台和文件 handler
- 配置统一 formatter
- 处理 root logger、应用 logger 与 Uvicorn logger 的级别对齐
- 在重复初始化时安全幂等

原因：

- 避免日志配置继续散落在 `app.py` 和 CLI 入口
- 便于测试初始化行为
- 后续无论是否引入 JSON formatter，都有统一落点

### 决策 3：上下文字段采用分层绑定，而不是全局一次性绑定

绑定策略：

- HTTP 中间件：绑定 `request_id`
- WebSocket 建连：绑定 `connection_id`
- WebSocket 消息处理：在拿到会话消息后绑定 `session_id`
- Runner 单轮执行：绑定 `turn_id`
- 工具执行封装层：绑定 `tool_call_id`

原因：

- `session_id` 并非所有 HTTP 请求都有
- WebSocket 握手阶段也拿不到稳定 `session_id`
- 在错误层级绑定字段会产生空值、伪上下文和误导

备选方案：

- 在 HTTP 中间件或 WebSocket 握手阶段统一绑定所有字段
  - 缺点：字段来源不真实，容易前后矛盾

结论：按实际拿到字段的层级逐步下沉绑定。

### 决策 4：文件持久化优先采用单一轮转语义

本 change 优先采用简单稳定的本地文件轮转策略，例如 `TimedRotatingFileHandler` 配合固定基名文件。

原因：

- 当前目标是先让日志可靠落盘
- 固定基名 + 自动轮转后缀的语义最简单
- 避免把“日期命名活跃文件”“按大小分片”“JSONL 命名规范”一次性揉进第一阶段

备选方案：

- 同时要求按日期命名当前文件并支持大小分片
  - 缺点：实现复杂度和配置歧义都更高

结论：先使用一种简单可测的轮转策略，后续需要更严格文件命名时再单独扩展。

### 决策 5：CLI 日志级别通过应用配置链路显式传递

`--log-level` 不应只传给 `uvicorn.run()`，还应进入应用的统一日志初始化逻辑。

实现方向可以是：

- 在 `create_app()` / lifespan 可读取的配置位置注入目标日志级别
- 或通过环境变量 / app state / 工厂参数传递

原则是：应用日志和 Uvicorn 日志必须使用同一来源的目标级别。

## Risks / Trade-offs

- [日志重复输出] → 统一配置 root / Uvicorn logger 时可能出现重复 handler；通过集中初始化和测试覆盖缓解。
- [上下文泄漏] → 若上下文容器未在请求或消息处理前清理，字段可能串到下一次处理；通过显式清理和作用域绑定缓解。
- [文件不可写] → `data/logs` 不可写会导致启动期异常；通过回退到控制台并发出 warning 缓解。
- [配置传递复杂] → `--log-level` 从 CLI 传入应用工厂可能涉及现有启动路径；通过保持参数最小化和补 CLI 测试缓解。
- [未来结构化迁移成本] → 先不引入 structlog 会把 JSON 结构化能力推迟到后续；这是当前阶段为降低复杂度所接受的权衡。

## Migration Plan

1. 新增 `logging_config.py`，在不改业务 logger 调用方式的前提下提供统一初始化函数。
2. 修改 `app.py` 启动生命周期，改为调用统一初始化函数。
3. 调整 `__main__.py`，让 `--log-level` 同时影响应用日志和 Uvicorn 日志。
4. 在 HTTP 中间件、WebSocket 建连与消息处理链路接入分层上下文绑定。
5. 增加测试覆盖日志文件生成、级别对齐和上下文字段作用域。

回滚方式：

- 若文件 handler 或上下文绑定引入不稳定性，可退回到仅控制台输出的集中初始化版本
- 若 CLI 级别传递路径出现兼容问题，可暂时保留 Uvicorn 现有参数行为，同时关闭应用层级别透传

## Open Questions

- `--log-level` 最终通过应用工厂参数还是环境变量注入，哪种方式与现有启动方式更契合
- 文件日志第一阶段是否直接使用文本格式，还是保留可选 JSON formatter 开关
