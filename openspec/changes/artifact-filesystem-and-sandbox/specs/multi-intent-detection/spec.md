## MODIFIED Requirements

### Requirement: 多意图并行标记词集合
`_PARALLEL_MARKERS` 正则表达式 SHALL 仅包含语义上真正独立并行的连接词：`同时`、`另外还`、`以及同时`。`顺便` SHALL 从并行标记词中移除（语义为主从关系而非独立并行），不再触发并行分类。

#### Scenario: "顺便"不触发并行分类
- **WHEN** 用户输入"分析数据，顺便帮我画个图"
- **THEN** `detect_multi_intent()` SHALL NOT 返回 `is_parallel=True` 的分类
- **AND** 系统 SHALL 按单一意图或顺序意图处理该请求

#### Scenario: "同时"触发并行分类
- **WHEN** 用户输入"同时进行数据清洗和统计分析"
- **THEN** `detect_multi_intent()` SHALL 返回多个子意图
- **AND** 对应的并行标记 SHALL 被正确识别

---

### Requirement: 并/串行标记互斥保存
`detect_multi_intent()` 在执行标点分割（策略 1）前，SHALL 先计算并保存 `is_parallel` 和 `is_sequential` 的布尔值。策略 1 分割后，返回的子意图列表 SHALL 附带对应的分类信息，供调用方（`router.py`）使用，而非由调用方重复扫描原始字符串。

#### Scenario: 标点分割路径保留分类信息
- **WHEN** 输入同时命中并行标记和串行标记（如"同时做A，然后做B"）
- **THEN** 标点分割结果 SHALL 附带 `is_parallel=True` 和 `is_sequential=True` 两个标记
- **AND** 调用方可根据业务规则决定如何处理冲突（优先串行）

#### Scenario: 仅命中串行标记时分类明确
- **WHEN** 输入仅命中串行标记（如"先清洗数据，然后做统计分析"）
- **THEN** `detect_multi_intent()` 的返回结果 SHALL 附带 `is_sequential=True, is_parallel=False`
