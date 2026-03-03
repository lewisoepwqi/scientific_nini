## 1. 运行时上下文入口收敛

- [x] 1.1 收敛 `src/nini/agent/runner.py` 与 `src/nini/agent/components/context_builder.py` 的消息构建逻辑，明确唯一生产入口
- [x] 1.2 让 `AgentRunner` 委托 canonical context builder，并移除重复的上下文注入实现
- [x] 1.3 为上下文构建收敛补回归测试，验证同一会话状态下生成的 messages 顺序与标签一致

## 2. Prompt Policy 集中治理

- [x] 2.1 新建统一的 prompt policy 模块，迁移可疑模式、非对话事件类型与上下文预算常量
- [x] 2.2 更新 `runner.py`、`context_builder.py`、相关辅助函数与测试，统一使用集中策略常量
- [x] 2.3 补充测试，验证可疑上下文过滤、非对话事件排除和预算阈值行为未回归

## 3. 不可信上下文协议统一

- [x] 3.1 统一数据集、知识、AGENTS.md、AnalysisMemory、ResearchProfile 等上下文块的 header 与顺序协议
- [x] 3.2 调整 `src/nini/knowledge/context_injector.py` 与运行时上下文拼装逻辑，确保知识始终作为非指令资料注入
- [x] 3.3 新增提示词契约测试，验证 system prompt 不包含不可信上下文且 runtime context 标签完全一致

## 4. System Prompt 组件职责收口

- [x] 4.1 精简 `src/nini/agent/prompts/builder.py` 职责，确保其只装配受信系统组件
- [x] 4.2 调整默认 prompt 组件与文件系统组件加载逻辑，保留热刷新与预算保护
- [x] 4.3 补充测试，验证组件刷新、截断保护和核心 system 指令保留策略

## 5. 文档与回归验证

- [x] 5.1 新增提示词架构文档，说明 system prompt、runtime context、tool schema 的分层与信任边界
- [x] 5.2 更新现有开发文档或测试说明，明确 prompt 相关修改的最小验证清单
- [x] 5.3 运行提示词相关回归：`pytest tests/test_prompt_guardrails.py tests/test_prompt_improvements.py tests/test_ecosystem_alignment.py -q`
- [x] 5.4 运行最小全量回归：`pytest -q`
