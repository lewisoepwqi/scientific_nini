# 研究记录：任务化分析与多图表管理

> 目的：固化关键技术决策并消除不确定性。

## 决策 1：任务状态机采用 7 阶段

- **Decision**: 采用 7 阶段：uploading → parsed → profiling → suggestion_pending → processing → analysis_ready → visualization_ready。
- **Rationale**: 与现有业务流程一致，能清晰覆盖解析、画像、建议与可视化的关键节点，便于可追溯与用户感知。
- **Alternatives considered**: 简化为 4 阶段或 3 阶段（信息不足以支撑 AI 建议与多图表阶段分离）。

## 决策 2：默认访问控制为“创建者独享 + 显式分享”

- **Decision**: 任务与分享包默认仅创建者可访问，团队成员需显式分享后才能访问。
- **Rationale**: 符合科研数据最小化暴露原则，降低误分享风险。
- **Alternatives considered**: 默认团队可见；默认生成外部分享链接（安全风险高）。

## 决策 3：分享包不包含原始数据

- **Decision**: 分享包仅包含数据版本引用与配置，不包含原始数据内容。
- **Rationale**: 降低敏感数据泄露风险，满足“数据最小化”与合规要求。
- **Alternatives considered**: 分享包包含脱敏/抽样数据；分享包包含完整数据副本（需要更复杂的权限与审计）。

## 决策 4：单任务图表数量设置可配置上限

- **Decision**: 每任务图表数量设定可配置上限。
- **Rationale**: 控制列表性能与存储成本，避免无界增长影响任务体验。
- **Alternatives considered**: 不设上限；仅软上限提示（难以保证性能目标）。

## 决策 5：数据与分享包默认保留 30 天

- **Decision**: 默认保留周期为 30 天。
- **Rationale**: 在可复现需求与成本控制之间取得平衡，覆盖常见科研协作周期。
- **Alternatives considered**: 180 天或永久保留（成本与合规风险升高）。

## 决策 6：对外能力统一走 `/api/v1` 的 REST 风格

- **Decision**: 前端通过 `/api/v1` 访问，AI 能力由后端转发，统一 REST 风格。
- **Rationale**: 与现有分层一致，减少接口不一致与鉴权风险。
- **Alternatives considered**: 前端直连 AI 服务；混用 GraphQL（增加维护成本）。

## 决策 7：核心持久化与文件存储的职责划分

- **Decision**: 任务/图表/数据版本元数据存储于 PostgreSQL，状态与临时数据通过 Redis，数据集与导出包使用文件存储。
- **Rationale**: 结构化查询与事务一致性由关系型数据库承担，缓存/队列由 Redis 支撑，文件存储适配大文件。
- **Alternatives considered**: 全量对象存储；全量关系库存储（成本与性能不均衡）。
