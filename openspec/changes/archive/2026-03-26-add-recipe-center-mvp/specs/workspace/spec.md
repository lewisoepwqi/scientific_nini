## MODIFIED Requirements

### Requirement: WebSocket 实时更新
系统 SHALL 在文件变更（新增/删除/重命名/产物生成）以及 deep task 项目工作区初始化时通过 WebSocket 推送 `workspace_update` 事件，前端自动刷新文件列表与工作区上下文。

#### Scenario: 产物生成后实时更新
- **WHEN** Agent 生成新产物
- **THEN** 前端工作区面板自动显示新文件，无需手动刷新

#### Scenario: deep task 创建项目工作区后实时更新
- **WHEN** Recipe 启动并完成项目工作区初始化
- **THEN** 服务端推送 `workspace_update` 事件
- **AND** 事件中包含工作区标识、绑定的 `recipe_id` 与初始化状态
- **AND** 前端自动刷新当前会话的工作区上下文
