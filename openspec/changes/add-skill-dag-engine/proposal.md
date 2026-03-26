## Why

C4 实现的 ContractRunner 仅支持线性 DAG（步骤严格串行），这满足了 V1 初期的三个新阶段 Skill 需求。但随着 Skill 复杂度增加，需要支持并行分支——例如数据分析 Skill 中「正态性检验」和「方差齐性检验」可以并行执行。本 change 将 ContractRunner 升级为完整的 DAG 执行引擎，支持并行分支、汇合点和条件跳过。

## What Changes

- **升级 ContractRunner**：从线性执行升级为真正的 DAG 执行引擎，支持并行分支（依赖关系允许的步骤并发执行）。
- **新增条件步骤**：SkillStep 新增可选的 `condition` 字段，支持基于前置步骤输出的条件跳过。
- **新增步骤输入/输出绑定**：SkillStep 新增 `input_from` 和 `output_key` 字段，支持步骤间数据传递。
- **性能优化**：并行步骤使用 `asyncio.gather` 并发执行。

## Non-Goals

- 不实现动态 DAG 修改（执行中不能增删步骤）。
- 不实现跨 Skill 的 DAG 编排（仅单 Skill 内部 DAG）。
- 不实现分布式执行。

## Capabilities

### New Capabilities

- `skill-dag-engine`: DAG 执行引擎——涵盖并行分支执行、条件步骤、步骤间数据传递、汇合点

### Modified Capabilities

（无既有 spec 需要修改，但实际上扩展了 C4 的 skill-contract-runtime）

## Impact

- **影响文件**：`src/nini/skills/contract_runner.py`（升级执行引擎）、`src/nini/models/skill_contract.py`（扩展 SkillStep 字段）
- **影响范围**：Skill 执行方式升级，向后兼容——线性 DAG 的 Skill 无需修改即可运行
- **API / 依赖**：无新增外部依赖
- **风险**：并行执行增加调试复杂度——通过完善的 observability 事件缓解
- **回滚**：revert contract_runner.py 和 skill_contract.py 的变更即可恢复
- **验证方式**：单元测试验证 DAG 拓扑排序、并行执行、条件跳过、数据传递；回归测试验证现有线性 Skill 不受影响
