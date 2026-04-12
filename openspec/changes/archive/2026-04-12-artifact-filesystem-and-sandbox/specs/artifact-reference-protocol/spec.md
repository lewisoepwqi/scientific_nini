## ADDED Requirements

### Requirement: 子 Agent 产物轻量引用结构
系统 SHALL 定义 `ArtifactRef` 数据结构，包含字段：`path: str`（相对于 session workspace 的文件路径）、`type: str`（`"chart"` / `"dataset"` / `"report"` / `"file"`）、`summary: str`（一句话描述）、`agent_id: str`（生成者 ID）。`SubAgentResult.artifacts` 中的值 SHALL 为 `ArtifactRef` 实例（或可序列化为等效字典），而非产物内容本身。

#### Scenario: run_code 产生图表时写入引用
- **WHEN** 子 Agent 通过 `run_code` 生成 matplotlib 图表并保存
- **THEN** `SubAgentResult.artifacts["chart"]` SHALL 为包含 `path`、`type="chart"`、`summary` 的引用结构
- **AND** 产物文件 SHALL 存在于 `workspace/artifacts/{agent_id}/` 目录下

#### Scenario: 父 Agent 通过路径访问产物
- **WHEN** 主 Agent 读取子 Agent 产物引用中的 `path` 字段
- **THEN** 该路径 SHALL 指向可通过 `read_file` 或 workspace 工具访问的真实文件

---

### Requirement: 子 Agent 沙箱工作区
每个子 Agent 执行期间 SHALL 使用独立的沙箱目录 `workspace/sandbox_tmp/{run_id}/` 作为写入空间，与其他子 Agent 和主 workspace 物理隔离。

#### Scenario: 子 Agent 成功完成时产物归档
- **WHEN** 子 Agent 执行成功（`SubAgentResult.success=True`）
- **THEN** 沙箱目录中的产物 SHALL 移入 `workspace/artifacts/{agent_id}/`
- **AND** 沙箱目录 SHALL 被清理（移动后删除空目录）

#### Scenario: 子 Agent 失败时保留现场
- **WHEN** 子 Agent 执行失败（`SubAgentResult.success=False`）
- **THEN** 沙箱目录 SHALL 移入 `workspace/sandbox_tmp/.failed/{run_id}/` 保留
- **AND** `SubAgentResult` SHALL 包含失败现场路径信息

#### Scenario: 多个子 Agent 并行时沙箱互不干扰
- **WHEN** `spawn_batch()` 并行执行 3 个子 Agent
- **THEN** 每个子 Agent SHALL 使用不同的 `run_id` 对应的沙箱目录
- **AND** 一个子 Agent 的写入操作 SHALL NOT 影响其他子 Agent 的沙箱内容
