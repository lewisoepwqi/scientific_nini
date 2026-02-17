## Why

当前 CLI 与沙箱模块存在三处可维护性缺口：Markdown Skill 脚手架仍输出 TODO 占位文本、`nini doctor` 对 kaleido/Chrome 检测失败的诊断信息不够明确、图表默认配置失败时存在静默降级。它们不会立即导致功能中断，但会提升排障成本并降低新手使用体验。

## What Changes

- 优化 `nini skills create --type markdown` 默认模板，移除 TODO 占位并提供可直接填写的结构化指引。
- 重构 `nini doctor` 的 kaleido + Chrome 检测逻辑，区分依赖缺失、检测模块不可用、运行期异常等分支并给出明确提示。
- 为图表默认配置流程补充受控日志，在异常降级时输出可观测信息，同时保持主流程不中断。
- 补充对应回归测试，覆盖模板内容、doctor 诊断分支与图表配置降级行为。

## Capabilities

### New Capabilities
- `cli-diagnostics`: 为 CLI 环境诊断提供可区分、可操作的错误提示语义。

### Modified Capabilities
- `skills`: 增强 Markdown Skill 脚手架输出质量，确保生成内容可直接落地。
- `chart-rendering`: 增加图表默认配置阶段的降级可观测性，不再静默吞错。

## Impact

- `src/nini/__main__.py`: 新增可测试的模板与诊断辅助函数，更新 doctor 检测流程。
- `src/nini/sandbox/executor.py`: 增加日志器与降级日志输出。
- `tests/test_phase7_cli.py`: 增加 doctor 诊断与模板内容相关测试。
- `tests/test_sandbox_import_fix.py`（或新增 sandbox 测试文件）: 补充图表降级日志行为测试。
