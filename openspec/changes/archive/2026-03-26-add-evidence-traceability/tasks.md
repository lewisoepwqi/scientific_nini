## 1. 证据数据契约

- [x] 1.1 定义 `claim_id`、来源记录与 Evidence Block 的结构化数据模型
- [x] 1.2 为知识检索结果、工作区资源或其他已支持来源接入最小溯源字段归一化
- [x] 1.3 在回答或报告组装流程中写入结论到来源的绑定关系

## 2. METHODS 与报告集成

- [x] 2.1 定义 METHODS 台账结构与关键步骤写入时机
- [x] 2.2 扩展报告会话资源，支持 Evidence Block 与 METHODS v1 区块
- [x] 2.3 扩展引用详情或来源列表，展示稳定来源标识对应的最小溯源信息

## 3. 验证与回归

- [x] 3.1 为来源归一化、`claim_id` 绑定与 METHODS 生成功能补充后端测试
- [x] 3.2 为引用详情或报告渲染补充前端测试或 E2E 用例
- [x] 3.3 运行 `pytest -q` 与 `cd web && npm run build`，并记录该 change 对后续 Claim 校验 change 的依赖接口

## 下游接口备注

- `ReportSessionRecord` 已提供 `evidence_blocks[]`，字段最小集合为 `claim_id`、`claim_summary`、`section_key`、`sources[]`；后续 Claim 校验 change 只应消费该契约，不再重新生成 `claim_id`。
- `SourceRecord` 已统一来源字段：`source_id`、`source_type`、`acquisition_method`、`accessed_at`、`source_time`、`stable_ref`、`document_id`、`resource_id`、`url`、`excerpt`。
- `ReportSessionRecord` 已提供 `methods_ledger[]` 与 `methods_v1`；后续 Claim 校验或导出 change 可以直接复用，不应重复维护另一套 METHODS 台账。
- `retrieval` 事件结果已补充 `source_id`、`source_type`、`acquisition_method`、`accessed_at`、`source_time`、`stable_ref`、`document_id`、`resource_id`、`source_url`，后续前端或校验流水线应按这些稳定字段消费，而不是依赖回答内的 `[1]` 顺序号。
