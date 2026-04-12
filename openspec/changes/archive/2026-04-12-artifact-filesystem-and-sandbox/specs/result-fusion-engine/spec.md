## MODIFIED Requirements

### Requirement: 结果冲突检测
`ResultFusionEngine._detect_conflicts(results)` SHALL 检测以下两类冲突（两类检测均不阻断融合流程，仅记录到 `FusionResult.conflicts`）：

**类型 1 — 数值差异（原有）**：提取各 Agent summary 中的最大数值，差异超过 50% 时记录 `numeric_discrepancy` 类型冲突。

**类型 2 — 产物键冲突（新增）**：当多个子 Agent 的 `artifacts` 中出现相同文件名（从 `ArtifactRef.path` 取文件名，兼容旧格式时取键名），记录 `artifact_key_conflict` 类型冲突，包含冲突文件名和涉及的 Agent ID 列表。

#### Scenario: 两个 Agent 生成同名产物时记录冲突
- **WHEN** Agent A 的 `artifacts` 包含路径 `workspace/artifacts/agent_a/report.pdf`
- **AND** Agent B 的 `artifacts` 包含路径 `workspace/artifacts/agent_b/report.pdf`
- **THEN** `FusionResult.conflicts` SHALL 包含一条 `type="artifact_key_conflict"` 的条目
- **AND** 该条目 SHALL 包含 `"filename": "report.pdf"` 和 `"agents": ["agent_a", "agent_b"]`
- **AND** 融合流程 SHALL 继续执行（冲突仅作为元数据记录）

#### Scenario: 无产物冲突时不产生误报
- **WHEN** 所有子 Agent 的产物文件名互不相同
- **THEN** `FusionResult.conflicts` SHALL 不包含 `artifact_key_conflict` 类型条目
