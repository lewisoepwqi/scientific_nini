# Nini Autoresearch — 自动优化 Nini Agent 质量

核心思路：Agent 自主修改代码 → 自动化评估 → keep/discard → 循环迭代。

## 角色映射

| autoresearch 概念 | Nini 适配 |
|---|---|
| `train.py` | Agent 修改 strategy_*.md / prompt_policy.py / .env 超参 |
| `uv run train.py` | `./scripts/run_experiment.sh "描述"` |
| `val_bpb` | `total_tokens`（prompt_tokens + tool_schema_tokens）复合指标 |
| `prepare.py` | `scripts/measure_baseline.py`（只读评估脚本） |
| `results.tsv` | 宽表实验日志（每实验一行，含所有指标） |

## Setup

```bash
git checkout -b autoresearch/apr3    # 从 main 创建实验分支
./scripts/run_experiment.sh "baseline"  # 运行 baseline 采集
```

## 可修改文件（每次只改一类）

| 实验类型 | 可改文件 | 关键指标 |
|---|---|---|
| Prompt 精简 | `data/prompt_components/strategy_*.md` | prompt_tokens |
| 超参调优 | `.env` 中 `NINI_LLM_TEMPERATURE` / `MAX_TOKENS` / `AUTO_COMPRESS_THRESHOLD_TOKENS` | prompt_tokens |
| 策略常量 | `src/nini/agent/prompt_policy.py` 的优先级和预算常量 | budget_* |
| 循环阈值 | `src/nini/agent/loop_guard.py` 的阈值 | test_duration_sec |
| 压缩提示 | `src/nini/memory/compression.py` 的 `_LLM_SUMMARY_PROMPT` | prompt_tokens |
| 工具描述 | 各 tool 的 description 字段（不改逻辑） | tool_schema_tokens |

## 只读文件（绝不允许修改）

- `tests/` 下所有测试文件（回归基准）
- `scripts/measure_baseline.py`（评估脚本本身）
- `scripts/run_experiment.sh`（自动化流水线）
- `src/nini/config.py` 的字段定义（可改 .env 的值，不改字段）
- `src/nini/tools/` 下的工具逻辑（描述可改，实现不可改）

## 实验循环

```
LOOP FOREVER:
  1. git status && git diff --stat    # 确认干净状态
  2. 从「实验候选队列」选一个方向
  3. 修改对应文件（**只改一个变量/策略**）
  4. git add <文件> && git commit -m "experiment: 描述"
  5. ./scripts/run_experiment.sh "描述"
  6. 判定结果：
     - keep  → 编辑 results.tsv 最后一行 status=keep，继续
     - discard → 编辑 results.tsv 最后一行 status=discard
                 git reset --soft HEAD~1 && git checkout -- <文件>
  7. 记录教训到「失败实验档案」（下方）
  8. 继续下一个实验
```

## 判定标准（量化门槛）

| 条件 | 判定 |
|---|---|
| test_failed > 0 | **必须 discard**，无论指标多好 |
| total_tokens 下降 > 10 且 test_failed = 0 | **keep** |
| total_tokens 下降 ≤ 10 但代码更简洁 | **keep**（simplicity 收益） |
| total_tokens 上升 | **discard**（除非有明确的质量收益且有数据证明） |
| test_duration_sec 下降 > 5% 且其他持平 | **keep** |
| 仅 budget 降低，其他不变 | **keep**（节省运行时内存） |

**Simplicity criterion**：
- 删除冗余段落且指标不变 → 值得（枯燥但有价值）
- 微小 token 降低需要 hacky 代码 → 不值得
- 精简文本带来的任何 token 降低 → 值得

## 实验候选队列

按优先级排列，完成一个划掉一个：

### 高优先级（token 收益大）
- [ ] 精简 `strategy_core.md`（3903 字符，最大的 strategy 文件）—— 注意 exp1 失败因过度删减
- [ ] 精简 `strategy_task.md`（2635 字符）中的 PDCA_DETAIL_BLOCK 冗余示例
- [ ] 合并 `prompt_policy.py` 中 PDCA_DETAIL_BLOCK 的重复错误示例

### 中优先级（稳定收益）
- [ ] 精简 `strategy_sandbox.md`（2240 字符）的沙箱规则
- [ ] 精简 `strategy_visualization.md`（1987 字符）
- [ ] 精简 `strategy_report.md`（2235 字符）
- [ ] 优化工具 description 减少 tool_schema_tokens —— 注意 exp2 失败因测试依赖具体措辞

### 低优先级（实验性）
- [ ] 降低 `budget_standard` 20K→15K
- [ ] 降低 `budget_compact` 10K→8K
- [ ] 调整 `loop_guard.py` warn_threshold 3→4
- [ ] 调整 compression.py 的 `_LLM_SUMMARY_PROMPT` 精简

## 失败实验档案

记录每次 discard 的根因，避免重复踩坑：

| 实验 | 改动 | 失败原因 | 教训 |
|---|---|---|---|
| exp1 | 精简 strategy_core.md -512 tokens | test_failed 6→7 | 不能删除"标准分析流程"和工具优先级规则，测试依赖这些行为 |
| exp2 | 精简 search_tools description -87 tokens | test_failed 6→7 | 工具 description 被测试断言匹配，不能随意改措辞 |

## 重要约束

- 每次实验只改一个变量，不要同时改多个东西
- 修改前先 `git diff` 确认改动范围
- 测试未通过则立即回退（`git reset --soft HEAD~1`），不要试图修复测试
- 回退时用 `--soft` 保留工作区，便于分析失败原因后清理
- 所有指标变化通过 `run_experiment.sh` 自动采集，不要手动填 results.tsv

**NEVER STOP.** 持续运行直到人类中断。
