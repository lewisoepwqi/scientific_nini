## Why

`add-evidence-traceability` 解决了“结论能否回溯到来源”，但还没有解决“来源是否足以支撑结论”。如果没有统一的 Claim 校验流水线，系统仍会把证据不足或相互冲突的结论直接写入摘要，无法满足科研输出对可信度和不确定性声明的要求。

## What Changes

- 新增 `claim-verification-pipeline` 能力，定义结论抽取、证据对齐、冲突检测与置信度评分流程。
- 扩展报告生成能力，使最终摘要默认只纳入已验证结论，并对待验证或冲突结论做显式标记。
- 扩展引用展示能力，使用户能看到结论或来源的验证状态，而不是仅看到来源列表。
- 将“待验证”作为正式系统状态，而不是提示词层的软约束。
- 非目标：本 change 不包含新的来源抓取能力、METHODS 台账记录逻辑、导出模板体系与成本预算策略。

## Capabilities

### New Capabilities

- `claim-verification-pipeline`: 定义结论抽取、证据对齐、冲突检测、置信度评分与验证状态输出。

### Modified Capabilities

- `report-generation`: 扩展报告摘要与章节渲染规则，区分已验证、待验证与冲突结论。
- `retrieval-citation`: 扩展引用详情与来源列表，展示验证状态与冲突提示。

## Impact

- 后端会影响 Agent 输出后处理、报告组装、证据绑定结果消费与验证评分逻辑。
- 前端会影响引用展示、报告预览以及结论状态提示。
- 不引入新的外部服务依赖，优先复用 `claim_id`、来源记录与 METHODS 台账等既有数据结构。
- 验证方式至少包括 `pytest -q`、验证状态回归测试，以及 `cd web && npm run build`。
