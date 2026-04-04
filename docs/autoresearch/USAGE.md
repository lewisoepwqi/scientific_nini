# Nini Autoresearch 使用说明

> 本文档是两条 `autoresearch` 线的操作手册。
> 目标是让你可以直接照着命令执行，并知道什么时候用哪一条线。

## 1. 先理解两条线

Nini 当前有两条独立实验线：

- `static`：优化固定上下文开销
- `harness`：优化真实任务表现

一句话区分：

- 如果你想压 prompt、压工具 schema、压固定预算，用 `static`
- 如果你想提高任务完成率、降低阻塞、降低失败率，用 `harness`

它们的入口、baseline、结果账本、判定逻辑都独立，不能混用。

## 2. 当前 baseline 状态

当前仓库里已经有正式 baseline，不需要从零初始化。

`static` 当前主 baseline：

- `metric_version = nini_runtime_v2`
- 记录位置：[static_results.tsv](/home/lewis/coding/scientific_nini/results/static_results.tsv)
- 当前 `keep`：`prompt_tokens=7501`、`tool_schema_tokens=4726`、`total_tokens=12227`

`harness` 当前主 baseline：

- `metric_version = nini_harness_v1`
- `benchmark_set = smoke`
- 记录位置：[harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)
- 当前 `keep`：`pass_count=3`、`blocked_count=0`、`failure_count=0`、`pass_rate=1.0`

## 3. 使用前的硬规则

1. 一个实验分支只能属于一条线。
2. 一次实验只改一个方向，不要混改。
3. `static` 不看 `harness` 指标判定。
4. `harness` 不看 `static` token 指标判定。
5. 结果只写本线账本：
   - `static` 写 [static_results.tsv](/home/lewis/coding/scientific_nini/results/static_results.tsv)
   - `harness` 写 [harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)

推荐分支命名：

- `autoresearch/static/<tag>`
- `autoresearch/harness/<tag>`

## 4. 第一条线：`static`

### 4.1 适用场景

适合这类问题：

- `SKILLS_SNAPSHOT` 太大
- system prompt 太长
- 某些工具 description 过于冗长
- 固定预算文本过于重复

不适合这类问题：

- 任务完成率低
- 会话容易阻塞
- 工具选择策略差
- 恢复策略不好

### 4.2 常用命令

查看当前基线与 delta：

```bash
python scripts/measure_static_baseline.py --compare
```

执行一次完整 static 实验：

```bash
./scripts/run_static_experiment.sh "描述"
```

### 4.3 标准流程

1. 建分支

```bash
git checkout -b autoresearch/static/<tag>
```

2. 看当前 baseline

```bash
python scripts/measure_static_baseline.py --compare
```

3. 只修改 `static` 白名单文件

常见区域：

- `data/prompt_components/`
- `data/AGENTS.md`
- `src/nini/tools/markdown_scanner.py`
- 工具 description 文本
- 与静态预算直接相关的提示文本

4. 提交实验

```bash
git add <文件>
git commit -m "experiment: <描述>"
```

5. 运行实验

```bash
./scripts/run_static_experiment.sh "<描述>"
```

6. 读取输出

重点看：

- `prompt_tokens`
- `tool_schema_tokens`
- `total_tokens`
- `test_failed`
- `suggestion`

7. 手工确认状态

打开 [static_results.tsv](/home/lewis/coding/scientific_nini/results/static_results.tsv)，把最后一行 `status` 改成：

- `keep`
- `discard`
- 或保留 `pending`

### 4.4 判定规则

优先级：

1. `test_failed > 0`：直接 `discard`
2. `total_tokens` 下降：通常 `keep`
3. `total_tokens` 上升：通常 `discard`
4. 变化很小但更简洁：可 `keep`

### 4.5 使用案例 1：压缩 `SKILLS_SNAPSHOT`

场景：

- 你发现 prompt 最大头来自技能快照

流程：

```bash
git checkout -b autoresearch/static/skills-snapshot-trim
python scripts/measure_static_baseline.py --compare
```

修改：

- [markdown_scanner.py](/home/lewis/coding/scientific_nini/src/nini/tools/markdown_scanner.py)

提交并运行：

```bash
git add src/nini/tools/markdown_scanner.py
git commit -m "experiment: trim skills snapshot metadata"
./scripts/run_static_experiment.sh "trim skills snapshot metadata"
```

判断：

- 如果 `total_tokens` 明显下降且测试全过，把最后一行改成 `keep`
- 如果测试失败或 `total_tokens` 反而上升，改成 `discard`

### 4.6 使用案例 2：精简工具 description

场景：

- 你怀疑 tool schema 太胖

流程：

```bash
git checkout -b autoresearch/static/shorter-tool-description
python scripts/measure_static_baseline.py --compare
```

修改：

- 某个工具的 description 文本

运行：

```bash
git add <工具文件>
git commit -m "experiment: shorten tool description"
./scripts/run_static_experiment.sh "shorten tool description"
```

判断：

- 看 `tool_schema_tokens` 和 `total_tokens`
- 不要顺手改工具执行逻辑

## 5. 第二条线：`harness`

### 5.1 适用场景

适合这类问题：

- deep task 做不完
- 容易 `blocked`
- completion check 误判
- tool exposure 不合理
- runtime context 太差
- 恢复策略太弱

不适合这类问题：

- 单纯压 prompt 成本
- 单纯压工具 schema

### 5.2 当前 benchmark

当前 `smoke` benchmark 固定包含 3 个 core recipe：

- `literature_review`
- `experiment_plan`
- `results_interpretation`

定义在 [harness_benchmarks.yaml](/home/lewis/coding/scientific_nini/data/autoresearch/harness_benchmarks.yaml)。

### 5.3 常用命令

自动跑 benchmark：

```bash
python scripts/run_harness_benchmarks.py --benchmark-set smoke
```

对已有 session 做评估：

```bash
python scripts/measure_harness_baseline.py --session-id <session_id> --benchmark-set smoke --compare
```

一键跑完整实验：

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "描述"
```

指定 provider / model：

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "描述" --provider dashscope --model glm-5
```

指定单 case 超时：

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "描述" --case-timeout 240
```

### 5.4 标准流程

1. 建分支

```bash
git checkout -b autoresearch/harness/<tag>
```

2. 只修改 `harness` 白名单文件

当前主要是：

- [prompt_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/prompt_policy.py)
- [context_tools.py](/home/lewis/coding/scientific_nini/src/nini/agent/components/context_tools.py)
- [tool_exposure_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/tool_exposure_policy.py)
- [config.py](/home/lewis/coding/scientific_nini/src/nini/config.py)
- 必要时可涉及 [runner.py](/home/lewis/coding/scientific_nini/src/nini/harness/runner.py) 这类 Harness 运行护栏，但应非常克制

3. 提交实验

```bash
git add <文件>
git commit -m "experiment: <描述>"
```

4. 执行完整实验

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "<描述>"
```

5. 读取输出

重点看：

- `pass_count`
- `blocked_count`
- `failure_count`
- `pass_rate`
- `blocked_rate`
- `median_cost_usd`
- `median_duration_s`
- `prompt_truncation_rate`
- `suggestion`

6. 手工确认状态

打开 [harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)，把最后一行 `status` 改成：

- `keep`
- `discard`
- 或保留 `pending`

### 5.5 判定规则

先看门槛：

- `pass_rate >= baseline`
- `blocked_rate <= baseline`
- 没有新的严重 failure tag
- `prompt_truncation_mismatch=false`

再看优先级：

1. 更高 `pass_count`
2. 更低 `blocked_count`
3. 更低 `failure_count`
4. 更低 `median_cost_usd`
5. 更低 `median_duration_s`
6. 更低 `median_input_tokens + median_output_tokens`

### 5.6 使用案例 1：修复 deep task 阻塞

场景：

- `experiment_plan` 经常 `blocked`
- 你怀疑是工具暴露面不对

流程：

```bash
git checkout -b autoresearch/harness/fix-experiment-plan-surface
```

修改：

- [tool_exposure_policy.py](/home/lewis/coding/scientific_nini/src/nini/agent/tool_exposure_policy.py)

运行：

```bash
git add src/nini/agent/tool_exposure_policy.py
git commit -m "experiment: allow analysis surface for recipe tool hints"
./scripts/run_harness_experiment.sh --auto-run smoke "allow analysis surface for recipe tool hints"
```

判断：

- 看 `experiment_plan` 是否从 `blocked/error` 变为 `completed`
- 看整体 `pass_rate` 是否上升

### 5.7 使用案例 2：修复 completion 误判

场景：

- 模型已经给出完整结果，但 Harness 误判成未完成

流程：

```bash
git checkout -b autoresearch/harness/fix-completion-check
```

修改：

- [runner.py](/home/lewis/coding/scientific_nini/src/nini/harness/runner.py)

运行：

```bash
git add src/nini/harness/runner.py
git commit -m "experiment: relax substantive completion detection"
./scripts/run_harness_experiment.sh --auto-run smoke "relax substantive completion detection"
```

判断：

- `blocked_count` 是否下降
- 是否出现新的 `failure_tags`

### 5.8 使用案例 3：调整预算阈值

场景：

- 你怀疑 deep task 预算过紧，导致过早中断

流程：

```bash
git checkout -b autoresearch/harness/raise-deep-budget
```

修改：

- [config.py](/home/lewis/coding/scientific_nini/src/nini/config.py)

运行：

```bash
git add src/nini/config.py
git commit -m "experiment: tune deep task budget"
./scripts/run_harness_experiment.sh --auto-run smoke "tune deep task budget"
```

判断：

- `pass_rate` 是否提高
- `blocked_rate` 是否降低
- `median_cost_usd` 是否可接受

## 6. 两条线怎么配合

推荐顺序：

1. 先跑 `static`
2. 再跑 `harness`

原因：

- `static` 先压固定开销
- `harness` 再验证真实任务表现是否提升或至少不退化

不要反过来做推断：

- `static` 变好，不代表 `harness` 一定变好
- `harness` 变好，也不代表 `static` 成本一定下降

## 7. 推荐的实际工作流

### 7.1 当你怀疑“上下文太胖”

```bash
git checkout -b autoresearch/static/<tag>
python scripts/measure_static_baseline.py --compare
# 修改 prompt / skills snapshot / tool description
git commit -am "experiment: <描述>"
./scripts/run_static_experiment.sh "<描述>"
```

### 7.2 当你怀疑“任务做不完”

```bash
git checkout -b autoresearch/harness/<tag>
# 修改 runtime context / tool exposure / budget / recovery
git commit -am "experiment: <描述>"
./scripts/run_harness_experiment.sh --auto-run smoke "<描述>"
```

## 8. 结果表怎么读

`static` 看 [static_results.tsv](/home/lewis/coding/scientific_nini/results/static_results.tsv)：

- `prompt_tokens`
- `tool_schema_tokens`
- `total_tokens`
- `test_passed`
- `test_failed`
- `test_duration_sec`
- `status`

`harness` 看 [harness_results.tsv](/home/lewis/coding/scientific_nini/results/harness_results.tsv)：

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
- `prompt_truncation_rate`
- `status`

## 9. `"描述"` 应该怎么写

命令里的 `"描述"` 不是装饰文本，它会直接写进结果账本：

- `static` 写入 `summary`
- `harness` 写入 `change_summary`

它的目的只有一个：

- 让你以后回看账本时，能立刻知道这次改了什么、为什么改、想验证什么

推荐格式：

```text
<改哪里> + <怎么改> + <希望改善什么>
```

或者：

```text
<目标问题> -> <改动手段> -> <预期结果>
```

### 9.1 `static` 的描述模板

`static` 关注固定开销，所以描述应偏向：

- 精简
- 压缩
- 去重
- 裁剪

推荐模板：

```text
精简 <对象> 以降低 prompt_tokens
压缩 <对象> 以降低 tool_schema_tokens
去重 <对象> 以降低 total_tokens
```

可直接照抄的例子：

```bash
./scripts/run_static_experiment.sh "精简 skills snapshot 元数据以降低 prompt_tokens"
./scripts/run_static_experiment.sh "压缩 analysis tools description 以降低 tool_schema_tokens"
./scripts/run_static_experiment.sh "去重 strategy 重复说明以降低 total_tokens"
```

也可以写成英文：

```bash
./scripts/run_static_experiment.sh "trim skills snapshot metadata to reduce prompt_tokens"
./scripts/run_static_experiment.sh "shorten analysis tool descriptions to reduce tool_schema_tokens"
```

### 9.2 `harness` 的描述模板

`harness` 关注真实任务表现，所以描述应偏向：

- 修复阻塞
- 调整策略
- 提升完成率
- 降低失败率

推荐模板：

```text
修复 <行为问题> 以降低 blocked_rate
调整 <策略点> 以提升 pass_rate
放宽/收紧 <判定逻辑> 以减少 failure_count
```

可直接照抄的例子：

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "放宽完成判定以减少 blocked"
./scripts/run_harness_experiment.sh --auto-run smoke "为 recipe tool hint 开启 analysis surface 以提升 pass_rate"
./scripts/run_harness_experiment.sh --auto-run smoke "调整 deep task 预算以降低 blocked_rate"
```

也可以写成英文：

```bash
./scripts/run_harness_experiment.sh --auto-run smoke "relax completion check to reduce blocking"
./scripts/run_harness_experiment.sh --auto-run smoke "enable analysis surface for recipe tool hints to improve pass_rate"
```

### 9.3 不推荐的写法

不要写得过空：

```text
fix bug
优化一下
实验
try again
misc changes
```

也不要把多个实验混在一句里：

```text
压 prompt + 改工具暴露 + 调预算 + 修 completion
```

这种写法会让你后面无法判断收益来自哪里。

### 9.4 实用规则

如果你不确定怎么写，就按这条规则：

- `static`：`改哪块 + 降哪个 token 指标`
- `harness`：`修哪种行为 + 改善哪个任务指标`

一句话标准：

- 如果两周后你只看这条描述，仍然知道“改了什么”和“想验证什么”，这条描述就合格。

## 10. 常见错误

- 在 `static` 分支顺手改 runtime 策略
- 在 `harness` 分支顺手改静态 prompt 文本
- 跑完实验后忘记把最后一行从 `pending` 改成 `keep/discard`
- 继续使用旧的根目录 `results.tsv`
- 把一次偶然 benchmark 好结果当成稳定收益

## 11. 当前需要特别注意的点

第二条线现在已经可正式使用，但当前 `smoke` baseline 是在 **prompt 截断发生** 的条件下建立的：

- `prompt_truncation_rate = 1.0`

这不影响第二条线正常 compare，但说明第一条 `static` 线仍然有持续价值：继续压 prompt，减少截断。

## 12. 最常用的两条命令

日常最常用的就是这两条：

```bash
./scripts/run_static_experiment.sh "<描述>"
./scripts/run_harness_experiment.sh --auto-run smoke "<描述>"
```

如果你不确定该选哪条线：

- 先问自己：我要优化的是“固定成本”，还是“真实完成表现”。
- 前者选 `static`
- 后者选 `harness`
