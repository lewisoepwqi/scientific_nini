## Context

当前产物存储路径：
```
子 Agent 执行 run_code / create_chart
  → 产物写入 session.workspace/artifacts/（主 workspace）
  → SubAgentResult.artifacts = {"key": <bytes 或 dict 内容>}
  → spawn_batch() 将内容 update 到父 session.artifacts
```

目标产物存储路径：
```
子 Agent 执行 run_code / create_chart
  → 产物写入 workspace/sandbox_tmp/{run_id}/（隔离沙箱）
  → 子 Agent 完成后，成功产物移入 workspace/artifacts/{agent_id}/
  → SubAgentResult.artifacts = {"key": {"path": "...", "type": "...", "summary": "..."}}
  → 父 Agent 通过路径引用按需访问产物，不在内存中传递大型对象
```

## Goals / Non-Goals

**Goals:**
- 子 Agent 产物写入独立沙箱目录，完成后按结果移入主 workspace
- `SubAgentResult.artifacts` 存储轻量引用而非产物内容
- `_detect_conflicts()` 能识别多个子 Agent 写入同名文件的冲突
- `detect_multi_intent()` 的并/串行分类更准确（移除误导性标记词）

**Non-Goals:**
- 不实现 OS 级别的沙箱隔离（如 seccomp/cgroups）
- 不改变主 Agent 的产物存储行为
- 不实现产物版本控制或差量存储
- 不引入新的外部依赖

## Decisions

### 决策 1：沙箱目录选在 workspace/sandbox_tmp/{run_id}/

**选项 A**：系统临时目录（`/tmp/nini-{run_id}/`）
**选项 B**：session workspace 下的子目录（`workspace/sandbox_tmp/{run_id}/`）

**选择 B**，原因：
- 与现有 workspace 生命周期绑定，session 删除时临时目录一并清理
- 失败产物保留路径（`.failed/{run_id}/`）与成功产物路径在同一根目录下，便于统一管理
- 主 Agent 可通过 `workspace_tool` 访问失败产物进行排障

### 决策 2：引用结构字段定义

```python
@dataclass
class ArtifactRef:
    path: str        # 相对于 session workspace 的路径
    type: str        # "chart" | "dataset" | "report" | "file"
    summary: str     # 一句话描述，供融合引擎生成摘要
    agent_id: str    # 生成者 agent_id
    size_bytes: int  # 文件大小，-1 表示未知
```

不使用 TypedDict 而使用 dataclass，与现有代码风格一致（`FusionResult`、`SubAgentResult` 等均为 dataclass）。

### 决策 3：产物移动策略

子 Agent 完成后，`_execute_agent()` 负责将沙箱产物移入主 workspace：
- 成功（`result.success=True`）：`shutil.move(sandbox_dir, workspace/artifacts/{agent_id}/)`
- 失败（`result.success=False`）：`shutil.move(sandbox_dir, workspace/sandbox_tmp/.failed/{run_id}/)`
- 移动操作在 `asyncio.to_thread()` 中执行，避免阻塞事件循环

### 决策 4：multi_intent 修复范围

本 change 只修复最高优先级的两个问题：
1. 移除"顺便"（从 `_PARALLEL_MARKERS` 中删除，改为不分类，交由标点分割处理）
2. 策略 1（标点分割命中时）在分割前先保存 `is_parallel`/`is_sequential` 值，供调用方使用

不修复"和"过于宽泛的问题（需要更大范围的语义测试，风险高，留给后续迭代）。

### 决策 5：`_detect_conflicts()` 产物键检测实现

```python
# 检测多个 Agent 的 artifacts 引用中是否有相同文件名
all_artifact_names: dict[str, list[str]] = {}  # filename → [agent_ids]
for result in results:
    for key, ref in result.artifacts.items():
        filename = Path(ref.get("path", key)).name if isinstance(ref, dict) else key
        all_artifact_names.setdefault(filename, []).append(result.agent_id)

for filename, agents in all_artifact_names.items():
    if len(agents) > 1:
        conflicts.append({"type": "artifact_key_conflict", "filename": filename, "agents": agents})
```

此实现兼容旧格式（`artifacts` 值为内容而非引用）——旧格式时用键名而非路径名比较，结果等效于 C1 中的命名空间键机制。

## Risks / Trade-offs

- **文件移动失败**：磁盘满、权限问题可能导致 `shutil.move` 失败 → 缓解：捕获 `OSError`，降级为将沙箱路径直接记录到 `SubAgentResult`（内容仍可访问，只是未归档到主 workspace）
- **`run_code` / `create_chart` 工具改动面广**：两个工具的产物写入路径变更会影响大量测试 → 缓解：逐个工具迁移，每次迁移后单独跑对应测试
- **主 Agent 通过文件路径访问产物**：`ArtifactRef.path` 是相对路径，主 Agent 需要通过 `workspace_tool` 或 `read_file` 访问；直接在会话内存中读取的旧代码需要迁移

## Migration Plan

**前提**：`fix-dispatch-parallel-serial-chain`（C1）必须已合并。C1 引入的命名空间键机制是本 change 产物引用结构的上游依赖——若两者同时开发，产物键格式会出现语义冲突（C1 用 `{agent_id}.{key}`，本 change 改为 `ArtifactRef`）。

1. 先实现 `ArtifactRef` dataclass 和沙箱目录管理（无 API 变化）
2. 修改 `spawner.py`（`_execute_agent`）创建/清理沙箱
3. 修改 `sub_session.py` 使其 workspace 指向沙箱目录
4. 逐个修改工具（`run_code`、`create_chart`）写入引用而非内容
5. 修改 `fusion.py` 冲突检测
6. 修改 `multi_intent.py`
7. 全量测试通过后合并
