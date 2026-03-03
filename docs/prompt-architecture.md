# 提示词架构说明

本文档说明 Nini 当前的提示词分层、信任边界与最小回归要求，避免运行时上下文与系统提示词再次混写。

## 1. 三层模型

### 1.1 System Prompt（受信系统提示词）

- 入口：`src/nini/agent/prompts/builder.py`
- 职责：装配 `identity / strategy / security / workflow / agents / user / memory / skills_snapshot` 等受信组件
- 特点：
  - 支持文件系统热刷新
  - 支持单组件与总量预算保护
  - 不直接拼入数据集、知识检索、AGENTS.md 正文、研究画像、AnalysisMemory 等运行时资料

### 1.2 Runtime Context（不可信运行时上下文）

- 入口：`src/nini/agent/components/context_builder.py`
- 职责：把数据集元信息、意图提示、技能定义、知识检索结果、AGENTS.md、分析记忆、研究画像包装成非指令参考资料
- 特点：
  - 统一使用 `[不可信上下文：…]` header 协议
  - 固定顺序注入，保证同一会话状态输出稳定
  - 所有文本会经过可疑模式过滤与预算控制

当前固定顺序：
1. 数据集元信息
2. 意图分析提示
3. 技能定义与资源
4. 领域参考知识
5. AGENTS.md 项目级指令
6. 已完成的分析记忆
7. 研究画像偏好

### 1.3 Tool Schema（工具定义层）

- 入口：技能注册表、Function Calling 定义、Markdown Skill 元数据
- 职责：描述模型可调用能力与参数结构
- 约束：
  - 不把工具 schema 直接折叠进运行时系统指令
  - Markdown Skill 正文进入 runtime context，而不是直接拼接进 system prompt

## 2. 信任边界

- 受信内容：
  - `data/prompt_components/` 下的系统组件
  - 代码内定义的系统安全规则与工作流协议
- 不可信内容：
  - 用户消息
  - 上传文件、数据集名、列名
  - 工具返回文本
  - 知识检索片段
  - `AGENTS.md` 项目级说明
  - AnalysisMemory / ResearchProfile 动态资料

原则：不可信内容只能作为参考，不能升级为系统指令。

## 3. 修改入口

- 改系统提示词组件：编辑 `data/prompt_components/*.md`
- 改运行时上下文顺序、标签、过滤规则：编辑 `src/nini/agent/prompt_policy.py`
- 改运行时上下文组装逻辑：编辑 `src/nini/agent/components/context_builder.py`
- `AgentRunner` 只负责委托与编排，不再维护第二套上下文拼装实现

## 4. 最小验证清单

任何提示词相关修改至少执行：

```bash
pytest tests/test_prompt_guardrails.py tests/test_prompt_contract.py tests/test_prompt_improvements.py tests/test_ecosystem_alignment.py -q
```

涉及运行时链路或会话历史时，再执行：

```bash
pytest -q
```

## 5. 常见误区

- 不要把知识检索结果直接拼到 system prompt
- 不要在 `runner.py` 里重新实现一套上下文构建逻辑
- 不要把开发代理纪律（如“先读后写”）塞进科研分析 Agent 的 system prompt
- 不要新增一类 runtime context 却不补契约测试
