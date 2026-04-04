# Nini Autoresearch Harness Protocol

> 本文件定义第二条 `harness` 线。
> 它不是第一条线的延伸，而是一套独立的 benchmark 驱动实验框架。

## 1. 目标

`harness` 线优化的是 Nini 在真实任务上的表现，而不是静态 prompt 成本。

主目标：

- 提高任务完成率
- 降低阻塞率
- 降低严重 failure tag

次目标：

- 降低中位成本
- 降低中位耗时
- 降低中位 token 与 tool call 数

## 2. 固定评估器

第二条线必须有独立 evaluator，对应上游 autoresearch 的 `prepare.py`。

建议入口：

- `scripts/measure_harness_baseline.py`
- `scripts/run_harness_experiment.sh`

这两个脚本应被视为只读评估基础设施，不纳入普通实验改动面。

当前最小可用版本说明：

- 现在可以用 `scripts/run_harness_benchmarks.py` 自动执行 benchmark 集，并生成新的 `session_id`。
- `scripts/run_harness_experiment.sh --auto-run` 会先自动执行 benchmark，再做 pytest 门控与结果记账。
- 仍然支持手工传入已有的 `session_id`，便于重复评估同一批 trace。
- 若 benchmark 路由命中 `dashscope`，第二条线默认使用 `glm-5`，避免误落到 `standard` 模式下的普通 Qwen 模型。
- 该默认值只作用于 `autoresearch-harness` 执行链路，不修改全局 provider 配置。

## 3. 固定 benchmark

第二条线必须运行固定 benchmark，而不是任意手工 case。

建议基准文件：

- `data/autoresearch/harness_benchmarks.yaml`

建议分层：

- `smoke`：8 到 12 个 case，每次实验必跑
- `full`：25 到 40 个 case，只在候选优胜或定时任务中跑

case 类型建议覆盖：

- `analysis`
- `report`
- `recovery`

当前 `smoke` 已内置 3 个 core recipe case：

- `literature_review`
- `experiment_plan`
- `results_interpretation`

## 4. 可修改文件白名单

第二条线优先只开放以下策略面：

- [prompt_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/prompt_policy.py)
- [context_tools.py](/home/lewis/coding/scientific_nini/src/nini/agent/components/context_tools.py)
- [tool_exposure_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/tool_exposure_policy.py)
- [config.py](/home/lewis/coding/scientific_nini/src/nini/config.py)

典型可优化点：

- runtime context 裁剪优先级
- skill 注入策略
- stage 工具暴露面
- deep task budget 阈值
- 恢复与重试阈值

## 5. 禁区

第二条线默认禁止：

- `tests/`
- static 线脚本与账本
- harness evaluator 自身
- benchmark case 数据
- 统计工具核心正确性实现
- 大规模架构重写

如果需要修改这些区域，必须单独立项，不归入 `autoresearch-harness`。

## 6. 结果账本

第二条线只写：

- [results/harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)

建议字段：

- `commit`
- `timestamp`
- `metric_version`
- `benchmark_set`
- `pass_count`
- `blocked_count`
- `failure_count`
- `pass_rate`
- `blocked_rate`
- `median_duration_s`
- `median_cost_usd`
- `median_input_tokens`
- `median_output_tokens`
- `median_tool_calls`
- `prompt_profiles`
- `prompt_truncated_runs`
- `prompt_truncation_rate`
- `median_prompt_tokens_before`
- `median_prompt_tokens_after`
- `median_prompt_token_budget`
- `new_failure_tags`
- `changed_files`
- `change_summary`
- `status`

推荐初始版本号：

- `nini_harness_v1`

## 7. keep/discard 规则

不要做模糊总分，按门槛与词典序判定。

先过门槛：

- `pass_rate >= baseline`
- `blocked_rate <= baseline`
- `new_severe_failure_tags == 0`
- `prompt_truncation_mismatch == false`，否则不得直接判定为 `keep`

再比较优劣：

1. 更高 `pass_count`
2. 更低 `blocked_count`
3. 更低 `failure_count`
4. 更低 `median_cost_usd`
5. 更低 `median_duration_s`
6. 更低 `median_input_tokens + median_output_tokens`

## 8. 分支与节奏

分支命名：

- `autoresearch/harness/<tag>`

运行节奏：

- `static` 可以高频运行
- `harness` 应低频运行，以 `smoke` benchmark 为主

不要因为一个小 prompt 改动就立刻触发整套 harness 实验。

## 9. 防串规则

1. 不与 `static` 共用 baseline。
2. 不与 `static` 共用结果账本。
3. 单个实验分支不得同时修改 `static` 白名单文件和 `harness` 白名单文件。
4. 若某改动同时影响两条线，必须拆分成两个实验。

## 10. 当前状态

本协议已经定稿，但第二条线的执行脚本与 benchmark 仍处于待实现状态。

当前可立即做的事：

- 固定 benchmark 样本格式
- 实现 `measure_harness_baseline.py`
- 实现 `run_harness_experiment.sh`
- 补齐 `harness_results.tsv` 写入与 compare 逻辑

当前已经完成：

- benchmark 样本格式与默认 `smoke/full` 配置
- `run_harness_benchmarks.py` 自动执行入口
- `measure_harness_baseline.py` 聚合与 compare
- `run_harness_experiment.sh --auto-run` 一键链路
- prompt 截断审计与结果记账，避免将截断 benchmark 与未截断 baseline 混比
