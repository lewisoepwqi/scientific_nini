## Context

代码审查发现 5 个 P2/P3 级效率和可观测性问题。这些改动互相独立，可并行实施，也可按优先级逐个推进。均为内部优化，不涉及 API 变更。

## Goals / Non-Goals

**Goals:**
- 长期记忆 JSONL 大文件加载不 OOM
- context_ratio 在不同模型下计算准确
- 并发压缩不会文件覆盖
- DPI 极端值不导致内存爆炸
- 知识检索调用方可区分"无结果"和"系统未就绪"

**Non-Goals:**
- 不重构记忆存储架构（JSONL → SQLite 迁移是独立议题）
- 不修改 ModelResolver 的 fallback 链
- 不扩展知识检索的 API 接口

## Decisions

### D1: JSONL 流式加载

将 `long_term_memory.py` 中的全量加载：
```python
for line in entries_file.read_text(encoding="utf-8").strip().split("\n"):
```
改为逐行流式读取：
```python
with open(entries_file, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        ...
```

内存占用从 O(全文件) 降至 O(单行)。

### D2: 动态上下文窗口

将 `runner.py:910` 的硬编码：
```python
self._context_ratio = min(1.0, input_tokens / 128000)
```
改为从 ModelResolver 获取：
```python
context_window = self._resolver.get_model_context_window() or 128000
self._context_ratio = min(1.0, input_tokens / context_window)
```

需在 `ModelResolver` 或 provider client 上添加 `get_model_context_window() -> int | None` 方法，返回当前活跃模型的 context window 大小。对于无法确定的本地模型，fallback 到 128000。

### D3: 归档文件名防碰撞

将 `compression.py` 中的：
```python
archive_path = archive_dir / f"compressed_{_now_ts()}.json"
```
改为：
```python
archive_path = archive_dir / f"compressed_{_now_ts()}_{uuid.uuid4().hex[:8]}.json"
```

### D4: DPI 范围校验

将 `style_contract.py` 中的：
```python
dpi=max(300, dpi),
```
改为：
```python
clamped_dpi = max(300, min(600, dpi))
if clamped_dpi != dpi:
    logger.warning("DPI 值 %d 超出范围，已截断至 %d", dpi, clamped_dpi)
```

### D5: 知识库查询可用性元数据

在 `vector_store.py` 的 `query()` 方法返回值中增加 `availability` 字段：
- `"available"` — 索引已加载，查询正常执行
- `"not_ready"` — llama-index 未安装或索引加载失败
- `"empty"` — 知识目录无文件

## Risks / Trade-offs

- **[JSONL 大文件编码兼容]** → 逐行读取依赖文件编码一致。Mitigation：显式指定 `encoding="utf-8"`，与现有行为一致。
- **[context window 查询开销]** → 每次迭代查询 ModelResolver。Mitigation：context window 是静态值，可缓存；或仅在模型切换时更新。
- **[UUID 文件名长度]** → 文件名增加 9 个字符。Mitigation：对文件系统无影响。
