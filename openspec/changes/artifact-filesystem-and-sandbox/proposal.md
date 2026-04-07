## Why

当前子 Agent 产物（图表、清洗后的数据集、分析报告）以 Python 对象形式存储在父会话的内存字典 `session.artifacts` 中，而非写入文件系统。这与 Anthropic 工程团队总结的"引用而非复制"（Reference, not copy）最佳实践相悖：大型产物占用主 Agent 上下文窗口、跨 Agent 传递时易失真（"传话游戏"），且无法在会话重启后恢复。与此同时，并行子 Agent 对同一 workspace 目录无任何写入隔离，多个子 Agent 同时写入同名文件时行为不可预期。

## What Changes

- **产物文件化**：子 Agent 工具（`run_code`、`create_chart`、`save_dataset`）生成的产物 SHALL 写入 `workspace/artifacts/{agent_id}/` 目录；`SubAgentResult.artifacts` 中存储的 SHALL 是轻量引用结构 `{"path": "workspace/artifacts/...", "type": "...", "summary": "..."}`，而非产物内容本身
- **沙箱工作区**：每个子 Agent 执行期间，在 `workspace/sandbox_tmp/{run_id}/` 创建独立临时目录作为写入沙箱；子 Agent 完成后，成功产物移入 `workspace/artifacts/{agent_id}/`，失败产物保留在 `workspace/sandbox_tmp/.failed/{run_id}/` 用于排障
- **冲突检测升级**：`ResultFusionEngine._detect_conflicts()` 新增产物键冲突检测——当多个子 Agent 的 `artifacts` 引用中出现相同文件名时，记录 `artifact_key_conflict` 类型冲突；现有数值差异检测保留
- **多意图检测修复（BREAKING）**：`detect_multi_intent()` 返回值从 `list[str] | None` 改为 `MultiIntentResult | None`（新 dataclass，包含 `intents: list[str]`、`is_parallel: bool`、`is_sequential: bool`）；调用方更新为使用 `.intents` 访问子意图列表。同时 `_PARALLEL_MARKERS` 移除"顺便"（主从关系，非独立并行）

## Capabilities

### New Capabilities
- `artifact-reference-protocol`：定义子 Agent 产物的轻量引用结构（路径 + 类型 + 摘要），及产物从沙箱工作区到主 workspace 的生命周期管理协议

### Modified Capabilities
- `result-fusion-engine`：`_detect_conflicts()` 新增 `artifact_key_conflict` 类型检测
- `multi-intent-detection`：修复并/串行标记的互斥逻辑，移除不准确的"顺便"并行标记

## Impact

- **受影响代码**：
  - `src/nini/agent/spawner.py`（`_execute_agent()`：创建沙箱目录；结果收集：从沙箱移入主 workspace）
  - `src/nini/agent/sub_session.py`（`workspace_root` 指向沙箱目录而非主目录）
  - `src/nini/agent/fusion.py`（`_detect_conflicts()`：新增产物键冲突检测）
  - `src/nini/agent/multi_intent.py`（`_PARALLEL_MARKERS` + 策略 1 分类保留）
  - `src/nini/tools/run_code.py`、`src/nini/tools/create_chart.py`（产物路径写入引用结构而非内存）
- **受影响测试**：
  - `tests/test_spawner.py`（新增沙箱隔离、产物移动测试）
  - `tests/test_fusion.py`（新增 artifact_key_conflict 检测测试）
  - `tests/test_phase3_run_code.py`（产物路径断言变更）
- **非目标**：不实现持久化产物版本控制；不改变主 Agent（非子 Agent）的产物存储行为；沙箱不提供 OS 级进程隔离（非安全沙箱）
- **依赖前提**：本 change 依赖 C1（fix-dispatch-parallel-serial-chain）中命名空间键机制，需在 C1 合并后实施
