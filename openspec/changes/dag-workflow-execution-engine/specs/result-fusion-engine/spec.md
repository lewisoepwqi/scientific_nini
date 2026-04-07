## MODIFIED Requirements

### Requirement: 分层融合批次并行执行
`ResultFusionEngine._hierarchical(results)` SHALL 使用 `asyncio.gather()` 并行执行各批次的 `_summarize()` 调用，而非顺序 `for` 循环串行等待。各批次输入互相独立，无副作用。

#### Scenario: 5 个子 Agent 结果的分层融合并行执行
- **WHEN** `fuse(results, strategy="hierarchical")` 被调用，`results` 含 5 个元素
- **THEN** 系统 SHALL 将结果分为 2 批（batch1=[1,2,3,4]，batch2=[5]）
- **AND** 两批的 `_summarize()` SHALL 并发发起（通过 `asyncio.gather()`）
- **AND** 批次内部的 LLM 调用 SHALL 在超时保护下完成
