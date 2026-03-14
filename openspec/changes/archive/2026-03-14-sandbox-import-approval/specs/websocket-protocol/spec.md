## ADDED Requirements

### Requirement: WebSocket 必须支持沙盒包审批事件流
系统 SHALL 在 WebSocket 通道中完整表达由沙盒扩展包审批触发的 `ask_user_question`、用户回答与工具恢复执行流程。

#### Scenario: 审批问题通过 ask_user_question 推送
- **WHEN** `run_code` 返回 `_sandbox_review_required`
- **THEN** 服务端 SHALL 推送 `ask_user_question` 事件
- **AND** 事件中包含当前工具调用关联的 `tool_call_id`
- **AND** 问题内容 SHALL 包含待审批包与授权选项

#### Scenario: 用户回答后恢复工具执行
- **WHEN** 前端通过 `ask_user_question_answer` 提交审批决定
- **THEN** 服务端 SHALL 将回答绑定到原始 `tool_call_id`
- **AND** 后端 SHALL 恢复原始工具调用的后续处理流程
- **AND** 最终继续推送对应的 `tool_result` 与后续事件

### Requirement: 审批事件流必须保持现有协议兼容性
系统 SHALL 在新增沙盒审批交互时继续兼容现有 `ask_user_question` 与 `tool_result` 事件消费者。

#### Scenario: 现有客户端继续消费审批结果
- **WHEN** 客户端已支持通用 `ask_user_question` 事件但不知道“沙盒审批”这一业务语义
- **THEN** 客户端仍 SHALL 能显示问题、提交回答并接收后续结果
- **AND** 不需要依赖新增专用事件类型

#### Scenario: 拒绝授权时返回明确结果
- **WHEN** 用户拒绝某个扩展包授权
- **THEN** 服务端 SHALL 返回对应的 `tool_result`
- **AND** 结果中包含明确的拒绝说明
- **AND** 不得让前端停留在无完成状态的悬挂请求中
