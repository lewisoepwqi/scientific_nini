## Context

本次变更集中于 CLI 体验与运行时可观测性增强，涉及 `src/nini/__main__.py` 与 `src/nini/sandbox/executor.py` 两个模块。目标是在不改变主流程行为的前提下，提升输出质量与故障诊断能力，并通过单测锁定回归边界。

## Goals / Non-Goals

**Goals:**
- 让 Markdown Skill 脚手架默认内容可直接使用，减少新建后手工清理成本。
- 让 `nini doctor` 对 kaleido/Chrome 状态给出可区分、可操作提示。
- 让图表样式降级路径输出日志，避免静默失败。
- 为以上行为补充回归测试。

**Non-Goals:**
- 不引入新的第三方依赖。
- 不改变 `doctor` 检查项集合与返回码策略。
- 不重构沙箱执行器整体架构。

## Decisions

### Decision 1: 提取可测试辅助函数
在 `__main__.py` 提取 `kaleido` 检测与 Markdown 模板渲染辅助函数，`_cmd_doctor` 与 `_create_markdown_skill` 仅负责编排。这样可在测试中直接覆盖分支逻辑，避免依赖真实环境。

### Decision 2: 诊断分支采用“明确分类 + 统一建议”
`kaleido` 检测将拆分为：未安装、检测模块不可用、路径检测异常、检测成功/未安装 Chrome。失败分支统一追加 `kaleido_get_chrome` 建议，降低用户操作成本。

### Decision 3: 沙箱降级日志使用轻量级 logger
`executor.py` 新增模块级 logger。对于可预期缺依赖使用 `debug`，对于运行期异常使用 `warning`，同时保持降级不中断，以兼顾可观测性与鲁棒性。

## Risks / Trade-offs

- [风险] 诊断文案调整可能影响依赖字符串断言的旧测试 -> [缓解] 同步更新测试断言并尽量匹配稳定关键词。
- [风险] 新增日志可能增加调试输出 -> [缓解] 依赖缺失使用 debug 级别，仅异常降级使用 warning。
