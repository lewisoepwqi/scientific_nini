# skill-dag-engine Specification

## Purpose
TBD - created by archiving change add-skill-dag-engine. Update Purpose after archive.

## Requirements

### Requirement: 并行分支执行

ContractRunner SHALL 支持同一拓扑层的步骤并发执行，依赖关系满足的步骤不再等待无关步骤完成。

#### Scenario: 独立步骤并行执行

- **WHEN** 步骤 B 和 C 仅依赖步骤 A，且 A 已完成
- **THEN** B 和 C 被并发执行

#### Scenario: 汇合点等待所有分支

- **WHEN** 步骤 D 依赖步骤 B 和 C
- **THEN** D 在 B 和 C 都完成后才执行

#### Scenario: 并行步骤之一失败

- **WHEN** 并行执行的步骤 B 失败
- **THEN** 步骤 C 继续执行，步骤 D 根据 retry_policy 处理

### Requirement: 条件步骤

SkillStep SHALL 支持可选的 `condition` 字段，执行引擎在步骤启动前评估条件。

#### Scenario: 条件为 True 时执行

- **WHEN** 步骤的 condition 评估为 True
- **THEN** 步骤正常执行

#### Scenario: 条件为 False 时跳过

- **WHEN** 步骤的 condition 评估为 False
- **THEN** 步骤被标记为 skipped，发射 skill_step 事件 status="skipped"

#### Scenario: 条件表达式安全执行

- **WHEN** condition 表达式包含非法操作（如函数调用、文件访问）
- **THEN** 条件评估失败，步骤按 retry_policy 处理

### Requirement: 步骤间数据传递

SkillStep SHALL 支持 `input_from` 和 `output_key` 字段，实现步骤间的数据流绑定。

#### Scenario: 输出存入上下文

- **WHEN** 步骤设置了 output_key="test_result"
- **THEN** 步骤输出以 "test_result" 为键存入共享上下文

#### Scenario: 输入从上下文读取

- **WHEN** 步骤设置了 input_from={"data": "load_step.dataset"}
- **THEN** 步骤启动时从共享上下文中读取 load_step 的 dataset 输出

### Requirement: 向后兼容

升级后的 ContractRunner SHALL 对线性 DAG 的执行结果与升级前完全一致。

#### Scenario: 线性 DAG 串行执行

- **WHEN** 执行仅包含线性依赖的 contract（A→B→C）
- **THEN** 执行顺序为 A, B, C，行为与升级前一致

#### Scenario: 无新字段的 SkillStep 正常运行

- **WHEN** SkillStep 未设置 condition、input_from、output_key
- **THEN** 步骤正常执行，新字段默认值不影响行为

### Requirement: 并行执行 observability

并行步骤的执行事件 SHALL 正确反映并行状态。

#### Scenario: 并行步骤事件包含层信息

- **WHEN** 步骤 B 和 C 并行执行
- **THEN** 发射的 skill_step 事件包含层信息（如 layer=1）
