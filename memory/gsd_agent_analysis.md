# GSD (Get Shit Done) Agent 系统深度分析

> 分析对象: https://github.com/gsd-build/get-shit-done/
> 分析日期: 2026-03-04

## 1. 项目概述

GSD 是一个基于 Claude Code CLI 的元提示（meta-prompting）和上下文工程系统，用于规范化的 AI 辅助软件开发。它不是传统意义上的 Agent 运行时，而是一套精心设计的提示词工程框架，通过结构化的 Markdown 文件来指导 Claude 的行为。

### 核心特点
- **纯提示词驱动**: 没有代码运行时，全部通过精心设计的 Markdown 提示词控制
- **文件即状态**: 使用 `.planning/` 目录下的 Markdown 文件作为状态存储
- **多 Agent 协作**: 通过不同的 Agent 定义文件实现角色分工
- **波浪式并行执行**: 支持并行 Plan 执行，通过依赖分析分组

---

## 2. Agent 架构模式分析

### 2.1 架构模式: Plan-and-Execute + 波浪并行

GSD 采用的是 **Plan-and-Execute** 模式，而非 ReAct:

```
┌─────────────────────────────────────────────────────────────┐
│                    Plan Phase                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Research   │→ │    Plan      │→ │    Check     │      │
│  │  (多Agent)   │  │  (gsd-planner)│  │(gsd-checker) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                              ↓                              │
│                    PLAN.md (可执行计划)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Execute Phase                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Wave 1: Plan 01, Plan 02 (并行执行)                 │   │
│  │  Wave 2: Plan 03 (依赖 Wave 1)                       │   │
│  │  Wave 3: Plan 04 (有 checkpoint)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                              ↓                              │
│                    SUMMARY.md (执行总结)                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Verify Phase                              │
│         gsd-verifier: 目标回溯验证                           │
│         VERIFICATION.md (验证报告)                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 与 ReAct 的区别

| 特性 | ReAct | GSD Plan-and-Execute |
|------|-------|---------------------|
| 思考方式 | 逐步思考，每步决定下一步 | 先完整规划，再执行 |
| 工具调用 | 每步可能调用工具 | 按预定义 Plan 执行 |
| 并行性 | 串行 | 支持波浪式并行 |
| 可验证性 | 难以验证 | 有明确的验证阶段 |
| 人机交互 | 随时可能中断 | 在 checkpoint 处中断 |

### 2.3 任务规划系统

**核心设计原则:**
1. **Plans Are Prompts**: PLAN.md 本身就是提示词，不是需要再转换的文档
2. **Goal-Backward Methodology**: 从目标倒推必须满足的条件
3. **Context Budget**: 每个 Plan 控制在 ~50% 上下文使用量，2-3 个任务

**Plan 结构 (YAML Frontmatter + XML):**
```yaml
---
phase: 03-features
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [src/models/user.ts, src/api/users.ts]
autonomous: true
requirements: [AUTH-01, AUTH-02]
must_haves:
  truths: ["User can login"]
  artifacts: [{path: "src/auth.ts", provides: "Auth logic"}]
  key_links: [{from: "Login.tsx", to: "/api/login", via: "fetch"}]
---
```

**任务类型:**
- `type="auto"`: 完全自主执行
- `type="checkpoint:human-verify"`: 需要人工验证（90% 情况）
- `type="checkpoint:decision"`: 需要人工决策（9% 情况）
- `type="checkpoint:human-action"`: 需要人工操作（1% 情况，如 2FA）

---

## 3. 工具系统设计

### 3.1 工具定义方式

GSD 没有传统意义上的"工具注册表"。工具通过以下方式定义:

**1. Agent Frontmatter 声明:**
```yaml
---
name: gsd-executor
tools: Read, Write, Edit, Bash, Grep, Glob
skills:
  - gsd-executor-workflow
---
```

**2. Command 文件声明:**
```yaml
---
name: gsd:execute-phase
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Task
  - TodoWrite
---
```

**3. 实际使用的工具:**
- `Read/Write/Edit`: 文件操作
- `Bash`: 命令执行
- `Grep/Glob`: 代码搜索
- `Task`: 派生子 Agent
- `WebFetch/mcp__context7__*`: 研究工具

### 3.2 工具调用机制

**通过 gsd-tools.cjs CLI:**
```bash
# 状态管理
node gsd-tools.cjs state advance-plan
node gsd-tools.cjs state add-decision --phase 1 --summary "..."

# 验证
node gsd-tools.cjs verify artifacts plan.md
node gsd-tools.cjs verify key-links plan.md

# 模板填充
node gsd-tools.cjs template fill summary --phase 1 --plan 1
```

### 3.3 与 Nini 工具系统的对比

| 方面 | GSD | Nini |
|------|-----|------|
| 工具定义 | Markdown frontmatter | Python 类继承 Skill |
| 工具注册 | 声明式 | ToolRegistry 显式注册 |
| 工具执行 | 通过提示词指导 | 显式 execute() 方法 |
| 工具类型 | 文件/搜索/命令/子Agent | 统计/可视化/代码执行/RAG |

---

## 4. 记忆和上下文管理

### 4.1 状态存储架构

GSD 使用**文件即状态**的设计:

```
.planning/
├── PROJECT.md          # 项目愿景（长期记忆）
├── REQUIREMENTS.md     # 需求规格（长期记忆）
├── ROADMAP.md          # 路线图（长期记忆）
├── STATE.md            # 当前状态（短期记忆，<100行）
├── config.json         # 配置
├── phases/
│   └── XX-name/
│       ├── XX-YY-PLAN.md      # 执行计划
│       ├── XX-YY-SUMMARY.md   # 执行结果
│       ├── CONTEXT.md         # 用户决策
│       ├── RESEARCH.md        # 研究结果
│       └── VERIFICATION.md    # 验证报告
```

### 4.2 上下文管理策略

**1. 分层加载:**
- **Orchestrator**: ~10-15% 上下文，保持精简
- **Subagent**: 每个子 Agent 获得全新的 200K 上下文

**2. 显式文件引用:**
```markdown
<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@src/relevant/file.ts
</context>
```

**3. 历史摘要 (History Digest):**
```bash
node gsd-tools.cjs history-digest
```
生成历史阶段摘要，用于选择相关上下文。

### 4.3 长上下文处理

**策略:**
1. **不保留完整历史**: 每个子 Agent 只加载必要的文件
2. **SUMMARY.md 作为压缩**: 每个 Plan 执行后生成摘要
3. **选择性加载**: 只加载与当前工作相关的历史 SUMMARY

**与 Nini 的对比:**
- GSD: 显式文件引用，子 Agent 隔离
- Nini: 会话历史存储在 memory.jsonl，需要时加载

---

## 5. LLM 交互设计

### 5.1 多模型支持

**Model Profile 系统:**
```json
{
  "model_profile": "balanced",
  "model_overrides": {
    "gsd-executor": "opus",
    "gsd-planner": "haiku"
  }
}
```

**Profile 定义:**

| Agent | quality | balanced | budget |
|-------|---------|----------|--------|
| gsd-planner | opus | opus | sonnet |
| gsd-executor | opus | sonnet | sonnet |
| gsd-verifier | sonnet | sonnet | haiku |
| gsd-codebase-mapper | sonnet | haiku | haiku |

**设计哲学:**
- **Opus**: 用于规划（架构决策）
- **Sonnet**: 用于执行（遵循明确指令）
- **Haiku**: 用于研究/验证（模式匹配）

### 5.2 Agent 派生机制

**通过 Task 工具派生:**
```markdown
Task(
  subagent_type="gsd-executor",
  model="sonnet",
  prompt="..."
)
```

**关键设计:**
- 每个子 Agent 获得**全新的上下文窗口**
- 通过 `<files_to_read>` 块显式传递上下文
- 子 Agent 完成后返回结构化结果

---

## 6. 验证与质量保证

### 6.1 三层验证体系

**1. Plan Check (规划阶段):**
- 检查任务完整性
- 检查依赖正确性
- 检查 must_haves 推导

**2. 执行验证 (执行阶段):**
- 偏差规则 (Deviation Rules): 自动修复 Bug、缺失功能
- 每个任务后提交，可追溯
- Self-Check: 验证文件和提交存在

**3. 目标验证 (验证阶段):**
- **Goal-Backward Verification**: 从目标倒推验证
- 三层检查:
  - Level 1: 文件存在
  - Level 2: 内容实质性
  - Level 3: 正确连接

### 6.2 偏差处理规则

| 规则 | 触发条件 | 处理方式 |
|------|---------|---------|
| Rule 1 | Bug、错误 | 自动修复 |
| Rule 2 | 缺失关键功能 | 自动添加 |
| Rule 3 | 阻塞问题 | 自动修复 |
| Rule 4 | 架构变更 | 停止询问用户 |

---

## 7. 对 Nini 的借鉴建议

### 7.1 值得借鉴的设计模式

**1. Plan-and-Execute 模式:**
- 对于复杂数据分析任务，可以先规划再执行
- 支持并行执行独立的分析步骤
- 明确的验证阶段确保结果质量

**2. 目标回溯验证 (Goal-Backward Verification):**
```python
# 可以添加到 Nini 的验证层
must_haves = {
    "truths": ["用户可以看到统计结果图表"],
    "artifacts": [
        {"path": "output/chart.png", "min_size": "10KB"}
    ],
    "key_links": [
        {"from": "analysis_result", "to": "chart.png", "via": "create_chart"}
    ]
}
```

**3. 波浪式并行执行:**
```python
# 分析任务可以并行化
wave_1 = [load_data, validate_data]  # 无依赖，并行
wave_2 = [analyze_correlation]        # 依赖 wave_1
wave_3 = [generate_report]            # 依赖 wave_2
```

**4. 模型分层策略:**
- 规划 Agent 使用最强模型
- 执行 Agent 可以使用较快模型
- 验证 Agent 使用经济模型

**5. 偏差自动处理规则:**
- 明确什么情况下 Agent 可以自主决策
- 什么情况下必须询问用户

### 7.2 需要适配的部分

**1. 文件即状态 vs 数据库状态:**
- GSD 适合项目开发（文件为中心）
- Nini 适合对话式分析（会话为中心）
- 可以借鉴 STATE.md 的模式，但保持数据库存储

**2. Checkpoint 机制:**
- GSD 的 checkpoint 适合长时间运行的开发任务
- Nini 可以借鉴用于需要人工确认的分析步骤

**3. 提示词模板系统:**
- GSD 的模板系统非常成熟
- Nini 可以引入类似的模板机制来规范化 Agent 行为

### 7.3 具体实现建议

**1. 引入 Plan Phase:**
```python
# 在 agent/planner.py 中
class AnalysisPlanner:
    def create_plan(self, user_intent: str) -> ExecutionPlan:
        # 生成包含 waves、tasks、must_haves 的计划
        pass
```

**2. 增强验证层:**
```python
# 在 agent/verifier.py 中
class GoalVerifier:
    def verify_truths(self, truths: List[str]) -> VerificationResult:
        # 验证每个 truth 是否达成
        pass

    def verify_artifacts(self, artifacts: List[Artifact]) -> VerificationResult:
        # 验证产物存在且实质性
        pass
```

**3. 模型路由优化:**
```python
# 在 agent/model_resolver.py 中
MODEL_PROFILES = {
    "planning": "claude-opus-4-6",
    "execution": "claude-sonnet-4-6",
    "verification": "claude-haiku-4-5"
}
```

---

## 8. 总结

GSD 是一个**提示词工程的艺术品**，展示了如何通过精心设计的 Markdown 文件和结构化流程来控制 LLM 的行为。其核心创新在于:

1. **Plans Are Prompts**: 计划文件本身就是可执行提示词
2. **Goal-Backward Verification**: 从目标倒推验证，而非仅检查任务完成
3. **Context Budget Management**: 显式管理上下文预算，确保质量
4. **Deviation Rules**: 明确的自主决策边界

对于 Nini 而言，最值得借鉴的是其**规划-执行-验证**的完整闭环，以及**目标回溯验证**的方法论。这些可以显著提升复杂数据分析任务的可靠性和可追溯性。
