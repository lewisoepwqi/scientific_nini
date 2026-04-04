# Nini Autoresearch

## 目标

Nini 的 `autoresearch` 现在分成两条独立实验线，分别优化不同目标：

- `static`：优化固定上下文开销，关注 prompt、工具面与静态预算。
- `harness`：优化真实任务表现，关注完成率、阻塞率、成本与耗时。

这两条线必须独立管理，不能混用 baseline、结果账本或判定逻辑。

## 目录

```
docs/autoresearch/
  README.md
  USAGE.md
  static/
    PROGRAM.md
    AGENT_PROTOCOL.md
  harness/
    PROTOCOL.md

results/
  static_results.tsv
  harness_results.tsv

scripts/
  measure_static_baseline.py
  run_static_experiment.sh
  measure_harness_baseline.py
  run_harness_experiment.sh
```

兼容入口仍保留：

- 根目录 [AUTORESEARCH_AGENT_PROTOCOL.md](/home/lewis/coding/scientific_nini/AUTORESEARCH_AGENT_PROTOCOL.md)
- 根目录 [autoresearch_program.md](/home/lewis/coding/scientific_nini/autoresearch_program.md)
- `scripts/measure_baseline.py`
- `scripts/run_experiment.sh`

这些入口只用于兼容旧流程；后续维护以新目录为准。

详细使用说明与案例见：

- [USAGE.md](/home/lewis/coding/scientific_nini/docs/autoresearch/USAGE.md)

## 硬规则

1. 两条线不得共用 `results.tsv`。
2. 两条线不得共用实验分支。
3. 单次实验不得跨越两条线的白名单文件。
4. `keep/discard` 只能由本线 evaluator 决定。
5. 若一个想法同时影响两条线，必须拆成两个实验。

## 分支命名

- `autoresearch/static/<tag>`
- `autoresearch/harness/<tag>`

单个分支只能属于一条线，不允许混跑。

## 结果账本

`static` 使用：

- [results/static_results.tsv](/home/lewis/coding/scientific_nini/results/static_results.tsv)

`harness` 使用：

- [results/harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)

禁止新增通用 `results.tsv` 写入逻辑。

## 文件边界

`static` 允许改：

- `data/prompt_components/`
- `data/AGENTS.md`
- `src/nini/tools/markdown_scanner.py`
- 工具 description 文本
- `src/nini/agent/prompt_policy.py` 中与静态预算直接相关的文本/阈值

`harness` 允许改：

- [prompt_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/prompt_policy.py)
- [context_tools.py](/home/lewis/coding/scientific_nini/src/nini/agent/components/context_tools.py)
- [tool_exposure_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/tool_exposure_policy.py)
- [config.py](/home/lewis/coding/scientific_nini/src/nini/config.py)

`harness` 禁止改：

- `tests/`
- harness evaluator 本身
- 统计工具 `execute()` 正确性实现
- `static` 线的结果账本和脚本

## 使用方式

如果要压固定开销：

```bash
python scripts/measure_static_baseline.py --compare
./scripts/run_static_experiment.sh "描述"
```

如果要设计或执行第二条线，先读：

- [docs/autoresearch/harness/PROTOCOL.md](/home/lewis/coding/scientific_nini/docs/autoresearch/harness/PROTOCOL.md)
- [USAGE.md](/home/lewis/coding/scientific_nini/docs/autoresearch/USAGE.md)

第二条线当前入口：

```bash
python scripts/run_harness_benchmarks.py --benchmark-set smoke
python scripts/measure_harness_baseline.py --session-id <session_id> --compare
./scripts/run_harness_experiment.sh <session_id> smoke "描述"
./scripts/run_harness_experiment.sh --auto-run smoke "描述"
```

## 管理原则

- `static` 是高频、小步、便宜的实验线。
- `harness` 是低频、批量、以 benchmark 为中心的实验线。
- `static` 的收益不能自动推导为 `harness` 收益。
- `harness` 的收益也不能反向覆盖 `static` baseline。
