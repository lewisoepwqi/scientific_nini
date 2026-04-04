# Autoresearch Agent 操作规程（兼容入口）

根目录协议文件已拆分为双线管理：

- 第一条 `static`：见 [docs/autoresearch/static/AGENT_PROTOCOL.md](/home/lewis/coding/scientific_nini/docs/autoresearch/static/AGENT_PROTOCOL.md)
- 第二条 `harness`：见 [docs/autoresearch/harness/PROTOCOL.md](/home/lewis/coding/scientific_nini/docs/autoresearch/harness/PROTOCOL.md)

使用规则：

- 优化 prompt / tool surface / 固定开销时，只使用 `static` 协议。
- 优化 benchmark 完成率 / 阻塞率 / 成本耗时时，只使用 `harness` 协议。
- 禁止在一个实验里同时跨两条线。

兼容说明：

- 旧入口 `python scripts/measure_baseline.py` 仍可用，但等价于 `python scripts/measure_static_baseline.py`
- 旧入口 `./scripts/run_experiment.sh` 仍可用，但等价于 `./scripts/run_static_experiment.sh`
- 第一条线结果账本已迁到 `results/static_results.tsv`

```bash
# 1. 修改 results.tsv 最后一行的 status 字段为 "discard"

# 2. 回退代码
git reset --soft HEAD~1
git checkout -- <修改的文件>

# 3. 记录教训到「失败实验档案」
# 编辑 autoresearch_program.md，在「失败实验档案」表格追加一行：
# | expN | 改了什么 | 为什么失败 | 下次要避免什么 |

# 4. 继续下一个实验（回到 Step 2）
```

**重要**：回退用 `git reset --soft`（不是 `--hard`），保留工作区方便分析。回退后再 `git checkout -- <文件>` 丢弃文件改动。

---

## 6. 指标参考值

当前 baseline（仅比较同 `metric_version=nini_runtime_v2` 的 keep 记录）：

| 指标 | 值 | 含义 |
|---|---|---|
| prompt_tokens | 以脚本实测为准 | 三类 full prompt 场景中的最坏 token 数 |
| tool_schema_tokens | 以脚本实测为准 | 三种主 Agent 可见工具面中的最坏 token 数 |
| total_tokens | 以脚本实测为准 | v2 主基线固定开销 |
| test_passed | 2010 | 通过的测试数 |
| test_duration_sec | 126.7 | 测试运行耗时 |
| budget_full | 40000→35000 | full profile 运行时上下文预算（字符） |
| budget_standard | 20000 | standard profile 运行时上下文预算 |
| budget_compact | 10000 | compact profile 运行时上下文预算 |

### v2 观察重点

- `SKILLS_SNAPSHOT` 常常是当前 prompt 中最大的单块，优先检查冗余元数据与重复描述。
- `data/AGENTS.md` 进入 trusted boundary，会直接推高 full prompt。
- 工具 description 优化要优先看 `analysis` 工具面；不要再以“注册表原始 14 工具”作为唯一依据。

### Token 分布

prompt 组件大小分布（字符数，大的优化空间最大）：

```
strategy_core.md          3903  ████████████████████  (最大，高优先级精简目标)
strategy_task.md          2635  █████████████
strategy_phases.md        2424  ████████████
strategy_sandbox.md       2240  ███████████
strategy_report.md        2235  ███████████
strategy_visualization.md 1987  ██████████
security.md                703  ████
identity.md                632  ███
agents.md                  546  ███
workflow.md                359  ██
user.md                     88  ▏
memory.md                   58  ▏
```

另外 `prompt_policy.py` 中的 `PDCA_DETAIL_BLOCK` 是一个巨大的字符串常量（~2200 字符），在 DOMAIN_TASK 意图时条件注入到运行时上下文。

---

## 7. 常见陷阱（必读）

### 陷阱 1：删除了测试依赖的行为描述
`strategy_core.md` 中的"标准分析流程"和"工具调用黄金路径"被多个测试断言所依赖。精简此文件时，只能删除重复的示例和冗余说明，不能改变核心行为指令。

**安全做法**：先跑 `grep -r "标准分析流程\|黄金路径\|dataset_catalog\|stat_test" tests/` 看哪些测试引用了这些关键词。

### 陷阱 2：工具 description 被测试直接匹配
工具的 `description` 字符串出现在 `get_tool_definitions()` 返回中，某些测试会断言这些字符串的内容。

**安全做法**：修改工具 description 前，先 `grep -r "description.*工具名" tests/` 确认没有测试直接匹配。

### 陷阱 3：一次改多个变量
如果同时改了 strategy_core.md 和 prompt_policy.py，测试失败时无法定位是哪个改动导致的。

**铁律**：每次实验只改一个文件中的一类内容。

### 陷阱 4：精简过度导致语义丢失
中文文本的每个字符约 1.5 token。删除 100 个中文字符约节省 150 token。但如果删除的内容包含了 LLM 需要遵循的指令，会导致 Agent 行为退化（测试虽可能通过，但真实使用时质量下降）。

**安全做法**：只删除明显重复的段落、过多的示例、格式性装饰文本。保留所有"必须"、"禁止"、"规则"类指令。

### 陷阱 5：忽略条件注入机制
`strategy_visualization.md`、`strategy_report.md`、`strategy_phases.md` 是条件加载组件，只在 intent_hints 匹配时才加入 prompt。`measure_baseline.py` 固定传入 `{"chart", "stat_test"}`，所以测量时会加载 `strategy_visualization.md` 但不加载另外两个。

**影响**：精简 `strategy_report.md` 和 `strategy_phases.md` 不会影响 baseline 测量的 prompt_tokens，但仍然值得做（运行时收益）。

---

## 8. 完整实验示例

### 示例：精简 strategy_task.md 中的冗余说明

```
Step 1: 读取文件
> cat data/prompt_components/strategy_task.md
（发现"task_state 调用示例"段落出现了两次类似的 JSON 示例）

Step 2: 执行修改
> 删除第二个重复的 JSON 示例段落（约 200 字符）

Step 3: 确认改动
> git diff
  data/prompt_components/strategy_task.md | 8 --------
  1 file changed, 8 deletions(-)

Step 4: 提交
> git add data/prompt_components/strategy_task.md
> git commit -m "experiment: 精简 strategy_task.md 删除重复的 task_state JSON 示例"

Step 5: 运行评估
> ./scripts/run_experiment.sh "精简 strategy_task.md 删除重复示例"
  pytest: passed=2010 failed=0 duration=125.3s exit=0
  --- delta vs last keep ---
    prompt_tokens: 6561 → 6480  (↓ 81, -1.2%)
    tool_schema_tokens: 9252 → 9252  (= 0, +0.0%)
    total_tokens: 15813 → 15732  (↓ 81, -0.5%)
  💡 建议: total_tokens 下降，若测试全通过则 keep

Step 6: 判定
  test_failed = 0 ✓
  total_tokens 下降 81 > 10 → keep ✓

Step 7: 执行 keep 流程
> 修改 results.tsv 最后一行 status → keep
> 标记 autoresearch_program.md 实验候选队列对应条目为 [x]

Step 8: 继续下一个实验
```

---

## 9. 循环状态检查

每完成 5 次实验后（无论 keep 或 discard），执行一次状态检查：

```bash
# 查看实验进展
cat results.tsv | column -t -s $'\t' | tail -10

# 查看累计改善
python scripts/measure_baseline.py --compare

# 查看剩余候选
grep '\[ \]' autoresearch_program.md
```

如果连续 3 次 discard，暂停并：
1. 重新审视失败实验档案，分析失败模式
2. 考虑切换到不同类型的实验（比如从 prompt 精简切换到常量调优）
3. 如果所有高/中优先级候选都已完成或失败，报告给用户

---

## 10. 紧急恢复

如果进入异常状态（比如 results.tsv 损坏、git 历史混乱）：

```bash
# 查看 autoresearch 分支的所有实验 commit
git log --oneline --first-parent

# 回到最后一个 keep 状态的 commit
git log --oneline | head -20
# 找到对应的 commit hash
git reset --hard <last-keep-commit>

# 重新采集 baseline
python scripts/measure_baseline.py --compare
```

**注意**：`git reset --hard` 是破坏性操作，只在紧急恢复时使用，正常 discard 请用 `--soft`。
