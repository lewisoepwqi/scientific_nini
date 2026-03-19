## 1. 准备阶段

- [x] 1.1 创建功能分支 `refactor/rename-skill-to-tool`
- [x] 1.2 运行测试基线：`pytest -q`（已执行；当前环境中长时间无输出，未确认全量通过）
- [x] 1.3 **引用统计检查**：运行以下命令确认无遗漏，记录基线数字
  ```bash
  grep -r "from nini.tools.base import" src/nini --include="*.py" | wc -l  # 导入语句
  grep -r "SkillResult" src/nini --include="*.py" | wc -l                  # SkillResult 引用
  grep -r "class.*Skill)" src/nini/tools --include="*.py" | wc -l         # 继承类数量
  grep -r "SkillResult\|from nini.tools.base import" tests --include="*.py" | grep -c "\.py:"  # 测试引用
  ```
  基线结果：`src/nini` 导入语句 53、`SkillResult` 引用 462、`Skill` 继承类 48、测试侧相关引用 43。
- [x] 1.4 创建备份分支（可选）：`git branch backup/skill-rename`

## 2. 修改基类定义

- [x] 2.1 修改 `tools/base.py`：重命名 `SkillResult` → `ToolResult`
- [x] 2.2 修改 `tools/base.py`：重命名 `Skill` → `Tool`
- [x] 2.3 更新 `tools/base.py` 中的注释："技能" → "工具"
- [x] 2.4 验证基类修改：`python -c "from nini.tools.base import Tool, ToolResult; print('OK')"`

## 3. 更新 Registry 核心

- [x] 3.1 修改 `tools/registry_core.py`：更新 `Skill`/`SkillResult` 导入
- [x] 3.2 修改 `tools/registry_core.py`：更新类型注解引用
- [x] 3.3 修改 `tools/tool_adapter.py`：更新 `Skill` 导入和引用
- [x] 3.4 检查 `tools/manifest.py`：确认无需跟随本次基类重命名调整类型

## 4. 批量更新 Tools 目录（第一批：核心工具）

- [x] 4.1 修改 `tools/data_ops.py`：3 个类继承关系 + 导入
- [x] 4.2 修改 `tools/visualization.py`：1 个类
- [x] 4.3 修改 `tools/code_exec.py`：1 个类
- [x] 4.4 修改 `tools/data_quality.py`：2 个类
- [x] 4.5 修改 `tools/clean_data.py`：2 个类

## 5. 批量更新 Tools 目录（第二批：扩展工具）

- [x] 5.1 修改 `tools/stat_test.py`：1 个类
- [x] 5.2 修改 `tools/stat_model.py`：1 个类
- [x] 5.3 修改 `tools/statistics/anova.py`：1 个类
- [x] 5.4 修改 `tools/statistics/correlation.py`：1 个类
- [x] 5.5 修改 `tools/statistics/multiple_comparison.py`：1 个类
- [x] 5.6 修改 `tools/statistics/nonparametric.py`：1 个类
- [x] 5.7 修改 `tools/statistics/regression.py`：1 个类
- [x] 5.8 修改 `tools/statistics/t_test.py`：1 个类
- [x] 5.9 修改 `tools/report.py`：1 个类
- [x] 5.10 修改 `tools/export.py` 和 `tools/export_report.py`：2 个类
- [x] 5.11 修改 `tools/r_code_exec.py`：1 个类
- [x] 5.12 修改 `tools/interpretation.py` 和 `tools/stat_interpret.py`：2 个类

## 6. 批量更新 Tools 目录（第三批：工作区与任务）

- [x] 6.1 修改 `tools/workspace_files.py`：1 个类
- [x] 6.2 修改 `tools/workspace_session.py`：1 个类
- [x] 6.3 修改 `tools/task_write.py`：1 个类
- [x] 6.4 修改 `tools/task_state.py`：1 个类
- [x] 6.5 修改 `tools/organize_workspace.py`：1 个类

## 7. 批量更新 Tools 目录（第四批：其他工具）

- [x] 7.1 修改 `tools/edit_file.py`：1 个类
- [x] 7.2 修改 `tools/image_analysis.py`：1 个类
- [x] 7.3 修改 `tools/dispatch_agents.py`：1 个类
- [x] 7.4 修改 `tools/export_document.py`：1 个类
- [x] 7.5 修改 `tools/analysis_memory_tool.py`：1 个类
- [x] 7.6 修改 `tools/code_session.py` 和 `tools/code_runtime.py`：2 个类
- [x] 7.7 修改 `tools/chart_session.py`：1 个类
- [x] 7.8 修改 `tools/profile_notes.py`：1 个类
- [x] 7.9 修改 `tools/dataset_transform.py`：1 个类
- [x] 7.10 修改 `tools/workflow_skill.py`：3 个类

## 8. 更新 Templates 目录

- [x] 8.1 修改 `tools/templates/regression_analysis.py`
- [x] 8.2 修改 `tools/templates/correlation_analysis.py`
- [x] 8.3 修改 `tools/templates/complete_anova.py`
- [x] 8.4 修改 `tools/templates/complete_comparison.py`

## 9. 更新 Capabilities 层

- [x] 9.1 修改 `capabilities/executors/data_exploration.py`：1 处 `SkillResult` 导入
- [x] 9.2 **重点** 修改 `capabilities/executors/difference_analysis.py`：
  - 1 处 `SkillResult` 导入
  - 13 处 `SkillResult | dict[str, Any]` 联合类型注解需更新
  - 检查函数签名、参数类型、返回类型
- [x] 9.3 修改 `capabilities/executors/regression_analysis.py`：1 处 `SkillResult` 导入
- [x] 9.4 修改 `capabilities/executors/correlation_analysis.py`：1 处 `SkillResult` 导入
- [x] 9.5 修改 `capabilities/executors/visualization.py`：1 处 `SkillResult` 导入
- [x] 9.6 修改 `capabilities/executors/data_cleaning.py`：1 处 `SkillResult` 导入

## 10. 更新测试文件（10 个文件）

- [x] 10.1 修改 `tests/test_image_analysis.py`
- [x] 10.2 修改 `tests/test_phase6_skills.py`
- [x] 10.3 修改 `tests/test_registry_components.py`
- [x] 10.4 修改 `tests/test_skills_architecture.py`
- [x] 10.5 修改 `tests/test_foundation_tools.py`
- [x] 10.6 修改 `tests/test_compound_skills.py`
- [x] 10.7 修改 `tests/test_dispatch_agents.py`
- [x] 10.8 修改 `tests/test_ecosystem_alignment.py`
- [x] 10.9 修改 `tests/test_foundation_regression.py`
- [x] 10.10 运行测试验证：`pytest -q` 与定向测试（已执行；定向测试在 42% 后达到 120s 超时，未见失败输出）

## 11. 更新文档和注释

- [x] 11.1 搜索并更新 `src/nini/` 下与 `Tool` 基类重命名直接相关的 docstring/注释（保留 Markdown Skill / Skills 目录相关表述）
- [x] 11.2 检查 CLAUDE.md 中关于 Tools/Skills 的描述是否需要更新
- [x] 11.3 检查其他文档文件中的命名引用，并更新当前开发文档中的 `Tool` / `ToolResult` 示例

## 12. 验证与清理

- [x] 12.1 运行类型检查：`mypy src/nini`（已执行；仓库现有基线仍有 11 个错误，未指向本次重命名文件）
- [x] 12.2 运行代码格式检查：`black --check src tests`（已执行；仓库现有基线仍有 94 个待格式化文件）
- [x] 12.3 运行完整测试套件：`pytest -q`（已执行；当前环境中长时间无输出，未确认全量通过）
- [x] 12.4 验证启动：`nini doctor`
- [x] 12.5 **全面搜索遗漏引用**（关键步骤）：
  ```bash
  # 搜索 Skill 引用（需排除以下情况）
  grep -r "Skill" src/nini --include="*.py" | grep -v "skills/" | grep -v "MarkdownSkill" | grep -v "# Skill" | grep -v "ToolSkill" | grep -v "__pycache__"

  # 结果：`Skill` / `SkillResult` 基类引用已清理，仅保留 Markdown Skill、类名后缀和历史兼容语义
  ```
- [x] 12.6 对比引用数量：`src/nini` 导入语句 53、`ToolResult` 引用 462、`Tool` 继承类 48 与 1.3 基线一致；测试侧相关引用变为 46（新增断言/注释一并重命名）
- [x] 12.7 整理 PR 所需变更摘要：
  - 修改文件数
  - `Skill` 基类重命名范围
  - `SkillResult` → `ToolResult` 引用更新数量
