## 1. 长期记忆 JSONL 流式加载

- [x] 1.1 将 `long_term_memory.py` 中 JSONL 全量加载改为逐行流式读取（`open()` + `for line in fh`）
- [x] 1.2 添加测试：验证 1000+ 条记忆的加载不会额外分配全文件大小的内存

## 2. 动态上下文窗口

- [x] 2.1 在 `ModelResolver` 或 provider client 上添加 `get_model_context_window() -> int | None` 方法
- [x] 2.2 将 `runner.py:910` 的硬编码 `128000` 替换为动态查询（fallback 128000）
- [x] 2.3 添加测试：验证不同模型返回正确的 context window 值

## 3. 压缩归档防碰撞

- [x] 3.1 将 `compression.py` 的归档文件名追加 UUID 短码 `_{uuid.uuid4().hex[:8]}`
- [x] 3.2 添加测试：验证同一秒内生成的两个归档文件名不同

## 4. DPI 范围校验

- [x] 4.1 将 `style_contract.py` 的 `max(300, dpi)` 改为 `max(300, min(600, dpi))` 并在截断时记录 warning
- [x] 4.2 添加测试：验证 DPI=1000 被截断到 600 并产生 warning 日志

## 5. 知识库查询可用性元数据

- [x] 5.1 修改 `vector_store.py` 的 `query()` 返回值，新增 `availability` 字段
- [x] 5.2 添加测试：未初始化时返回 `"not_ready"`，空目录返回 `"empty"`，正常返回 `"available"`

## 6. 验证

- [x] 6.1 运行 `pytest -q` 确认全部测试通过
- [x] 6.2 运行 `black --check src tests` 确认格式
- [x] 6.3 运行 `mypy src/nini` 确认类型检查通过
