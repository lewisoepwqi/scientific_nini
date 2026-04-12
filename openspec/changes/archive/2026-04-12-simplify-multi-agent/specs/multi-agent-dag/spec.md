## REMOVED Requirements

### Requirement: DagTask 数据结构与依赖声明
**Reason**: DagTask（含 `id` 和 `depends_on` 字段）的 DAG 依赖格式对用户不可见，用户通过自然语言提出需求，不会手写依赖声明。该格式只对主 Agent LLM 可见，但实际上 LLM 极少使用，且一旦产生 DAG 参数会增加解析和调试复杂度。
**Migration**: 有序执行需求由主 Agent 多次调用 dispatch_agents 实现：第一次调用完成后，主 Agent 根据结果决定是否发起第二次调用。

### Requirement: DagExecutor 拓扑排序与分 wave 执行
**Reason**: DAG 拓扑排序引擎（Kahn 算法 + wave 并行）为假设的高级用法而设计，实际从未被触发。循环依赖检测、wave 间结果注入等机制增加了代码复杂度和测试负担。
**Migration**: 无替代，dispatch_agents 只支持并行执行（所有 agents 同时启动）。

### Requirement: dispatch_agents tasks 参数支持对象格式（{task, id, depends_on}）
**Reason**: `tasks` 参数的混合格式（字符串或带 id/depends_on 的对象）增加了 schema 解析复杂度，且对象格式从未被实际使用。
**Migration**: dispatch_agents 参数改为 `agents: [{agent_id, task}]`，只支持此单一格式。

### Requirement: 循环依赖检测与降级
**Reason**: 循环依赖检测随 DagExecutor 一起移除。
**Migration**: 无替代，dispatch_agents 不支持依赖声明，不存在循环依赖场景。
