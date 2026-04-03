# Autoresearch Agent 操作规程

> 本文件是 AI Agent 执行 autoresearch 实验循环的完整操作手册。
> **你（AI Agent）必须严格按照本文件的步骤执行，不得跳步、合并步骤或自行发挥。**

---

## 0. 你的身份与目标

你是 Nini 项目的自动优化 Agent。你的唯一目标是：**在不破坏任何测试的前提下，减少 Nini 的 prompt token 消耗和工具 schema 开销**。

核心指标（按重要性排序）：
1. `test_failed = 0` — 硬性约束，不可违反
2. `total_tokens`（= prompt_tokens + tool_schema_tokens）— 主优化目标，越低越好
3. `test_duration_sec` — 次优化目标，越短越好
4. `budget_*` — 辅助指标，降低可节省运行时内存

---

## 1. 环境确认（每次会话开始时执行一次）

```bash
# 确认当前在 autoresearch 分支
git branch --show-current
# 预期输出包含 "autoresearch/"，若不是则停止

# 确认工作区干净
git status --short
# 预期输出为空（untracked 文件可忽略），若有未提交改动则先处理

# 确认 baseline 存在
cat results.tsv | head -2
# 预期第二行有 status=keep 的 baseline 记录
```

**如果环境不满足以上条件，停止并询问用户。**

---

## 2. 选择实验方向

### 2.1 查阅实验候选队列

打开 `autoresearch_program.md`，找到「实验候选队列」章节，选择一个未完成（`[ ]`）的条目。

优先级规则：
- 高优先级条目优先
- 同级条目中，选字符数最大的文件（收益最大）
- 跳过「失败实验档案」中记录过的相似改动

### 2.2 查阅失败实验档案

打开 `autoresearch_program.md`，找到「失败实验档案」章节。确认你选择的方向不会重蹈覆辙。

**关键教训**：
- 不能删除 `strategy_core.md` 中的"标准分析流程"和工具调用黄金路径（exp1 教训）
- 不能修改工具 description 中被测试断言匹配的措辞（exp2 教训）

### 2.3 确定本次实验的精确改动

在动手之前，明确写出：
1. 要改哪个文件
2. 要改哪些行/段落
3. 改完预期 token 变化方向
4. 为什么这个改动不会破坏测试

---

## 3. 可修改文件清单与禁区

### 可修改（每次只改一类）

| 实验类型 | 文件路径 | 改什么 |
|---|---|---|
| Prompt 精简 | `data/prompt_components/strategy_core.md` | 删除冗余示例/重复段落 |
| Prompt 精简 | `data/prompt_components/strategy_task.md` | 精简 PDCA 说明 |
| Prompt 精简 | `data/prompt_components/strategy_sandbox.md` | 精简沙箱规则 |
| Prompt 精简 | `data/prompt_components/strategy_visualization.md` | 精简可视化指引 |
| Prompt 精简 | `data/prompt_components/strategy_report.md` | 精简报告指引 |
| Prompt 精简 | `data/prompt_components/strategy_phases.md` | 精简阶段策略 |
| 策略常量 | `src/nini/agent/prompt_policy.py` | 修改预算常量值 |
| 策略常量 | `src/nini/agent/prompt_policy.py` | 精简 PDCA_DETAIL_BLOCK 文本 |
| 循环阈值 | `src/nini/agent/loop_guard.py` | 调整 warn/hard_limit 阈值 |
| 压缩提示 | `src/nini/memory/compression.py` | 精简 _LLM_SUMMARY_PROMPT |
| 工具描述 | `src/nini/tools/*.py` 的 description | 精简描述文本（不改逻辑） |
| 超参 | `.env` | 调整 NINI_LLM_* 参数 |

### 绝对禁止修改

- `tests/` 下任何文件
- `scripts/measure_baseline.py`
- `scripts/run_experiment.sh`
- `src/nini/config.py` 的字段定义
- `src/nini/tools/*.py` 的 `execute()` 方法和函数逻辑
- `results.tsv` 的历史行（只能追加或修改最后一行的 status）

---

## 4. 执行实验（逐步操作）

### Step 4.1：读取当前文件

```bash
# 读取目标文件，理解当前内容
cat <目标文件>
```

**要求**：在修改前，你必须先完整阅读目标文件。不要对未读取的文件做修改。

### Step 4.2：执行修改

规则：
- **每次只改一个变量/策略**，不要同时改多处
- 精简文本时，保留核心语义，删除重复/冗余/示例过多的部分
- 修改常量时，只改值，不改变量名或类型
- 改完后用 `git diff` 确认改动范围

```bash
# 确认改动范围
git diff
# 检查：改动是否仅限于一个文件？是否只改了预期的部分？
```

### Step 4.3：提交实验

```bash
git add <修改的文件>
git commit -m "experiment: <简要描述>"
```

commit message 格式要求：
- 前缀固定为 `experiment:`
- 描述要包含：改了什么、预期效果
- 示例：`experiment: 精简 strategy_core.md 删除重复的方法选择表`, `experiment: 降低 budget_standard 20K→15K`

### Step 4.4：运行评估

```bash
./scripts/run_experiment.sh "描述"
```

**注意**：此脚本会自动完成以下所有步骤，你不需要手动做：
1. 运行 pytest（门控）
2. 运行 measure_baseline.py（采集指标）
3. 与上次 keep 记录对比（输出 delta）
4. 追加结果到 results.tsv（status=pending 或 discard）

如果你无法执行 shell 脚本（例如权限问题），可以手动分步执行：

```bash
# 手动分步执行（仅当脚本不可用时）
# Step A: pytest 门控
python -m pytest -q --tb=short 2>&1 | tail -5
# 记录 passed/failed 数量

# Step B: 采集指标并对比
python scripts/measure_baseline.py --compare

# Step C: 追加到 results.tsv（根据结果填入参数）
python scripts/measure_baseline.py \
    --append \
    --commit "$(git rev-parse --short HEAD)" \
    --changed-file "<文件名>" \
    --summary "<描述>" \
    --status "pending" \
    --test-passed <N> \
    --test-failed <N> \
    --test-duration <秒>
```

---

## 5. 判定结果

### 5.1 读取评估输出

从 `run_experiment.sh` 或 `measure_baseline.py --compare` 的输出中找到：

```
--- delta vs last keep ---
  prompt_tokens: 6561 → XXXX  (↑/↓ N, +/-X.X%)
  tool_schema_tokens: 9252 → XXXX  (↑/↓ N, +/-X.X%)
  total_tokens: 15813 → XXXX  (↑/↓ N, +/-X.X%)
```

### 5.2 应用判定规则

按以下优先级判定（从上到下，命中第一条即停止）：

| # | 条件 | 判定 | 操作 |
|---|---|---|---|
| 1 | `test_failed > 0` | **discard** | 必须回退 |
| 2 | `total_tokens` 下降 > 10 | **keep** | 保留并继续 |
| 3 | `total_tokens` 变化 ≤ 10 且代码更简洁 | **keep** | simplicity 收益 |
| 4 | `total_tokens` 上升 | **discard** | 回退 |
| 5 | 仅 `test_duration_sec` 下降 > 5% | **keep** | 速度收益 |
| 6 | 仅 `budget_*` 降低 | **keep** | 内存收益 |

### 5.3 执行 keep 流程

```bash
# 1. 修改 results.tsv 最后一行的 status 字段为 "keep"
# （用编辑器或 sed，确保只改最后一行的 status 字段）

# 2. 更新实验候选队列：将完成的条目标记为 [x]
# 编辑 autoresearch_program.md

# 3. 继续下一个实验（回到 Step 2）
```

### 5.4 执行 discard 流程

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

当前 baseline（最后一条 keep 记录）：

| 指标 | 值 | 含义 |
|---|---|---|
| prompt_tokens | 6561 | system prompt 消耗的 token 数 |
| tool_schema_tokens | 9252 | 工具定义（14 个工具）消耗的 token 数 |
| total_tokens | 15813 | 每次 API 调用的固定开销 |
| test_passed | 2010 | 通过的测试数 |
| test_duration_sec | 126.7 | 测试运行耗时 |
| budget_full | 40000→35000 | full profile 运行时上下文预算（字符） |
| budget_standard | 20000 | standard profile 运行时上下文预算 |
| budget_compact | 10000 | compact profile 运行时上下文预算 |

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
