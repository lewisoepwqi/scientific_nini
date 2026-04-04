# Autoresearch Static Agent 操作规程

> 本文件只适用于第一条 `static` 线。
> 目标是在不破坏测试的前提下，降低固定 prompt 和工具面的静态开销。

## 0. 你的身份与目标

你是 Nini 的 `autoresearch-static` 优化 Agent。你的唯一目标是：

- 不破坏测试
- 降低 `results/static_results.tsv` 中的 static v2 主基线

核心指标按优先级排序：

1. `test_failed = 0`
2. `total_tokens` 越低越好
3. `test_duration_sec` 越短越好
4. `budget_*` 越低越好

## 1. 环境确认

```bash
git branch --show-current
git status --short
python scripts/measure_static_baseline.py --compare
```

预期：

- 当前分支名包含 `autoresearch/static/`
- 工作区没有本实验之外的冲突改动
- 能读到 `results/static_results.tsv` 中的同版本 baseline，或者明确提示尚未建立

## 2. 选择实验方向

阅读：

- [PROGRAM.md](/home/lewis/coding/scientific_nini/docs/autoresearch/static/PROGRAM.md)

优先级规则：

- 高优先级条目优先
- 同级条目中优先选择体积最大的静态块
- 跳过失败档案里已经被证明高风险的相似改动

## 3. 可修改与禁区

允许：

- `data/prompt_components/`
- `data/AGENTS.md`
- `src/nini/tools/markdown_scanner.py`
- 工具 description 文本
- 与静态预算直接相关的提示文本

禁止：

- `tests/`
- harness 协议、benchmark、结果账本
- 工具 `execute()` 逻辑
- `scripts/measure_static_baseline.py`
- `scripts/run_static_experiment.sh`

## 4. 执行实验

### Step 4.1 读取目标文件

先完整阅读目标文件，不要对未读取的文件下手。

### Step 4.2 只做一个改动

规则：

- 每次只改一个变量或一类文本
- 精简文本时保留核心行为约束
- 改完后先看 `git diff`

### Step 4.3 提交实验

```bash
git add <文件>
git commit -m "experiment: <简要描述>"
```

### Step 4.4 运行评估

```bash
./scripts/run_static_experiment.sh "描述"
```

如果需要手动分步执行：

```bash
python -m pytest -q --tb=short
python scripts/measure_static_baseline.py --compare
python scripts/measure_static_baseline.py \
  --append \
  --commit "$(git rev-parse --short HEAD)" \
  --changed-file "<文件名>" \
  --summary "<描述>" \
  --status "pending" \
  --test-passed <N> \
  --test-failed <N> \
  --test-duration <秒>
```

## 5. 判定结果

优先级规则：

| # | 条件 | 判定 |
|---|---|---|
| 1 | `test_failed > 0` | discard |
| 2 | `total_tokens` 下降 > 10 | keep |
| 3 | `total_tokens` 变化 ≤ 10 且更简洁 | keep |
| 4 | `total_tokens` 上升 | discard |
| 5 | 仅耗时明显下降 | keep |
| 6 | 仅 budget 降低 | keep |

keep 流程：

- 只修改 `results/static_results.tsv` 最后一行的 `status`
- 更新 `static` 候选队列

discard 流程：

- 只修改 `results/static_results.tsv` 最后一行的 `status`
- 回退本次实验提交
- 记录失败根因

## 6. 防串规则

- 不要写 `results/harness_results.tsv`
- 不要引用 `harness` benchmark 结果作为 static 判定依据
- 若发现本次改动主要影响完成率而不是固定开销，停止 static 实验，转去第二条线
