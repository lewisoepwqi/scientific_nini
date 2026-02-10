# 科研 Nini 项目优化方案

> **版本**: v1.0
> **日期**: 2026-02-10
> **设计者**: 方案设计员
> **目标**: 使科研用户能够用自然语言直接生成可发表的数据分析和图表

---

## 一、项目现状分析

### 1.1 当前架构概览

科研 Nini 是一个基于 ReAct 循环的 AI Agent 平台，核心架构包括：

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Web)                           │
│                  React + TypeScript                         │
└────────────────────┬────────────────────────────────────────┘
                     │ WebSocket / HTTP
┌────────────────────▼────────────────────────────────────────┐
│                    FastAPI 应用层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  HTTP API    │  │  WebSocket   │  │ 静态文件服务  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   Agent Runner (ReAct)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. 构建上下文 (系统Prompt + 会话历史 + 知识检索)    │  │
│  │  2. 调用 LLM (流式响应 + 工具调用)                  │  │
│  │  3. 执行工具 (技能注册中心)                        │  │
│  │  4. 迭代循环 (最多 max_iterations 次)               │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 会话管理     │  │ 记忆压缩     │  │ 知识检索     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   技能注册中心                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │统计分析  │ │ 可视化   │ │ 数据操作 │ │ 工作流   │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心组件清单

| 组件 | 文件位置 | 职责 |
|------|----------|------|
| AgentRunner | `src/nini/agent/runner.py` | ReAct 主循环执行器 |
| Session | `src/nini/agent/session.py` | 会话状态管理 |
| SkillRegistry | `src/nini/skills/registry.py` | 技能注册与执行 |
| PromptBuilder | `src/nini/agent/prompts/builder.py` | 系统提示词装配 |
| ModelResolver | `src/nini/agent/model_resolver.py` | 多模型适配 |

---

## 二、问题清单（按严重程度排序）

### P0 级别问题（阻碍核心功能）

#### P0-1: 缺乏意图理解与任务分解层

**问题描述**：
当前 Agent 直接从用户消息跳转到工具调用，缺乏对复杂科研任务的规划和分解能力。

**影响**：
- 用户说"分析这个数据集的差异"时，Agent 可能随机选择工具
- 多步骤分析任务（如"先检查正态性，再选择合适的检验方法"）需要用户明确指导
- 无法处理"像某篇论文那样分析"这种高级需求

**代码位置**：
- `src/nini/agent/runner.py` (第 96-362 行)
- 直接进入 ReAct 循环，无预处理

#### P0-2: 技能粒度过细，缺乏组合能力

**问题描述**：
现有技能都是原子操作（t_test、anova、correlation），缺乏"分析方案"级别的复合技能。

**影响**：
- LLM 需要多轮对话才能完成一个完整的科研分析流程
- 用户需要懂统计学术语才能有效使用
- 无法一键生成"可发表"的分析报告

**代码位置**：
- `src/nini/skills/` 目录下所有技能文件
- `src/nini/skills/registry.py` (第 158-180 行)

#### P0-3: 缺乏用户画像与上下文记忆

**问题描述**：
系统无法记忆用户的分析偏好、领域知识、常用图表风格等。

**影响**：
- 每次会话都需要重新指定期刊风格、参数偏好
- 无法根据用户领域（生物学、心理学等）调整分析策略
- 重复性工作效率低

**代码位置**：
- `src/nini/agent/prompts/builder.py` (第 64 行)
- user.md 内容为空，实际未实现

---

### P1 级别问题（影响用户体验）

#### P1-1: 错误处理与自我修复能力不足

**问题描述**：
工具执行失败时，Agent 缺乏智能重试和降级策略。

**影响**：
- 统计检验前提不满足时（如正态性检验失败），系统不会自动改用非参数方法
- 参数错误时直接报错，而不是提供智能建议
- 用户需要手动修正并重试

**代码位置**：
- `src/nini/agent/runner.py` (第 691-713 行)
- 错误仅记录日志，无修复逻辑

#### P1-2: 可解释性不足

**问题描述**：
系统执行的分析过程对用户不透明。

**影响**：
- 用户不理解为什么选择某个统计方法
- 无法审计分析步骤的科学性
- 难以将结果用于论文写作

**代码位置**：
- 事件流中缺乏"推理"类型
- `src/nini/agent/runner.py` (第 50-62 行) EventType 定义

#### P1-3: 成本追踪不完善

**问题描述**：
虽然有 token 统计，但缺乏向用户展示成本的机制。

**影响**：
- 用户不知道使用成本
- 无法优化提示词长度
- 长对话可能导致意外高费用

**代码位置**：
- `src/nini/utils/token_counter.py` (存在但未集成到 UI)

---

### P2 级别问题（优化空间）

#### P2-1: 记忆压缩策略单一

**问题描述**：
当前仅依赖 LLM 自身进行上下文压缩，无结构化摘要。

**影响**：
- 长对话中早期分析结果可能被遗忘
- 无法保留关键发现（如"数据集X有显著差异"）
- 重复分析相同问题

**代码位置**：
- `src/nini/memory/compression.py` (文件存在但未完整实现)

#### P2-2: 知识检索能力有限

**问题描述**：
知识检索仅基于关键词匹配，缺乏语义理解。

**影响**：
- 无法理解"检验两组间差异"与"比较均值"是同一需求
- 领域知识建议不够精准

**代码位置**：
- `src/nini/knowledge/loader.py`
- `src/nini/knowledge/vector_store.py` (新建但未集成)

#### P2-3: 缺乏多模态支持

**问题描述**：
系统无法处理图片数据（如实验扫描图、手写数据）。

**影响**：
- 用户需要手动转录图片中的数据
- 无法分析图像中的图表信息

---

## 三、优化方案设计

### 3.1 架构优化方案（解决 P0 级别问题）

#### 方案 3.1.1: 引入双层 Agent 架构

**设计理念**：
将单层 ReAct Agent 拆分为"规划层 + 执行层"双层架构。

```
┌─────────────────────────────────────────────────────────────┐
│                      用户输入                                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   规划层 Agent                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. 意图识别 (用户想做什么?)                         │  │
│  │  2. 任务分解 (需要哪些步骤?)                         │  │
│  │  3. 方案选择 (用什么统计方法?)                       │  │
│  │  4. 生成执行计划 (JSON 格式)                         │  │
│  └──────────────────────────────────────────────────────┘  │
│  输出: ExecutionPlan {                                      │
│    steps: [                                                 │
│      { phase: "data_check", actions: [...] },              │
│      { phase: "statistical_test", actions: [...] },         │
│      { phase: "visualization", actions: [...] }            │
│    ]                                                        │
│  }                                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   执行层 Agent (现有)                        │
│  按照 ExecutionPlan 逐步执行，支持计划修正                   │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   结果汇总层                                 │
│  生成结构化报告 + 可视化 + 统计表格                          │
└─────────────────────────────────────────────────────────────┘
```

**优先级**: P0
**工作量**: 5-7 人日
**预期收益**:
- 用户只需描述目标，Agent 自动规划分析路径
- 多步骤任务可一次性完成
- 计划可展示给用户确认，提升信任度

**实现要点**：
1. 新增 `PlannerAgent` 类 (继承自 `AgentRunner`)
2. 新增 `ExecutionPlan` 数据模型
3. 实现计划验证与修正机制
4. 向后兼容：无明确计划时降级为原 ReAct 模式

---

#### 方案 3.1.2: 复合技能系统

**设计理念**：
将原子技能组合成"分析模板"，覆盖常见科研场景。

```python
# 新增复合技能示例
class CompleteComparisonSkill(Skill):
    """完整比较分析技能 (模板)"""

    name = "complete_comparison"
    description = """
    执行完整的两组比较分析，包括：
    1. 数据质量检查 (样本量、缺失值、异常值)
    2. 正态性与方差齐性检验
    3. 根据前提选择合适的统计检验 (t检验/Mann-Whitney)
    4. 效应量计算 (Cohen's d)
    5. 可视化 (箱线图 + 森林图)
    6. 生成APA格式结果描述
    """

    async def execute(self, session, dataset_name, value_column, group_column):
        # 步骤1: 数据检查
        check_result = await self._check_data(session, dataset_name, value_column, group_column)

        # 步骤2: 前提检验
        assumptions = await self._test_assumptions(session, ...)

        # 步骤3: 选择检验方法
        test_method = self._select_test(assumptions)
        test_result = await test_method.execute(...)

        # 步骤4: 效应量
        effect_size = self._calculate_effect_size(...)

        # 步骤5: 可视化
        chart = await self._create_visualization(...)

        # 步骤6: 报告
        report = self._generate_report(test_result, effect_size, chart)

        return SkillResult(
            success=True,
            data={"report": report, "chart": chart, "test": test_result}
        )
```

**预置模板**：

| 模板名称 | 适用场景 | 输出 |
|---------|---------|------|
| `complete_comparison` | 两组均值比较 | 检验结果 + 效应量 + 箱线图 + APA报告 |
| `complete_anova` | 多组均值比较 | ANOVA + 事后检验 + 效应量 + 图表 |
| `correlation_analysis` | 变量关联分析 | 相关矩阵 + 散点图 + 报告 |
| `regression_analysis` | 预测建模 | 回归结果 + 诊断图 + 报告 |
| `time_series_analysis` | 时间序列数据 | 趋势分析 + 预测 + 图表 |

**优先级**: P0
**工作量**: 3-5 人日
**预期收益**:
- 用户无需懂统计术语即可获得专业分析
- 一键生成"可发表"级别的内容
- 减少对话轮次

---

#### 方案 3.1.3: 用户画像系统

**设计理念**：
构建持久化的用户画像，记录偏好、领域、历史行为。

```python
@dataclass
class UserProfile:
    user_id: str
    # 领域偏好
    domain: str = "general"  # biology, psychology, medicine, ...
    # 统计偏好
    significance_level: float = 0.05
    preferred_correction: str = "bonferroni"  # 多重比较校正
    # 可视化偏好
    journal_style: str = "nature"
    color_palette: str = "default"
    # 分析习惯
    auto_check_assumptions: bool = True
    include_effect_size: bool = True
    include_ci: bool = True
    # 历史统计
    total_analyses: int = 0
    favorite_tests: list[str] = field(default_factory=list)
```

**实现要点**：
1. 新增 `UserProfileManager` 类
2. 会话开始时加载用户画像
3. 在系统 Prompt 中注入用户偏好
4. 分析后更新画像 (如常用检验方法)

**优先级**: P0
**工作量**: 2-3 人日
**预期收益**:
- 越用越智能，个性化体验
- 减少重复配置

---

### 3.2 智能化增强方案（解决 P1 级别问题）

#### 方案 3.2.1: 自我修复与降级策略

**设计理念**：
当工具执行失败时，Agent 应尝试智能修复。

```python
class SkillExecutor:
    async def execute_with_fallback(self, skill_name, session, **kwargs):
        try:
            return await self.registry.execute(skill_name, session, **kwargs)
        except AssumptionError as e:
            # 统计前提不满足，尝试非参数替代
            if skill_name == "t_test":
                logger.info("正态性不满足，降级为 Mann-Whitney U 检验")
                return await self.registry.execute("mann_whitney", session, **kwargs)
            elif skill_name == "anova":
                logger.info("方差齐性不满足，降级为 Kruskal-Wallis 检验")
                return await self.registry.execute("kruskal_wallis", session, **kwargs)
        except DataError as e:
            # 数据问题，尝试自动修复
            suggestion = self._diagnose_data_error(e)
            return SkillResult(success=False, message=f"数据问题: {suggestion}")
```

**优先级**: P1
**工作量**: 2-3 人日
**预期收益**:
- 减少用户手动重试
- 提升分析成功率

---

#### 方案 3.2.2: 可解释性增强

**设计理念**：
在事件流中新增"推理"事件类型，展示 Agent 的决策过程。

```python
class EventType(str, Enum):
    # ... 现有类型
    REASONING = "reasoning"  # 新增

# 使用示例
yield AgentEvent(
    type=EventType.REASONING,
    data={
        "step": "method_selection",
        "thought": "数据有3个分组，选择单因素ANOVA而非t检验",
        "alternatives": ["t检验 (需要恰好2组)", "Kruskal-Wallis (非参数替代)"],
        "rationale": "ANOVA适合比较3组以上均值差异"
    }
)
```

**UI 展示**：
- 折叠面板显示推理过程
- 高亮关键决策点
- 提供方法切换建议

**优先级**: P1
**工作量**: 2 人日
**预期收益**:
- 用户理解分析过程
- 增强对系统的信任

---

#### 方案 3.2.3: 成本透明化

**设计理念**：
在 UI 中实时展示 token 消耗和费用估算。

```python
# 前端显示示例
┌─────────────────────────────────────┐
│  会话统计                            │
│  ┌───────────────────────────────┐  │
│  │ Token 消耗: 12,345 / 50,000   │  │
│  │ 预估费用: ¥0.45               │  │
│  │ 分析次数: 8 次                │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**实现要点**：
1. WebSocket 推送 token 统计
2. 前端实时更新进度条
3. 超出预算时预警

**优先级**: P1
**工作量**: 1-2 人日

---

### 3.3 智能化优化方案（解决 P2 级别问题）

#### 方案 3.3.1: 结构化记忆压缩

**设计理念**：
将分析结果提取为结构化知识，而非简单文本摘要。

```python
@dataclass
class AnalysisMemory:
    """分析结果的结构化记忆"""
    session_id: str
    findings: list[dict]  # 关键发现
    statistics: dict      # 统计结果摘要
    decisions: list[dict] # 方法决策记录
    artifacts: list[str]  # 产出的文件

    def to_context(self) -> str:
        """转换为可注入的上下文"""
        return f"""
        之前分析发现: {self.findings}
        已使用的统计方法: {list(self.statistics.keys())}
        用户决策记录: {self.decisions}
        """
```

**优先级**: P2
**工作量**: 3 人日

---

#### 方案 3.3.2: 语义化知识检索

**设计理念**：
集成向量检索，理解用户意图的语义相似性。

```python
class HybridKnowledgeLoader:
    """混合检索 (关键词 + 向量)"""

    def select(self, query: str, **kwargs) -> str:
        # 1. 关键词检索 (精确匹配)
        keyword_results = self._keyword_search(query)

        # 2. 向量检索 (语义匹配)
        vector_results = self._vector_search(query)

        # 3. 融合排序
        return self._merge_and_rank(keyword_results, vector_results)
```

**优先级**: P2
**工作量**: 2-3 人日
**注意**: `vector_store.py` 已存在框架，需集成

---

#### 方案 3.3.3: 多模态数据支持

**设计理念**：
集成视觉模型，处理图片数据。

```python
class ImageAnalysisSkill(Skill):
    """图片数据提取技能"""

    name = "analyze_image"
    description = "从图片中提取数据和图表信息"

    async def execute(self, session, image_url):
        # 调用视觉模型 (如 GPT-4V)
        vision_result = await self._call_vision_model(image_url)

        # 提取表格/图表数据
        extracted_data = self._parse_chart_data(vision_result)

        # 保存为新数据集
        dataset_name = f"extracted_{uuid.uuid4().hex[:8]}"
        session.datasets[dataset_name] = extracted_data

        return SkillResult(
            success=True,
            message=f"已从图片提取数据，保存为数据集 '{dataset_name}'"
        )
```

**优先级**: P2
**工作量**: 3-4 人日
**依赖**: GPT-4V 或其他视觉模型 API

---

## 四、分阶段实施计划

### 第一阶段 (2周) - 解决 P0 核心问题

| 任务 | 工作量 | 优先级 | 输出 |
|------|--------|--------|------|
| 实现双层 Agent 架构 | 5-7 人日 | P0 | PlannerAgent + ExecutionPlan |
| 开发 3 个复合技能模板 | 3-5 人日 | P0 | complete_comparison, complete_anova, correlation_analysis |
| 实现用户画像系统 | 2-3 人日 | P0 | UserProfile + 集成 |
| 集成测试 | 2 人日 | P0 | 测试用例 + 验收 |

**里程碑**: 用户可以说"分析这两组的差异"，系统自动完成完整分析并生成可发表报告。

---

### 第二阶段 (1.5周) - 优化用户体验 (P1)

| 任务 | 工作量 | 优先级 | 输出 |
|------|--------|--------|------|
| 实现自我修复机制 | 2-3 人日 | P1 | 智能降级策略 |
| 增强可解释性 | 2 人日 | P1 | REASONING 事件 + UI |
| 成本透明化 | 1-2 人日 | P1 | Token 统计 UI |
| 测试与优化 | 1 人日 | P1 | 用户体验测试 |

**里程碑**: 系统能智能处理错误，展示推理过程，透明化成本。

---

### 第三阶段 (2周) - 智能化增强 (P2)

| 任务 | 工作量 | 优先级 | 输出 |
|------|--------|--------|------|
| 结构化记忆压缩 | 3 人日 | P2 | AnalysisMemory |
| 语义化知识检索 | 2-3 人日 | P2 | 混合检索 |
| 多模态支持 | 3-4 人日 | P2 | 图片分析技能 |
| 全面测试 | 2 人日 | P2 | 完整测试覆盖 |

**里程碑**: 系统具备长期记忆、语义理解和多模态能力。

---

## 五、向后兼容策略

所有优化都采用"渐进增强"策略，确保向后兼容：

1. **双层架构**: 无明确计划时自动降级为原 ReAct 模式
2. **复合技能**: 原子技能仍然可用，复合技能是"快捷方式"
3. **用户画像**: 默认提供通用配置，不影响现有用户
4. **API 兼容**: 所有现有 API 端点保持不变

---

## 六、风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 输出不稳定 | 规划质量下降 | 使用结构化输出 (JSON Schema) + 多轮验证 |
| 成本增加 | 用户负担加重 | 成本透明化 + 设置预算上限 |
| 性能下降 | 响应变慢 | 异步执行 + 流式响应 |
| 复杂度增加 | 维护困难 | 模块化设计 + 完整文档 |

---

## 七、成功指标

| 指标 | 当前 | 目标 | 测量方式 |
|------|------|------|----------|
| 单次分析平均对话轮次 | 5-7 轮 | 2-3 轮 | 日志统计 |
| 用户满意度 (NPS) | 未知 | >50 | 用户调研 |
| 分析成功率 | ~70% | >90% | 错误日志分析 |
| 平均响应时间 | 未知 | <30秒 | 性能监控 |

---

## 八、附录：代码位置索引

| 优化项 | 新增文件 | 修改文件 |
|--------|----------|----------|
| 双层架构 | `src/nini/agent/planner.py`, `src/nini/models/execution_plan.py` | `src/nini/agent/runner.py` |
| 复合技能 | `src/nini/skills/templates/` 目录 | `src/nini/skills/registry.py` |
| 用户画像 | `src/nini/models/user_profile.py`, `src/nini/agent/profile_manager.py` | `src/nini/agent/prompts/builder.py` |
| 自我修复 | 无 | `src/nini/skills/registry.py`, `src/nini/agent/runner.py` |
| 可解释性 | 无 | `src/nini/agent/runner.py`, 前端组件 |
| 成本透明 | 无 | WebSocket 事件, 前端组件 |
| 记忆压缩 | `src/nini/memory/structured_memory.py` | `src/nini/agent/runner.py` |
| 语义检索 | 无 | `src/nini/knowledge/loader.py` |
| 多模态 | `src/nini/skills/vision.py` | 无 |

---

**文档结束**
