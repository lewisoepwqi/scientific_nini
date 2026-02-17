## ADDED Requirements

### Requirement: kaleido 诊断分支可区分且可操作
系统 MUST 在 `nini doctor` 中将 kaleido + Chrome 诊断结果区分为依赖缺失、检测模块不可用、检测失败和检测成功四类，并输出可操作提示。

#### Scenario: kaleido 未安装
- **WHEN** 环境中不可导入 `kaleido`
- **THEN** doctor 输出 `kaleido 未安装` 提示
- **AND** 提供安装指引

#### Scenario: Chrome 检测模块不可用
- **WHEN** `kaleido` 可导入但 `choreographer.browsers.chromium` 不可用
- **THEN** doctor 输出 `Chrome 状态未知` 及原因
- **AND** 保留 `kaleido_get_chrome` 操作提示

#### Scenario: Chrome 检测过程异常
- **WHEN** Chrome 路径检测过程中抛出运行时异常
- **THEN** doctor 输出包含异常类型/信息的诊断提示
- **AND** 命令返回成功，不影响其他检查项输出
