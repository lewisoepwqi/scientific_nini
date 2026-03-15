## 1. HypothesisContext 数据模型

- [x] 1.1 新建 `src/nini/agent/hypothesis_context.py`：实现 `Hypothesis` 数据类，字段 `id`、`content`、`confidence=0.5`、`evidence_for`、`evidence_against`、`status="pending"`，使用 `field(default_factory=list)` 避免可变默认值
- [x] 1.2 实现 `HypothesisContext` 数据类，字段 `hypotheses`、`current_phase="generation"`、`iteration_count=0`、`max_iterations=3`、`_prev_confidences: list[float]`
- [x] 1.3 实现 `HypothesisContext.should_conclude()` 三条件收敛判断：硬上限（iteration_count >= max_iterations）/ 所有假设已定论（无 pending）/ 贝叶斯收敛（Δ < 0.05）
- [x] 1.4 实现 `HypothesisContext.update_confidence(hypothesis_id, evidence_type)`：支持 +0.15 / -0.20，边界 clamp [0.0, 1.0]，更新前保存 `_prev_confidences` 快照

## 2. 假设推理事件

- [x] 2.1 在 `src/nini/agent/events.py` 的 `EventType` 枚举末尾追加 6 个新值：`HYPOTHESIS_GENERATED`、`EVIDENCE_COLLECTED`、`HYPOTHESIS_VALIDATED`、`HYPOTHESIS_REFUTED`、`HYPOTHESIS_REVISED`、`PARADIGM_SWITCHED`
- [x] 2.2 在 `src/nini/agent/event_builders.py` 中添加 `build_hypothesis_generated_event(agent_id, hypotheses)`、`build_evidence_collected_event(agent_id, hypothesis_id, evidence_type, evidence_content)`、`build_hypothesis_validated_event(agent_id, hypothesis_id, confidence)`、`build_hypothesis_refuted_event(agent_id, hypothesis_id, reason)`、`build_paradigm_switched_event(agent_id, paradigm)` 五个构造函数

## 3. SubAgentSpawner 范式分支

- [x] 3.1 在 `src/nini/agent/spawner.py` 的 `spawn()` 方法中，在获取 `agent_def` 后增加范式判断：`paradigm == "hypothesis_driven"` 时调用 `_spawn_hypothesis_driven()`，否则走原 `_spawn_react()` 路径（将现有逻辑提取为 `_spawn_react()` 私有方法）
- [x] 3.2 实现 `_spawn_hypothesis_driven(agent_def, task, session, timeout_seconds)`：创建 `SubSession`、初始化 `HypothesisContext` 并存入 `sub_session.artifacts["_hypothesis_context"]`、外层循环调用 `AgentRunner` 单轮 ReAct、每轮推送假设事件、调用 `should_conclude()` 判断退出，整体受 `asyncio.wait_for` 约束
- [x] 3.3 在 `_spawn_hypothesis_driven()` 开始时通过父会话 `session.event_callback` 推送 `paradigm_switched` 事件；每轮迭代按情况推送 `hypothesis_generated`、`evidence_collected`、`hypothesis_validated`、`hypothesis_refuted` 事件

## 4. AgentRegistry YAML 更新

- [x] 4.1 修改 `src/nini/agent/prompts/agents/builtin/literature_reading.yaml`：将 `paradigm` 字段从 `react` 改为 `hypothesis_driven`
- [x] 4.2 修改 `src/nini/agent/prompts/agents/builtin/research_planner.yaml`：将 `paradigm` 字段从 `react` 改为 `hypothesis_driven`
- [x] 4.3 在 `src/nini/agent/registry.py` 的 `AgentDefinition` 或注册逻辑中，对不合法的 `paradigm` 值（不在 `{"react", "hypothesis_driven"}` 中）记录 WARNING 日志（不阻断创建）

## 5. 前端假设状态管理

- [x] 5.1 在 `web/src/store/types.ts` 中新增 `HypothesisInfo` 接口（`id`、`content`、`confidence: number`、`status: 'pending' | 'validated' | 'refuted' | 'revised'`、`evidenceFor: string[]`、`evidenceAgainst: string[]`）和 `HypothesisSlice` 接口（`hypotheses`、`currentPhase`、`iterationCount`、`activeAgentId`）
- [x] 5.2 新建 `web/src/store/hypothesis-slice.ts`：实现初始状态和 `setHypothesesGenerated`、`addEvidence`、`setHypothesisValidated`、`setHypothesisRefuted`、`setParadigmSwitched`、`clearHypotheses` 更新方法
- [x] 5.3 新建 `web/src/store/hypothesis-event-handler.ts`：处理 `hypothesis_generated`（清空并写入新假设）、`evidence_collected`（追加证据到对应假设）、`hypothesis_validated`（更新 status + confidence）、`hypothesis_refuted`（更新 status）、`paradigm_switched`（设置 activeAgentId，重置 phase）
- [x] 5.4 在 `web/src/store/event-handler.ts` 中导入并注册 `hypothesis-event-handler.ts` 中的处理器

## 6. HypothesisTracker 前端组件

- [x] 6.1 新建 `web/src/components/HypothesisTracker.tsx`：从 store 读取 `hypotheses`，`hypotheses.length === 0` 时返回 `null`；渲染假设卡片列表，每张卡片含假设内容、置信度进度条、状态标签
- [x] 6.2 实现证据链折叠展开：默认折叠，点击展开显示 `evidenceFor` 和 `evidenceAgainst` 两个列表，使用本地 `useState` 控制折叠状态
- [x] 6.3 实现状态标签颜色：`pending` → 蓝/灰、`validated` → 绿色、`refuted` → 红色、`revised` → 橙色
- [x] 6.4 在 `web/src/App.tsx`（或 `ChatPanel.tsx`）中引入 `HypothesisTracker`（`lazy` 导入），在 `hypotheses.length > 0` 时条件渲染，位于对话面板上方（与 AgentExecutionPanel 同区域）

## 7. 模块导出与整合

- [x] 7.1 更新 `src/nini/agent/__init__.py`，导出 `HypothesisContext`、`Hypothesis`，确保调用方可通过 `from nini.agent import HypothesisContext` 使用

## 8. 测试

- [x] 8.1 新建 `tests/test_hypothesis_context.py`：测试 `Hypothesis` 默认值、`HypothesisContext` 三条件收敛（每条件单独测试）、`update_confidence` 边界 clamp、`_prev_confidences` 快照保存
- [x] 8.2 新建 `tests/test_spawner_hypothesis.py`：测试 `spawn()` 范式路由（react / hypothesis_driven 分支正确调用）、`_spawn_hypothesis_driven` 成功迭代后返回 `SubAgentResult(success=True)`、整体超时返回失败、`paradigm_switched` 事件被推送、`spawn_batch` 中混合范式 Agent 并发执行互不影响

## 9. 集成验证

- [x] 9.1 运行 `pytest tests/test_hypothesis_context.py tests/test_spawner_hypothesis.py -q`，确认全部通过
- [x] 9.2 运行 `black --check src tests` 和 `mypy src/nini`，确认无格式或类型错误
- [x] 9.3 运行 `cd web && npm run build`，确认前端构建无错误
- [x] 9.4 启动开发服务器，发送"请综述近5年XXX领域研究进展"，验证收到 `paradigm_switched` 和 `hypothesis_generated` 两个 WebSocket 事件，前端 `HypothesisTracker` 可见
