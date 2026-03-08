<!-- Wave 3（规范文档阶段）：与 Wave 1-2 并行推进，是 Wave 4 代码实现的依据 -->

## 1. 提案与规范

- [ ] 1.1 补写 `proposal.md`，明确当前缺口、目标状态、受影响能力和非目标
- [ ] 1.2 补写 `design.md`，锁定两条边界、四层披露、引用展开和预算策略
- [ ] 1.3 修改 `skills` spec，补充渐进式披露、引用内容层和工具白名单契约
- [ ] 1.3.1 同步修改既有“技能快照生成与注入” requirement，消除与 trusted prompt 边界的新冲突
- [ ] 1.4 修改 `prompt-system-composition` spec，收敛 trusted system prompt 边界
- [ ] 1.5 修改 `prompt-runtime-context-safety` spec，定义 Skill 相关 runtime context 的统一协议和预算规则

## 2. Skills 契约拆解

- [ ] 2.1 定义索引层、说明层、资源清单层、引用内容层四级披露行为
- [ ] 2.2 定义 Skill 正文引用资源的路径解析、根目录校验、缺失处理，以及“未引用资源不得读取正文”
- [ ] 2.3 定义 `allowed-tools` 的激活规则、阻断规则、错误反馈要求和“仅约束模型发起工具调用”的边界
- [ ] 2.4 定义默认路径输出为相对路径或逻辑标识，覆盖技能列表、运行时资源和文件树接口

## 3. Prompt 边界拆解

- [ ] 3.1 定义 `SKILLS_SNAPSHOT` 仅可承载系统生成技能摘要，不得承载可编辑 Skill 原文
- [ ] 3.2 定义 `AGENTS.md` 进入 trusted assembly boundary 的要求，包括根目录与子目录的优先级/合并规则
- [ ] 3.3 定义 Markdown Skill 正文和引用资源必须停留在 untrusted runtime context
- [ ] 3.4 定义 Skill runtime context 的独立预算、裁剪顺序和稳定排序

## 4. 验证场景

- [ ] 4.1 为 `skills` spec 编写按需读取、未引用资源不加载、路径穿越拒绝等场景
- [ ] 4.2 为 `prompt-system-composition` spec 编写“不可信 skill 元数据不得进入 trusted prompt”场景
- [ ] 4.3 为 `prompt-runtime-context-safety` spec 编写“Skill 大上下文优先裁剪自身而非仅裁剪历史消息”场景
- [ ] 4.4 为 `allowed-tools` 编写“越界工具调用被阻断”场景

## 5. OpenSpec 校验

- [ ] 5.1 运行 `openspec validate align-skills-industry-standard --strict`
- [ ] 5.2 若校验失败，使用 `openspec show align-skills-industry-standard --json --deltas-only` 定位问题并修正
- [ ] 5.3 确认 proposal、design、tasks 和 spec deltas 可直接交给实现阶段执行

## 6. Wave 1 — 基础强化（立即可做，不依赖规范完成）

- [ ] 6.1 在 `src/nini/api/websocket.py` 的两处补充 `consolidate_session_memories` 异步触发：① stop 消息处理（行 302-314）在 `task.cancel()` + `await task` 完成后，以 `session.id` 调用 `asyncio.create_task(consolidate_session_memories(session.id))`；② 外层 WebSocketDisconnect finally 块（行 436-444）在取消 active_chat_task 后，若 `session` 不为 None 则同样触发
- [ ] 6.2 在 `src/nini/agent/components/context_memory.py` 的 `build_long_term_memory_context()` 加入注入日志：injected_count、query_len、min_importance 实际阈值
- [ ] 6.3 在 `src/nini/agent/components/context_builder.py:185-199` 长期记忆注入分支加 debug 日志，记录注入是否发生及 token 估算
- [ ] 6.4 在 `src/nini/agent/model_resolver.py` 的 `DEFAULT_PURPOSE_ROUTES` 新增 `"planning": None` 和 `"verification": None`（None 表示复用默认路由，key 存在以备后续配置）

## 7. Wave 2 — 规划质量强化（7.1-7.3 立即可做；7.4 依赖 6.4 完成）

- [ ] 7.1 在 `src/nini/models/execution_plan.py` 新增 `MustHave` Pydantic model（`type: Literal["truth","artifact","key_link"]`，`description: str`），`ExecutionPlan` 新增 `must_haves: list[MustHave] = []`
- [ ] 7.2 在 `src/nini/agent/planner.py` 的规划提示词末尾增加 must_haves 生成指令，LLM 在计划 JSON 中输出 must_haves 数组
- [ ] 7.3 在 `src/nini/agent/runner.py` done 分支（行 835 附近）遍历 `must_haves`，生成 validation_warnings（不阻断，日志 + warning 事件）
- [ ] 7.4 在 `src/nini/agent/planner.py` 的 LLM 调用处显式传 `purpose="planning"`
- [ ] 7.5 新增 `pytest tests/ -k "test_planner or test_execution_plan"` 覆盖 must_haves 字段填充和序列化

## 8. Wave 4A — align-skills 代码实现（依赖 1.x-5.x 规范完成）

- [ ] 8.1 **AGENTS.md trusted 化**：在 `src/nini/agent/prompts/builder.py` 新增 `agents_external_md` 组件（priority=80），读取项目根 AGENTS.md 进入 trusted assembly；同步删除 `context_builder.py` 中 `_discover_agents_md()` 调用和 `format_untrusted_context_block("agents_md", ...)`；从 `prompt_policy.py::UNTRUSTED_CONTEXT_HEADERS` 删除 `agents_md` 键
- [ ] 8.2 **runtime context 预算控制**：在 `src/nini/agent/prompt_policy.py` 新增 `RUNTIME_CONTEXT_BLOCK_PRIORITY`（按 1.5/3.4 规范锁定的裁剪顺序）和 `trim_runtime_context_by_priority()` 函数；在 `context_builder.py` 的 `compose_runtime_context_message()` 前调用预算控制
- [ ] 8.3 **allowed-tools 硬约束**：在工具执行路径（`runner.py` 或 `tool_executor.py`）加入 allowlist 检查，调用白名单外工具时推送 error 事件；无声明时保持默认行为（不收缩）
- [ ] 8.4 **路径安全**：在 `src/nini/agent/components/context_skills.py` 将 location 字段改为相对路径或逻辑标识符
- [ ] 8.5 **SKILLS_SNAPSHOT 摘要纯化**：确认 `prompts/builder.py` 的 `_extract_markdown_skills_snapshot()` 只承载系统生成摘要，不含用户可编辑原文；如有则修正

## 9. Wave 4B — P2 记忆与调度强化（可与 Wave 4A 并行，依赖 1.x-5.x 规范稳定）

- [ ] 9.1 **高重要性记忆自动沉淀**：在 `src/nini/memory/long_term_memory.py` 的 `add_memory()` 末尾，当 `importance_score >= 0.8` 时以已有的 `source_session_id` 参数触发 `asyncio.get_event_loop().create_task(consolidate_session_memories(source_session_id))`；使用 session 级 in-flight 锁（`_consolidating: set[str]`，类变量）防止并发重复触发
- [ ] 9.2 **Wave 任务并行调度**：在 `src/nini/agent/task_manager.py` 的 `TaskItem`（frozen dataclass）新增 `depends_on: list[int] = field(default_factory=list)`（类型与 `id: int` 一致），新增 `group_into_waves()` 拓扑排序；在 `runner.py` 工具执行循环中同 wave 内任务用 `asyncio.gather()` 并行触发；`to_analysis_plan_dict()` 初版**不暴露** depends_on（避免前端阻塞，等 10.3 单独 PR）
- [ ] 9.3 **科研实体关系（轻量）**：在 `LongTermMemoryEntry.metadata` 内定义标准 `relations` 子字段（`list[dict]`，含 type/entities/dataset），`add_memory()` 接受可选 `relations` 参数写入 metadata，不修改顶层 schema
- [ ] 9.4 新增 pytest 覆盖：`test_long_term_memory`（自动沉淀）、`test_task_manager`（wave 调度）

## 10. P3 — 远期能力（Wave 4 完成后）

- [ ] 10.1 **记忆冲突检测**：在 `LongTermMemoryStore.add_memory()` 检测同 dataset + analysis_type 的矛盾发现，策略：最新覆盖 + 日志告警
- [ ] 10.2 **主动记忆推送**：在 `ContextBuilder` 识别到 dataset 加载时，自动注入该 dataset 的历史记忆摘要（复用 Wave 4A 的预算控制确定可用空间）
- [ ] 10.3 **前端 depends_on 展示**：将 `TaskItem.depends_on` 加入 `to_analysis_plan_dict()` 的 steps 输出，前端 `store.ts` 同步支持依赖关系展示
