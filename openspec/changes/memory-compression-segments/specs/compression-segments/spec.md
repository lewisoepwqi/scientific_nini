## ADDED Requirements

### Requirement: CompressionSegment 结构体
系统 SHALL 定义 `CompressionSegment` dataclass，用于表示单轮压缩产生的摘要段，包含字段：`summary`（str）、`archived_count`（int）、`created_at`（ISO 8601 str）、`depth`（int，0=直接摘要/1=摘要的摘要）。该 dataclass 须提供 `to_dict()` 和 `from_dict()` 方法以支持 JSON 序列化。

#### Scenario: 创建 depth=0 段
- **WHEN** 调用 `compress_session_history_with_llm()` 或 `compress_session_history()` 完成一轮压缩
- **THEN** 系统创建一个 `depth=0` 的 `CompressionSegment`，`archived_count` 等于本轮归档消息数，`created_at` 为当前 UTC 时间

#### Scenario: 序列化为 dict
- **WHEN** 调用 `CompressionSegment.to_dict()`
- **THEN** 返回包含所有字段的普通 dict，可直接 `json.dumps` 序列化

### Requirement: Session.compression_segments 字段
`Session` dataclass SHALL 新增 `compression_segments: list[dict[str, Any]]` 字段（默认空列表），与现有 `compressed_context: str` 字段并存，两者均维护但各自独立。`Session.__post_init__` 须确保该字段始终为 `list` 类型（防御 meta.json 中的 `null` 值）。

#### Scenario: 新建会话的初始状态
- **WHEN** 创建一个新的 `Session` 实例
- **THEN** `compression_segments` 为空列表，`compressed_context` 为空字符串

#### Scenario: 调用 set_compressed_context 后 segments 同步增加
- **WHEN** 调用 `session.set_compressed_context(summary)` 且 summary 非空
- **THEN** `session.compression_segments` 新增一条 `depth=0` 的 segment，且 `len(compression_segments)` 增加 1

### Requirement: 段数超限时的行为（按路径区分）
当 `len(Session.compression_segments) > settings.compressed_context_max_segments` 时，系统行为按压缩路径不同：

- **轻量路径**（同步）：`set_compressed_context()` SHALL 直接丢弃最旧一段，`len(compression_segments)` 减少 1
- **LLM 路径**（异步）：`try_merge_oldest_segments()` SHALL 尝试调用 LLM 将最旧的两段合并为一个 `depth=1` 的新段；LLM 失败时，维持轻量路径已丢弃的结果（不再额外操作）

无论哪条路径，超限处理完成后 `session.compressed_context` 必须与 `compression_segments` 保持一致。

#### Scenario: 轻量路径超限直接丢弃
- **WHEN** `compress_session_history()` 执行后 `len(compression_segments) > compressed_context_max_segments`
- **THEN** 最旧一段被丢弃，`len(compression_segments)` 减少 1，`compressed_context` 由剩余 segments 重新 join 生成，系统不调用 LLM

#### Scenario: LLM 路径合并成功
- **WHEN** `compress_session_history_with_llm()` 触发 `try_merge_oldest_segments()` 且 `_llm_summarize()` 返回非空摘要
- **THEN** 最旧两段被替换为一个 `depth=1` 的新段，`len(compression_segments)` 净减少 1，`compressed_context` 由更新后的 segments 重新 join 生成（不应用 `compressed_context_max_chars` 截断）

#### Scenario: LLM 路径合并失败
- **WHEN** `compress_session_history_with_llm()` 触发 `try_merge_oldest_segments()` 且 `_llm_summarize()` 返回 None 或抛出异常
- **THEN** `set_compressed_context()` 已丢弃的最旧段结果被保留，`len(compression_segments)` 净减少 1，系统不抛出异常，`compressed_context` 由剩余 segments join 生成

#### Scenario: 段数未超限时不触发合并
- **WHEN** `len(compression_segments) <= compressed_context_max_segments`
- **THEN** 不调用 LLM，不修改 segments 列表

### Requirement: compression_segments 持久化与加载
`session_manager.save_session_compression()` SHALL 将 `compression_segments` 字段写入 `meta.json`；`create_session()` SHALL 从 `meta.json` 读取并恢复该字段。

#### Scenario: 保存后重新加载
- **WHEN** 调用 `save_session_compression()` 后，再次调用 `create_session()` 加载同一会话
- **THEN** 重新加载的 session 的 `compression_segments` 与保存前内容一致

#### Scenario: 旧格式会话向后兼容
- **WHEN** `meta.json` 存在 `compressed_context` 字段但不含 `compression_segments` 字段
- **THEN** `create_session()` 加载后：若 `compressed_context` 为空则 `compression_segments` 为空列表；若 `compressed_context` 非空则自动构造含一个 `depth=0`、`archived_count=0`、`summary=compressed_context` 的单段列表；系统不抛出任何异常

### Requirement: compressed_context_max_segments 配置项
系统 SHALL 在 `Settings` 中提供 `compressed_context_max_segments: int` 配置项，默认值为 3，允许通过环境变量 `NINI_COMPRESSED_CONTEXT_MAX_SEGMENTS` 覆盖。该配置项仅控制 LLM 路径的二次压缩触发；轻量路径的字符截断由现有 `compressed_context_max_chars` 控制。

#### Scenario: 使用默认值
- **WHEN** 环境变量 `NINI_COMPRESSED_CONTEXT_MAX_SEGMENTS` 未设置
- **THEN** `settings.compressed_context_max_segments == 3`

#### Scenario: 环境变量覆盖
- **WHEN** 设置 `NINI_COMPRESSED_CONTEXT_MAX_SEGMENTS=5`
- **THEN** `settings.compressed_context_max_segments == 5`
