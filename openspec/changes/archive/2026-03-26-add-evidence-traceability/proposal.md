## Why

`add-recipe-center-mvp` 解决了任务入口问题，但当前 Nini 的科研输出仍以“回答中附带引用” 为主，缺少稳定的结论到来源映射与方法记录。为了让深任务产物具备可复查性，需要先把证据绑定和 METHODS 台账做成独立 change，再在其上叠加后续的 Claim 校验与冲突检测。

## What Changes

- 新增 `evidence-traceability` 能力，定义结论、证据节点与来源元数据之间的结构化绑定关系。
- 新增 `methods-ledger` 能力，自动记录数据来源、统计方法、参数阈值、模型版本与执行时间，并生成 METHODS v1 内容。
- 扩展报告生成能力，使报告会话可输出 Evidence Block 与 METHODS 区块。
- 扩展引用展示能力，使回答中的引用标注能链接到稳定来源标识与最小溯源信息，而不只是一组展示用编号。
- 非目标：本 change 不包含冲突检测、置信度评分、无证据结论拦截、预算治理与导出模板体系。

## Capabilities

### New Capabilities

- `evidence-traceability`: 定义结论与证据的结构化绑定、来源元数据归一化与 Evidence Block 输出约束。
- `methods-ledger`: 定义 METHODS 台账的记录字段、生成时机与报告嵌入要求。

### Modified Capabilities

- `report-generation`: 扩展报告会话，使其支持 Evidence Block 与 METHODS v1 输出。
- `retrieval-citation`: 扩展引用标注，使其可关联稳定来源标识与最小来源详情。

## Impact

- 后端会影响 `src/nini/agent/`、报告组装逻辑、检索结果归一化与资源模型定义。
- 前端会影响引用详情展示、报告预览与可能的证据块渲染。
- 不新增外部服务依赖，优先复用现有检索、报告与工作区资源契约。
- 验证方式至少包括 `pytest -q`、必要的报告/引用回归测试，以及 `cd web && npm run build`。
