## Why

科研场景中的文献综述、实验设计、结论验证等任务，其推理模式是"提出假设 → 收集证据 → 验证修正 → 得出结论"，而现有 ReAct 范式的工具链式触发无法显式建模这一推理过程，导致假设游移、证据堆砌而非推理收敛，输出质量显著低于预期。

## What Changes

- 新增 `HypothesisContext` + `Hypothesis` 数据类，存储假设列表、置信度（贝叶斯更新）及三条件收敛判断
- 新增 5 个 WebSocket 事件类型：`hypothesis_generated`、`evidence_collected`、`hypothesis_validated`、`hypothesis_refuted`、`paradigm_switched`
- 修改 `SubAgentSpawner.spawn()` 增加范式分支：`paradigm == "hypothesis_driven"` 时走 `_spawn_hypothesis_driven()` 循环
- 修改 `AgentRegistry` 内置 YAML：`literature_reading` 和 `research_planner` 的 `paradigm` 字段改为 `"hypothesis_driven"`
- 新增前端 `HypothesisTracker` 组件，实时展示假设链（内容 + 置信度 + 状态标签 + 证据折叠）

## Capabilities

### New Capabilities

- `hypothesis-context`：`Hypothesis` 数据类（id/content/confidence/evidence_for/evidence_against/status）+ `HypothesisContext`（假设列表、当前阶段、迭代计数、三条件收敛判断）
- `hypothesis-driven-agent`：Spawner 中 Hypothesis-Driven 执行路径（生成假设 → 工具收集证据 → 贝叶斯更新置信度 → 收敛判断循环）；触发条件检测（意图关键词匹配）
- `hypothesis-events`：5 个新 EventType 枚举值及对应 `event_builders` 构造函数，payload 结构规范
- `hypothesis-tracker-ui`：前端 `HypothesisTracker` 组件，订阅 store 中的假设状态，展示假设卡片（置信度进度条、状态标签、证据链折叠展开）；假设 slice 状态管理

### Modified Capabilities

- `sub-agent-spawner`：`spawn()` 增加 `paradigm` 分支判断，新增 `_spawn_hypothesis_driven()` 执行路径
- `agent-registry`：`literature_reading` 和 `research_planner` 的 `paradigm` 字段由 `"react"` 改为 `"hypothesis_driven"`

## Impact

- **后端新建**：`src/nini/agent/hypothesis_context.py`
- **后端修改**：`src/nini/agent/spawner.py`（范式分支）、`src/nini/agent/events.py`（追加枚举）、`src/nini/agent/event_builders.py`（新增构造函数）、`src/nini/agent/prompts/agents/builtin/literature_reading.yaml`、`src/nini/agent/prompts/agents/builtin/research_planner.yaml`
- **前端新建**：`web/src/components/HypothesisTracker.tsx`、`web/src/store/hypothesis-slice.ts`、`web/src/store/hypothesis-event-handler.ts`
- **前端修改**：`web/src/store/types.ts`（新增类型）、`web/src/store/event-handler.ts`（注册处理器）、`web/src/App.tsx` 或 `ChatPanel.tsx`（条件渲染 HypothesisTracker）
- **测试新建**：`tests/test_hypothesis_context.py`、`tests/test_spawner_hypothesis.py`
- **无 Breaking Change**：未触发 Hypothesis-Driven 时系统行为与 Phase 1/2 完全相同
