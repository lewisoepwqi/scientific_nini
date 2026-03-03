## Why

当前项目的提示词体系已经具备组件化、运行时刷新和基础注入防护，但运行时消息构建仍同时存在于 `AgentRunner` 与 `ContextBuilder` 两套实现中，导致提示词边界、安全规则和上下文标签容易漂移。现在进入维护阶段后，如果不先收敛提示词架构，后续对知识注入、研究画像、AGENTS.md、技能上下文的任何调整都会继续放大维护成本和回归风险。

## What Changes

- 收敛提示词与上下文构建为单一运行时入口，避免 `AgentRunner` 与 `ContextBuilder` 双份实现继续分叉。
- 抽取统一的 prompt policy 常量，集中管理可疑上下文模式、非对话事件类型、上下文预算与截断阈值。
- 明确 system prompt 与 runtime context 的信任边界，统一“不可信上下文”标签、块结构与注入顺序。
- 精简 `PromptBuilder` 职责，使其只负责受信系统组件装配，不再承载运行时上下文拼装语义。
- 增加提示词契约测试与文档，覆盖 system prompt 组件、runtime context 注入、安全边界和回归要求。

## Capabilities

### New Capabilities
- `prompt-system-composition`: 定义系统提示词组件的装配、刷新、预算保护与职责边界。
- `prompt-runtime-context-safety`: 定义运行时上下文的注入顺序、可信边界、不可信标签协议与回归约束。

### Modified Capabilities
- `conversation`: 会话运行时上下文需要遵循统一的 prompt/runtime contract，避免同一会话在不同构建路径下生成不同上下文。
- `explainability-enhancement`: reasoning 相关上下文与展示所依赖的运行时资料需要遵循统一的注入边界与标签协议。

## Impact

- 受影响代码：`src/nini/agent/runner.py`、`src/nini/agent/components/context_builder.py`、`src/nini/agent/prompts/builder.py`、`src/nini/knowledge/context_injector.py`
- 受影响测试：`tests/test_prompt_guardrails.py`、`tests/test_prompt_improvements.py`、`tests/test_ecosystem_alignment.py`，并新增提示词契约测试
- 受影响文档：新增提示词架构说明文档，并更新与 prompt/runtime context 边界有关的开发文档
- 无外部依赖新增；重点影响运行时上下文构建、提示词回归策略与维护流程
