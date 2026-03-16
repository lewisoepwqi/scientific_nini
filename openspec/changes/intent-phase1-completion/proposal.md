## Why

Phase 0 已修复 Harness 误判和路由缺口，并完成同义词 YAML 化基础工作，但意图体系在两个维度仍有缺口：`CapabilityRegistry` 中缺少 `citation_management`、`peer_review`、`research_planning` 三个 Capability 的正式定义（导致这三条路由路径无法经由意图层触发），同时 `_OUT_OF_SCOPE_RE` 仅覆盖联网检索类请求，用户提交"订机票"、"天气查询"等非科研请求时会 fallback 到 CASUAL_CHAT 并触发 LLM 自由回答，存在无意义执行风险。

## What Changes

- **新增** 三个 Capability 的正式定义：`citation-management`、`peer-review`、`research-planning`，追加到 `create_default_capabilities()`，完成意图层到路由层的完整通路
- **扩充** `config/intent_synonyms.yaml`，为三个新 Capability 添加完整同义词列表（含中英文科研术语）
- **扩展** `_OUT_OF_SCOPE_RE` 或新增 `_GENERAL_OOS_KEYWORDS` 黑名单，覆盖非科研类通用请求
- **新增** `QueryType.OUT_OF_SCOPE` 枚举值，命中 OOS 时设置该类型，LLM 返回引导性回复而非执行工具

## Capabilities

### New Capabilities

- `citation-management`：引用管理能力——支持参考文献格式化、引用规范转换（APA/MLA/GB），映射到 `citation_manager` Agent
- `peer-review`：同行评审辅助能力——整理审稿意见、生成回复信件，映射到 `review_assistant` Agent
- `research-planning`：研究规划能力——研究设计、实验方案制定、任务拆解，映射到 `research_planner` Agent

### Modified Capabilities

（无现有 spec 级别的行为变更）

## Impact

- `src/nini/capabilities/defaults.py`：在 `create_default_capabilities()` 末尾追加三个 Capability 字面量
- `src/nini/intent/base.py`（或同路径）：`QueryType` 枚举新增 `OUT_OF_SCOPE`
- `src/nini/intent/optimized.py`：扩展 OOS 检测逻辑，`OUT_OF_SCOPE` 类型时跳过工具路由
- `config/intent_synonyms.yaml`：补充三个新 Capability 的同义词
- 无 API 变更，无数据库迁移，无新外部依赖
