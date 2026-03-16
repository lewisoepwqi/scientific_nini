## Why

Phase 2 完成后，意图系统已具备多意图检测、子检验类型识别和数据集感知澄清策略，但在两个方向仍缺乏基础设施：（1）系统不感知用户历史偏好——同一个"分析差异"请求，对生物医学领域用户应优先推荐 Mann-Whitney，对习惯用 ANOVA 的用户应优先推荐方差分析，但当前意图分数完全基于文本匹配，忽略了 `UserProfile.preferred_methods` 和 `domain` 已有的信息；（2）没有任何定量指标衡量意图识别质量——团队无法知道澄清触发率是否真的降低了，也无法在引入新同义词后回归测试准确率，更无法监控线上低置信度查询的趋势。

## What Changes

- **新增** `src/nini/intent/profile_booster.py`：基于 `UserProfile.preferred_methods` 的意图评分 Boosting 函数（本次只用方法偏好权重，不使用 `research_domains`），在 `analyze()` 中对候选评分做后处理调整
- **修改** `OptimizedIntentAnalyzer.analyze()`：新增可选参数 `user_profile: UserProfile | None = None`，传入时调用 `profile_booster` 后处理候选排序
- **新增** `tests/fixtures/intent_eval_dataset.yaml`：90 条带标注的评估查询（50 条域内、20 条模糊/多意图、20 条 OOS），作为意图准确率基线
- **新增** `tests/test_intent_eval.py`：基于评估数据集的参数化测试，在 session 结束时打印 Top-1 准确率和 OOS 召回率汇总；首次运行用于建立基线，准确率目标（>= 80%）为长期迭代指标而非 CI 断言
- **新增** 低置信度查询结构化日志：在 `analyze()` 中，当最高候选分数 < 阈值时写入专用 logger（`nini.intent.lowconf`），供运维分析

## Capabilities

### New Capabilities

- `intent-profile-boosting`：用户画像意图 Boosting——基于用户历史偏好方法（`preferred_methods`），对意图候选评分做加权调整，相同文本对不同用户返回不同排名
- `intent-evaluation`：意图评估基线——提供 YAML 格式的带标注评估数据集和对应的参数化测试套件，可持续追踪意图识别准确率

### Modified Capabilities

（无现有 spec 级别行为变更）

## Impact

- `src/nini/intent/profile_booster.py`（新建）：Boosting 逻辑
- `src/nini/intent/optimized.py`：`analyze()` 新增 `user_profile` 参数，低置信度日志记录
- `tests/fixtures/intent_eval_dataset.yaml`（新建）：评估数据集
- `tests/test_intent_eval.py`（新建）：评估测试套件
- 无 API 变更，无数据库迁移，无新外部依赖
