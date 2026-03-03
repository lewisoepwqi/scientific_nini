## Context

当前 Nini 的运行时提示词体系分成两层：`PromptBuilder` 负责系统提示词组件装配，`AgentRunner` / `ContextBuilder` 负责把数据集、知识检索、技能定义、AGENTS.md、研究画像等运行时资料拼成 LLM messages。问题在于，运行时上下文构建同时存在于 `src/nini/agent/runner.py` 与 `src/nini/agent/components/context_builder.py` 两份实现中，且两边各自维护可疑模式、非对话事件类型、上下文预算和不可信标签，已经出现标点与标签文案漂移。

这个变更面向维护阶段的稳定性治理，不引入新的模型能力或外部依赖，而是收敛提示词架构，让后续对知识注入、研究画像、技能上下文、AGENTS.md 注入和 reasoning 展示的任何修改都走同一条链路，并受统一测试保护。

相关约束：

- 运行时系统提示词必须继续支持文件系统组件热刷新，不能退回为纯代码硬编码。
- 数据集、知识、AGENTS.md、研究画像等资料必须继续作为“不可信上下文”进入对话，而不是直接提升为 system prompt。
- 提示词架构改动不能破坏现有 prompt guardrails、生态对齐和 reasoning 相关测试。

## Goals / Non-Goals

**Goals:**
- 建立唯一的运行时上下文构建入口，消除 `AgentRunner` 与 `ContextBuilder` 的双份实现。
- 抽取统一的 prompt policy 常量，单点维护注入过滤规则、预算阈值和上下文标签。
- 明确 system prompt 与 runtime context 的职责边界，让 `PromptBuilder` 只负责受信系统组件装配。
- 为 prompt/runtime context 建立契约测试，防止安全边界、标签协议和注入顺序回归。
- 补充架构文档，说明提示词资产的分层与变更流程。

**Non-Goals:**
- 不改写科研分析策略本身，不在本次变更中重新设计统计方法、工作流模板或 few-shot 内容。
- 不引入提示词 A/B 测试、自动评分平台或线上埋点系统。
- 不合并 `AGENTS.md` 与 `CLAUDE.md`，仅澄清它们在开发态和运行时的不同职责。
- 不改动 WebSocket 协议或前端消息生命周期契约，除非 prompt/runtime context 契约需要最小配套调整。

## Decisions

### 1. 以 `ContextBuilder` 作为唯一的运行时上下文构建实现

保留 `ContextBuilder.build_messages_and_retrieval()` 作为唯一生产实现，`AgentRunner` 只做委托和编排。

原因：
- `ContextBuilder` 已经是组件层抽象，适合集中沉淀运行时上下文治理规则。
- 继续保留 runner 内联实现只会让 prompt 规则再次双写。

备选方案：
- 保留 runner 为主实现、删除 `ContextBuilder`：可行，但会削弱组件层边界，不利于后续单测与复用。
- 维持双实现，仅抽共享常量：不能解决构建顺序和标签协议漂移问题，因此拒绝。

### 2. 新增集中式 `prompt_policy` 模块统一策略常量

把可疑上下文模式、非对话事件类型、上下文预算、AGENTS.md 截断阈值等策略常量迁移到一个模块，例如 `src/nini/agent/prompt_policy.py`。

原因：
- 这些常量跨 `runner.py`、`context_builder.py`、知识注入和测试使用，属于策略，而非某个类的私有实现细节。
- 单点维护后，测试可以围绕策略模块建立明确断言。

备选方案：
- 继续放在 `runner.py` 中并由其他模块导入：职责不清，增加模块耦合。
- 放到 `config.py`：这些值大多不是用户配置，而是内部策略常量，不适合暴露为环境变量。

### 3. 明确三层提示词资产边界：system prompt / runtime context / tool schema

本次设计明确：
- `PromptBuilder` 只装配受信 system prompt 组件
- `ContextBuilder` 只拼装 runtime context，并显式标记为非指令
- Tool schema / Markdown Skills 保持作为单独层次，不混入 system prompt 文本说明

原因：
- 当前报告和实现混淆了“编码代理规则”和“科研分析 Agent 规则”，需要先切清边界。
- 这样能避免把“先读后写”等开发代理纪律错误塞进运行时分析 prompt。

备选方案：
- 把 AGENTS.md、知识片段、技能定义直接折叠进 system prompt：会扩大 prompt 注入面，拒绝。

### 4. 统一“不可信上下文”标签协议与注入顺序

所有运行时资料采用统一的 header 模板、统一标点和固定顺序：
1. 数据集元信息
2. 意图运行时上下文
3. 显式技能定义
4. 领域知识
5. AGENTS.md 项目级指令
6. AnalysisMemory
7. ResearchProfile

原因：
- 当前全角/半角和文案漂移会削弱模型对边界的稳定理解。
- 固定顺序让测试和排障都更稳定。

备选方案：
- 允许每类上下文自行定义 header：短期灵活，长期不可验证，因此拒绝。

### 5. 用契约测试替代“经验性 prompt 调整”

新增或扩展测试，覆盖：
- system prompt 不含不可信上下文
- runtime context 标签完全一致
- AGENTS.md / 知识检索 / 研究画像都以非指令形式进入消息
- `PromptBuilder` 的组件刷新与预算保护行为稳定

原因：
- 当前已有 [test_prompt_guardrails.py] 和 [test_prompt_improvements.py] 基础，可以继续扩展为架构级保护网。
- 这是维护阶段最实际的风险控制手段。

备选方案：
- 只靠文档规范：无法防止回归，不足以支撑后续频繁 prompt 调整。

## Risks / Trade-offs

- [收敛单一入口时可能改变上下文顺序] → 先用现有行为写契约测试，再重构实现，确保变更是显式的。
- [统一标签协议后可能影响部分 prompt 既有表现] → 保持语义不变，只统一格式；必要时对关键用例做回归对比。
- [抽出策略常量后测试引用位置变化] → 同步更新 prompt guardrails 与生态对齐测试，避免出现“代码改了、测试还指向旧模块”。
- [`PromptBuilder` 责任收缩后默认组件文本可能需要迁移] → 分阶段实施，先收敛运行时上下文，再调整 builder 默认文本。
- [AGENTS.md 仍然进入运行时上下文，可能继续带来噪音] → 本次仅保证它始终以“不可信上下文”注入；是否进一步瘦身 AGENTS 内容留到后续 change。

## Migration Plan

1. 新增 prompt policy 模块并补最小测试，不改变生产路径。
2. 让 `ContextBuilder` 接管唯一运行时上下文构建逻辑，`AgentRunner` 改为委托。
3. 统一不可信上下文标签与注入顺序，更新相关测试。
4. 精简 `PromptBuilder` 职责和默认组件文案，确保运行时上下文不再在 builder 层渗透。
5. 增加文档并运行完整后端测试。

回滚策略：
- 若上下文构建收敛导致行为异常，可先回滚到双实现状态，但保留新增测试与文档。
- 若统一标签协议影响模型表现，可仅回滚标签文案与顺序调整，而不回滚单一入口和常量收敛。

## Open Questions

- 是否需要把部分预算阈值提升为可配置项，还是维持内部常量即可？
- AGENTS.md 在运行时上下文中的内容是否应进一步裁剪成专用摘要，而不是直接复用开发文档全文？
- 知识检索结果是否需要单独的 runtime context 结构化对象，以减少纯文本模板的维护成本？
