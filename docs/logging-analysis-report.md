# Nini 日志系统分析报告与迭代优化计划（修订版）

> 修订时间：2026-03-26
> 范围：`src/nini/` 当前代码快照
> 目标：在不破坏现有运行链路的前提下，建立可追踪、可保留、可逐步演进的日志基础设施

---

## 1. 执行摘要

### 1.1 结论

Nini 当前日志系统的核心问题不是“完全没有日志”，而是 **日志基础设施不足、上下文关联缺失、配置入口分裂**：

| 优先级 | 问题 | 当前影响 |
|--------|------|----------|
| **P0** | 日志仅输出到控制台，无文件持久化 | 进程退出后历史日志不可追溯 |
| **P0** | HTTP `request_id` 已生成，但未进入日志上下文 | 同一请求的日志无法串联 |
| **P0** | CLI `--log-level` 与应用内 `basicConfig` 分离 | Uvicorn 与应用日志级别可能不一致 |
| **P1** | `session_id` / `turn_id` / `tool_call_id` 主要靠手工拼接 | 追踪字段格式不统一，检索成本高 |
| **P1** | 存在较多 `except Exception: pass` | 部分失败路径缺少可观测性 |
| **P2** | 关键路径缺少统一耗时日志 | 性能瓶颈难以定位 |

### 1.2 已核实的现状快照

以下数据基于 2026-03-26 对当前仓库的静态扫描，已替换旧版文档中的过时统计：

```text
存在 logger 调用的 Python 文件: 80 个
logger 调用总数:              481 处
日志配置入口:                 1 处（app.py 中 basicConfig）
文件持久化处理器:             0 个
HTTP Request ID:              已生成并回传响应头，但未注入日志上下文
WebSocket connection_id:      无
except ...: pass:             39 处
logger.exception():           3 处
logger.critical():            0 处
api/routes.py 日志调用:       6 处
knowledge/ 日志调用:          95 处
workspace/manager.py:         0 处
```

### 1.3 本次修订的原则

- 先修正文档与现状偏差，再规划实施
- 优先解决基础问题，不把运维平台能力塞进 P0
- 先保证与现有 `logging.getLogger(__name__)` 兼容，再考虑增强
- 中间件只绑定当前层真正能拿到的字段，避免伪上下文

---

## 2. 现状分析（基于当前代码）

### 2.1 日志配置：单点、极简、与 CLI 分裂

当前唯一日志初始化在 [src/nini/app.py](/home/lewis/coding/scientific_nini/src/nini/app.py)：

```python
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```

对应位置：
- [app.py:39](/home/lewis/coding/scientific_nini/src/nini/app.py#L39)
- [app.py:40](/home/lewis/coding/scientific_nini/src/nini/app.py#L40)
- [app.py:41](/home/lewis/coding/scientific_nini/src/nini/app.py#L41)

同时，CLI 在 [src/nini/__main__.py](/home/lewis/coding/scientific_nini/src/nini/__main__.py) 提供了 `--log-level`，但该参数只传给 `uvicorn.run()`：

- [__main__.py:175](/home/lewis/coding/scientific_nini/src/nini/__main__.py#L175)
- [__main__.py:374](/home/lewis/coding/scientific_nini/src/nini/__main__.py#L374)
- [__main__.py:381](/home/lewis/coding/scientific_nini/src/nini/__main__.py#L381)

这意味着：

- 应用层日志级别由 `settings.debug` 决定
- Uvicorn 日志级别由 `--log-level` 决定
- 两套配置可能不一致

### 2.2 Request ID：已生成，但没有进入日志

HTTP 中间件已生成并回传 `X-Request-ID`：

- [app.py:95](/home/lewis/coding/scientific_nini/src/nini/app.py#L95)
- [app.py:100](/home/lewis/coding/scientific_nini/src/nini/app.py#L100)
- [app.py:102](/home/lewis/coding/scientific_nini/src/nini/app.py#L102)

当前能力边界：

- 已有 `request_id` 生成逻辑
- 已写入响应头
- 尚未注入日志上下文
- 尚未传播到后续业务日志

因此旧版文档中“生成但未传播”的判断成立，但“可在中间件直接统一绑定 `session_id`”不成立，因为中间件层并不总能拿到 `session_id`。

### 2.3 WebSocket：连接建立时没有连接级上下文

当前 WebSocket 入口：

- [websocket.py:58](/home/lewis/coding/scientific_nini/src/nini/api/websocket.py#L58)
- [websocket.py:82](/home/lewis/coding/scientific_nini/src/nini/api/websocket.py#L82)
- [websocket.py:83](/home/lewis/coding/scientific_nini/src/nini/api/websocket.py#L83)

现状是：

- 建连时仅记录“WebSocket 连接已建立”
- 连接握手阶段没有 `connection_id`
- `session_id` 来自后续客户端消息，而不是 `/ws` 路径或握手参数

因此，正确的设计应是：

- 连接建立时绑定 `connection_id`
- 收到具体消息并解析出 `session_id` 后，再在消息处理范围内绑定 `session_id`
- `turn_id` / `tool_call_id` 在 runner 或工具执行范围内继续下沉绑定

### 2.4 追踪字段现状：有数据实体，没有统一注入机制

代码中已经广泛存在这些业务标识：

- `session_id`
- `turn_id`
- `tool_call_id`

但它们主要用于业务对象、事件流或手工拼接日志，不等于“日志上下文已建立”。

当前更准确的表述应是：

| 字段 | 当前状态 | 备注 |
|------|----------|------|
| `request_id` | 已生成 | 仅 HTTP 响应头 |
| `connection_id` | 无 | WebSocket 连接级缺失 |
| `session_id` | 广泛存在 | 主要在业务层、部分手工拼日志 |
| `turn_id` | 广泛存在 | 主要在 Agent 事件与消息 |
| `tool_call_id` | 广泛存在 | 主要在工具事件与工具结果 |
| `user_id` | 不适合作为 P0 日志字段 | 当前请求链路无稳定主体解析 |

### 2.5 静默吞错：问题存在，但旧清单已过期

旧版文档写“19 处 `except Exception: pass`”，当前代码快照静态扫描结果为 **39 处**。

需要注意两点：

1. 这 39 处并不都同等严重
2. 很多位于资源释放、回收、清理路径

因此不应继续用“19 处静默吞错”作为摘要结论，而应改成：

- 存在较多静默吞错
- 需要按业务风险分层治理
- 先修复业务失败路径，再处理纯清理路径

### 2.6 日志覆盖：不是“知识库完全缺失”，而是分布不均

旧版文档里有两处明显失真：

- `knowledge/` 并非“完全缺失日志”
- `workspace/manager.py` 才是当前明显缺日志的模块

基于当前代码：

- `knowledge/` 下已有较多初始化、降级、检索相关日志
- `api/routes.py` 已有少量日志，但离关键 API 可观测性仍有距离
- `workspace/manager.py` 当前没有 logging 入口

建议改写为：

```text
覆盖充分:    runner.py、websocket.py
覆盖一般:    knowledge/、memory/、tools/
覆盖不足:    api/routes.py、models_routes.py、workspace/manager.py
```

### 2.7 异常日志：应优先补 `exc_info=True`，而不是只统计 `logger.exception()`

当前仓库中：

- `logger.exception()` 为 3 处
- `logger.error()` 为 56 处
- 其中并非所有 `logger.error()` 都带堆栈

因此问题表述应从：

- “`logger.exception()` 只有 1 处”

修正为：

- “关键失败路径中仍有较多 `logger.error()` 未携带 `exc_info=True`”

这更贴近真实优化目标。

---

## 3. 设计约束与修订后的目标

### 3.1 设计约束

本仓库当前约束如下：

- 已广泛使用 stdlib `logging`
- 当前以本地优先部署为主，不宜把 ELK/Loki 之类平台建设纳入 P0
- CLI 已有 `start` / `doctor`，但 `doctor` 当前职责是环境体检，不是日志运营分析
- WebSocket `session_id` 不是握手期字段

### 3.2 修订后的目标

P0-P1 阶段只做这些事：

1. 建立统一日志初始化入口
2. 打通控制台 + 文件双写
3. 让 HTTP / WebSocket / Agent / Tool 的核心日志能带上正确上下文
4. 修复高价值异常路径的可观测性
5. 为后续结构化日志保留扩展位

明确不放进 P0 的内容：

- `user_id` 统一日志上下文
- `doctor` 输出“昨日日志错误数”
- 日志采样
- ELK / Loki / Datadog 接入
- 为了结构化而一次性重写全部 logger 调用

---

## 4. 推荐方案

### 4.1 总体建议

**Phase 1 先基于 stdlib logging 完成统一配置与上下文传播，不在第一阶段强依赖 structlog。**

原因：

- 与现有代码最兼容
- 不会引入“伪零迁移”问题
- 能先解决 80% 的实际问题：持久化、级别统一、上下文关联、异常堆栈
- 后续若确实需要 JSON 日志和更强上下文字段，再增量引入 structlog 或自定义 formatter

### 4.2 目标架构（最小可行版）

```text
HTTP 中间件
  -> 生成/接收 request_id
  -> 绑定 request_id

WebSocket 连接入口
  -> 生成 connection_id
  -> 绑定 connection_id

消息处理/路由层
  -> 当拿到 session_id 时绑定 session_id

Agent Runner
  -> 绑定 turn_id

Tool 执行封装层
  -> 绑定 tool_call_id

统一 logging 配置
  -> Console 输出
  -> File 输出
  -> 同一日志格式
  -> 统一 log level
```

### 4.3 关键设计决策

#### 决策 1：`session_id` 不在 HTTP 中间件统一绑定

原因：

- 并非所有 HTTP 请求都带 `session_id`
- WebSocket 握手阶段也没有稳定 `session_id`
- 在拿不到字段时硬绑，只会制造空值和误导

#### 决策 2：P0 不引入 `user_id`

原因：

- 当前鉴权只验证 API key / cookie 是否有效
- 没有稳定的请求主体解析链路
- 把 `user_id` 放进目标日志字段会造成伪设计

#### 决策 3：P0 只做文件持久化，不做日志运营命令

原因：

- `nini logs`、`doctor` 错误统计属于运维便利性
- 当前更大的问题是“日志还没稳定落盘、上下文还没打通”
- 先把基础设施做实，再考虑查看命令

#### 决策 4：结构化日志分两步走

建议路径：

- Phase 1：统一 formatter，保留文本格式，确保可读和兼容
- Phase 3：再评估 JSON formatter 或 structlog 接入

这样可以避免第一阶段引入大面积 logger API 风格不兼容。

---

## 5. 分阶段迭代计划

### 5.1 Phase 1（P0）：统一配置 + 文件持久化 + 核心上下文

**目标**：先让日志“可保存、可关联、可统一控制”。

#### 范围

- 新增统一日志配置模块，例如 `src/nini/logging_config.py`
- 将 `app.py` 中的 `basicConfig()` 替换为统一初始化
- 对齐 CLI `--log-level` 与应用日志级别
- 增加文件输出与轮转
- 引入 `contextvars`，但只绑定当前层真实可得字段

#### 建议绑定策略

| 层级 | 绑定字段 |
|------|----------|
| HTTP 中间件 | `request_id` |
| WebSocket 建连 | `connection_id` |
| WebSocket 消息处理 | `session_id` |
| Runner 单轮执行 | `turn_id` |
| 工具执行封装层 | `tool_call_id` |

#### 建议输出策略

- 控制台：文本格式，优先人类可读
- 文件：文本格式或 JSON Lines 二选一
- 文件轮转：优先一种简单策略，不混用“按日期命名活跃文件”和“按大小分片”两套语义

建议先采用：

- `TimedRotatingFileHandler`
- 固定基名，例如 `nini.log`
- 轮转后由 handler 自动追加日期后缀

如果确实要求 `.jsonl` 与稳定文件名，再单独设计，不应在文档中混写两套方案。

#### 预计改动文件

- `src/nini/logging_config.py`（新）
- `src/nini/app.py`
- `src/nini/__main__.py`
- `src/nini/api/websocket.py`
- `src/nini/config.py`
- `tests/` 下新增日志初始化与上下文传播测试

### 5.2 Phase 2（P1）：异常可观测性补齐

**目标**：减少“失败了但看不明白”的情况。

#### 范围

- 梳理高价值 `except Exception: pass`
- 优先修复业务失败路径
- 为关键 `logger.error()` 补 `exc_info=True`
- 为少量关键模块补最基本的开始/失败/结束日志

#### 优先级建议

1. `runner.py`
2. `api/websocket.py`
3. `api/routes.py`
4. `agent/model_resolver.py`
5. `tools/registry.py`
6. `workspace/manager.py`

#### 静默吞错治理原则

- 清理/回收路径：允许保守忽略，但建议至少 `debug` 记录
- 业务失败路径：不得静默吞错
- 不强求一次性清零 39 处，先按风险分层

### 5.3 Phase 3（P2）：关键耗时与结构化增强

**目标**：提升定位性能问题的能力。

#### 关键耗时点

- Agent 单轮执行耗时
- 模型调用耗时
- 工具执行耗时
- 沙箱执行耗时
- 检索耗时

#### 结构化增强建议

此阶段再二选一：

- 方案 A：保持 stdlib logging，引入 JSON formatter
- 方案 B：在兼容评估通过后引入 structlog

是否引入 structlog 的判断标准：

- 是否确实需要稳定 JSON 字段输出
- 是否接受对少量关键 logger 调用风格做约束
- 是否愿意补足 Uvicorn / 第三方日志桥接测试

### 5.4 Phase 4（P3，可选）：运维便利性

**目标**：提升排障效率，但不阻塞主流程。

可选项：

- `nini logs` 查看命令
- 基础日志目录体检
- 简单过滤脚本或开发辅助命令

不建议在这一阶段之前修改 `doctor` 语义为“日志质量巡检”。

---

## 6. 实施任务拆解

### 6.1 Phase 1 任务

| 序号 | 任务 | 文件 |
|------|------|------|
| 1.1 | 新建统一日志配置模块 | `src/nini/logging_config.py` |
| 1.2 | 应用启动改为调用统一日志初始化 | `src/nini/app.py` |
| 1.3 | CLI `--log-level` 传入应用配置，而不只传给 Uvicorn | `src/nini/__main__.py` |
| 1.4 | HTTP 中间件绑定 `request_id` | `src/nini/app.py` |
| 1.5 | WebSocket 建连绑定 `connection_id`，消息处理绑定 `session_id` | `src/nini/api/websocket.py` |
| 1.6 | 增加日志目录与日志级别相关配置 | `src/nini/config.py` |
| 1.7 | 增加日志初始化、文件输出、上下文传播测试 | `tests/` |

### 6.2 Phase 2 任务

| 序号 | 任务 | 文件 |
|------|------|------|
| 2.1 | 梳理并标记 39 处静默吞错 | `src/nini/**` |
| 2.2 | 先修复业务失败路径中的静默吞错 | `runner.py`、`websocket.py`、`routes.py` 等 |
| 2.3 | 为关键 `logger.error()` 增补 `exc_info=True` | 关键模块 |
| 2.4 | 为 `workspace/manager.py` 增加基础日志 | `src/nini/workspace/manager.py` |

### 6.3 Phase 3 任务

| 序号 | 任务 | 文件 |
|------|------|------|
| 3.1 | 在 runner 增加单轮耗时日志 | `src/nini/agent/runner.py` |
| 3.2 | 在模型调用链增加耗时日志 | `src/nini/agent/model_resolver.py` |
| 3.3 | 在工具注册与执行链增加耗时日志 | `src/nini/tools/registry.py` |
| 3.4 | 在检索与沙箱增加耗时日志 | `knowledge/`、`sandbox/` |
| 3.5 | 评估 JSON formatter / structlog | 配置模块与测试 |

---

## 7. 风险与回滚

### 7.1 主要风险

| 风险 | 说明 | 缓解方式 |
|------|------|----------|
| 日志重复输出 | 同时配置 root logger 与 Uvicorn logger 时容易重复 | 增加启动测试，明确 handler 挂载位置 |
| 上下文泄漏 | `contextvars` 未清理可能跨请求串字段 | 每次请求/消息处理前清理并重新绑定 |
| 文件句柄/权限问题 | `data/logs` 不可写会导致启动异常 | 启动阶段回退到 console，并输出明确 warning |
| 结构化方案不兼容 | 过早引入 structlog 会影响旧 logger 调用 | 推迟到 Phase 3 再评估 |

### 7.2 回滚策略

- Phase 1 采用增量替换，保留 stdlib logging 基础
- 若文件输出出现问题，可临时关闭 FileHandler，仅保留 ConsoleHandler
- 若上下文注入影响不稳定，可先保留 `request_id`，推迟 `session_id` / `turn_id` 自动注入

---

## 8. 验收标准

### Phase 1 验收

- `nini start` 启动后可同时看到控制台日志和文件日志
- `--log-level` 对应用日志与 Uvicorn 日志生效一致
- HTTP 请求产生的日志可带 `request_id`
- WebSocket 连接日志可带 `connection_id`
- 处理具体会话消息时可带 `session_id`

### Phase 2 验收

- 关键业务失败路径不再静默吞错
- 核心错误日志包含 traceback
- `workspace/manager.py` 有最基本的操作日志

### Phase 3 验收

- 核心执行链路具备耗时日志
- 结构化输出方案经测试验证后再启用

---

## 9. 下一步建议

建议直接按 Phase 1 开始实施，不再等待额外大设计：

1. 先完成统一日志初始化与文件持久化
2. 再补 `request_id` / `connection_id` / `session_id` 分层绑定
3. 随后处理关键异常路径和 `exc_info=True`

这条路径最符合当前仓库现状，也能最快把日志系统从“能打印”推进到“能排障”。
