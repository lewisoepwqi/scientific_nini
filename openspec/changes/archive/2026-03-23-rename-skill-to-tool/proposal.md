## Why

`src/nini/tools/base.py` 中的 `Skill` 类是 Tools 层的原子函数基类，但由于历史原因命名为 "Skill"，这与项目中 `skills/` 目录（存放完整工作流项目）产生了严重的命名混淆。这种混淆导致新开发者难以理解架构分层，也影响代码的可维护性。需要彻底重命名以明确架构边界：Tools = 原子工具层，Skills = 完整工作流层。

## What Changes

- **BREAKING**: 将 `tools/base.py` 中的 `Skill` 类重命名为 `Tool`
- **BREAKING**: 将 `SkillResult` 重命名为 `ToolResult`
- **BREAKING**: 将所有 Tool 子类（`tools/` 目录下）的继承关系从 `Skill` 改为 `Tool`
- **BREAKING**: 将 `ToolRegistry` 中对 `Skill` 的引用改为 `Tool`
- **BREAKING**: 更新所有导入语句（`from nini.tools.base import Skill` → `from nini.tools.base import Tool`）
- 更新文档、注释中的相关命名引用
- 保留 `Skill` 作为 `Tool` 的别名（可选，用于向后兼容），但内部代码全部使用新命名

## Capabilities

### New Capabilities

（无新能力，这是代码重构）

### Modified Capabilities

（无 spec 级别变更，纯代码级重构）

## Impact

- **代码范围**: `src/nini/tools/` 目录（约 48 个 Python 文件）及引用 `Skill` 类的所有模块
- **变更规模**: 约 50+ 文件、400+ 处 `SkillResult` 引用、49 个继承 `Skill` 的类需要更新
- **API 影响**: HTTP API 不变；内部 API（`capabilities/executors/` 中的函数返回类型 `SkillResult | dict`）会变更
- **测试影响**: 10 个测试文件需要更新
- **开发者体验**: 显著提升——Tools 与 Skills 的架构分层将更加清晰
- **风险**: 中高风险；遗漏任何 `Skill` 引用都会导致运行时错误
