# intent-evaluation Specification

## Purpose
TBD - created by archiving change intent-phase3-monitoring. Update Purpose after archive.
## Requirements
### Requirement: YAML 评估数据集包含 90 条带标注查询

`tests/fixtures/intent_eval_dataset.yaml` SHALL 包含不少于 90 条查询记录，每条记录包含 `query`（查询文本）、`expected_top1`（期望的 Top-1 capability 名，OOS 时为 `null`）、`query_type`（`domain_task` / `out_of_scope` / `ambiguous`）和 `note`（可选备注）。数据集分布：50 条域内查询（覆盖全部 Capability）、20 条模糊/多意图查询、20 条 OOS 查询。

#### Scenario: 数据集格式正确可加载

- **WHEN** 用 PyYAML 加载 `intent_eval_dataset.yaml`
- **THEN** 返回列表，每条记录均包含 `query` 和 `query_type` 字段，总数 >= 90

#### Scenario: 数据集覆盖所有 Capability

- **WHEN** 统计 `domain_task` 类型记录的 `expected_top1` 去重集合
- **THEN** 包含 `difference_analysis`、`correlation_analysis`、`regression_analysis`、`data_exploration`、`data_cleaning`、`visualization`、`report_generation`、`article_draft` 全部 8 个

### Requirement: 参数化测试报告意图识别 Top-1 准确率

`tests/test_intent_eval.py` SHALL 用 `@pytest.mark.parametrize` 加载评估数据集，对每条 `domain_task` 类型记录断言意图分析器的 Top-1 候选与 `expected_top1` 一致。测试运行后控制台输出整体 Top-1 准确率（通过 `pytest` 的 `conftest.py` 或 session 级 fixture 汇总）。

#### Scenario: 域内标准查询 Top-1 准确率打印到控制台（首次运行建立基线）

- **WHEN** 运行 `pytest tests/test_intent_eval.py -q`
- **THEN** 控制台输出域内 Top-1 准确率数值；首次运行允许低于 80%，**不作为 CI 断言**；长期迭代目标 >= 80%（后续目标 >= 88%）

### Requirement: 参数化测试报告 OOS 召回率

对 `out_of_scope` 类型记录，`tests/test_intent_eval.py` SHALL 断言 `query_type` 返回 `QueryType.OUT_OF_SCOPE`，并汇总 OOS 召回率。

#### Scenario: OOS 查询识别召回率打印到控制台（首次运行建立基线）

- **WHEN** 运行评估测试套件
- **THEN** 控制台输出 OOS 召回率数值；首次运行允许低于 70%，**不作为 CI 断言**；长期迭代目标 >= 70%（后续目标 >= 85%）

