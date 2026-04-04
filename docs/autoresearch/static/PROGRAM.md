# Nini Autoresearch Static Program

核心思路：Agent 自主修改静态上下文相关文件 → 自动化评估 → keep/discard → 循环迭代。

## 角色映射

| autoresearch 概念 | Nini static 适配 |
|---|---|
| `train.py` | Agent 修改 prompt 组件、description、静态预算相关文本 |
| `uv run train.py` | `./scripts/run_static_experiment.sh "描述"` |
| `val_bpb` | `total_tokens`（最坏 full prompt + 最坏主 Agent 可见工具面） |
| `prepare.py` | `scripts/measure_static_baseline.py` |
| `results.tsv` | `results/static_results.tsv` |

## 指标版本

- `legacy_v1`：旧口径，单一 prompt 场景 + 注册表原始 14 工具 schema。
- `nini_runtime_v2`：当前口径，多场景 prompt 明细 + 主 Agent 真实可见工具面。
- 只与 `results/static_results.tsv` 中同 `metric_version` 的 `keep` 记录比较。

## Setup

```bash
git checkout -b autoresearch/static/<tag>
./scripts/run_static_experiment.sh "baseline"
```

## 可修改文件

| 实验类型 | 可改文件 | 关键指标 |
|---|---|---|
| Prompt 精简 | `data/prompt_components/strategy_*.md` | prompt_tokens |
| Prompt 精简 | `data/AGENTS.md` | prompt_tokens |
| 策略常量 | `src/nini/agent/prompt_policy.py` 的静态预算与文本块 | budget_* |
| 压缩提示 | `src/nini/memory/compression.py` 的 `_LLM_SUMMARY_PROMPT` | prompt_tokens |
| 工具描述 | 各 tool 的 description 字段 | tool_schema_tokens |
| 技能快照来源 | `src/nini/tools/markdown_scanner.py` / 技能元数据 | prompt_tokens |

## 只读文件

- `tests/` 下所有测试文件
- `scripts/measure_baseline.py`
- `scripts/measure_static_baseline.py`
- `scripts/run_experiment.sh`
- `scripts/run_static_experiment.sh`
- `results/harness_results.tsv`
- harness benchmark 与 harness 协议文件
- `src/nini/tools/` 下工具逻辑实现

## 实验循环

```
LOOP:
  1. git status && git diff --stat
  2. 从候选队列选一个方向
  3. 只改一个变量或一类文本
  4. git add <文件> && git commit -m "experiment: 描述"
  5. ./scripts/run_static_experiment.sh "描述"
  6. 判定：
     - keep -> 修改 results/static_results.tsv 最后一行 status=keep
     - discard -> 修改 results/static_results.tsv 最后一行 status=discard
  7. 记录教训
  8. 继续
```

## 判定标准

| 条件 | 判定 |
|---|---|
| `test_failed > 0` | 必须 discard |
| `total_tokens` 下降 > 10 | keep |
| `total_tokens` 变化 ≤ 10 且代码更简洁 | keep |
| `total_tokens` 上升 | discard |
| `test_duration_sec` 下降 > 5% 且其他持平 | keep |
| 仅 `budget_*` 降低 | keep |

## v2 指标说明

- `prompt_tokens`：`analysis_full/report_full/literature_full` 的最坏值。
- `tool_schema_tokens`：`profile/analysis/export` 三个可见工具面的最坏值。
- `total_tokens = prompt_tokens + tool_schema_tokens`。

## 实验候选队列

### 高优先级

- [ ] 控制 `SKILLS_SNAPSHOT` 体积
- [ ] 精简 `data/AGENTS.md` 与高频 trusted 指令块
- [ ] 精简 `strategy_report.md`

### 中优先级

- [ ] 继续清理低价值 prompt 重复段落
- [ ] 审核剩余工具 description 的冗余措辞

### 低优先级

- [ ] 进一步压缩静态预算常量
- [ ] 评估压缩提示模板的冗余文本

## 已知失败教训

| 实验 | 改动 | 失败原因 | 教训 |
|---|---|---|---|
| exp1 | 精简 strategy_core.md -512 tokens | test_failed 6→7 | 不能删除标准分析流程与工具优先级规则 |
| exp2 | 精简 search_tools description -87 tokens | test_failed 6→7 | 被测试断言依赖的 description 不能随意改措辞 |

## 重要约束

- 单次实验只改一个变量。
- 不要写入 `results/harness_results.tsv`。
- 不要用 `harness` 指标为 `static` 实验判定 keep/discard。
- 若改动触碰 `harness` 白名单文件，必须转去第二条线重新立项。
