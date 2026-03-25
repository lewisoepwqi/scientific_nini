## ADDED Requirements

### Requirement: 工具层分层异常体系
系统 SHALL 在 `tools/base.py` 中定义三级异常层次，所有工具的 `execute()` 方法 SHALL 使用这些异常替代通用 `except Exception` 捕获：
- `ToolInputError(ToolError)`: 用户输入错误（缺少参数、数据集不存在、列名无效），不应重试
- `ToolTimeoutError(ToolError)`: 可重试的超时错误（LLM 调用超时、沙箱执行超时）
- `ToolSystemError(ToolError)`: 需告警的系统故障（内存不足、依赖不可用），应记录 error 级别日志

#### Scenario: 用户输入错误返回友好提示
- **WHEN** 工具收到无效参数（如不存在的 dataset_name）
- **THEN** SHALL 抛出 `ToolInputError` 并附带用户可理解的中文错误信息
- **AND** 调用层 SHALL 将其包装为 `ToolResult(success=False)` 返回给 LLM

#### Scenario: 超时错误标记为可重试
- **WHEN** 工具执行超时
- **THEN** SHALL 抛出 `ToolTimeoutError`
- **AND** 调用层 SHALL 记录 warning 日志并在 ToolResult 中标记 `retryable=True`

#### Scenario: 系统故障记录 error 日志
- **WHEN** 工具遇到系统级错误（MemoryError、依赖不可用）
- **THEN** SHALL 抛出 `ToolSystemError`
- **AND** 调用层 SHALL 记录 error 级别日志（含完整 traceback）

#### Scenario: 未知异常兜底
- **WHEN** 工具抛出未归类的 Exception
- **THEN** 调用层 SHALL 将其视为 `ToolSystemError` 处理
- **AND** SHALL 记录 error 级别日志以便排查

### Requirement: registry_core.py 统一异常调度
`FunctionToolRegistryOps.execute()` SHALL 基于异常类型分层处理，替代当前的统一 `except Exception` 模式。

#### Scenario: ToolInputError 不记录 error 日志
- **WHEN** 工具执行抛出 `ToolInputError`
- **THEN** `execute()` SHALL 返回 `{"success": False, "message": ...}` 并记录 info 级别日志（非 error）

#### Scenario: ToolTimeoutError 记录 warning 并标记重试
- **WHEN** 工具执行抛出 `ToolTimeoutError`
- **THEN** `execute()` SHALL 返回失败结果并记录 warning 日志
- **AND** 结果中 SHALL 包含 `retryable: true` 标记

#### Scenario: ToolSystemError 记录 error 含 traceback
- **WHEN** 工具执行抛出 `ToolSystemError` 或未分类 Exception
- **THEN** `execute()` SHALL 记录 error 级别日志（含 exc_info=True）
- **AND** 返回失败结果

### Requirement: model_resolver 区分可重试与永久失败
`ModelResolver.chat()` 的 LLM 调用层 SHALL 区分可重试错误（429 Rate Limit、503 Service Unavailable、网络超时）和永久失败（401 Unauthorized、403 Forbidden、400 Bad Request）。

#### Scenario: 429 Rate Limit 触发延迟重试
- **WHEN** LLM API 返回 429 状态码
- **THEN** 系统 SHALL 记录 warning 日志并在 fallback 链中尝试下一个 provider
- **AND** SHALL NOT 将该错误直接暴露给用户

#### Scenario: 401 Unauthorized 立即报错
- **WHEN** LLM API 返回 401 状态码
- **THEN** 系统 SHALL 立即返回认证错误，不尝试同一 provider 的重试
- **AND** SHALL 在错误信息中提示用户检查 API Key 配置
