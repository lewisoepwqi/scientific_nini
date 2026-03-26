## Why

当前 `Capability` 数据类缺少研究阶段归属和风险等级信息。11 个已定义的 Capability 无法表达「属于哪个研究阶段」和「默认风险等级是什么」，导致 Agent 无法根据用户任务所属阶段过滤推荐能力，也无法在能力层面继承风险等级。C2 已在 models 中定义了 `RiskLevel` 和 `OutputLevel` 枚举，本 change 将这些元数据接入 Capability 体系，并为现有 11 个 Capability 标注阶段和风险属性。

## What Changes

- **扩展 Capability 数据类**：在 `capabilities/base.py` 的 `Capability` dataclass 中新增 `phase`（所属研究阶段）、`risk_level`（默认风险等级）、`max_output_level`（最高输出等级）三个可选字段。
- **定义研究阶段枚举**：新增 `ResearchPhase` 枚举（选题、文献调研、实验设计、数据采集、数据分析、论文写作、投稿发表、传播转化），放在 `models/risk.py` 或 Capability 模块中。
- **标注现有 Capability**：为 `defaults.py` 中的 10 个 Capability 标注 phase 和 risk_level 属性。
- **扩展 `to_dict()` 输出**：API 响应中包含新增字段，前端可按需消费。

## Non-Goals

- 不新增 Capability 定义（新阶段的 Capability 在 C6/C7/C8 中添加）。
- 不实现基于阶段的 Capability 路由逻辑（属于 C4 Skill 契约的范围）。
- 不修改前端 UI 展示。
- 不修改 Capability executor 的执行逻辑。

## Capabilities

### New Capabilities

- `phase-aware-capability`: 阶段感知能力模型——涵盖 Capability 数据类扩展、ResearchPhase 枚举、现有 Capability 的阶段/风险标注

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/capabilities/base.py`（字段扩展）、`src/nini/capabilities/defaults.py`（属性标注）、`src/nini/models/risk.py`（可能新增 ResearchPhase 枚举）
- **影响范围**：Capability API 响应新增字段（向后兼容），能力推荐逻辑的数据基础
- **API / 依赖**：`/api/capabilities` 响应新增可选字段，无新增外部依赖
- **风险**：纯增量字段，默认值为 None，不影响现有行为
- **回滚**：revert base.py 和 defaults.py 的字段新增即可恢复
- **验证方式**：单元测试验证 Capability 字段存在性、to_dict 输出、现有 Capability 标注正确性；`pytest -q` 确认无回归
