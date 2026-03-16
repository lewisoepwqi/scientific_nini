## Context

`intent-system-optimization` 完成了 Phase 0 全部修复和 Phase 1-P1-1（同义词 YAML 化）。当前剩余两个缺口：

1. **Capability 缺口**：`capabilities/defaults.py` 的 `create_default_capabilities()` 只返回 8 个 Capability，缺少 `citation_management`、`peer_review`、`research_planning`。这三个 Capability 已有对应的 Specialist Agent YAML（`citation_manager` / `review_assistant` / `research_planner`），但意图层无法推荐它们，用户通过能力列表/意图匹配无法触达。

2. **OOS 缺口**：`QueryType` 枚举没有 `OUT_OF_SCOPE` 值，非科研类通用请求（订机票、天气、播放音乐等）无法被快速拒绝，会 fallback 到 `CASUAL_CHAT` 由 LLM 自由处理。

## Goals / Non-Goals

**Goals:**
- 在 `create_default_capabilities()` 中追加三个 Capability，使意图层可以推荐并路由到对应 Agent
- `config/intent_synonyms.yaml` 中为三个新 Capability 补充完整同义词
- 新增 `QueryType.OUT_OF_SCOPE`；扩展 `_OUT_OF_SCOPE_RE` 覆盖通用非科研类词汇；`_classify_query_type` 命中时返回 `OUT_OF_SCOPE`

**Non-Goals:**
- 不新增这三个能力的可执行 Executor（`is_executable=False`，走 Agent 对话路径）
- 不修改 `TaskRouter` 路由规则（已在 Phase 0 中完成）
- 不实现 OOS 时的专用 LLM 提示词（Agent 已有能力解释边界）

## Decisions

### 决策 1：Capability 定义放在 `defaults.py` 而非新文件

三个新 Capability 均为"对话驱动型"（`is_executable=False`），无需 Executor 类，直接在 `create_default_capabilities()` 末尾追加 `Capability(...)` 字面量即可，与现有 `report_generation`、`article_draft` 的写法完全一致。

**备选**：新建 `capabilities/research_services.py` 模块——被否决，过度工程，三个字面量加进去不超过 60 行。

### 决策 2：OOS 黑名单追加到现有 `_OUT_OF_SCOPE_RE`，不新建正则

现有 `_OUT_OF_SCOPE_RE` 已有联网检索类词汇，语义上属于同一类"超出服务范围"检测。直接扩展同一正则，`_classify_query_type` 逻辑不变，只需在命中时返回 `QueryType.OUT_OF_SCOPE`（目前命中返回 `CASUAL_CHAT`）。

**备选**：新建 `_GENERAL_OOS_RE`——被否决，两个正则触发逻辑相同，分开维护增加认知负担。

### 决策 3：`QueryType.OUT_OF_SCOPE` 不影响现有 RAG 门控

`analysis.rag_needed` 当前条件为 `query_type in {DOMAIN_TASK, KNOWLEDGE_QA}`，`OUT_OF_SCOPE` 不在集合内，自动跳过 RAG，无需改动。Agent runner 收到 `OUT_OF_SCOPE` 时与 `CASUAL_CHAT` 一样走纯 LLM 路径，但下游可以检查该字段决定是否给出引导性回复（本次改动不要求实现此逻辑，留作 hook）。

## Risks / Trade-offs

**[风险 1] 新 Capability 同义词触发误匹配** → `peer_review` 的"审稿"可能与 `writing_assistant` 的"写作"在某些查询中产生竞争（如"帮我写审稿意见回复"）。缓解：意图分析器返回 Top 5 候选，多命中时澄清逻辑可介入；`TaskRouter` 规则路由已在 Phase 0 中为 `review_assistant` 精确定义了关键词集合。

**[风险 2] OOS 黑名单误拦科研相关词** → "天气"在气候研究场景下可能是合理科研词。缓解：黑名单选用高度通用的非科研词（"订机票"、"外卖"等），不包含领域双关词；`_OUT_OF_SCOPE_RE` 命中时 Agent 仍可回复，只是 `query_type` 变为 `OUT_OF_SCOPE`，不会硬性拒绝。

## Migration Plan

1. 三处改动均无破坏性变更，直接部署即可
2. `QueryType.OUT_OF_SCOPE` 新增枚举值不影响现有序列化（JSON 值为字符串 `"out_of_scope"`）
3. 回滚：`git revert` 本次提交；YAML 变更单独回滚删除新增条目即可
