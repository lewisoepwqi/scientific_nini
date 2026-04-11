## 1. MemoryProvider ABC

- [ ] 1.1 创建 `tests/memory/__init__.py`（空文件，建立测试包）
- [ ] 1.2 编写 `tests/memory/test_memory_provider.py`：不可实例化抽象类、未实现抽象方法的子类不可实例化、完整子类可实例化且可选钩子有默认值
- [ ] 1.3 运行测试，确认失败（`ModuleNotFoundError`）
- [ ] 1.4 创建 `src/nini/memory/provider.py`，实现 `MemoryProvider` ABC（`name`、`initialize`、`get_tool_schemas` 为抽象；其余钩子有默认实现）
- [ ] 1.5 运行测试，确认全部通过
- [ ] 1.6 提交：`feat(memory): 添加 MemoryProvider ABC`

## 2. MemoryManager 编排层

- [ ] 2.1 编写 `tests/memory/test_memory_manager.py`：fencing 函数（空输入/非空输入/嵌套标签剥离）、provider 注册规则（内置 OK、多个外部 provider 均可注册）、工具路由、prefetch_all 汇总、provider 异常隔离、全局单例 get/set
- [ ] 2.2 运行测试，确认失败
- [ ] 2.3 创建 `src/nini/memory/manager.py`：`sanitize_context`、`build_memory_context_block`、`MemoryManager`（add_provider/build_system_prompt/prefetch_all/sync_all/on_session_end/on_pre_compress/get_all_tool_schemas/handle_tool_call/initialize_all/shutdown_all）、`get_memory_manager`/`set_memory_manager` 全局单例
- [ ] 2.4 运行测试，确认全部通过
- [ ] 2.5 提交：`feat(memory): 添加 MemoryManager 编排层`

## 3. MemoryStore — Schema 初始化

- [ ] 3.1 编写 `tests/memory/test_memory_store.py`（schema 部分）：`facts` 表存在、WAL 模式开启、必要列齐全、`research_profiles` 表存在
- [ ] 3.2 运行测试，确认失败
- [ ] 3.3 创建 `src/nini/memory/memory_store.py`，实现 `MemoryStore.__init__`：WAL、`_SCHEMA_SQL`（facts + research_profiles + 索引）、`_FTS5_SQL`（虚拟表 + 三个触发器）、FTS5 可用性探测、`json_extract` 索引（失败静默跳过）
- [ ] 3.4 运行测试，确认通过
- [ ] 3.5 提交：`feat(memory): MemoryStore SQLite schema 初始化`

## 4. MemoryStore — 写操作

- [ ] 4.1 在 `test_memory_store.py` 追加写操作测试：`upsert_fact` 返回 UUID、相同内容幂等（dedup_key）、不同内容各自独立、`upsert_profile`/`get_profile`/覆盖/不存在返回 None
- [ ] 4.2 运行测试，确认失败
- [ ] 4.3 在 `MemoryStore` 中实现 `upsert_fact`（dedup_key = MD5，存在则更新 access_count，不存在则 INSERT）和 `upsert_profile` / `get_profile`
- [ ] 4.4 运行测试，确认通过
- [ ] 4.5 提交：`feat(memory): MemoryStore upsert_fact + upsert_profile`

## 5. MemoryStore — 读操作

- [ ] 5.1 在 `test_memory_store.py` 追加读操作测试：`search_fts` 命中匹配内容、空查询返回空列表、`filter_by_sci` 按 `max_p_value` 过滤、按 `dataset_name` 过滤
- [ ] 5.2 运行测试，确认失败
- [ ] 5.3 实现 `search_fts`（FTS5 路径；LIKE 降级路径需转义 `%`/`_` 特殊字符，使用 `ESCAPE '\\'` 子句）和 `filter_by_sci`（JSON1 `json_extract` 路径；不可用时全表扫描 + 内存过滤）
- [ ] 5.4 运行测试，确认通过
- [ ] 5.5 提交：`feat(memory): MemoryStore search_fts + filter_by_sci`

## 6. MemoryStore — 旧数据迁移

- [ ] 6.1 创建 `tests/fixtures/sample_entries.jsonl`（2 条 JSONL 样本，含 `content`、`memory_type`、`importance_score`、`source_dataset` 字段）
- [ ] 6.2 编写 `tests/memory/test_migration.py`：JSONL 迁移条数正确、迁移幂等（二次调用不增加行数）、文件不存在时静默跳过、profile JSON 迁移
- [ ] 6.3 运行测试，确认失败
- [ ] 6.4 实现 `MemoryStore.migrate_from_jsonl`（字段映射：`source_dataset`→`sci_metadata.dataset_name`、`importance_score`→`importance`、`analysis_type`→`sci_metadata.analysis_type`）和 `migrate_profile_json`；在 `__init__` 中自动探测并调用（`data_dir` 路径存在时执行）
- [ ] 6.5 运行测试，确认通过
- [ ] 6.6 提交：`feat(memory): MemoryStore 旧数据迁移（JSONL + profile JSON）`

## 7. ScientificMemoryProvider — initialize + prefetch

- [ ] 7.1 编写 `tests/memory/test_scientific_provider.py`（initialize + prefetch 部分）：初始化创建 db、未初始化时 prefetch 返回空、空 facts 表时 prefetch 返回空、检索命中相关记忆
- [ ] 7.2 运行测试，确认失败
- [ ] 7.3 创建 `src/nini/memory/scientific_provider.py`，实现 `ScientificMemoryProvider`（`name="builtin"`）的 `initialize`（创建 `MemoryStore`，执行迁移）和 `prefetch`（FTS5 检索 → 上下文加权重排 → top_k 截取，返回纯文本）
- [ ] 7.4 运行测试，确认通过
- [ ] 7.5 提交：`feat(memory): ScientificMemoryProvider initialize + prefetch`

## 8. ScientificMemoryProvider — sync_turn

- [ ] 8.1 在 `test_scientific_provider.py` 追加 sync_turn 测试：含 p 值回复触发写入 statistic、普通文本不触发写入、sync_turn 异常不向外抛出
- [ ] 8.2 运行测试，确认失败
- [ ] 8.3 实现 `sync_turn`（`_STAT_PATTERNS` 正则匹配，importance < 0.4 不写入）
- [ ] 8.4 运行测试，确认通过
- [ ] 8.5 提交：`feat(memory): ScientificMemoryProvider sync_turn 轻量提取`

## 9. ScientificMemoryProvider — on_session_end

- [ ] 9.1 在 `test_scientific_provider.py` 追加 on_session_end 测试：高置信度 Finding 写入 facts（使用 Finding.summary 作 content）、显著统计写入 statistic（sci_metadata 含 p_value/effect_size/dataset_name）、幂等（dedup_key）、空 messages 传入不抛出异常
- [ ] 9.2 运行测试，确认失败
- [ ] 9.3 实现 `on_session_end`：使用 `self._session_id`（存于 `initialize()`）调用 `list_session_analysis_memories(session_id)` 读取 AnalysisMemory；`Finding.summary`→`content`、`Finding.detail`→`summary`、`AnalysisMemory.dataset_name`→`sci_metadata.dataset_name`；按阈值写入 facts → 更新 research_profiles；messages 参数可为空（仅传递给基类或用于轻量提取，不用于读取 AnalysisMemory）
- [ ] 9.4 运行测试，确认通过
- [ ] 9.5 提交：`feat(memory): ScientificMemoryProvider on_session_end 重度沉淀`

## 10. ScientificMemoryProvider — on_pre_compress + 工具

- [ ] 10.1 在 `test_scientific_provider.py` 追加测试：含统计数值的消息触发保留提示、无统计数值返回空、`nini_memory_find` 按 max_p_value 过滤、`nini_memory_save` 写入新发现、未初始化时工具返回错误 JSON
- [ ] 10.2 运行测试，确认失败
- [ ] 10.3 实现 `on_pre_compress`（抽取统计行，最多 10 条）和 `handle_tool_call`（路由到 `_handle_find` / `_handle_save`）；实现 `get_tool_schemas` 返回 `nini_memory_find` / `nini_memory_save` schema；实现 `system_prompt_block` 返回包含两个工具名称和用途说明的静态文本
- [ ] 10.4 运行 `tests/memory/` 全量测试，确认通过
- [ ] 10.5 提交：`feat(memory): ScientificMemoryProvider on_pre_compress + LLM 工具 + system_prompt_block`

## 10b. AnalysisMemoryTool 适配 MemoryManager

- [ ] 10b.1 读取 `src/nini/tools/analysis_memory_tool.py`，了解当前 list/find 实现
- [ ] 10b.2 在 `execute()` 中添加 MemoryManager 优先路径：`find` 操作优先调用 `get_memory_manager().handle_tool_call("nini_memory_find", ...)` ；失败或 manager 未初始化时降级到原有路径
- [ ] 10b.3 验证：现有 `AnalysisMemoryTool` 测试仍通过（`pytest tests/ -k analysis_memory -q`）
- [ ] 10b.4 提交：`feat(memory): AnalysisMemoryTool 适配 MemoryManager（保留向后兼容降级路径）`

## 11. memory/__init__.py 导出 + 向后兼容

- [ ] 11.1 读取 `src/nini/memory/__init__.py` 当前内容
- [ ] 11.2 追加新导出：`MemoryManager`、`MemoryProvider`、`ScientificMemoryProvider`、`get_memory_manager`、`set_memory_manager`；保留现有导出不变
- [ ] 11.3 验证：`python -c "from nini.memory import MemoryManager, ScientificMemoryProvider; print('OK')`
- [ ] 11.4 运行 `python scripts/check_event_schema_consistency.py` 和 `pytest tests/memory/ -q`，确认零回归
- [ ] 11.5 提交：`feat(memory): memory/__init__.py 新增 MemoryProvider 架构导出`

## 12. AgentRunner 接入 MemoryManager

- [ ] 12.1 在 `AgentRunner.__init__`（`runner.py:379`）末尾追加 `self._memory_manager: MemoryManager | None = None`
- [ ] 12.2 在 `runner.py` 顶部 import 区域添加 `from nini.memory.manager import MemoryManager, set_memory_manager, build_memory_context_block` 和 `from nini.memory.scientific_provider import ScientificMemoryProvider`
- [ ] 12.3 在 `AgentRunner.run()` 的 system_prompt 组装前，添加 MemoryManager 惰性初始化逻辑（`db_path = settings.sessions_dir.parent / "nini_memory.db"`）和 `initialize_all` 调用；将 `build_system_prompt()` 输出追加到 `system_prompt`
- [ ] 12.4 在 `runner.py:1294`（会话结束处）的现有 `consolidate_session_memories` 调用后，追加 `MemoryManager.on_session_end(session.messages)` 后台任务（保留旧路径）
- [ ] 12.5 验证：`python -c "from nini.agent.runner import AgentRunner; print('OK')"`
- [ ] 12.6 提交：`feat(memory): AgentRunner 接入 MemoryManager 初始化与会话结束钩子`

## 13. context_memory.py 主检索路径切换

- [ ] 13.1 读取 `src/nini/agent/components/context_memory.py`，定位 `build_long_term_memory_context` 函数
- [ ] 13.2 在函数开头添加 try/except 优先路径：调用 `get_memory_manager().prefetch_all()`，成功则用 `build_memory_context_block()` 包裹返回；失败则 pass 降级到原有路径
- [ ] 13.3 原有 `LongTermMemoryStore` 路径保持完整不变（降级路径）
- [ ] 13.4 在 `_build_dataset_history_memory`（`context_builder.py:554`）中同样添加 MemoryManager 优先路径（同上结构）
- [ ] 13.5 运行 `python scripts/check_event_schema_consistency.py` 和 `pytest -q --ignore=tests/memory/`，确认零回归
- [ ] 13.6 运行 `mypy src/nini/memory/` 和 `black --check src/nini/memory/ src/nini/agent/runner.py src/nini/agent/components/context_memory.py src/nini/agent/components/context_builder.py`
- [ ] 13.7 提交：`feat(memory): 主检索路径切换到 MemoryManager（context_memory + context_builder）`

## 14. 验收与 PR

- [ ] 14.1 运行 `pytest tests/memory/ -v --tb=short`，确认全部通过
- [ ] 14.2 运行 `pytest -q`（全量），确认零回归
- [ ] 14.3 运行 `mypy src/nini/memory/`，确认无类型错误
- [ ] 14.4 创建 PR，标题：`feat(memory): P005 MemoryProvider 架构 — SQLite 统一存储 + MemoryManager 生命周期`，描述包含变更内容、验证命令、回滚方案
