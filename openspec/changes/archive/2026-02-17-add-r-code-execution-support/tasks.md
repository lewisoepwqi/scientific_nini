# 任务清单：R 代码执行支持

## 1. 沙箱与执行器

- [x] 1.1 新增 `r_policy.py`：实现 R 代码静态策略校验。
- [x] 1.2 新增 `r_executor.py`：实现 R 环境探测、包检测、缺包安装与执行。
- [x] 1.3 更新 `sandbox/__init__.py` 导出 R 执行器接口。

## 2. 技能与注册

- [x] 2.1 新增 `run_r_code` 技能并对齐 `run_code` 返回契约。
- [x] 2.2 在 `registry.py` 中按配置和环境可用性条件注册 `run_r_code`。
- [x] 2.3 在 `config.py` 中新增 R 沙箱配置项。

## 3. 系统接入

- [x] 3.1 在 `nini doctor` 增加 R 环境与版本检查。
- [x] 3.2 在 `PromptBuilder` 默认策略中增加 R 使用规范。
- [x] 3.3 在 `agent/runner.py` 与 `api/websocket.py` 中接入 `run_r_code` 执行历史链路。

## 4. 测试与验证

- [x] 4.1 新增 `test_r_policy.py`（策略单测）。
- [x] 4.2 新增 `test_r_executor.py`（执行器测试，按 R 可用性跳过）。
- [x] 4.3 新增 `test_r_code_exec.py`（技能集成测试）。
- [x] 4.4 更新 `test_phase7_cli.py` 与 `test_phase4_websocket_run_code.py` 覆盖新增接入点。
- [x] 4.5 通过 `pytest -q` 与最小构建回归。
