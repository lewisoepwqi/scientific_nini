# context-aware-memory-ranking Specification

## Purpose
TBD - created by archiving change optimize-memory-prompt-system. Update Purpose after archive.
## Requirements
### Requirement: 长期记忆检索使用情境加权 + 时间衰减复合评分
系统 SHALL 在长期记忆检索排序中，综合考虑记忆的基础重要性、访问次数、当前情境匹配度和时间衰减因子，而非仅按 importance_score 排序。

检索路径 SHALL 优先通过 `MemoryManager.prefetch_all()` 执行，`MemoryManager` 不可用时降级为 `LongTermMemoryStore.search()`（向后兼容路径，P5 阶段删除）。

#### Scenario: 与当前数据集匹配的记忆获得评分提升
- **WHEN** `search()` 或 `prefetch()` 被调用时传入包含当前数据集名称的上下文
- **AND** 某记忆的 `sci_metadata.dataset_name` 与当前数据集相同
- **THEN** 该条目的最终评分 SHALL 乘以情境权重因子（≥ 1.3）
- **AND** 其排名 SHALL 优先于其他条件相同但来自不同数据集的条目

#### Scenario: 与当前分析类型匹配的记忆获得评分提升
- **WHEN** 检索上下文包含当前分析类型
- **AND** 某记忆的 `sci_metadata.analysis_type` 与当前分析类型相同
- **THEN** 该条目的最终评分 SHALL 乘以分析类型权重因子（≥ 1.3）

#### Scenario: 旧记忆重要性随时间衰减
- **WHEN** 某记忆的 `created_at` 距当前已超过 30 天
- **THEN** 其评分 SHALL 低于同等 importance_score 但创建时间更近的条目
- **AND** 衰减函数 SHALL 使用 `e^(-λ × days)`，λ 不大于 0.02

#### Scenario: 高频访问记忆的衰减速度降低
- **WHEN** 某记忆的 `access_count >= 5`
- **THEN** 其时间衰减速率 SHALL 低于访问次数少的记忆

#### Scenario: 无上下文时仍正常排序
- **WHEN** 检索调用不传入情境信息
- **THEN** 系统 SHALL 按 importance × 时间衰减 × 访问次数加成排序
- **AND** SHALL NOT 应用任何情境权重
- **AND** SHALL NOT 抛出异常

### Requirement: 长期记忆检索支持最小重要性阈值过滤
系统 SHALL 在检索时允许调用方过滤低于指定重要性分值的记忆条目，防止低质量旧记忆污染结果。

#### Scenario: min_importance 过滤生效
- **WHEN** 检索方法被调用时传入 `min_importance=0.3`
- **THEN** importance < 0.3 的条目 SHALL NOT 出现在返回结果中
- **AND** 过滤在情境加权和时间衰减计算之前执行（基于原始 importance 值）

### Requirement: 长期记忆检索主路径通过 MemoryManager 执行
系统 SHALL 在 `build_long_term_memory_context()` 中优先调用 `MemoryManager.prefetch_all()`，失败时降级到 `LongTermMemoryStore.search()`，两条路径对调用方透明（接口签名不变）。

#### Scenario: MemoryManager 可用时走新路径
- **WHEN** `get_memory_manager()` 返回的 `MemoryManager` 已注册 providers
- **AND** `build_long_term_memory_context(query)` 被调用
- **THEN** 实际检索 SHALL 通过 `MemoryManager.prefetch_all()` 执行
- **AND** 返回值 SHALL 用 `<memory-context>` 标签包裹（非 `<untrusted-context>` 标签）

#### Scenario: MemoryManager 不可用时降级到旧路径
- **WHEN** `MemoryManager` 未注册任何 provider（空实例）
- **AND** `build_long_term_memory_context(query)` 被调用
- **THEN** 系统 SHALL 降级到 `LongTermMemoryStore.search()` 执行
- **AND** SHALL NOT 向调用方抛出异常

