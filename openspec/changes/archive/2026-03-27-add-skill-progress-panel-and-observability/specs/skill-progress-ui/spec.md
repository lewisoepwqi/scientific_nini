## ADDED Requirements

### Requirement: SkillProgressPanel 组件
前端 SHALL 提供 `SkillProgressPanel` 组件，实时展示当前 Skill 的执行进度。

#### Scenario: 展示步骤列表
- **WHEN** 收到 skill_step 事件且 status="started"
- **THEN** 面板展示 Skill 名称和步骤列表，当前步骤高亮

#### Scenario: 步骤完成更新
- **WHEN** 收到 skill_step 事件且 status="completed"
- **THEN** 对应步骤显示完成状态和耗时

#### Scenario: 失败步骤标记
- **WHEN** 收到 skill_step 事件且 status="failed"
- **THEN** 对应步骤显示失败状态和错误信息

### Requirement: review_gate UI 交互
当步骤需要人工确认时，面板 SHALL 展示确认按钮。

#### Scenario: review_required 展示确认按钮
- **WHEN** 收到 skill_step 事件且 status="review_required"
- **THEN** 面板在对应步骤展示「确认继续」和「取消」按钮

#### Scenario: 用户确认发送消息
- **WHEN** 用户点击「确认继续」
- **THEN** 前端通过 WebSocket 发送 review_confirm 消息

#### Scenario: 用户取消发送消息
- **WHEN** 用户点击「取消」
- **THEN** 前端通过 WebSocket 发送 review_cancel 消息

### Requirement: Zustand store 扩展
前端 store SHALL 新增 skillExecution 切片，管理 Skill 执行状态。

#### Scenario: skill_step 事件更新 store
- **WHEN** WebSocket 收到 skill_step 事件
- **THEN** store 的 skillExecution 状态更新

#### Scenario: Skill 完成后清理状态
- **WHEN** 收到 skill_summary 事件且 overall_status="completed"
- **THEN** store 的 activeSkill 设为 null
