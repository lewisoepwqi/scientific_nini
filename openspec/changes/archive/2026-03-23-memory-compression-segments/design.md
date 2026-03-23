## Context

`Session.set_compressed_context()` 每轮压缩后将摘要文本追加到 `compressed_context` 字符串，当总长度超过 `compressed_context_max_chars`（默认 2000 字符）时，直接 `pop(0)` 丢弃最旧的摘要段，导致历史信息永久丢失且越压越失真。

现有约束：
- `set_compressed_context()` 是同步方法，被 `compress_session_history()`（同步）和 `compress_session_history_with_llm()`（异步）共同调用
- `meta.json` 已有 `compressed_context` 字段，旧会话必须向后兼容
- LLM 摘要调用（`_llm_summarize()`）为异步操作，失败率约 5%（需 fallback）

## Goals / Non-Goals

**Goals:**
- 用结构化 `CompressionSegment` 替代纯字符串拼接，保留 depth 层级元数据
- LLM 压缩路径：当段数超限时调用 LLM 对最旧两段做 depth=1 二次压缩，而非直接丢弃
- 旧会话无缝兼容（无需迁移脚本）
- 同步调用链不破坏（`set_compressed_context` 保持同步签名）

**Non-Goals:**
- 不实现三层以上的 DAG 压缩（保留 depth≤1 两级即可）
- 不修改 `context_builder.py` 中 `compressed_context` 的注入方式
- 轻量路径不引入 LLM 调用

## Decisions

### D1：`compression_segments` 使用 `list[dict]` 而非 `list[CompressionSegment]`

**选择**：在 `Session` dataclass 中存储 `list[dict[str, Any]]`，而非直接存 dataclass 实例。

**理由**：Session 字段通过 `json.dumps` 序列化到 `meta.json`，dataclass 实例无法直接序列化。用 dict 存储后调用 `CompressionSegment.from_dict()` / `.to_dict()` 转换，无需引入额外 JSON encoder。

**替代方案**：使用 Pydantic BaseModel —— 引入额外依赖，且 Session 中其他字段均为原始类型，风格不一致。

### D2：二次压缩在 `compress_session_history_with_llm()` 末尾调用，不改 `set_compressed_context` 签名

**选择**：新增 `async def try_merge_oldest_segments(session)` 函数，在已是异步的 `compress_session_history_with_llm()` 末尾 `await`，`set_compressed_context()` 保持同步签名。

**理由**：`set_compressed_context()` 被同步路径（`compress_session_history()`）调用，改为 async 会强制整条调用链变 async，影响范围过大。LLM merge 只有在 LLM 压缩模式下才有意义，放在异步函数末尾调用刚好匹配语义。

**两条路径的超限行为**：

| 路径 | 段数超限时的行为 |
|------|----------------|
| 轻量路径（同步）| `set_compressed_context()` 直接丢弃最旧段，等同于修改前行为 |
| LLM 路径（异步）| `set_compressed_context()` 先丢弃最旧段（临时状态），随后 `try_merge_oldest_segments()` 尝试 LLM 合并最旧两段；LLM 失败则维持丢弃结果 |

注：轻量路径与 LLM 路径均在超限时丢弃，区别在于 LLM 路径额外尝试用合并替代丢弃，是一种"尽力而为"的优化。

### D3：向后兼容策略：in-memory 自动迁移，不写回磁盘

**选择**：`create_session()` 加载时，若 `meta.json` 含 `compressed_context` 但无 `compression_segments`，in-memory 构造一个 depth=0 的 segment 记录（`archived_count=0`，`summary=compressed_context` 全文），不主动写回 `meta.json`。

**理由**：避免迁移写回引入不必要的 I/O，且下次压缩发生时自然会写入新格式，渐进式迁移。

### D4：`compressed_context` 字段继续维护（双写）

**选择**：`set_compressed_context()` 继续更新 `compressed_context` 字符串（用于 `context_builder.py` 中的注入），同时 append 到 `compression_segments`；`try_merge_oldest_segments()` 合并后从 segments 重新 join 覆写 `compressed_context`。

**理由**：`context_builder.py` 直接读取 `session.compressed_context`，该字段变更会影响 LLM 上下文注入。保持双写可以零修改 context_builder，降低本次变更范围。

### D5：`compressed_context_max_chars` 与 `compressed_context_max_segments` 的分工

**选择**：两个配置分管两条路径，不互相替代。

| 配置项 | 生效路径 | 作用 |
|--------|---------|------|
| `compressed_context_max_chars`（已有，2000）| 轻量路径 | 字符级安全截断，防止单段过长 |
| `compressed_context_max_segments`（新增，默认 3）| LLM 路径 | 段数级控制，触发 LLM 二次压缩 |

LLM 路径中，`try_merge_oldest_segments()` 在合并完成后，从更新后的 segments 重新 join 生成 `compressed_context`，**此时不再应用 `compressed_context_max_chars` 截断**（segments 已被合并控制在合理长度）。

**`compressed_context_max_chars` 不废弃**：它对轻量路径仍是必要的安全兜底；若未来移除，需独立变更。

## Risks / Trade-offs

- **LLM merge 失败回退为丢弃**：`try_merge_oldest_segments()` 调用 LLM 失败时维持 `set_compressed_context()` 已丢弃的结果，与修改前行为相同。最坏情况退化到现有行为，不引入新的信息丢失。
- **双写可能漂移**：`compressed_context` 在 `set_compressed_context()` 中一次、在 `try_merge_oldest_segments()` 中再次被写入，两次写入均有意义（前者是中间态，后者是最终态）。测试覆盖合并后一致性验证。
- **轻量路径不受益于 LLM 合并**：多轮轻量压缩仍会丢弃最旧段，接受这个 trade-off，轻量路径本身成本低，LLM merge 是 LLM 路径的专属增强。

## Migration Plan

无需迁移脚本。`create_session()` 加载时 in-memory 兼容旧格式，下次压缩时新格式自动写入。

回滚：删除 `compression_segments` 字段读写代码即可，`compressed_context` 字段全程保留。

## Open Questions

（无）
