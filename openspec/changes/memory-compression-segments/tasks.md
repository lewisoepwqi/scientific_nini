## 1. 数据模型与配置

- [x] 1.1 在 `src/nini/memory/compression.py` 中新增 `CompressionSegment` dataclass，包含 `summary`、`archived_count`、`created_at`、`depth` 字段（无 `archive_path`），实现 `to_dict()` 和 `from_dict()` 方法
- [x] 1.2 在 `src/nini/config.py` 中新增 `compressed_context_max_segments: int = 3` 配置项，支持 `NINI_COMPRESSED_CONTEXT_MAX_SEGMENTS` 环境变量覆盖
- [x] 1.3 在 `src/nini/agent/session.py` 的 `Session` dataclass 中新增 `compression_segments: list[dict[str, Any]] = field(default_factory=list)` 字段
- [x] 1.4 在 `Session.__post_init__` 中添加防御：`if not isinstance(self.compression_segments, list): self.compression_segments = []`

## 2. set_compressed_context 改造

- [x] 2.1 修改 `session.py` 的 `set_compressed_context()` 方法：每次调用时将新摘要封装为 `CompressionSegment(depth=0, archived_count=0, ...).to_dict()` 并 append 到 `self.compression_segments`（`archived_count` 在轻量/LLM 两条路径均先写 0，后续由调用方按需覆写）
- [x] 2.2 在 `set_compressed_context()` 中：当 `len(compression_segments) > settings.compressed_context_max_segments` 时，**无论哪条调用路径均直接丢弃最旧段**（`compression_segments.pop(0)`），并从剩余 segments 重新 join 更新 `compressed_context`；现有的 `compressed_context_max_chars` 字符截断逻辑**仅保留于此处（轻量路径兜底）**
- [x] 2.3 保持 `self.compressed_context` 的 `"\n\n---\n\n"` 追加拼接逻辑，但在 2.2 的超限丢弃后改为从 segments 重新 join 生成，不再在字符截断处重复 pop 逻辑（两套超限机制统一为：段数超限 → pop → join）

## 3. LLM 二次压缩

- [x] 3.1 在 `src/nini/memory/compression.py` 中新增 `async def try_merge_oldest_segments(session: Session, max_segments: int) -> None` 函数：当 `len(session.compression_segments) > max_segments` 时，取最旧两段的 `summary` 拼接，调用 `_llm_summarize()` 生成 depth=1 摘要
- [x] 3.2 在 `try_merge_oldest_segments()` 中：LLM 成功时用新 `CompressionSegment(depth=1)` 替换 `compression_segments` 中最旧的两段；LLM 失败（返回 None 或异常）时不再额外操作（`set_compressed_context()` 已丢弃最旧段，维持该结果即可）；捕获所有异常不向上抛出
- [x] 3.3 在 `try_merge_oldest_segments()` 结束前（无论是否合并），从最终的 `compression_segments` 重新 join 覆写 `session.compressed_context`：`"\n\n---\n\n".join(s["summary"] for s in session.compression_segments)`，此处**不应用** `compressed_context_max_chars` 截断
- [x] 3.4 在 `compress_session_history_with_llm()` 末尾调用 `await try_merge_oldest_segments(session, settings.compressed_context_max_segments)`

## 4. 持久化与加载兼容

- [x] 4.1 扩展 `session_manager.save_session_compression()`：函数签名增加可选参数 `compression_segments: list[dict] | None = None`，在写入 `meta.json` 的字段中新增 `compression_segments` 键（值不为 None 时才写入）
- [x] 4.2 在 `_auto_compress_memory()` 和手动压缩 API 端点（`src/nini/api/session_routes.py` 的 POST compress）中，调用 `save_session_compression()` 时传入 `session.compression_segments`
- [x] 4.3 扩展 `session_manager.create_session()`：从 `meta.get("compression_segments", [])` 加载字段；若字段为空列表但 `compressed_context` 非空，则 in-memory 构造一个 `depth=0`、`archived_count=0`、`summary=compressed_context` 的 segment（不写回磁盘）
- [x] 4.4 验证：旧格式会话（有 `compressed_context` 无 `compression_segments`）加载后能正常使用，下次压缩时自动写入新格式

## 5. 测试

- [x] 5.1 新建 `tests/test_compression_segments.py`，测试 `CompressionSegment.to_dict()` / `from_dict()` 往返序列化正确，字段无 `archive_path`
- [x] 5.2 测试 `set_compressed_context()` 调用后 `compression_segments` 长度增加 1，且新增段的 `depth == 0`
- [x] 5.3 测试轻量路径超限时直接丢弃：`len(segments) > max_segments` → `len` 减少 1，`compressed_context` 由剩余 segments join 生成，未调用 LLM
- [x] 5.4 测试 `try_merge_oldest_segments()`：LLM 成功时最旧两段被替换为 depth=1 段（mock `_llm_summarize`），`compressed_context` 重新 join
- [x] 5.5 测试 `try_merge_oldest_segments()`：LLM 失败时最旧段丢弃（由 `set_compressed_context()` 已处理），无异常抛出，`compressed_context` 由剩余 segments join 覆写
- [x] 5.6 测试向后兼容加载：旧格式 `meta.json`（有 `compressed_context` 无 `compression_segments`）加载后 `compression_segments` 含一个 depth=0 段，系统不报错
- [x] 5.7 测试 `save_session_compression()` + `create_session()` 往返：`compression_segments` 内容一致
- [x] 5.8 运行全量回归：`pytest tests/ -q --ignore=tests/e2e`，确保 1530+ 已有测试全部通过

## 6. 提交

- [ ] 6.1 等 A 阶段 PR（`fix/fresh-tail-and-token-trigger`）合并到 `main` 后，从 `main` 新建分支 `feat/memory-compression-segments`
- [ ] 6.2 创建 PR，base 为 `main`，描述包含变更摘要、验证步骤和回滚方法
