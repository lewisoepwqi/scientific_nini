# 计划：为 Nini 添加 R 语言代码执行支持

## Context

在会话 1127d080377b 中，用户分析 LHY 基因昼夜节律数据。Agent 建议使用 R/Bioconductor 专有工具（MetaCycle、JTK_CYCLE、DESeq2 等），但当前沙箱仅支持 Python，无法执行 R 代码。R 在科研统计场景中有大量 Python 无等价实现的包（Bioconductor 生态），需要原生支持。

目标：新增 run_r_code 技能，通过 Rscript 子进程安全执行 R 代码，支持数据传递、图表捕获、结构化结果返回，以及自动安装缺失的 R 包。

## 文件变更清单

| 文件 | 操作 | 描述 |
|------|------|------|
| src/nini/sandbox/r_policy.py | 新建 | R 代码安全策略：正则静态分析 + 包白名单 + 函数黑名单 |
| src/nini/sandbox/r_executor.py | 新建 | R 子进程执行器：subprocess 隔离 + 数据传递 + 图表收集 + R 包自动安装 |
| src/nini/skills/r_code_exec.py | 新建 | run_r_code 技能：继承 Skill 基类，处理 R 执行结果 |
| src/nini/sandbox/__init__.py | 修改 | 导出 R 执行器 |
| src/nini/skills/registry.py | 修改 | 条件注册 RunRCodeSkill（R 可用时） |
| src/nini/config.py | 修改 | 添加 R 沙箱配置项 |
| src/nini/__main__.py | 修改 | nini doctor 添加 R 环境检查 |
| src/nini/agent/prompts/builder.py | 修改 | strategy.md 添加 R 语言使用策略 |
| tests/test_r_policy.py | 新建 | R 安全策略单元测试 |
| tests/test_r_executor.py | 新建 | R 执行器测试（系统已安装 R） |
| tests/test_r_code_exec.py | 新建 | run_r_code 技能集成测试 |

## 实施步骤

### Phase 1: R 代码安全策略 (sandbox/r_policy.py)

- BANNED_R_CALLS：system, system2, shell, shell.exec, file.remove, file.rename, file.copy, unlink, download.file, url, curl, browseURL, eval, parse, source, Sys.getenv, Sys.setenv, .Internal, .Call, .External
- ALLOWED_R_PACKAGES：约 40 个分层白名单（R 内置 / 数据处理 / 可视化 / 统计 / 生物信息 / 工具）
- validate_r_code() 逐行正则匹配，跳过注释，违规抛 RSandboxPolicyError
- install.packages 不在黑名单中（由执行器控制安装逻辑）

### Phase 2: R 子进程执行器 (sandbox/r_executor.py)

- detect_r_installation()：检测 Rscript 可用性和版本
- check_r_packages()：检测 R 包安装状态
- install_r_packages()：自动安装缺失包（CRAN + BiocManager），维护 BIOC_PACKAGES 集合
- RSandboxExecutor 类：
  1. validate_r_code() 安全检查
  2. 从代码提取 library/require 引用的包，检测并自动安装缺失包
  3. datasets 导出为 CSV 到 r_sandbox_tmp/
  4. 构建 R wrapper 脚本（数据加载 + 图表目录 + 结果序列化）
  5. subprocess.run(["Rscript", "--vanilla", ...]) 执行
  6. 收集 stdout/stderr、_result.json、_output_df.csv、plots/
- R wrapper 注入：datasets 列表、df 变量、ggplot2 自动捕获、base R 绘图设备捕获
- 环境：--vanilla + R_PROFILE_USER="" 禁用用户配置

### Phase 3: 配置扩展 (config.py)

添加：r_sandbox_timeout=120, r_sandbox_max_memory_mb=1024, r_enabled=True, r_package_install_timeout=300

### Phase 4: run_r_code 技能 (skills/r_code_exec.py)

RunRCodeSkill(Skill)：name="run_r_code"
参数：code（必填）、dataset_name、save_as、label、intent
复用：ArtifactStorage、WorkspaceManager、dataframe_to_json_safe

### Phase 5: 注册 + 环境检测 + Prompt

- registry.py：条件注册（settings.r_enabled + detect_r_installation）
- __main__.py：nini doctor 添加 R 检查
- prompts/builder.py：strategy.md 添加 R 语言使用策略

### Phase 6: 测试

- test_r_policy.py：安全策略正面/负面用例（无需 R）
- test_r_executor.py：R 执行器功能测试（需要 R，系统已安装）
- test_r_code_exec.py：技能集成测试

## 验证方式

```bash
black --check src/nini/sandbox/r_policy.py src/nini/sandbox/r_executor.py src/nini/skills/r_code_exec.py tests/test_r_*.py
mypy src/nini/sandbox/r_policy.py src/nini/sandbox/r_executor.py src/nini/skills/r_code_exec.py
pytest tests/test_r_policy.py tests/test_r_executor.py tests/test_r_code_exec.py -v
pytest -q  # 全量回归
nini doctor  # 手动检查 R 环境信息
```
