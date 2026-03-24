## Why

`ToolRegistry` 的 `expose_to_llm` 分层机制已经就绪（目前 31 个工具暴露给 LLM，2 个隐藏），但没有"按需发现"隐藏工具的入口——LLM 无法知道隐藏工具的存在，也无法在需要时主动获取其 schema。随着工具数量增长（目前 31 个可见），全量 schema 注入消耗约 3000-5000 token/次。引入 `search_tools` 工具后，可将低频工具标记为 `expose_to_llm = False`，由 LLM 按需发现，从而减少 context token 消耗。

## What Changes

- 新增 `src/nini/tools/search_tools.py`：`SearchToolsTool`，接收查询字符串，返回匹配的隐藏工具名称 + 描述 + 完整 schema
- 查询支持两种形式：`select:name1,name2`（精确名称）、关键词搜索（匹配名称和描述）
- 在 `tools/registry.py` 中注册该工具，并给 `SearchToolsTool` 自身设置 `expose_to_llm = True`
- 评估现有 31 个可见工具，将低频/专业工具标记为 `expose_to_llm = False`（目标：将 LLM 可见工具减少到 15-20 个）
- 在 system prompt 中补充 `search_tools` 的使用说明

## Capabilities

### New Capabilities

- `deferred-tools`：LLM 按需发现隐藏工具的能力（`search_tools` 工具 + 工具可见性分层配置）

### Modified Capabilities

（无现有规格变更）

## Impact

- **新增文件**：`src/nini/tools/search_tools.py`
- **修改文件**：
  - `src/nini/tools/registry.py`（注册 `SearchToolsTool`）
  - 约 10-15 个工具文件（将 `expose_to_llm` 改为 `False`）
  - `src/nini/agent/prompts/builder.py`（补充 `search_tools` 使用说明）
- **行为变化**：被隐藏的工具 LLM 无法直接调用，需要先通过 `search_tools` 发现。如果 system prompt 指导不够清晰，可能导致 LLM 遗漏某些工具——需要谨慎控制隐藏范围，优先隐藏低频工具
