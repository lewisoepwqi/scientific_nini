## ADDED Requirements

### Requirement: ToolGuardrail 可插拔接口
系统 SHALL 提供 `ToolGuardrail` 抽象基类，定义 `evaluate(tool_name: str, kwargs: dict) -> GuardrailDecision` 接口。`GuardrailDecision` SHALL 包含 `ALLOW`、`BLOCK`、`REQUIRE_CONFIRMATION` 三种决策及附带的 `reason` 字符串。

#### Scenario: guardrail 返回 ALLOW 时正常执行
- **WHEN** guardrail 链中所有规则对当前工具调用返回 `ALLOW`
- **THEN** `ToolRegistry.execute()` 继续执行原有工具调用逻辑，行为不变

#### Scenario: guardrail 链短路于第一个 BLOCK
- **WHEN** guardrail 链中任一规则返回 `BLOCK`
- **THEN** 后续规则不再执行
- **THEN** `ToolRegistry.execute()` 立即返回失败结果，不调用 `Tool.execute()`

### Requirement: BLOCK 决策返回标准失败结果
当 guardrail 返回 `BLOCK` 时，`ToolRegistry.execute()` SHALL 返回与 `ToolResult(success=False)` 等价的 dict，`message` 字段包含拦截原因，不抛出异常，不中断会话。

#### Scenario: BLOCK 决策不中断会话
- **WHEN** guardrail 返回 `BLOCK`
- **THEN** `execute()` 返回 `{"success": False, "message": "操作被安全策略拦截：<reason>"}` 格式的 dict
- **THEN** 调用方（`tool_executor.py`）正常处理该失败结果，会话继续

#### Scenario: BLOCK 决策写入 warning 日志
- **WHEN** guardrail 返回 `BLOCK`
- **THEN** 系统写入 warning 级别日志，包含 tool_name、kwargs 摘要和拦截原因

### Requirement: REQUIRE_CONFIRMATION 本次降级为 BLOCK
当 guardrail 返回 `REQUIRE_CONFIRMATION` 时，当前版本 SHALL 以与 `BLOCK` 相同的方式处理，附加说明"需要用户确认后才能执行"。

#### Scenario: REQUIRE_CONFIRMATION 返回提示性失败
- **WHEN** guardrail 返回 `REQUIRE_CONFIRMATION`
- **THEN** `execute()` 返回失败结果，message 说明需要用户确认
- **THEN** 行为与 BLOCK 一致，不挂起等待

### Requirement: DangerousPatternGuardrail 拦截科研数据破坏性操作
`DangerousPatternGuardrail` SHALL 检测以下危险模式并返回 BLOCK：
- `clean_data` 工具携带 `inplace=True` 且目标 DataFrame 名称含 `_raw`、`_original` 或 `original` 字样
- `organize_workspace` 工具携带批量删除参数（`delete_all=True` 或 `pattern="*"`）
- 任意工具的参数字符串中包含系统路径（`/etc/`、`/sys/`、`~/.ssh/` 等）

#### Scenario: 保护 raw 数据集不被 inplace 修改
- **WHEN** `clean_data` 被调用，参数包含 `inplace=True` 且 dataset 名称含 `_raw`
- **THEN** guardrail 返回 `BLOCK`，原始数据集不被修改

#### Scenario: 阻止批量删除工作区
- **WHEN** `organize_workspace` 被调用，参数包含 `delete_all=True`
- **THEN** guardrail 返回 `BLOCK`

#### Scenario: 普通操作不受影响
- **WHEN** `clean_data` 被调用，参数 `inplace=False` 或 dataset 名称不含 raw/original
- **THEN** guardrail 返回 `ALLOW`，工具正常执行

### Requirement: Guardrail 链在 ToolRegistry 初始化时注册
`ToolRegistry` 初始化 SHALL 默认包含 `DangerousPatternGuardrail` 实例。外部代码 SHALL 能通过 `ToolRegistry.add_guardrail(guardrail)` 在运行时追加额外规则。

#### Scenario: 默认 guardrail 链包含 DangerousPatternGuardrail
- **WHEN** 使用默认参数创建 `ToolRegistry` 实例
- **THEN** guardrail 链中包含一个 `DangerousPatternGuardrail` 实例
