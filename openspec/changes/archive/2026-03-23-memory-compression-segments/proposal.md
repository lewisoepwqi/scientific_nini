## Why

当会话压缩多轮后，`compressed_context` 超出 2000 字符上限时，当前代码直接丢弃最旧的摘要段（`segments.pop(0)`），导致历史知识永久失真、越压越失真。通过引入两级 `CompressionSegment` 结构，在 LLM 异步压缩路径末尾对最旧两段做二次压缩替代直接丢弃，可以在有限 token 预算内保留更完整的历史语义。

## What Changes

- 新增 `CompressionSegment` dataclass（`compression.py`），字段：`summary`、`archived_count`、`created_at`、`depth`（0=直接摘要，1=摘要的摘要）
- `Session` dataclass 新增 `compression_segments: list[dict]` 字段，与 `compressed_context` 并存（向后兼容）
- `set_compressed_context()` 同步维护 `compression_segments` 列表；当段数超过 `compressed_context_max_segments` 时，**同步路径（轻量压缩）直接丢弃最旧段**，**异步路径（LLM 压缩）由 `try_merge_oldest_segments()` 在末尾触发 LLM 二次压缩**，失败时回退丢弃
- 新增 `async try_merge_oldest_segments(session)` 函数，封装二次压缩逻辑，在 `compress_session_history_with_llm()` 末尾调用
- `config.py` 新增 `compressed_context_max_segments: int = 3`；现有 `compressed_context_max_chars` 字符截断逻辑仅保留于轻量路径，LLM 路径改由段数控制
- `session_manager` 的 `save_session_compression()` 和 `create_session()` 扩展以持久化并加载 `compression_segments`；旧 `meta.json`（无该字段）向后兼容，自动从现有 `compressed_context` 迁移为单段列表

## Capabilities

### New Capabilities

- `compression-segments`：两级压缩段结构，管理 `CompressionSegment` 的生命周期（积累、合并、持久化、加载），是对现有会话压缩机制的增强层

### Modified Capabilities

（无规格级行为变更，本次修改为实现层优化）

## Impact

- `src/nini/memory/compression.py`：新增 `CompressionSegment` dataclass、`try_merge_oldest_segments()` 异步函数
- `src/nini/agent/session.py`：Session dataclass 扩展、`set_compressed_context()` 维护 segments 并调整超限行为、`save_session_compression()` / `create_session()` 扩展
- `src/nini/config.py`：新增 `compressed_context_max_segments` 配置项
- `data/sessions/*/meta.json`：schema 扩展，新增 `compression_segments` 字段（只写不读旧会话时保持兼容）
- 测试：新增 `tests/test_compression_segments.py`
