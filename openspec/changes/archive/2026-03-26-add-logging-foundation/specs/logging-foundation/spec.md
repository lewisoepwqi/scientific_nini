## ADDED Requirements

### Requirement: 系统必须通过统一入口初始化应用日志

系统 MUST 使用统一的日志初始化入口配置应用日志，而不是在多个启动路径中各自配置日志行为。

#### Scenario: 应用启动时使用统一日志配置
- **WHEN** `nini start` 启动应用
- **THEN** 系统通过统一日志初始化入口配置应用日志
- **AND** 不再依赖 `app.py` 内部的裸 `basicConfig()` 作为唯一初始化方式

#### Scenario: CLI 日志级别与应用日志一致
- **WHEN** 用户通过 `nini start --log-level debug` 指定日志级别
- **THEN** Uvicorn 日志与应用日志使用一致的目标级别
- **AND** 不得出现 Uvicorn 与应用日志级别来源分裂

### Requirement: 系统必须支持本地文件日志持久化

系统 MUST 在保留控制台输出的同时，将运行期日志写入本地文件，并提供基础轮转能力。

#### Scenario: 启动后生成日志文件
- **WHEN** 应用成功启动并产生运行日志
- **THEN** 系统在本地日志目录中写入日志文件
- **AND** 控制台日志输出仍保持可用

#### Scenario: 文件日志启用基础轮转
- **WHEN** 日志文件达到配置的轮转条件
- **THEN** 系统自动轮转日志文件
- **AND** 不得要求人工手动清理当前活跃日志文件才能继续运行

### Requirement: 系统必须为 HTTP 与 WebSocket 链路提供最小上下文传播

系统 MUST 按字段真实可得的层级传播日志上下文，至少覆盖 `request_id`、`connection_id` 和 `session_id`。

#### Scenario: HTTP 请求日志可关联 request_id
- **WHEN** 系统处理一个 HTTP 请求
- **THEN** 该请求关联的日志可携带 `request_id`
- **AND** 响应头继续返回同一个 `X-Request-ID`

#### Scenario: WebSocket 连接日志可关联 connection_id
- **WHEN** 客户端建立新的 WebSocket 连接
- **THEN** 该连接范围内的日志可携带 `connection_id`

#### Scenario: 会话消息处理日志可关联 session_id
- **WHEN** WebSocket 消息已解析出 `session_id`
- **THEN** 后续该次消息处理链路中的日志可携带 `session_id`
- **AND** 系统不得要求在握手阶段预先提供 `session_id`

### Requirement: 日志基础设施必须保持现有 logger 调用兼容

系统 MUST 在引入统一日志配置与上下文传播后，继续兼容现有基于 stdlib `logging` 的模块级 logger 调用方式。

#### Scenario: 现有模块级 logger 继续工作
- **WHEN** 现有模块通过 `logging.getLogger(__name__)` 输出日志
- **THEN** 日志仍能正常输出到控制台与文件
- **AND** 不要求业务代码一次性迁移到新的 logger API 风格
