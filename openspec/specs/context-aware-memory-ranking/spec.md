# context-aware-memory-ranking Specification

## Purpose
TBD - created by archiving change optimize-memory-prompt-system. Update Purpose after archive.
## Requirements
### Requirement: 长期记忆检索使用情境加权 + 时间衰减复合评分
系统 SHALL 在长期记忆检索排序中，综合考虑记忆的基础重要性、访问次数、当前情境匹配度和时间衰减因子，而非仅按 importance_score 排序。

#### Scenario: 与当前数据集匹配的记忆获得评分提升
- **WHEN** `search()` 被调用时传入 `context={"dataset": current_dataset}`
- **AND** 某 LongTermMemoryEntry 的 `source_dataset` 与 `current_dataset` 相同
- **THEN** 该条目的最终评分 SHALL 乘以情境权重因子（≥ 1.3）
- **AND** 其排名 SHALL 优先于其他条件相同但来自不同数据集的条目

#### Scenario: 与当前分析类型匹配的记忆获得评分提升
- **WHEN** `search()` 被调用时传入 `context={"analysis_type": current_type}`
- **AND** 某 LongTermMemoryEntry 的 `analysis_type` 与 `current_type` 相同
- **THEN** 该条目的最终评分 SHALL 乘以分析类型权重因子（≥ 1.3）

#### Scenario: 旧记忆重要性随时间衰减
- **WHEN** 某 LongTermMemoryEntry 的 `created_at` 距当前已超过 30 天
- **THEN** 其评分 SHALL 低于同等 importance_score 但创建时间更近的条目
- **AND** 衰减函数 SHALL 使用 `e^(-λ × days)`，λ 不大于 0.02（防止过度衰减）

#### Scenario: 高频访问记忆的衰减速度降低
- **WHEN** 某 LongTermMemoryEntry 的 `access_count >= 5`
- **THEN** 其时间衰减速率 SHALL 低于访问次数少的记忆
- **AND** 反复被检索的记忆 SHALL 在排序中保持更长时间的竞争力

#### Scenario: context 参数为 None 时仍正常排序
- **WHEN** `search()` 被调用时 `context=None`
- **THEN** 系统 SHALL 按 importance_score × 时间衰减 × 访问次数加成排序
- **AND** 不应用任何情境权重
- **AND** 函数 SHALL NOT 抛出异常

### Requirement: 长期记忆检索支持最小重要性阈值过滤
系统 SHALL 在检索时允许调用方过滤低于指定重要性分值的记忆条目，防止低质量旧记忆污染结果。

#### Scenario: min_importance 过滤生效
- **WHEN** `search()` 被调用时传入 `min_importance=0.3`
- **THEN** importance_score < 0.3 的条目 SHALL NOT 出现在返回结果中
- **AND** 过滤在情境加权和时间衰减计算之前执行（基于原始 importance_score）

