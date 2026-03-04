# GSD (Get Shit Done) 项目调研与优化建议报告

## 执行摘要

**GSD** 是一个专为 Claude Code 设计的元提示（meta-prompting）、上下文工程和规范驱动开发系统。它通过解决"上下文衰减"（context rot）问题——即 Claude 在上下文窗口填满时质量下降的现象——来实现可靠、可扩展的 AI 辅助开发。

本报告分析了 GSD 的核心机制，并提炼出 **15 项可借鉴到 Nini 项目的优化建议**，涵盖任务规划、上下文管理、Agent 编排、验证机制等方面。

---

## 1. GSD 项目概述

### 1.1 项目定位

| 属性 | 内容 |
|------|------|
| **名称** | Get Shit Done (GSD) |
| **作者** | TÂCHES |
| **核心理念** | "The complexity is in the system, not in your workflow" |
| **目标用户** | 独立开发者、使用 AI 编程助手的技术人员 |
| **解决痛点** | 上下文衰减、vibe coding 质量不稳定、缺乏系统性开发流程 |

### 1.2 核心工作流（6 步循环）

```
┌─────────────────────────────────────────────────────────────┐
│  1. /gsd:new-project                                        │
│     提问 → 调研 → 需求定义 → 路线图                          │
│                      ↓                                      │
│  2. /gsd:discuss-phase N     3. /gsd:plan-phase N          │
│     捕获实现决策               调研 + 规划 + 验证             │
│                      ↓                                      │
│  4. /gsd:execute-phase N                                    │
│     波浪式并行执行                                            │
│                      ↓                                      │
│  5. /gsd:verify-work N                                      │
│     人工验收测试                                             │
│                      ↓                                      │
│  6. /gsd:complete-milestone                                 │
│     归档里程碑，标记发布                                      │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 技术架构亮点

| 组件 | 说明 |
|------|------|
| **上下文工程系统** | PROJECT.md / REQUIREMENTS.md / ROADMAP.md / STATE.md / PLAN.md / SUMMARY.md |
| **XML 提示格式** | 结构化任务定义，包含 `<name>`, `<files>`, `<action>`, `<verify>`, `<done>` 标签 |
| **多 Agent 编排** | 研究型、规划型、执行型、验证型 Agent 协同工作 |
| **波浪式执行** | 按依赖关系分组，独立计划并行执行，依赖计划顺序执行 |
| **原子化 Git 提交** | 每个任务独立提交，便于追踪和回滚 |

---

## 2. GSD 核心机制深度分析

### 2.1 上下文管理文件体系

GSD 使用一组精心设计的 Markdown 文件来管理项目状态：

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `PROJECT.md` | 项目愿景和核心目标 | 里程碑节点 |
| `REQUIREMENTS.md` | 已验证/进行中/范围外的需求 | 每个阶段 |
| `ROADMAP.md` | 阶段划分和进度追踪 | 规划时 |
| `STATE.md` | 决策记录、阻塞项、会话记忆 | 持续更新 |
| `PLAN.md` | 原子化执行计划 | 每个计划 |
| `SUMMARY.md` | 执行历史记录 | 任务完成后 |
| `CONTEXT.md` | 实现偏好和决策 | 讨论阶段 |
| `RESEARCH.md` | 生态系统调研结果 | 规划阶段 |

### 2.2 目标逆向（Goal-Backward）方法论

**传统正向规划**："我们应该构建什么？" → 产生任务列表
**目标逆向规划**："目标达成时，什么必须为真？" → 产生需求验证标准

**实施步骤**：
1. 陈述目标（结果导向，非任务导向）
2. 推导出可观察的真值（3-7 条，用户视角）
3. 推导出必需的产物（具体文件）
4. 推导出必需的连接（组件如何交互）
5. 识别关键连接点（最可能出问题的地方）

### 2.3 波浪式执行（Wave Execution）

```
WAVE 1 (并行)          WAVE 2 (并行)          WAVE 3
┌─────────┐ ┌─────────┐    ┌─────────┐ ┌─────────┐    ┌─────────┐
│ Plan 01 │ │ Plan 02 │ →  │ Plan 03 │ │ Plan 04 │ →  │ Plan 05 │
│ User    │ │ Product │    │ Orders  │ │ Cart    │    │ Checkout│
│ Model   │ │ Model   │    │ API     │ │ API     │    │ UI      │
└─────────┘ └─────────┘    └─────────┘ └─────────┘    └─────────┘
     │           │              ↑           ↑              ↑
     └───────────┴──────────────┴───────────┘              │
            依赖关系：Plan 03 依赖 Plan 01                  │
                     Plan 04 依赖 Plan 02                  │
                     Plan 05 依赖 Plan 03 + 04             │
```

**优势**：
- 独立计划 → 同波浪 → 并行执行
- 依赖计划 → 后续波浪 → 等待前置完成
- 文件冲突 → 顺序执行或合并到同一计划

### 2.4 XML 任务格式

```xml
<task type="auto">
  <name>创建登录端点</name>
  <files>src/app/api/auth/login/route.ts</files>
  <action>
    使用 jose 库处理 JWT（不是 jsonwebtoken - Edge 运行时有 CommonJS 问题）。
    验证凭据与 users 表。
    成功时返回 httpOnly cookie。
  </action>
  <verify>
    <automated>curl -X POST localhost:3000/api/auth/login 返回 200 + Set-Cookie</automated>
  </verify>
  <done>有效凭据返回 cookie，无效凭据返回 401</done>
</task>
```

---

## 3. Nini 可借鉴的优化建议

### 3.1 任务规划系统增强

#### 建议 1：引入"波浪式执行"机制

**现状**：Nini 的任务规划是线性执行，缺乏并行优化。

**借鉴点**：
- 分析任务依赖关系，构建依赖图
- 无依赖的任务并行执行
- 有依赖的任务按波浪顺序执行

**实施思路**：
```python
# 在 agent/planner.py 或 agent/task_manager.py 中
class WaveScheduler:
    def build_dependency_graph(self, tasks: List[Task]) -> Dict[str, Set[str]]:
        # 分析任务间的 needs/creates 关系
        pass

    def assign_waves(self, graph: DependencyGraph) -> List[List[Task]]:
        # 返回波浪分组，每组可并行执行
        pass
```

**优先级**：P1（高）
**预估工作量**：3-5 天

---

#### 建议 2：强化"目标逆向"验证

**现状**：Nini 的任务完成后缺乏系统化的验证机制。

**借鉴点**：
- 每个计划必须包含 `must_haves` 字段
- 从目标逆向推导出：真值（truths）、产物（artifacts）、连接（key_links）
- 执行后自动验证 must_haves

**实施思路**：
```python
# 在 models/execution_plan.py 中
class Plan(BaseModel):
    must_haves: MustHaves

class MustHaves(BaseModel):
    truths: List[str]          # 用户视角的可观察行为
    artifacts: List[Artifact]  # 必须存在的文件
    key_links: List[KeyLink]   # 关键连接点
```

**优先级**：P1（高）
**预估工作量**：2-3 天

---

#### 建议 3：引入"讨论阶段"（discuss-phase）概念

**现状**：用户意图主要通过自然语言对话传达，缺乏结构化捕获。

**借鉴点**：
- 在正式规划前，专门捕获实现偏好
- 区分：已锁定决策（必须执行）、延迟想法（不执行）、Claude 自由裁量
- 输出 `CONTEXT.md` 供后续阶段引用

**实施思路**：
```python
# 新增 discuss-phase 工作流
# 在 agent/prompts/builder.py 中添加
DISCUSS_PHASE_PROMPT = """
分析用户意图，识别以下类别：
1. Locked Decisions（已锁定决策）- 必须严格实现
2. Deferred Ideas（延迟想法）- 明确不实现
3. Claude's Discretion（自由裁量）- 使用合理判断
"""
```

**优先级**：P2（中）
**预估工作量**：2-3 天

---

### 3.2 上下文管理体系

#### 建议 4：建立标准化的项目状态文件体系

**现状**：Nini 的会话状态存储在 `data/sessions/{id}/` 中，但缺乏结构化的项目级文档。

**借鉴点**：引入 GSD 的文件模板体系

| Nini 新增文件 | 用途 |
|--------------|------|
| `SESSION.md` | 会话愿景和分析目标 |
| `DATASETS.md` | 已加载数据集目录和描述 |
| `ANALYSIS.md` | 分析需求（v1/v2/范围外） |
| `PLAN.md` | 当前执行计划 |
| `SUMMARY.md` | 已完成的分析步骤记录 |

**实施思路**：
```python
# 在 workspace/manager.py 中
class ProjectDocumentManager:
    def create_project_md(self, session_id: str, description: str):
        pass

    def create_analysis_md(self, session_id: str, requirements: List[Requirement]):
        pass
```

**优先级**：P1（高）
**预估工作量**：3-4 天

---

#### 建议 5：实现会话状态快照与恢复

**现状**：Nini 会话数据持久化，但缺乏显式的"暂停/恢复"机制。

**借鉴点**：
- `/gsd:pause-work` - 创建交接文档
- `/gsd:resume-work` - 从上次会话恢复完整上下文
- `/gsd:progress` - 查看当前状态和下一步

**实施思路**：
```python
# 新增命令或工具
class SessionLifecycle:
    def pause_work(self, session_id: str) -> HandoffDocument:
        # 创建 STATE.md 记录当前位置、决策、阻塞项
        pass

    def resume_work(self, session_id: str) -> SessionContext:
        # 读取 STATE.md 恢复上下文
        pass
```

**优先级**：P2（中）
**预估工作量**：2-3 天

---

### 3.3 Agent 编排优化

#### 建议 6：细化 Agent 角色分工

**现状**：Nini 主要使用通用 AgentRunner，Agent 角色不够细分。

**借鉴点**：GSD 的 Agent 类型设计

| GSD Agent | 职责 | Nini 对应场景 |
|-----------|------|--------------|
| `gsd-planner` | 创建可执行计划 | 分析规划 Agent |
| `gsd-executor` | 执行计划任务 | 工具执行 Agent |
| `gsd-verifier` | 验证目标达成 | 结果验证 Agent |
| `gsd-debugger` | 诊断失败原因 | 错误诊断 Agent |
| `gsd-researcher` | 调研技术方案 | 方法推荐 Agent |

**实施思路**：
```python
# 在 agent/components/ 下新增 specialized_agents/
class AnalysisPlannerAgent(SpecializedAgent):
    """专门负责分析规划的 Agent"""
    pass

class ResultVerifierAgent(SpecializedAgent):
    """专门负责验证分析结果的 Agent"""
    pass
```

**优先级**：P2（中）
**预估工作量**：4-6 天

---

#### 建议 7：实现模型分层策略

**现状**：Nini 支持多模型，但缺乏按任务类型分配模型的策略。

**借鉴点**：GSD 的 Model Profiles

| Profile | 规划 | 执行 | 验证 |
|---------|------|------|------|
| quality | Opus | Opus | Sonnet |
| balanced | Opus | Sonnet | Sonnet |
| budget | Sonnet | Sonnet | Haiku |

**实施思路**：
```python
# 在 agent/model_resolver.py 中
class ModelProfileResolver:
    def __init__(self, profile: str = "balanced"):
        self.profile = profile

    def get_model_for_task(self, task_type: TaskType) -> str:
        mapping = {
            "planning": {"quality": "opus", "balanced": "opus", "budget": "sonnet"},
            "execution": {"quality": "opus", "balanced": "sonnet", "budget": "sonnet"},
            "verification": {"quality": "sonnet", "balanced": "sonnet", "budget": "haiku"},
        }
        return mapping[task_type][self.profile]
```

**优先级**：P2（中）
**预估工作量**：1-2 天

---

### 3.4 验证与质量保证

#### 建议 8：引入 Nyquist 验证层

**现状**：Nini 的验证主要依赖人工检查或简单断言。

**借鉴点**：GSD 的 Nyquist 验证架构——在规划阶段就映射自动化测试覆盖

**实施思路**：
```python
# 新增 validation/ 模块
class NyquistValidator:
    def map_requirement_to_tests(self, requirement: Requirement) -> List[TestCase]:
        """将需求映射到测试用例"""
        pass

    def validate_phase(self, phase: Phase) -> ValidationReport:
        """验证阶段是否满足所有需求的自动化测试"""
        pass
```

**优先级**：P3（低）
**预估工作量**：5-7 天

---

#### 建议 9：强化 TDD（测试驱动开发）支持

**现状**：Nini 支持代码执行，但缺乏系统化的 TDD 流程。

**借鉴点**：
- 识别 TDD 候选：业务逻辑、API 端点、数据转换
- RED → GREEN → REFACTOR 循环
- 每个 TDD 计划产生 2-3 个原子提交

**实施思路**：
```python
# 在 tools/run_code.py 或新增 tdd.py
class TDDExecutor:
    def red_phase(self, test_file: str, behavior: BehaviorSpec):
        """编写失败的测试"""
        pass

    def green_phase(self, implementation_file: str, test_file: str):
        """编写最小实现使测试通过"""
        pass

    def refactor_phase(self, files: List[str]):
        """重构并保持测试通过"""
        pass
```

**优先级**：P3（低）
**预估工作量**：4-5 天

---

### 3.5 快速模式与工具增强

#### 建议 10：实现 Quick Mode（快速模式）

**现状**：Nini 的所有任务都经过完整规划流程，对小任务来说过于沉重。

**借鉴点**：`/gsd:quick` - 用于临时任务，跳过研究、计划检查、验证

**实施思路**：
```python
# 新增快速分析模式
class QuickAnalysis:
    def execute(self, description: str) -> AnalysisResult:
        """
        快速分析流程：
        1. 直接生成精简计划（无研究阶段）
        2. 单 Agent 执行
        3. 简化验证
        """
        pass
```

**优先级**：P2（中）
**预估工作量**：2-3 天

---

#### 建议 11：添加任务检查点（Checkpoint）

**现状**：Nini 的工具执行是全自动的，缺乏人机协作的验证点。

**借鉴点**：三种检查点类型
- `checkpoint:human-verify` - 人工确认自动化工作
- `checkpoint:decision` - 人工做实现选择
- `checkpoint:human-action` - 人工执行必要步骤

**实施思路**：
```python
# 在 tools/base.py 中扩展
class CheckpointType(Enum):
    HUMAN_VERIFY = "human-verify"
    DECISION = "decision"
    HUMAN_ACTION = "human-action"

class Task(BaseModel):
    checkpoint: Optional[CheckpointType] = None
    checkpoint_gate: Optional[str] = None  # "blocking" or "non-blocking"
```

**优先级**：P2（中）
**预估工作量**：3-4 天

---

### 3.6 文档与模板体系

#### 建议 12：建立模板体系

**现状**：Nini 有 prompts/builder.py，但缺乏标准化的 Markdown 模板。

**借鉴点**：GSD 的 `get-shit-done/templates/` 目录

**建议模板**：
```
nini/templates/
├── project.md          # 项目描述模板
├── analysis.md         # 分析需求模板
├── plan.md             # 执行计划模板
├── summary.md          # 执行摘要模板
├── context.md          # 分析偏好模板
└── research.md         # 调研结果模板
```

**优先级**：P2（中）
**预估工作量**：2-3 天

---

#### 建议 13：完善 User Guide

**现状**：Nini 的文档分散在代码注释和 README。

**借鉴点**：GSD 的 `docs/USER-GUIDE.md` 包含完整的工作流图、命令参考、配置说明

**建议内容**：
- 工作流图示（Mermaid）
- 完整命令/工具参考
- 配置项说明
- 故障排除指南
- 恢复快速参考

**优先级**：P3（低）
**预估工作量**：3-5 天

---

### 3.7 工程实践

#### 建议 14：实现原子化 Git 提交

**现状**：Nini 没有显式的版本控制集成。

**借鉴点**：每个任务完成后立即提交，提交信息格式：
```
<type>(<phase>-<plan>): <description>

feat(08-02): add email confirmation flow
```

**实施思路**：
```python
# 在 workspace/manager.py 或新增 git.py
class GitIntegration:
    def commit_task(self, task: Task, phase: str, plan: str):
        """
        自动提交任务变更
        """
        message = f"{task.type}({phase}-{plan}): {task.description}"
        # git add && git commit
```

**优先级**：P3（低）
**预估工作量**：2-3 天

---

#### 建议 15：添加健康检查命令

**现状**：Nini 有 `nini doctor`，但可以扩展更多检查项。

**借鉴点**：`/gsd:health [--repair]` - 验证目录完整性，自动修复

**建议检查项**：
- 会话数据完整性
- 产物文件一致性
- 配置有效性
- 工具可用性

**实施思路**：
```python
# 扩展现有 doctor 命令
class HealthChecker:
    def check_session_integrity(self, session_id: str) -> List[Issue]:
        pass

    def check_artifact_consistency(self, session_id: str) -> List[Issue]:
        pass

    def repair(self, issues: List[Issue]) -> RepairReport:
        pass
```

**优先级**：P3（低）
**预估工作量**：1-2 天

---

## 4. 实施路线图建议

### 阶段 1：基础设施（2-3 周）

| 周次 | 任务 | 产出 |
|------|------|------|
| 1 | 实现项目状态文件体系（建议 4） | SESSION.md, DATASETS.md, ANALYSIS.md 支持 |
| 1-2 | 实现波浪式执行（建议 1） | WaveScheduler 类，任务依赖分析 |
| 2-3 | 实现目标逆向验证（建议 2） | must_haves 字段，自动验证 |
| 3 | 模型分层策略（建议 7） | ModelProfileResolver |

### 阶段 2：体验优化（2-3 周）

| 周次 | 任务 | 产出 |
|------|------|------|
| 4 | 快速模式（建议 10） | QuickAnalysis 类 |
| 4-5 | 讨论阶段概念（建议 3） | discuss-phase 工作流 |
| 5-6 | 任务检查点（建议 11） | Checkpoint 支持 |
| 6 | 会话暂停/恢复（建议 5） | pause/resume 命令 |

### 阶段 3：质量提升（2-3 周）

| 周次 | 任务 | 产出 |
|------|------|------|
| 7-8 | Agent 角色细化（建议 6） | 专用 Agent 类 |
| 8-9 | 模板体系（建议 12） | templates/ 目录 |
| 9 | TDD 支持（建议 9） | TDDExecutor 类 |

### 阶段 4：完善（2 周）

| 周次 | 任务 | 产出 |
|------|------|------|
| 10 | Nyquist 验证层（建议 8） | NyquistValidator |
| 10-11 | Git 集成（建议 14） | GitIntegration 类 |
| 11 | 健康检查扩展（建议 15） | 扩展 HealthChecker |
| 11 | 完善文档（建议 13） | USER-GUIDE.md |

---

## 5. 风险与考虑

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 过度工程化 | 增加不必要的复杂性 | 按阶段实施，先验证核心功能 |
| 用户体验变化 | 现有用户不适应新流程 | 保持向后兼容，新功能可选启用 |
| 上下文开销 | 新文件体系增加 token 消耗 | 按需加载，摘要索引 |
| 维护成本 | 更多组件需要维护 | 清晰的接口边界，完善的测试 |

---

## 6. 总结

GSD 为 Nini 提供了丰富的可借鉴经验，特别是在以下方面：

1. **系统化的上下文管理** - 通过标准化文件体系解决上下文衰减
2. **目标逆向验证** - 从目标出发定义成功标准，而非仅关注任务列表
3. **波浪式执行** - 通过依赖分析最大化并行度
4. **精细的 Agent 分工** - 不同任务使用不同专业 Agent
5. **人机协作的检查点** - 在关键节点引入人工验证

建议优先实施 **项目状态文件体系**、**波浪式执行**、**目标逆向验证** 这三项，它们将为 Nini 的分析流程带来显著提升。

---

*报告生成时间：2026-03-04*
*调研对象：GSD v1.22.4*
*报告作者：Claude Code Agent Team*
