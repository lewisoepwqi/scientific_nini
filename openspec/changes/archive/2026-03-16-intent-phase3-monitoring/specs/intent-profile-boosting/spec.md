## ADDED Requirements

### Requirement: apply_boost 基于用户偏好方法对意图候选评分加权

`src/nini/intent/profile_booster.py` SHALL 提供 `apply_boost(candidates: list[IntentCandidate], user_profile: UserProfile) -> list[IntentCandidate]` 函数。仅基于 `UserProfile.preferred_methods`（方法偏好权重），对对应 capability 的候选评分加 boost_delta（范围 [0, 3]），返回重新排序后的候选列表。`research_domains` 不参与本阶段 Boosting。

#### Scenario: 习惯 t_test 的用户 difference_analysis 排名提升

- **WHEN** `user_profile.preferred_methods = {"t_test": 0.8}` 且 `difference_analysis` 在候选列表中
- **THEN** `apply_boost()` 返回列表中 `difference_analysis` 的 score 高于未 Boost 时

#### Scenario: 无匹配偏好时评分不变

- **WHEN** `user_profile.preferred_methods = {}`
- **THEN** `apply_boost()` 返回列表的分数与输入相同，顺序不变

### Requirement: analyze() 接受 user_profile 参数并调用 Boosting

`OptimizedIntentAnalyzer.analyze()` SHALL 接受 `user_profile: UserProfile | None = None` 参数。当 `user_profile` 非 `None` 时，在构建候选列表后调用 `apply_boost(candidates, user_profile)` 并用结果替换 `analysis.capability_candidates`。

#### Scenario: 传入 user_profile 时 Boosting 生效

- **WHEN** 调用 `analyze(query, user_profile=profile)` 且 profile 有明确偏好方法
- **THEN** 返回的 `capability_candidates` 顺序可能与不传 user_profile 时不同

#### Scenario: 不传 user_profile 时行为与 Phase 2 完全一致

- **WHEN** 调用 `analyze(query)` 不传 `user_profile`
- **THEN** 返回结果与 `analyze(query, user_profile=None)` 完全相同

### Requirement: 低置信度查询写入专用日志

当 `analyze()` 完成后，若 `capability_candidates` 为空或 Top-1 分数 < 3.0，SHALL 通过 `logging.getLogger("nini.intent.lowconf")` 写入 INFO 级别日志，内容包含 `query`（截断到 200 字符）、`top_score`、`timestamp`（ISO 格式）。

#### Scenario: 低分查询触发低置信度日志

- **WHEN** 用户输入无任何意图关键词的查询，Top-1 分数 < 3.0
- **THEN** `nini.intent.lowconf` logger 记录一条包含 query 和 top_score 的 INFO 日志

#### Scenario: 高分查询不触发低置信度日志

- **WHEN** 用户输入明确科研查询，Top-1 分数 >= 3.0
- **THEN** `nini.intent.lowconf` logger 无新增记录
