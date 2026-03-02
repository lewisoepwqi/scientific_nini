# Nini 2.0 架构迭代设计

## Context

Nini 是一个本地优先的科研数据分析 AI Agent，采用单架构设计：Python 后端（FastAPI + WebSocket）+ React 前端。系统核心是一个 ReAct 循环的 Agent，通过技能系统（Skill）执行统计、可视化、数据清洗等任务。

当前代码审计发现的问题：
1. **严重 Bug**: `runner.py` 中 RAG 混合检索因异步调用错误在生产中静默失败
2. **功能断联**: 统计降级 fallback 已实现但未接入 agent 循环；CostPanel 组件已开发但未在 App.tsx 渲染
3. **代码巨石**: 3 个超大文件（runner.py 2633 行、store.ts 3956 行、routes.py 2900 行）严重影响可维护性
4. **技术债务**: 死代码、命名冲突、类型不匹配、缺失测试

本设计涵盖 5 个阶段迭代，每个阶段独立可交付。

## Goals / Non-Goals

**Goals:**
- P0: 修复所有关键 Bug，让已开发但未生效的功能真正工作
- P1: 清理技术债务，消除死代码和命名冲突
- P1: 拆分代码巨石，提升可维护性（只移动代码，不改逻辑）
- P2: 补全缺失功能，提升系统完成度到 95%
- P3: 架构演进，为 Nini 3.0 奠定基础

**Non-Goals:**
- 不添加新的 AI 模型或外部服务
- 不修改核心 ReAct 循环逻辑（Phase 3 只拆不分）
- 不改技能的业务逻辑（只改接入方式）
- 不重构数据库 schema

## Decisions

### Decision 1: 异步修复方案 - async/await 而非 nest_asyncio

**问题**: `runner.py:1359-1360` 使用 `asyncio.get_event_loop().run_until_complete()` 在已运行的事件循环中调用会抛出 RuntimeError

**方案选择**:
- 选项 A: 使用 `nest_asyncio` 补丁 - 简单但引入魔法，可能隐藏其他问题
- 选项 B: 将 `_build_messages_and_retrieval` 改为 async，使用 await - **选中**

**理由**: 选项 B 更符合 Python asyncio 最佳实践，调用处 `run()` 已是 async generator，直接 await 即可，无副作用。

### Decision 2: 统计 Fallback 接入点 - 在 _execute_tool 层

**问题**: `runner.py:2379` 直接调用 `execute()`，未使用已实现的 `execute_with_fallback()`

**接入点选择**:
- 选项 A: 在 runner.py 中替换调用 - **选中**
- 选项 B: 修改 SkillRegistry 默认行为

**理由**: 选项 A 改动最小，且允许特定技能选择不使用 fallback。fallback 触发时推送 REASONING 事件，让用户知道发生了降级。

### Decision 3: 代码巨石拆分策略 - 按职责垂直拆分

**runner.py 拆分**:
- 保留核心 ReAct 循环和事件调度在 `runner.py` (~600 行)
- 上下文构建 → `context_builder.py`
- 上下文压缩 → `context_compressor.py`
- 意图路由 → `intent_router.py`
- 工具执行 → `tool_executor.py`
- 推理追踪 → `reasoning_tracker.py`

**store.ts 拆分**:
- 创建 Zustand slices 模式
- `session-slice.ts`: 会话管理、消息历史
- `websocket-slice.ts`: WebSocket 连接、重连、心跳
- `event-handler.ts`: handleEvent switch + 17 种事件处理
- `plan-state-machine.ts`: 计划/任务状态机
- `api-actions.ts`: 所有 fetch 操作
- `normalizers.ts`: 数据规范化函数

**routes.py 拆分**:
- 主路由文件只保留 include_router
- 按资源分组到独立文件

### Decision 4: Token 持久化格式 - JSON Lines

**问题**: `SessionTokenTracker` 仅内存存储，重启丢失

**格式选择**:
- 选项 A: SQLite 表 - 结构化但需要 schema 迁移
- 选项 B: JSON Lines (jsonl) - **选中**

**理由**: jsonl 便于追加写入，与现有 `memory.jsonl` 格式一致，无需额外的 schema 管理。

### Decision 5: 功能开关默认值

```python
enable_cost_tracking: bool = True
enable_reasoning: bool = True
enable_knowledge: bool = True
knowledge_max_tokens: int = 2000
knowledge_top_k: int = 5
```

**理由**: 所有功能默认开启保持向后兼容，用户可通过环境变量关闭。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 代码拆分引入 import 循环 | 高 | 使用延迟导入 (TYPE_CHECKING)，分阶段验证 |
| async 修复影响其他异步代码 | 中 | 全量 pytest 覆盖，特别关注 knowledge 测试 |
| store.ts 拆分破坏状态持久化 | 高 | 保持 serialize/deserialize 逻辑不变 |
| Token 持久化写放大 | 低 | 批量写入或异步刷盘 |
| Phase 改动互相依赖 | 中 | 严格按阶段顺序执行，每阶段独立验证 |

## Migration Plan

### 阶段执行顺序
1. **Phase 1** (P0): 修复 Bug 和功能断联 → 立即验证核心流程
2. **Phase 2** (P1): 清理代码质量 → 类型检查和 lint 通过
3. **Phase 3** (P1): 拆分代码巨石 → 测试无回归
4. **Phase 4** (P2): 功能补全 → E2E 测试通过
5. **Phase 5** (P3): 架构演进 → 可选发布

### 回滚策略
- 每阶段独立分支，可单独 revert
- Phase 3 代码拆分保持 git history（使用 git mv）
- 关键 Bug 修复（Phase 1）优先合并，不等待后续阶段

## Open Questions

1. **ReasoningTimeline 组件**: 当前未使用，是否集成到 MessageBubble 还是直接删除？
2. **CostPanel 位置**: 顶栏 Coins 图标 vs 侧边栏标签，需要 UI 确认
3. **Phase 5 优先级**: 是否所有项目都需要在 Nini 3.0 之前完成？
