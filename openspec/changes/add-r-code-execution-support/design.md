## Context

现有 `run_code` 基于 Python 进程隔离沙箱，已形成统一的工具调用与产物沉淀链路。新增 R 支持需要复用既有契约（SkillResult、工作区、WebSocket 事件），同时避免引入高风险系统调用。

## Goals / Non-Goals

- Goals:
  - 提供受控的 R 代码执行能力，支持 `datasets`/`df` 数据注入。
  - 输出结构与 `run_code` 兼容（stdout/stderr/result/output_df/artifacts）。
  - R 不可用时自动降级，不影响现有 Python 路径。
- Non-Goals:
  - 不实现完整容器级隔离（仍以进程隔离与静态策略为主）。
  - 不保证任意 R 包都可安装（受白名单与环境限制）。

## Architecture

1. `r_policy.py`
- 采用逐行与正则的静态策略校验。
- 限制 `library()/require()` 包名必须在白名单。
- 禁止高风险函数调用（系统命令、网络下载、动态执行、环境变量读写等）。

2. `r_executor.py`
- 使用 `Rscript --vanilla` 执行包装脚本。
- 执行前解析代码依赖包并检测是否缺失。
- 根据配置执行受控安装（CRAN + BiocManager）。
- 将 Python DataFrame 导出为 CSV，再由 R 包装层加载到 `datasets` 与 `df`。
- 统一写出 `_result.json`、`_output_df.csv`、`plots/`，由 Python 侧回收。

3. `run_r_code` 技能
- 调用 `r_sandbox_executor.execute()`。
- 将图表文件保存为工作区产物并返回 artifacts。
- 对 DataFrame 结果构建预览并支持 `save_as`。

4. 系统接入
- registry 条件注册。
- doctor 检测 Rscript 版本。
- runner/websocket 将 `run_r_code` 纳入代码执行工具集合并记录语言为 `r`。

## Risks / Mitigations

- 风险：R 包自动安装耗时长。
  - 缓解：增加安装超时与开关，默认可关闭自动安装。
- 风险：静态策略误拦截或漏拦截。
  - 缓解：先保守白名单，补充正反测试样例。
- 风险：无 R 环境导致 CI 波动。
  - 缓解：执行器测试按 `Rscript` 可用性条件跳过。
