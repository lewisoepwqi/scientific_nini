## Why

当前 Skills 系统已经具备目录扫描、语义目录、说明层读取、资源清单读取等基础能力，但距离行业内成熟的 Coding Agent Skills 规范仍有明显差距：

- 渐进式披露只做到“索引层 + 正文层 + 文件树层”，没有做到“正文引用资源按需展开”
- Markdown Skill 的元数据会进入 `SKILLS_SNAPSHOT`，并被注入 trusted system prompt，trusted / untrusted 边界不清晰
- `allowed-tools` 仅作推荐提示，不具备执行约束，无法形成稳定、可审计的技能包契约
- Skill 相关运行时上下文没有独立预算控制，容易挤压真实对话与工具结果
- `AGENTS.md` 被当作不可信参考，而不是项目级受信约束，与主流 Agent 生态不一致
- 绝对路径被暴露到 API 和模型上下文中，增加实现耦合与信息泄露风险

这些问题会同时影响三件事：系统稳定性、技能可复用性、以及对外兼容度。需要通过一次明确的 OpenSpec 提案，把 Skills 的能力边界、提示词边界和执行语义一起收敛。

### 扩展背景：记忆系统与 Agent 质量研究发现

通过对 GSD 元提示系统（Plan-and-Execute 模式）、mem0、momOS、Memary 三种记忆范式的调研，识别出以下与本提案高度相关的改进点，纳入统一管理：

- `consolidate_session_memories` 在 WebSocket 断开时不触发，导致会话记忆丢失
- `PlannerAgent` 无 Goal-Backward 验证机制（must_haves），无法确认分析任务实际达成
- `ModelResolver.chat()` 的 `purpose` 路由缺少 `planning` 和 `verification` 语义，规划与验证阶段使用默认模型
- `TaskManager` 存在 `depends_on` 字段但未实际使用，任务只能线性执行
- 长期记忆注入缺少可观测日志，注入效果无法评估

## What Changes

- 将 Markdown Skills 升级为四层渐进式披露模型：
  - 索引层
  - 说明层
  - 资源清单层
  - 引用内容层（按需展开）
- 将正文中对 `references/`、`scripts/`、`assets/` 等资源的引用纳入正式契约，定义只读最小集、路径校验和缺失处理
- 将 `allowed-tools` 从“推荐提示”提升为“执行期硬约束白名单”
- 将 `AGENTS.md` 提升为 trusted 项目级约束，进入 system prompt 的 trusted assembly boundary
- 禁止 Markdown Skill 可编辑元数据原文进入 trusted system prompt；trusted prompt 仅接收系统生成的技能摘要
- 为 Skill 相关运行时上下文建立独立预算与裁剪顺序，避免只裁剪历史消息
- 统一 Skill 相关 API 与模型上下文中的路径表示，避免暴露绝对路径
- 补全 `consolidate_session_memories` 触发链路（WebSocket disconnect/stop 场景）
- 在 `ExecutionPlan` 引入 `must_haves`（truths/artifacts/key_links），支持 Goal-Backward 验证
- 扩展 `ModelResolver` purpose 路由，新增 `planning` 和 `verification` 语义
- 启用 `TaskManager` 的依赖声明，支持 wave 级并行任务调度
- 为长期记忆注入增加可观测日志
- 将高重要性记忆（importance >= 0.8）自动沉淀机制整合到 runtime context 预算框架内

## Capability Mapping

### Modified Capabilities

- `skills`
- `prompt-system-composition`
- `prompt-runtime-context-safety`
- `agent-runner` (consolidate 触发、Goal-Backward 验证)
- `model-routing` (purpose 语义扩展)
- `memory-system` (触发链路、可观测性、自动沉淀)
- `task-management` (wave 并行调度)

### No New Runtime Capability Names

本提案不新增面向用户的独立 Runtime Capability 名称，而是在现有规范上补齐缺失契约。Modified Capabilities 中新增的 `agent-runner`、`model-routing`、`memory-system`、`task-management` 是内部实现模块标识，用于追踪变更范围，不作为新的用户可见能力对外发布。

## Product Decisions Locked

- `AGENTS.md` 采用 trusted 约束语义
- `allowed-tools` 采用硬约束白名单语义

## Non-Goals

- 本提案不修改 Function Tool 体系本身的能力边界
- 本提案不重新设计全部意图分析算法，只约束其与 Skills 的接口行为
- 本提案不定义新的前端交互形态，只要求现有 API 与上下文契约稳定可用（P3 任务 10.3 的 depends_on 前端展示作为独立 PR 执行，不在本提案范围内）
