## 1. 基础设施：ArtifactRef 与沙箱管理

- [x] 1.1 定义 `ArtifactRef` dataclass（`src/nini/agent/artifact_ref.py`，新建文件）：字段 `path`、`type`、`summary`、`agent_id`（无 `size_bytes`），含 `to_dict()` / `from_dict()` 方法
- [x] 1.2 在 `spawner.py:_execute_agent()` 中：执行开始前创建沙箱目录 `workspace/sandbox_tmp/{run_id}/`；将 `sub_session.workspace_root` 指向沙箱目录
- [x] 1.3 在 `spawner.py:_execute_agent()` 中：执行完成后，成功时移动产物到 `workspace/artifacts/{agent_id}/`，失败时移动到 `workspace/sandbox_tmp/.failed/{run_id}/`（用 `asyncio.to_thread(shutil.move, ...)`）
- [x] 1.4 补充异常处理：`shutil.move` 失败时记录 ERROR 日志，降级为将沙箱路径写入 `SubAgentResult` 错误信息，不抛出异常

## 2. 工具层：产物写入引用而非内容

- [x] 2.1 修改 `tools/run_code.py`：代码执行产生的图表/文件，写入 `session.workspace_root/`（即沙箱目录）后，在 `session.artifacts` 中存储 `ArtifactRef` 而非文件内容
- [x] 2.2 修改 `tools/create_chart.py`：图表保存到沙箱目录后，在 `session.artifacts` 中存储 `ArtifactRef`
- [x] 2.3 更新 `tests/test_phase3_run_code.py` 和 `tests/test_phase2_skills.py`：断言 `session.artifacts` 中的值为引用结构（有 `path` 字段）而非内容

## 3. 融合层：产物冲突检测

- [x] 3.1 修改 `fusion.py:_detect_conflicts()`：在现有数值差异检测基础上，新增产物文件名冲突检测（提取 `ArtifactRef.path` 的文件名，兼容旧字典格式）
- [x] 3.2 更新 `tests/test_fusion.py`：新增两个子 Agent 产出同名文件时检测到 `artifact_key_conflict` 的测试用例

## 4. 路由层：multi_intent 修复

- [x] 4.1 修改 `agent/multi_intent.py`：从 `_PARALLEL_MARKERS` 移除"顺便"
- [x] 4.2 修改 `detect_multi_intent()` 返回值：附带 `is_parallel: bool` 和 `is_sequential: bool` 元信息（可通过返回 `NamedTuple` 或 `dataclass` 实现，保持向后兼容）
- [x] 4.3 修改 `router.py`：直接使用 `detect_multi_intent()` 返回的分类信息，不再重复 `_PARALLEL_MARKERS.search(intent)`
- [x] 4.4 更新多意图检测相关测试：验证"顺便"不触发并行、标点分割路径附带分类信息

## 5. 集成验证

- [x] 5.1 端到端测试：并行派发两个子 Agent，验证沙箱互不干扰、成功产物正确归档
- [x] 5.2 运行 `pytest -q tests/test_spawner.py tests/test_fusion.py tests/test_phase3_run_code.py` 全部通过
- [x] 5.3 运行 `python scripts/check_event_schema_consistency.py` 通过
- [x] 5.4 运行 `pytest -q` 全量测试通过
