# Nini 2.0 架构迭代计划

## Why

经过深度代码审计，发现 Nini 2.0 愿景已实现约 85%，但存在 1 个严重 Bug（RAG 混合检索在生产中静默失败）、2 个功能断联（统计降级 fallback 未接入、CostPanel 未渲染）、3 个代码巨石（runner.py 2633 行、store.ts 3956 行、routes.py 2900 行），以及死代码、命名冲突、缺失测试等质量问题。这些问题阻碍系统稳定性与可维护性，需在 Nini 3.0 之前完成技术债务清理。

## What Changes

本计划按优先级分为 5 个迭代阶段：

### Phase 1: 修复关键 Bug 和断联功能（P0 紧急）
- 修复 RAG 异步 Bug：`runner.py` 中 `asyncio.get_event_loop().run_until_complete()` 在已运行事件循环中调用导致 `RuntimeError`
- 接入统计降级 Fallback：将 `execute()` 替换为 `execute_with_fallback()`，触发时推送 REASONING 事件
- 接入 CostPanel 到 App.tsx：导入组件、添加 Coins 图标按钮、渲染面板
- 修复 ReportTemplatePanel 存根：实现 `generateReport()` 和 `downloadReport()` 真实 API 调用

### Phase 2: 清理代码质量问题（P1 技术债务）
- 删除 `cost_service.py` 死代码（335 行完全未使用）
- 解决 `TokenUsage` 命名冲突：`utils/token_counter.py` 重命名为 `TokenRecord`
- 补齐 `PricingConfig` Pydantic 模型字段：`tier_definitions` 和 `cost_warnings`
- 补齐 `WSEvent` schema 注释：添加 `session` 和 `reasoning` 类型
- 修复 Store 类型不匹配：`setWorkspacePanelTab` 参数类型对齐状态类型
- 评估并处理 `ReasoningTimeline` 组件（集成或删除）

### Phase 3: 拆分代码巨石（P1 可维护性）
- 拆分 `agent/runner.py`（2633 行 → 6 个模块）：context_builder、context_compressor、intent_router、tool_executor、reasoning_tracker
- 拆分 `web/src/store.ts`（3956 行 → 7 个模块）：session-slice、websocket-slice、event-handler、plan-state-machine、api-actions、normalizers
- 拆分 `api/routes.py`（2900 行 → 按资源分组）：session_routes、workspace_routes、skill_routes、profile_routes

### Phase 4: 功能补全（P2 完善度 85% → 95%）
- 实现 `regression_analysis` 复合技能模板（参考 `correlation_analysis.py`）
- 实现 `regression_analysis` Capability（从 409 存根升级为可执行）
- 添加成本追踪持久化：`SessionTokenTracker` 追加写入 `cost.jsonl`，启动时恢复
- 添加实时 Token WebSocket 事件：`EventType.TOKEN_USAGE`，每次 LLM 调用后推送
- 实现功能特性开关：`config.py` 添加 `enable_cost_tracking`、`enable_reasoning` 等
- 添加前端单元测试基础设施：vitest + @testing-library/react + jsdom

### Phase 5: 架构演进（P3 长期）
- 拆分 `model_resolver.py`（1393 行）：提供商适配器提取到 `agent/providers/`
- 更多 Capability 实现：`data_exploration`、`data_cleaning`、`visualization` 从 409 存根升级
- 知识库 UI 管理：前端上传知识文档、触发索引重建
- 长期记忆持久化：关键发现写入向量数据库，跨会话检索

## Capabilities

### New Capabilities
- `rag-async-fix`: 修复 RAG 混合检索异步调用 Bug
- `stats-fallback`: 统计降级 fallback 机制（t_test→mann_whitney、anova→kruskal_wallis）
- `cost-panel`: 成本追踪面板 UI 组件
- `report-generation`: 报告生成与下载功能
- `regression-analysis`: 回归分析复合技能与 Capability
- `token-persistence`: Token 使用持久化存储
- `feature-flags`: 功能特性开关配置

### Modified Capabilities
- `conversation`: 添加 TOKEN_USAGE WebSocket 事件类型
- `workspace`: 知识库文档上传与索引重建接口
- `skills`: 统计技能 fallback 降级逻辑接入

## Impact

**后端代码**:
- 修改: `src/nini/agent/runner.py`（修复 + 拆分）
- 修改: `src/nini/api/routes.py`（拆分）
- 删除: `src/nini/services/cost_service.py`
- 修改: `src/nini/utils/token_counter.py`（重命名类）
- 修改: `src/nini/models/cost.py`（补齐字段）
- 修改: `src/nini/models/schemas.py`（补齐注释）
- 修改: `src/nini/config.py`（添加功能开关）
- 新增: `src/nini/tools/templates/regression_analysis.py`
- 新增: `src/nini/capabilities/implementations/regression_analysis.py`
- 新增: `src/nini/agent/context_builder.py` 等拆分模块
- 新增: `src/nini/agent/providers/` 目录

**前端代码**:
- 修改: `web/src/App.tsx`（接入 CostPanel）
- 修改: `web/src/components/ReportTemplatePanel.tsx`（修复存根）
- 修改: `web/src/store.ts`（修复类型 + 拆分）
- 修改: `web/src/components/ReasoningTimeline.tsx`（评估处理）
- 新增: `web/src/store/` 目录（拆分后的 slices）
- 新增: `web/vitest.config.ts`（测试配置）

**基础设施**:
- 新增依赖: `vitest`, `@testing-library/react`, `jsdom`（前端测试）
- 构建验证: 每阶段完成后运行 black、mypy、pytest、npm run build
