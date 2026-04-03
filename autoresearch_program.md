# Nini Autoresearch — 自动优化 Nini Agent 质量

这是 autoresearch 方法论在 Nini 项目上的应用。

核心思路：让 Agent 自主修改 Nini 的代码 → 茉测试/度量脚本 → keep/discard → 循环。

**三个角色（对应 autoresearch）：**

| 角色 | Nini 适配 |
|---|---|
| `train.py` → Agent 修改 `strategy_*.md` / `prompt_policy.py` / `.env` 超参 |
| `uv run train.py` → `pytest -q` + `python scripts/measure_baseline.py` |
| `val_bpb` | `prompt_tokens` + `test_pass_rate` 组合指标 |
| `prepare.py` → 评估基准（不可修改） |
| `results.tsv` | 实验日志 |

## Setup
1. 创建分支：`git checkout -b autoresearch/apr3` 从当前 main
2. 运行 baseline：`pytest -q --tb=no && python scripts/measure_baseline.py`，全部通过
3. 创建 `results.tsv`，表头： `commit  metric_name  metric_value  status  description`

## 可修改文件（每次只改一类）

- **Prompt 实验**: `data/prompt_components/strategy_core.md`, `strategy_sandbox.md`, `strategy_task.md`, `strategy_visualization.md`, `strategy_report.md`, `strategy_phases.md`
- **超参实验**: `.env` 中的 `NINI_LLM_TEMPERATURE`, `NINI_LLM_MAX_TOKENS`, `NINI_AUTO_COMPRESS_THRESHOLD_TOKENS`
- **策略实验**: `src/nini/agent/prompt_policy.py` 的优先级和预算常量
- **循环实验**: `src/nini/agent/loop_guard.py` 的阈值
- **压缩实验**: `src/nini/memory/compression.py` 的 `_LLM_SUMMARY_PROMPT`

## 只读文件（绝不允许修改）
- `tests/` 下所有测试文件（作为回归基准）
- `scripts/measure_baseline.py`（评估脚本本身）
- `src/nini/config.py` 的字段定义（可改 .env 的值，不改字段）

- `src/nini/tools/` 下的工具实现（工具逻辑不可改，描述可改）

## 评估方法
每次实验运行：
```bash
# 1. 正确性门控：必须全部通过
pytest -q --tb=no 2>&1 | tail -1

# 2. 指标采集
python scripts/measure_baseline.py
```

输出格式（类似 val_bpb）：
```
---
prompt_tokens: 3200
tool_schema_tokens: 5100
runtime_budget_chars: 40000
test_passed: 156
test_duration_sec: 12.5
```

## 实验循环
LOOP FOREVER:
1. 查看 git 状态
2. 选择一个优化方向，修改对应文件（**只改一个变量/策略**）
3. git commit -m "experiment: 描述"
4. 运行评估：
   pytest -q --tb=no > run.log 2>&1
   python scripts/measure_baseline.py >> run.log 2>&1
5. 如果测试未全部通过 → git reset， 记录 crash， 继续
6. 读取指标：
   grep "passed" run.log
   grep -E "^(prompt_tokens|tool_schema_tokens|runtime_budget_chars):" run.log
7. 记录到 results.tsv
8. **判定标准**：
   - prompt_tokens 降低 → keep（token 消耗减少）
   - tool_schema_tokens 降低 → keep（工具调用开销减少）
   - test_pass_rate = 100% → 必须保持
   - test_duration_sec 降低 → keep（测试变快）
9. 改善 → 推进分支； 退步/持平 → git reset 回退
10. 继续下一个实验

## 重要约束
- 每次实验只改一个变量
不要同时改多个东西
- 修改前先备份当前值（git diff 确认改动范围）
- 测试未通过则立即回退，不要试图修复测试
- **Simplicity criterion**: 优化应使代码更简单而非更复杂
  - 删除冗余段落且指标不变 → 枯燥性改进
  - 0.001 prompt_tokens 减少需要 20 行 hacky代码 → 不值
  - 0.001 prompt_tokens 减少来自精简文本 → 绝对值得

NEVER STOP. 持续运行直到人类中断。
