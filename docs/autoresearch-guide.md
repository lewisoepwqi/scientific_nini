# Nini Autoresearch 指南

> 面向人类的原理解释、运行方式与学习路径。

---

## 一、为什么要做 Autoresearch

### 问题

Nini 是科研 AI 助手。每次对话时，LLM 需要处理：

```
用户消息  +  system prompt（~6500 tokens）+  工具定义（~9200 tokens）+  运行时上下文
```

这 **15,000+ tokens 是每次 API 调用的固定开销**，直接影响：
- **成本**：token 按量计费，固定开销越大，每次对话越贵
- **延迟**：LLM 处理更多 token 需要更长时间
- **上下文空间**：固定部分占用越多，留给用户对话和工具结果的空间越少

### 解法

借鉴 [autoresearch](https://github.com/jxnl/autoresearch) 的理念：**让 AI Agent 自主迭代优化自己的配置**。

核心循环：

```
修改代码/配置 → 自动评估（测试 + 指标采集）→ keep/discard → 重复
```

这个方法的精髓在于：
1. **有客观指标**：token 数是可精确测量的，不需要主观判断
2. **有安全护栏**：测试套件保证改动不破坏功能
3. **单变量控制**：每次只改一处，可追因
4. **持续积累**：每个 keep 都是净收益，100 次小优化累积成显著改善

---

## 二、架构概览

### 文件关系图

```
autoresearch_program.md          ← 方法论：实验循环规则、候选队列、失败档案
AUTORESEARCH_AGENT_PROTOCOL.md   ← Agent 操作手册：逐步指令、判定规则、陷阱
results.tsv                      ← 实验日志：每行一个实验，14 列指标
scripts/
  ├── measure_baseline.py        ← 指标采集器（纯测量，不跑测试）
  └── run_experiment.sh          ← 一键实验流水线（pytest + 采集 + 对比）
```

### 数据流

```
                    ┌─────────────────────────────────┐
                    │  Agent 或人类修改代码/配置         │
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────┐
                    │  git commit -m "experiment: ..." │
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────────┐
              │        run_experiment.sh                     │
              │  ┌──────────┐    ┌──────────────────────┐  │
              │  │  pytest   │───▶│  measure_baseline.py │  │
              │  │  (门控)   │    │  --compare --append  │  │
              │  └──────────┘    └──────────┬───────────┘  │
              └───────────────────────────────┼────────────┘
                                              │
                                              ▼
                              ┌────────────────────────────┐
                              │  results.tsv（追加一行）     │
                              │  status = pending / discard │
                              └──────────────┬─────────────┘
                                             │
                                             ▼
                              ┌────────────────────────────┐
                              │  人类/Agent 判定 keep/discard│
                              │  更新 results.tsv status    │
                              └────────────────────────────┘
```

### 可优化的维度

Nini 的 prompt 由多个 Markdown 组件装配而成，按优先级排列：

```
┌─────────────────────────────────────────────────────┐
│  identity.md (632 字符)           优先级 100 (最高)   │  ← 不可优化，核心身份
│  security.md (703 字符)           优先级 95           │  ← 不可优化，安全规则
│  strategy_core.md (3903 字符)     优先级 90           │  ← 高价值优化目标
│  strategy_task.md (2635 字符)     优先级 88           │  ← 高价值优化目标
│  strategy_sandbox.md (2240 字符)  优先级 85           │  ← 中等优化目标
│  agents.md (546 字符)             优先级 65           │
│  workflow.md (359 字符)           优先级 60           │
├─────────────────────────────────────────────────────┤
│  strategy_visualization.md (1987) 优先级 50 (条件加载) │  ← 仅图表意图时加载
│  strategy_report.md (2235)        优先级 48 (条件加载) │  ← 仅报告意图时加载
│  strategy_phases.md (2424)        优先级 45 (条件加载) │  ← 仅文献/写作意图时加载
├─────────────────────────────────────────────────────┤
│  user.md (88 字符)                优先级 30 (动态)    │
│  memory.md (58 字符)              优先级 20 (动态)    │
└─────────────────────────────────────────────────────┘

另外：prompt_policy.py 中的 PDCA_DETAIL_BLOCK (~2200 字符) 在运行时条件注入
另外：14 个工具的 JSON Schema 定义共 ~9252 tokens
```

---

## 三、快速开始

### 前置条件

```bash
pip install -e .[dev]    # 安装 Nini 及开发依赖
pip install tiktoken      # 精确 token 计数（可选，不装则用近似值）
```

### 手动运行一次完整实验

```bash
# 1. 切到实验分支
git checkout autoresearch/apr3

# 2. 确认 baseline
python scripts/measure_baseline.py --compare

# 3. 做一个小改动（例如删除 strategy_core.md 中的一个重复示例段落）
vim data/prompt_components/strategy_core.md

# 4. 提交
git add data/prompt_components/strategy_core.md
git commit -m "experiment: 精简 strategy_core.md 删除重复示例"

# 5. 运行自动化评估
./scripts/run_experiment.sh "精简 strategy_core.md 删除重复示例"

# 6. 查看输出，决定 keep 或 discard
# 看到 total_tokens 下降且 test_failed=0 → 编辑 results.tsv 最后一行 status=keep
# 看到 test_failed>0 或 total_tokens 上升 → 编辑 status=discard，然后回退：
#   git reset --soft HEAD~1 && git checkout -- data/prompt_components/strategy_core.md
```

### 让 AI Agent 自动运行

```bash
# 方法 1：在 Claude Code 中直接引用协议文件
# 告诉 Agent：
#   "请按照 AUTORESEARCH_AGENT_PROTOCOL.md 的规程，执行 autoresearch 实验循环"

# 方法 2：将 autoresearch_program.md 的内容放入 Agent 的 system prompt
# Agent 会按照「实验循环」章节自动迭代
```

---

## 四、各文件详解

### `measure_baseline.py` — 指标采集器

**职责**：测量当前代码状态下的 prompt token 开销，**不运行测试**（测试交给 run_experiment.sh）。

**工作原理**：
1. 实例化 `PromptBuilder(context_window=None)`（即 full profile）
2. 调用 `builder.build(intent_hints={"chart", "stat_test"})` 装配完整 system prompt
3. 用 tiktoken (GPT-4 编码器) 计算 token 数
4. 实例化 `create_default_tool_registry()`，将工具定义 JSON 序列化后计算 token 数
5. 读取 `prompt_policy.py` 中三档 runtime context 预算

**命令行参数**：

| 参数 | 作用 |
|---|---|
| `--compare` | 读取 results.tsv 最后一条 keep 记录，输出 delta 对比 |
| `--append` | 将当前指标追加为 results.tsv 新行 |
| `--commit <hash>` | 记录到 TSV 的 commit 列 |
| `--changed-file <path>` | 记录本次改了什么文件 |
| `--summary <text>` | 变更描述 |
| `--status <keep/discard/pending>` | 实验状态 |
| `--test-passed <N>` | pytest 通过数（由外部传入） |
| `--test-failed <N>` | pytest 失败数（由外部传入） |
| `--test-duration <sec>` | pytest 耗时（由外部传入） |

**设计决策**：为什么不在脚本内跑 pytest？
- 旧版在内部跑 pytest，但 `autoresearch_program.md` 的流程又要求先单独跑 pytest 做门控
- 这导致测试跑两遍，浪费 2 分钟
- 新版分离职责：`run_experiment.sh` 负责 pytest，`measure_baseline.py` 纯采集

### `run_experiment.sh` — 一键实验流水线

**流程**：

```
Step 1: pytest -q --tb=short
  ├── 失败 → 采集指标 + 标记 discard + exit 1
  └── 通过 → 继续
Step 2: measure_baseline.py --compare --append
  → 输出指标 + delta 对比 + 追加 results.tsv (status=pending)
Step 3: 输出建议
  → 人类/Agent 手动将 status 改为 keep 或 discard
```

**自动检测**：脚本会自动从 `git diff --name-only HEAD~1` 提取改动文件名，从 `git rev-parse --short HEAD` 获取 commit hash。

### `results.tsv` — 宽表实验日志

每行一个实验，14 列：

| 列名 | 类型 | 说明 |
|---|---|---|
| commit | string | git short hash 或实验标识 |
| timestamp | ISO 8601 | UTC 时间 |
| prompt_tokens | int | system prompt 的 token 数 |
| tool_schema_tokens | int | 工具定义的 token 数 |
| total_tokens | int | prompt + tool（复合主指标） |
| test_passed | int | pytest 通过数 |
| test_failed | int | pytest 失败数（必须为 0 才能 keep） |
| test_duration_sec | float | pytest 总耗时 |
| budget_full | int | full profile 运行时上下文预算(字符) |
| budget_standard | int | standard profile 预算 |
| budget_compact | int | compact profile 预算 |
| changed_file | string | 本次修改的文件 |
| change_summary | string | 变更描述 |
| status | enum | keep / discard / pending |

**为什么用 TSV 不用 JSON？**
- TSV 可以直接 `column -t` 终端预览、`grep` 过滤、Excel/Google Sheets 打开
- 每行独立，追加不需要解析整个文件
- 与 autoresearch 原版 `results.tsv` 保持一致

### `autoresearch_program.md` — 方法论

这是 Agent 和人类共用的方法论文档，定义了：
- 角色映射（与 autoresearch 原版概念的对应关系）
- 可改/不可改文件清单
- 实验循环的伪代码
- 量化判定标准
- 实验候选队列（按优先级排列的 TODO 列表）
- 失败实验档案（避免重蹈覆辙）

### `AUTORESEARCH_AGENT_PROTOCOL.md` — Agent 操作手册

这是专门给 AI Agent 看的逐步操作指令，比 `autoresearch_program.md` 更细致：
- 每一步该执行什么命令
- 每步的预期输出是什么
- 判定规则的优先级表
- 常见陷阱和安全做法
- 完整的实验示例（从头到尾）
- 紧急恢复流程

---

## 五、原理深入

### 为什么单变量控制这么重要

假设你同时精简了 `strategy_core.md`（-200 tokens）和 `strategy_task.md`（-100 tokens），测试失败了 3 个。你无法知道：
- 是 strategy_core 的精简导致的？
- 还是 strategy_task 的精简导致的？
- 还是两者交互导致的？

你不得不回退全部改动。如果分两次实验做，可能 strategy_task 的精简是安全的，你白白浪费了 100 tokens 的收益。

### 测试作为安全护栏

Nini 的 2010 个测试覆盖了 Agent 的核心行为：
- prompt builder 的组装逻辑
- 工具注册与调用
- 意图分类
- 上下文压缩
- 会话管理

当你精简 prompt 时，如果删除了某个关键行为指令（比如"禁止空参数调用"），相关测试会失败。这是你的安全网。

**但测试不是万能的**：测试只能捕获已知的行为回归。如果你删除了一段"建议性"文本（比如"优先使用非参数方法"），测试可能仍然通过，但真实使用时 Agent 的分析质量可能下降。这就是为什么我们强调「只删除明显冗余，保留行为指令」。

### Token 计数的精确性

`measure_baseline.py` 使用 tiktoken 的 GPT-4 编码器。这与 Nini 实际使用的 LLM（可能是不同的模型）编码方式可能不完全一致。但：
- **相对变化是可靠的**：同一编码器下，-81 tokens 就是真实的 -81 tokens
- **绝对值是参考性的**：实际模型可能是 ±10% 的差异
- **没装 tiktoken 时的降级**：`len(text) // 4` 是粗略估算，适合快速迭代但不适合精确对比

### 条件注入机制

不是所有 prompt 组件都会在每次对话中加载：

```python
# builder.py 中的条件注入逻辑
_CONDITIONAL_COMPONENT_KEYWORDS = {
    "strategy_visualization.md": {"chart", "plot", "图", "可视化", ...},
    "strategy_report.md": {"report", "报告", "总结", ...},
    "strategy_phases.md": {"文献", "实验设计", "论文", ...},
}
```

当用户的消息不包含这些关键词时，对应组件不会加载。所以：
- `measure_baseline.py` 固定传入 `{"chart", "stat_test"}`，会加载 `strategy_visualization.md`
- `strategy_report.md` 和 `strategy_phases.md` 不会被加载，精简它们不影响 baseline 测量
- 但它们在运行时仍会被加载，所以精简仍有价值

---

## 六、学习路径

### 阶段 1：理解系统（1-2 小时）

1. **阅读本文档**（你正在看）
2. **阅读 `autoresearch_program.md`** — 理解实验循环
3. **运行一次 `python scripts/measure_baseline.py --compare`** — 亲眼看指标输出
4. **阅读 `results.tsv`** — 理解已有实验的历史

### 阶段 2：理解 Nini 的 prompt 架构（2-3 小时）

1. **阅读 `src/nini/agent/prompts/builder.py`** — PromptBuilder 如何装配 system prompt
   - 重点理解 `_load_components()`、`_filter_conditional_components()`、`_dedupe_paragraphs()`
2. **阅读 `data/prompt_components/strategy_core.md`** — 最大的组件，理解 Nini 的分析流程
3. **阅读 `src/nini/agent/prompt_policy.py`** — 运行时上下文的裁剪机制
   - 重点理解 `RUNTIME_CONTEXT_BLOCK_PRIORITY` 和 `trim_runtime_context_by_priority()`
4. **阅读 `src/nini/tools/registry.py`** — 工具注册，理解 tool_schema_tokens 的来源

### 阶段 3：手动做一个实验（30 分钟）

1. 选一个简单目标：精简 `strategy_visualization.md` 中的一个冗余段落
2. 按 `run_experiment.sh` 跑完整流程
3. 体验 keep/discard 的判定过程

### 阶段 4：让 Agent 自动跑（持续）

1. 把 `AUTORESEARCH_AGENT_PROTOCOL.md` 交给 Claude Code
2. 指示它执行实验循环
3. 监控 `results.tsv` 的变化
4. 每 5-10 个实验做一次人工审查

### 阶段 5：拓展优化维度（进阶）

当 prompt 精简的收益趋于平稳后，可以考虑：
- 优化 `PDCA_DETAIL_BLOCK` 的文本（目前约 2200 字符，条件注入）
- 优化工具定义中的 `parameters` 描述（影响 tool_schema_tokens）
- 调整运行时上下文预算（影响长对话的质量）
- 重新设计条件注入关键词映射（减少误加载）

---

## 七、FAQ

### Q: 为什么不直接用 LLM 评估 prompt 质量？

因为 LLM 评估 prompt 是主观的、不稳定的。Token 数是客观指标，测试通过率是客观指标。我们只优化客观指标。

### Q: 优化 prompt 会不会让 Agent 变笨？

有可能。这就是测试护栏的作用：如果删除了关键指令导致行为退化，测试会失败。但测试无法覆盖所有情况，所以我们强调「只删冗余，不删指令」。

### Q: 一个实验大概能节省多少 token？

从已有数据看：
- 精简 strategy 文本：-50 到 -500 tokens/次
- 降低预算常量：不影响 token 但节省运行时内存
- 精简工具 description：-10 到 -100 tokens/次（但容易触发测试失败）

### Q: results.tsv 里的 exp1/exp2 为什么没有真实 commit hash？

这是早期手动记录的实验。新的 `run_experiment.sh` 会自动用 `git rev-parse --short HEAD` 填入真实 hash。

### Q: 能否并行跑多个实验？

不能。单变量控制要求每次只有一个改动。如果要加速，可以让 Agent 在一个实验的 discard 后立即开始下一个（不需要人工介入）。

### Q: 为什么 baseline 的 test_failed 是 0 但 exp1/exp2 是 6→7？

baseline 是在干净状态下测量的（所有测试通过）。exp1 和 exp2 的改动导致了 6-7 个测试失败（不是原来就有 6 个失败然后变成 7 个，而是原来 0 个失败变成了 6-7 个）。`results.tsv` 中的记录方式可能产生歧义——实际含义是 `test_failed` 从 0 变为 6 或 7。
