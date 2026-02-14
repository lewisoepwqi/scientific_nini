## ADDED Requirements
### Requirement: 工具结果结构化持久化
系统 SHALL 在会话持久化中为工具结果保留结构化元信息（至少包含 `tool_name`、`status`、`tool_call_id`），以支持报告生成与审计过滤。

#### Scenario: 持久化工具结果元信息
- **WHEN** Agent 完成一次工具调用并写入会话记忆
- **THEN** 工具结果记录包含 `tool_name` 与执行状态字段
- **AND** 可通过 `tool_call_id` 追踪到对应调用

#### Scenario: 报告提取可识别工具来源
- **WHEN** 报告模块读取历史工具结果
- **THEN** 能基于 `tool_name` 进行分类过滤
- **AND** 不依赖纯文本猜测工具类型

### Requirement: 会话消息读取支持解引用
系统 SHALL 在面向前端会话历史读取接口中支持大型 payload 解引用，确保图表等引用化内容可直接使用。

#### Scenario: 前端请求历史消息
- **WHEN** 客户端调用会话消息接口加载历史
- **THEN** 已引用化的 `chart_data` 能被解析为实际对象
- **AND** 前端不会收到仅包含 `_ref` 的占位对象

#### Scenario: 解引用失败降级
- **WHEN** 引用文件缺失或解析失败
- **THEN** 系统返回可识别降级信息
- **AND** 不影响其他消息加载
