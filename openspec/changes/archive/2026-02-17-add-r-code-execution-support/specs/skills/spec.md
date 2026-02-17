## ADDED Requirements

### Requirement: run_r_code 技能可用性与降级
系统 SHALL 在 R 环境可用且配置启用时注册 `run_r_code`，并在不可用时自动降级为不暴露该技能。

#### Scenario: R 可用时注册
- **WHEN** `settings.r_enabled=true` 且检测到 `Rscript` 可执行
- **THEN** 技能注册中心包含 `run_r_code`

#### Scenario: R 不可用时降级
- **WHEN** 未检测到 `Rscript` 或 `settings.r_enabled=false`
- **THEN** 技能注册中心不注册 `run_r_code`
- **AND** 现有 `run_code` 等技能行为不受影响

### Requirement: run_r_code 执行契约
系统 SHALL 让 `run_r_code` 提供与 `run_code` 对齐的核心结果契约，包括标准输出、结构化结果、DataFrame 预览与图表产物。

#### Scenario: 返回标量结果
- **WHEN** R 代码设置 `result` 为可序列化标量/列表
- **THEN** 技能返回 `success=true`
- **AND** `data.result` 包含结构化结果

#### Scenario: 返回数据框结果
- **WHEN** R 代码设置 `output_df` 为 data.frame
- **THEN** 技能返回 `has_dataframe=true` 与预览
- **AND** 在设置 `save_as` 时写入会话数据集

#### Scenario: 生成图表产物
- **WHEN** R 代码生成可导出的图表文件
- **THEN** 技能返回 `artifacts` 列表
- **AND** 产物可在工作区下载与预览

### Requirement: R 代码执行安全策略
系统 SHALL 对 `run_r_code` 的输入进行静态策略校验，禁止高风险调用与非白名单包使用。

#### Scenario: 拦截危险函数
- **WHEN** R 代码包含 `system()`、`source()` 或 `eval(parse())` 等危险调用
- **THEN** 系统拒绝执行并返回策略错误

#### Scenario: 拦截非白名单包
- **WHEN** R 代码通过 `library()/require()` 引用非白名单包
- **THEN** 系统拒绝执行并说明包名

### Requirement: 代码执行历史一致性
系统 SHALL 将 `run_r_code` 纳入代码执行历史链路，与 `run_code` 保持一致的工具调用追踪能力。

#### Scenario: WebSocket 记录 run_r_code
- **WHEN** Agent 通过 WebSocket 调用 `run_r_code`
- **THEN** 服务端推送 `tool_call` 与 `tool_result` 事件
- **AND** 持久化执行记录包含 `tool_name=run_r_code` 与 `language=r`
