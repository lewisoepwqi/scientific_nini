# Nini 2.0 架构迭代计划

**审计日期**: 2026-02-28
**审计方法**: 3 个并行 Explore Agent 深度扫描后端（2633 行 runner.py 逐方法分析）、前端（3956 行 store.ts 完整审查）、文档与基础设施

---

## 执行摘要

Nini 2.0 愿景已实现约 **85%**，但经过深度代码审计发现了若干关键问题：

| 类别 | 发现 |
|------|------|
| 严重 Bug | 1 个 — RAG 混合检索在生产中永远静默失败（async 调用错误） |
| 功能断联 | 2 个 — 统计降级 fallback 未接入 agent 循环；CostPanel 未渲染到 App |
| 代码巨石 | 3 个 — runner.py（2633 行）、store.ts（3956 行）、routes.py（2900 行） |
| 死代码 | 1 个 — cost_service.py（335 行）完全未使用 |
| 存根功能 | 2 个 — ReportTemplatePanel 的生成/下载方法是假实现；5/7 Capability 返回 409 |
| 命名冲突 | 1 个 — 两个不同的 `TokenUsage` 类 |
| 缺失测试 | 前端零单元测试；store 状态机逻辑无测试覆盖 |

本计划按优先级组织为 **5 个迭代阶段**，每阶段独立可交付。

---

## Phase 1：修复关键 Bug 和断联功能（P0 紧急）

> 目标：让已写好但未生效的功能真正工作起来
> 预计改动：4 个文件

### 1.1 修复 RAG 异步 Bug（Critical）

**问题**：`runner.py:1359-1360` 在已运行的 asyncio 事件循环中调用 `asyncio.get_event_loop().run_until_complete()`，永远抛出 `RuntimeError`，被 `except Exception` 静默吞掉。**混合检索路径在生产中完全失效**，永远降级到关键词搜索。

**修复方案**：
- 文件：`src/nini/agent/runner.py`（`_build_messages_and_retrieval` 方法）
- 将方法改为 `async`，使用 `await` 调用 `inject_knowledge_to_prompt()`
- 调用处 `run()` 已是 `async generator`，直接 `await` 即可
- 移除冗余的内层 `import asyncio`（line 1341）
- 将 `raise Exception("No knowledge retrieved, falling back")` 改为 `if not documents` 条件分支

**验证**：
```bash
pytest tests/test_knowledge_*.py tests/e2e/test_knowledge_retrieval.py -q
# 手动：启动 nini，上传数据集，确认日志出现 hybrid retriever 命中
```

### 1.2 接入统计降级 Fallback（High）

**问题**：`runner.py:2379` 调用 `self._skill_registry.execute()` 而非 `execute_with_fallback()`。正态性检验降级（t_test→mann_whitney、anova→kruskal_wallis）基础设施完整但未接入生产循环。

**修复方案**：
- 文件：`src/nini/agent/runner.py`（`_execute_tool` 方法内 skill 调用处）
- 将 `execute()` 替换为 `execute_with_fallback()`
- fallback 触发时推送 `REASONING` 事件说明降级原因

**验证**：
```bash
pytest tests/test_fallback_strategy.py tests/test_fallback_mechanism.py -q
# 手动：上传非正态分布数据，请求 t 检验，确认自动降级为 Mann-Whitney
```

### 1.3 接入 CostPanel 到 App.tsx（High）

**问题**：`CostPanel.tsx`（333 行）已完整实现，store 中状态和 action 已就位，但 `App.tsx` **未导入和渲染该组件**，也没有触发按钮。

**修复方案**：
- 文件：`web/src/App.tsx`
- 导入 `CostPanel` 和 `Coins` 图标（lucide-react）
- 在顶栏添加 Coins 图标按钮（onClick → `toggleCostPanel`）
- 在组件树中渲染 `<CostPanel />`

**验证**：
```bash
cd web && npm run build
# 手动：启动前端，点击 Coins 图标，确认面板显示 token 统计
```

### 1.4 修复 ReportTemplatePanel 存根（High）

**问题**：`ReportTemplatePanel.tsx` 的 `generateReport()` 是 `setTimeout(2000)` 假延迟，`downloadReport()` 只 `console.log`。

**修复方案**：
- 文件：`web/src/components/ReportTemplatePanel.tsx`
- `generateReport()` → 调用 `POST /api/sessions/{id}/generate-report`
- `downloadReport()` → 调用 `GET /api/sessions/{id}/workspace/files/{path}` 下载产物

**验证**：
```bash
cd web && npm run build
# 手动：生成分析结果后，测试报告生成和下载
```

---

## Phase 2：清理代码质量问题（P1 技术债务）

> 目标：消除死代码、命名冲突和类型不一致
> 预计改动：6 个文件

### 2.1 清理 cost_service.py 死代码

- **问题**：`src/nini/services/cost_service.py`（335 行）与 `api/cost_routes.py` 逻辑完全重复，无生产代码导入
- **方案**：删除文件，grep 确认无引用

### 2.2 解决 TokenUsage 命名冲突

- **问题**：`models/cost.py` 和 `utils/token_counter.py` 各有一个 `TokenUsage` 类，语义不同
- **方案**：`utils/token_counter.py` 中重命名为 `TokenRecord`（单次记录），保留 `models/cost.py` 中的（会话聚合）

### 2.3 补齐 PricingConfig Pydantic 模型

- **问题**：API 实际返回 `tier_definitions` 和 `cost_warnings`，但模型未定义
- **文件**：`src/nini/models/cost.py`

### 2.4 补齐 WSEvent schema 注释

- **问题**：`schemas.py` 事件类型注释缺少 `session` 和 `reasoning`
- **文件**：`src/nini/models/schemas.py`

### 2.5 修复 Store 类型不匹配

- **问题**：`setWorkspacePanelTab` 接受 `"files" | "executions" | "tasks"` 但状态类型包含 `"knowledge"`
- **文件**：`web/src/store.ts`

### 2.6 处理 ReasoningTimeline 组件

- **问题**：`ReasoningTimeline.tsx`（276 行）已实现但未被任何组件导入
- **方案**：评估集成价值，集成到 UI 或删除避免死代码

**验证**：
```bash
black --check src tests && mypy src/nini
cd web && npm run build
pytest -q
```

---

## Phase 3：拆分代码巨石（P1 可维护性）

> 目标：将 3 个超大文件拆分为可维护的模块
> 原则：仅做提取，不改逻辑

### 3.1 拆分 AgentRunner（2633 行 → ~6 个模块）

| 新模块 | 职责 | 预估行数 |
|--------|------|---------|
| `agent/runner.py` | 核心 ReAct 循环 + 事件调度（保留） | ~600 |
| `agent/context_builder.py` | 消息构建、上下文组装、知识注入 | ~400 |
| `agent/context_compressor.py` | 自动压缩、滑动窗口、阈值管理 | ~300 |
| `agent/intent_router.py` | 意图分析集成、技能匹配、澄清对话 | ~350 |
| `agent/tool_executor.py` | 工具执行、结果处理、fallback 调度 | ~300 |
| `agent/reasoning_tracker.py` | 推理链追踪 | ~200 |

### 3.2 拆分 store.ts（3956 行 → ~7 个模块）

| 新模块 | 职责 | 预估行数 |
|--------|------|---------|
| `store/index.ts` | Zustand create + 组合 slices | ~200 |
| `store/session-slice.ts` | 会话管理、消息历史 | ~500 |
| `store/websocket-slice.ts` | WebSocket 连接、重连、心跳 | ~400 |
| `store/event-handler.ts` | handleEvent switch + 17 种事件 | ~600 |
| `store/plan-state-machine.ts` | 计划/任务状态机逻辑 | ~400 |
| `store/api-actions.ts` | 所有 fetch 操作 | ~500 |
| `store/normalizers.ts` | 8+ 数据规范化函数 | ~300 |

### 3.3 拆分 routes.py（2900 行 → 按资源分组）

| 新模块 | 职责 |
|--------|------|
| `api/routes.py` | 主路由注册（仅 include） |
| `api/session_routes.py` | 会话 CRUD |
| `api/workspace_routes.py` | 工作区文件操作 |
| `api/skill_routes.py` | 技能/工具目录 |
| `api/profile_routes.py` | 用户画像 |

**验证**：
```bash
pytest -q && cd web && npm run build && npm run test:e2e
# 确认无功能回归
```

---

## Phase 4：功能补全（P2 完善度 85% → 95%）

> 目标：补齐缺失功能，提升完成度

### 4.1 实现 regression_analysis 复合技能模板

- 新文件：`src/nini/tools/templates/regression_analysis.py`
- 参考 `correlation_analysis.py`（342 行）
- 流程：数据检查 → 假设检验 → 线性/多元回归 → 残差诊断 → 可视化 → APA 结果

### 4.2 实现 regression_analysis Capability

- 新文件：`src/nini/capabilities/implementations/regression_analysis.py`
- 参考 `correlation_analysis.py`（539 行）
- 在 `defaults.py` 中标记 `is_executable: True`

### 4.3 添加成本追踪持久化

- **问题**：`SessionTokenTracker` 仅内存存储，服务器重启丢失
- **方案**：在 `record()` 后追加 `data/sessions/{session_id}/cost.jsonl`，启动时恢复

### 4.4 添加实时 Token WebSocket 事件

- 在 `agent/events.py` 添加 `EventType.TOKEN_USAGE`
- 在 `runner.py` 每次 LLM 调用后推送 token 增量事件
- 前端 store 添加 `token_usage` case 实时更新 CostPanel

### 4.5 实现功能特性开关

- 文件：`src/nini/config.py`
- 添加：`enable_cost_tracking`、`enable_reasoning`、`enable_knowledge`、`knowledge_max_tokens`、`knowledge_top_k`
- 已在 `docs/nini_20_features.md` 文档化但未实现

### 4.6 添加前端单元测试基础设施

- 安装 vitest + @testing-library/react + jsdom
- 配置 `web/vitest.config.ts`
- 为 Phase 3 拆分后的 `plan-state-machine.ts` 和 `normalizers.ts` 编写首批测试

**验证**：
```bash
pytest -q
cd web && npm run build && npm run test && npm run test:e2e
```

---

## Phase 5：架构演进（P3 长期）

> 目标：为 Nini 3.0 奠定基础

### 5.1 拆分 model_resolver.py（1393 行）

- 将每个 LLM 提供商适配器提取到 `agent/providers/` 目录
- `model_resolver.py` 只保留路由和降级逻辑

### 5.2 更多 Capability 实现

- `data_exploration`、`data_cleaning`、`visualization` 从 409 存根升级为可执行
- 每个 Capability 编排已有的原子 Tools

### 5.3 知识库 UI 管理

- 前端上传知识文档、触发索引重建
- 知识库检索结果可视化展示

### 5.4 长期记忆持久化

- 将 LLM 摘要压缩的关键发现写入向量数据库
- 跨会话检索历史分析结论

---

## 关键文件清单

| 文件 | 涉及阶段 | 操作 |
|------|---------|------|
| `src/nini/agent/runner.py` | P1→P2→P3 | 修复 async bug → 接入 fallback → 拆分 |
| `web/src/App.tsx` | P1 | 接入 CostPanel |
| `web/src/components/ReportTemplatePanel.tsx` | P1 | 修复存根方法 |
| `web/src/store.ts` | P2→P3 | 修复类型 → 拆分 |
| `src/nini/services/cost_service.py` | P2 | 删除（死代码） |
| `src/nini/utils/token_counter.py` | P2→P4 | 重命名类 → 添加持久化 |
| `src/nini/models/cost.py` | P2 | 补齐字段 |
| `src/nini/api/routes.py` | P3 | 拆分为按资源分组 |
| `src/nini/tools/templates/` | P4 | 新增 regression_analysis |
| `src/nini/capabilities/implementations/` | P4 | 新增 regression_analysis |
| `src/nini/config.py` | P4 | 添加功能开关 |
| `src/nini/agent/events.py` | P4 | 添加 TOKEN_USAGE 事件 |
| `src/nini/agent/model_resolver.py` | P5 | 拆分到 providers/ |

## 验证策略

每个 Phase 完成后：
1. `black --check src tests` — 格式检查
2. `mypy src/nini` — 类型检查
3. `pytest -q` — 后端测试
4. `cd web && npm run build` — 前端构建
5. `cd web && npm run test:e2e` — E2E 测试（如涉及前端改动）
6. 手动启动 `nini start --reload`，验证核心流程

---

*生成时间: 2026-02-28*
*审计范围: 后端 30,000+ 行 Python + 前端 15,000+ 行 TypeScript + 文档/基础设施*
