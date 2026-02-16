# Change: 为技能体系新增 R 代码执行支持

## Why

当前系统仅支持 `run_code`（Python 沙箱），在科研统计场景中无法直接调用 R/Bioconductor 生态（如 `MetaCycle`、`DESeq2`、`limma` 等），导致部分分析链路需要外部工具中转，破坏会话内可追溯性与自动化体验。

## What Changes

- 新增 `run_r_code` Function Skill，通过 `Rscript --vanilla` 在受限子进程中执行 R 代码。
- 新增 R 沙箱安全策略（包白名单 + 危险调用黑名单 + 静态校验）。
- 新增 R 执行器（数据集注入、结果结构化、图表文件采集、可选缺包自动安装）。
- 在技能注册、系统提示词、`nini doctor`、WebSocket 执行历史中接入 R 能力。
- 保持默认兼容：R 不可用或禁用时不暴露 `run_r_code`。

## Impact

- Affected specs:
  - `skills`
- Affected code:
  - `src/nini/sandbox/r_policy.py`
  - `src/nini/sandbox/r_executor.py`
  - `src/nini/sandbox/__init__.py`
  - `src/nini/skills/r_code_exec.py`
  - `src/nini/skills/registry.py`
  - `src/nini/config.py`
  - `src/nini/__main__.py`
  - `src/nini/agent/prompts/builder.py`
  - `src/nini/agent/runner.py`
  - `src/nini/api/websocket.py`
  - `tests/test_r_policy.py`
  - `tests/test_r_executor.py`
  - `tests/test_r_code_exec.py`
  - `tests/test_phase7_cli.py`
  - `tests/test_phase4_websocket_run_code.py`
