## Why

当前意图路由与 Harness 完成校验存在两个直接影响用户体验的 Bug：`HarnessRunner` 将 AI 介绍自身能力时提到"图表"/"报告"误判为"已承诺产物未交付"，导致同一消息收到两次完整回答；同时 `TaskRouter` 的内置规则和 LLM Prompt 仅覆盖 9 个 Specialist Agent 中的 6 个，`citation_manager`、`research_planner`、`review_assistant` 三个 Agent 已有 YAML 定义但永远无法被路由触发。此外，意图分析器的同义词表硬编码在 Python 源码中，每次扩展都需要改代码，维护成本高。

## What Changes

- **修复**：`HarnessRunner._run_completion_check` 中 `promised_artifact` 检测逻辑，改为要求"完成语义词 + 产物词"组合匹配，消除能力描述类文本的误判
- **修复**：`TaskRouter` 内置规则表补充 `citation_manager`、`research_planner`、`review_assistant` 三条关键词规则，同步更新 LLM 兜底 Prompt 中的 Agent 列表
- **新增**：意图同义词外置配置能力，将 `_SYNONYM_MAP` 从 Python 源码迁移到 YAML 配置文件，支持运行时加载，无需修改代码即可扩展同义词

## Capabilities

### New Capabilities

- `intent-synonyms-config`：意图同义词 YAML 化配置——支持从外部 `config/intent_synonyms.yaml` 加载同义词映射，优先级高于代码内置，缺失时自动回退到内置 dict

### Modified Capabilities

- `task-router`：新增 3 条内置路由规则（`citation_manager` / `research_planner` / `review_assistant`），并更新 LLM 路由 Prompt 中的可用 Agent 列表，确保规则覆盖率从 6/9 提升到 9/9
- `agent-harness-runtime`：收紧"承诺产物已生成"校验条件——仅当最终文本出现"完成语义词（已生成/已导出/以下是/请查看等）+ 产物词（图表/报告/产物等）"组合时才判定为承诺，消除能力描述类文本的误触发

## Impact

- `src/nini/harness/runner.py`：修改 `_run_completion_check` 中第 385 行的 `promised_artifact` 正则
- `src/nini/agent/router.py`：`_BUILTIN_RULES` 新增 3 条规则；`_LLM_ROUTING_PROMPT` 和 `_LLM_BATCH_ROUTING_PROMPT` 补充 3 个 Agent 描述
- `src/nini/intent/optimized.py`：`OptimizedIntentAnalyzer.__init__` 中增加 YAML 加载逻辑；`_SYNONYM_MAP` 保留作 fallback
- `config/intent_synonyms.yaml`（新建）：外置同义词配置文件，初始内容与现有 `_SYNONYM_MAP` 一致
- 无 API 变更，无数据库迁移，无依赖新增
