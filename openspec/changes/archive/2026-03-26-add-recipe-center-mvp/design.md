## Context

Nini 当前已经具备任务计划、工作区、WebSocket 事件流与多能力路由，但入口仍以通用会话为主。`docs/scienceclaw_benchmark_and_iteration_plan.md` 已将“任务入口产品化”列为第一个阶段，目标是在不重写 Tool/Capability/Skill 三层架构的前提下，把高频科研任务包装成可直接运行的模板入口。

现有系统已经有 `plan_progress`、`workspace_update` 等事件，也有工作区与任务状态基础设施，因此本次设计应优先复用这些现成机制，而不是引入新的大而全工作流引擎。

## Goals / Non-Goals

**Goals:**
- 提供首批 3 个可直接启动的 Recipe 模板，降低首用门槛。
- 定义最小可实现的 Recipe 元数据契约，支撑前端渲染与后端编排。
- 为 deep task 增加统一的任务状态、工作区初始化与步骤进度反馈。
- 为后续证据链、交付物导出和评测 change 提供稳定入口与上下文标识。

**Non-Goals:**
- 不在本 change 中实现 Citation Graph、Claim 校验、METHODS 自动生成。
- 不在本 change 中实现 Word/PPTX/LaTeX 导出、产物版本管理高级能力。
- 不重写现有 capability/router 架构，也不引入新的外部工作流引擎。

## Decisions

### 决策 1：Recipe 作为配置驱动的轻量编排层，而不是新的 Agent 类型

Recipe 只负责描述输入、步骤、默认输出和恢复规则，实际执行仍复用现有 Agent Runner、task manager、workspace 与事件体系。

备选方案：
- 方案 A：新增专用 Recipe Runner。
- 方案 B：在现有 Agent Runner 上增加 Recipe 上下文与步骤协议。

选择 B，因为它能最小化改动范围，并复用已有 `plan_progress`、任务状态和工作区逻辑。

### 决策 2：Phase A 只落 3 个高频 Recipe，避免模板数量先于执行契约稳定

文档原始设想是首批 6 个 Recipe，但 MVP 阶段先收敛到 3 个高频模板，更容易完成端到端闭环，也便于验证元数据 schema 是否足够稳定。

备选方案：
- 方案 A：一次上线 6 个模板。
- 方案 B：先上线 3 个模板，保留扩展字段。

选择 B，因为当前风险不在模板覆盖面，而在入口、状态机和工作区联动是否稳定。

### 决策 3：deep task 状态机与 WebSocket 事件做增量扩展

前端已经消费 `plan_progress`、`workspace_update` 等事件。本次新增 Recipe 生命周期事件时，优先扩展现有事件体系与 store，而不是定义一整套独立通道。

备选方案：
- 方案 A：重用现有 `plan_progress` 负载并附加 Recipe 元数据。
- 方案 B：新增 Recipe 专属事件，并与 `plan_progress` 并存。

选择“增量扩展并允许并存”的折中方案：保留 `plan_progress` 作为步骤展示基础，同时增加能标识 `recipe_id`、任务类型和恢复状态的协议字段，避免前端语义不清。

### 决策 4：项目工作区在 deep task 启动时显式绑定 `recipe_id`

后续证据链、交付物导出与回放评测都需要明确“本次任务来自哪个模板”。因此 deep task 初始化工作区时需要写入 `recipe_id` 和任务标识，作为跨阶段稳定锚点。

备选方案：
- 方案 A：仅在会话内存中记录 Recipe。
- 方案 B：在工作区与会话层同时记录。

选择 B，因为只记录在会话内存中无法支撑后续产物管理与恢复。

### 决策 5：MVP 分类策略采用规则优先

为了保证测试口径、前后端联调和回放评测的一致性，MVP 阶段的 `quick task` / `deep task` 分类采用确定性规则优先。显式启动的 Recipe 直接归类为 `deep task`，自由输入命中规则时进入对应路径，模型兜底延后到后续迭代。

备选方案：
- 方案 A：首版就引入模型参与分类兜底。
- 方案 B：MVP 先使用规则优先，保留后续扩展点。

选择 B，因为当前阶段更需要稳定口径，而不是更高但不稳定的召回。

## Risks / Trade-offs

- [模板定义过早固化] -> 仅承诺最小元数据契约，保留可扩展字段，不在 MVP 强化复杂 DAG 分支。
- [前端状态展示重复] -> 优先复用现有计划头部和任务面板，避免首页卡片、会话头和工作区各自维护独立状态机。
- [deep task 自动恢复误判] -> Phase A 只定义最小回退策略与重试上限，复杂冲突校验留给后续 change。
- [工作区初始化增加噪音] -> 仅在 deep task 启动时创建项目工作区，quick task 保持现状，避免普通对话被过度结构化。

## Migration Plan

1. 先落 Recipe 元数据 schema 与后端读取逻辑。
2. 接入首页 Recipe Center 与 deep task 状态展示，但默认保留原自由会话入口。
3. 完成 WebSocket 与工作区联动后，再接入首批 3 个 Recipe。
4. 如出现入口转化下降或任务失败率升高，可回退首页入口改动并保留底层契约，避免阻塞后续 change。

## Open Questions

- 首批 3 个 Recipe 最终选择是否需要结合真实 usage 数据再微调。
- 是否需要在 Phase A 就为 Recipe 增加最小成本预算字段，供后续成本治理复用。
