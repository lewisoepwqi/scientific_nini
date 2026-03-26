## Context

当前 `Capability` dataclass（`capabilities/base.py`）有 9 个字段：name、display_name、description、icon、required_tools、suggested_workflow、is_executable、execution_message、executor_factory。`defaults.py` 定义了 11 个 Capability 实例（6 个核心数据分析 + 5 个全流程扩展）。C2 已在 `models/risk.py` 中定义了 `RiskLevel`、`TrustLevel`、`OutputLevel` 枚举。

## Goals / Non-Goals

**Goals:**
- Capability 可声明所属研究阶段
- Capability 可声明默认风险等级和最高输出等级
- 现有 10 个 Capability 完成标注
- API 响应包含新字段

**Non-Goals:**
- 不实现阶段路由逻辑
- 不新增 Capability 实例

## Decisions

### D1: ResearchPhase 枚举的存放位置

**选择**：放在 `src/nini/models/risk.py` 中，与 `RiskLevel`、`OutputLevel` 共处。

**理由**：研究阶段是 V1 纲领的核心概念之一，与风险/输出等级同属基础模型。放在 `models/risk.py`（可考虑重命名为 `models/research.py`，但为减少 C2 的 diff，暂不重命名）中便于跨模块引用。

**替代方案**：放在 `capabilities/base.py` → 但 phase 概念不仅 Capability 使用，后续 Skill、Task 也会引用。

### D2: Capability 新增字段的设计

**选择**：新增三个可选字段：
```python
phase: ResearchPhase | None = None          # 所属研究阶段
risk_level: RiskLevel | None = None          # 默认风险等级
max_output_level: OutputLevel | None = None  # 能力可达到的最高输出等级
```

**理由**：Optional 字段保证向后兼容。一个 Capability 可能跨阶段使用（如 visualization），phase=None 表示「通用」。risk_level 为该能力的默认风险等级，具体执行时可根据上下文动态调整。max_output_level 表示该能力最高可达到的输出等级（受 trust-ceiling 约束）。

### D3: 现有 Capability 标注方案

**选择**：

| Capability | phase | risk_level | max_output_level |
|-----------|-------|------------|-----------------|
| difference_analysis | data_analysis | medium | o4 |
| correlation_analysis | data_analysis | medium | o4 |
| regression_analysis | data_analysis | medium | o4 |
| data_exploration | data_analysis | low | o3 |
| data_cleaning | data_analysis | low | o3 |
| visualization | None（通用） | low | o4 |
| report_generation | data_analysis | medium | o4 |
| article_draft | paper_writing | high | o2 |
| citation_management | paper_writing | medium | o3 |
| peer_review | paper_writing | high | o2 |
| research_planning | experiment_design | high | o2 |

**理由**：
- 数据分析类 Capability 经过充分验证，trust 较高，max_output_level 可达 O4
- 论文写作/实验设计类目前为 L1（提示词引导），trust_ceiling 为 T1→O2
- article_draft 和 peer_review 涉及研究判断，risk_level 为 high
- visualization 跨阶段使用，phase 设为 None

### D4: to_dict() 扩展

**选择**：在 `to_dict()` 中包含新字段，值为枚举的字符串形式或 None。

**理由**：保持 API 响应的完整性，前端可选择性消费。

## Risks / Trade-offs

- **[风险] 标注方案主观性** → 基于纲领的 Lx/Tx 模型确定，有据可循。后续可通过实际使用数据调整。
- **[风险] models/risk.py 职责膨胀** → 仅新增一个枚举（ResearchPhase），可接受。若后续增长过快再拆分。
- **[回滚]** revert base.py 字段 + defaults.py 标注 + risk.py 枚举即可恢复。
