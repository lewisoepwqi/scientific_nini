## 1. Harness 运行编排

- [x] 1.1 新增 harness 运行编排模块，定义 `HarnessRunner` 与运行阶段钩子接口，并保持对现有 `AgentRunner` 事件流的兼容包装
- [x] 1.2 实现运行前上下文摘要装配，统一产出当前轮数据集、产物、工具提示和关键约束信息
- [x] 1.3 实现 completion verification 结构化校验与恢复分支，确保未通过校验时不会直接进入 `done`
- [x] 1.4 实现科研分析场景的坏循环检测与分级恢复策略，支持恢复失败后进入 `blocked`
- [x] 1.5 接入按阶段切换的 reasoning budget 调度逻辑，并保证对现有模型解析与路由最小侵入

## 2. Trace 与评测能力

- [x] 2.1 定义 harness trace 数据模型和本地存储目录结构，覆盖事件序列、校验结果、恢复路径与最终状态
- [x] 2.2 实现 SQLite 摘要索引与 JSON/JSONL 明细双层持久化，并建立索引到明细的关联
- [x] 2.3 实现单次运行回放能力，能够重建关键执行轨迹与结果摘要
- [x] 2.4 实现失败分类与聚合分析，输出验证缺失、坏循环、方法选择错误、产物缺失等标准标签统计
- [x] 2.5 为维护者补充 CLI 或等效入口，支持 trace 查看、回放与 harness eval 结果输出

## 3. 协议与前端诊断展示

- [x] 3.1 扩展后端事件模型与 WebSocket 发送链路，新增 `run_context`、`completion_check`、`blocked` 事件类型和数据结构
- [x] 3.2 在 WebSocket 入口切换为通过 harness 编排层驱动运行，并保持既有 `reasoning`、`task_attempt`、`ask_user_question` 等交互兼容
- [x] 3.3 更新前端 store 与事件处理逻辑，消费新的 harness 事件并维护对应状态
- [x] 3.4 在现有分析计划、推理或任务视图中展示 completion check、恢复状态和 blocked 原因，而不引入独立必需页面
- [x] 3.5 为旧事件消费者保留兼容行为，确保忽略新增事件时不会破坏基础会话体验

## 4. 验证与回归保护

- [x] 4.1 为 completion verification、坏循环恢复、blocked 分支和阶段化 reasoning budget 编写后端单元测试
- [x] 4.2 为 trace 持久化、回放和失败聚合分析编写后端测试，覆盖正常完成、阻塞和恢复失败路径
- [x] 4.3 为新增 WebSocket 事件和前端 store 状态流转补充契约测试与界面测试
- [x] 4.4 运行 `pytest -q` 与 `cd web && npm run build`，修复回归并更新必要测试样例
