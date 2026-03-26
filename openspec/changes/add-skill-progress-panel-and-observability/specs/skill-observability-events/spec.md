## ADDED Requirements

### Requirement: skill_summary 事件
ContractRunner SHALL 在 Skill 执行完成后发射 skill_summary 事件。

#### Scenario: 全部成功摘要
- **WHEN** Skill 所有步骤成功完成
- **THEN** 发射 skill_summary 事件，overall_status="completed"，包含总步骤数、完成数、总耗时

#### Scenario: 部分成功摘要
- **WHEN** Skill 部分步骤被 skip
- **THEN** 发射 skill_summary 事件，overall_status="partial"，包含 skipped_steps 数

### Requirement: review_confirm WebSocket 消息处理
后端 SHALL 处理前端发送的 review_confirm 和 review_cancel WebSocket 消息。

#### Scenario: 确认消息唤醒 ContractRunner
- **WHEN** 后端收到 review_confirm 消息
- **THEN** ContractRunner 的 review_gate asyncio.Event 被 set，步骤继续执行

#### Scenario: 取消消息终止步骤
- **WHEN** 后端收到 review_cancel 消息
- **THEN** ContractRunner 将当前步骤标记为 skipped

### Requirement: SkillStepEventData 字段完整性
所有 skill_step 事件 SHALL 包含完整的字段：skill_name、step_id、step_name、status、trust_level、duration_ms（completed 时）。

#### Scenario: started 事件字段
- **WHEN** 步骤开始执行
- **THEN** 事件包含 skill_name、step_id、step_name、status="started"

#### Scenario: completed 事件字段
- **WHEN** 步骤完成
- **THEN** 事件包含 duration_ms、trust_level、output_level
