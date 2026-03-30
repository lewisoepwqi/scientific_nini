# Nini 三层架构概念说明

本文档澄清 Nini 项目中 **Tools**、**Capabilities** 和 **Skills** 三个核心概念的区别与联系，并介绍能力成熟度模型、风险分级与阶段归属。

> 相关纲领文档：`docs/nini-vision-charter.md`
> Skill 执行契约详细规范：`docs/skill-contract-spec.md`

## 概览

| 层级 | 定位 | 技术形态 | 目标用户 |
|------|------|----------|----------|
| **Tools** | 原子函数 | Python 类（继承 `Tool` 基类） | AI 模型 |
| **Capabilities** | 领域能力编排 | 元数据（`Capability` dataclass） | 终端用户 |
| **Skills** | 工作流模板 | 目录（Markdown + 脚本 + 资源），含步骤 DAG、降级策略与人工复核门 | 开发者/高级用户 |

三层架构不加新层——Skill 层吸收 Recipe 理念，演进为契约驱动的工作流模板层。

## 工具基础层（Tool Foundation）

自 consolidate-tool-foundation 变更后，工具层采用**基础工具层 + 内部编排层**架构：

### 基础工具层（9个核心工具）

模型可见的工具收敛为9个基础工具，降低选择成本：

| 工具名 | 职责 | 替代的旧工具 |
|--------|------|--------------|
| `task_state` | 任务状态管理 | - |
| `dataset_catalog` | 数据集目录与加载 | `load_dataset`, `preview_data` |
| `dataset_transform` | 结构化数据转换 | `clean_data`（部分） |
| `stat_test` | 统计检验 | `t_test`, `anova`, `mann_whitney`, `kruskal_wallis` |
| `stat_model` | 统计建模 | `correlation`, `regression` |
| `stat_interpret` | 结果解读 | `interpretation` |
| `chart_session` | 图表会话管理 | `create_chart`, `export_chart` |
| `report_session` | 报告会话管理 | `generate_report`, `export_report` |
| `workspace_session` | 工作区文件操作 | `fetch_url`, 文件读写 |
| `code_session` | 脚本会话管理 | `run_code`, `run_r_code` |

### 内部编排层

复杂分析流程（如完整差异分析、ANOVA、相关分析、回归分析）改为内部编排层实现，通过组合基础工具完成，不再作为与基础工具同级的模型接口暴露。

### 统一资源标识

所有基础工具遵循统一的资源契约：

- **创建资源时**：返回 `resource_id`、`resource_type`、`name`
- **引用资源时**：优先使用 `resource_id` 而非文本名称
- **资源类型**：`dataset`、`file`、`script`、`chart`、`report`、`stat_result`、`transform`、`artifact`

### 脚本会话生命周期

`code_session` 提供完整的脚本生命周期管理：

1. `create_script` - 创建脚本资源
2. `run_script` - 执行脚本
3. `patch_script` - 局部修补（失败恢复）
4. `rerun` - 重试执行（保留上下文）
5. `promote_output` - 提升输出为正式资源

---

## 1. Tools（工具）

**定位**：模型可调用的原子函数

**特点**：
- 单一职责，如执行 t 检验、创建图表、加载数据
- 暴露给 LLM 的 function calling 接口
- 有明确的输入参数和输出格式

**示例**：
```python
# tools/statistics/t_test.py
class TTestSkill(Tool):
    name = "t_test"
    description = "执行 t 检验比较两组数据"
    parameters = {...}

    async def execute(self, session, **kwargs) -> ToolResult:
        # 执行统计检验
        return ToolResult(success=True, data={...})
```

**注册方式**：
```python
# tools/registry.py
registry.register(TTestSkill())
```

**API 访问**：
- `GET /api/tools` - 列出所有 Tools
- 通过 WebSocket tool_call 调用

---

## 2. Capabilities（能力）

**定位**：用户层面的"能力"标签

**特点**：
- 面向终端用户的概念，如"差异分析"、"相关性分析"
- 编排多个 Tools 完成特定业务场景
- 包含 UI 元数据（图标、显示名称、描述）

**示例**：
```python
# capabilities/defaults.py
Capability(
    name="difference_analysis",
    display_name="差异分析",
    description="比较两组或多组数据的差异",
    icon="🔬",
    required_tools=["t_test", "mann_whitney", "anova", ...],
    suggested_workflow=["data_summary", "t_test", "create_chart"],
)
```

**与 Tools 的关系**：
- Capability 知道它需要哪些 Tools
- 但 Tools 不知道自己是哪个 Capability 的一部分
- 一个 Capability 可以编排多个 Tools

**API 访问**：
- `GET /api/capabilities` - 列出所有 Capabilities
- `GET /api/capabilities/{name}` - 获取单个 Capability
- `POST /api/capabilities/{name}/execute` - 执行 Capability

**前端展示**：
- 紫色 Sparkles 图标按钮打开 CapabilityPanel
- 卡片式展示，按类别分组

---

## 3. Skills（技能）

**定位**：完整的工作流项目

**特点**：
- 包含 Markdown 文档、可执行脚本、参考文档、示例数据
- 是 Capabilities 的"实现"或"模板"
- 可以包含 Python/R 脚本、Jinja 模板、批量处理工具

**目录结构**：
```
skills/root-analysis/
├── SKILL.md                 # 元数据和说明文档
├── scripts/
│   ├── generate_r_project.py    # R 项目生成器
│   ├── batch_analysis.py        # 批量分析工具
│   ├── validate_data.py         # 数据验证脚本
│   └── r_templates/             # R 脚本模板
├── references/
│   ├── statistical_methods.md   # 统计方法说明
│   ├── data_format.md          # 数据格式规范
│   └── customization.md        # 自定义指南
└── assets/
    └── example_data.csv        # 示例数据
```

**SKILL.md 结构**：
```yaml
---
name: root-analysis
description: 植物根长度数据的自动化统计分析
category: statistics
agents: [nini, claude-code]
tags: [root-length, anova, tukey-hsd]
aliases: [根长分析, 根系分析]
allowed-tools: [load_dataset, run_code, run_r_code, create_chart]
user-invocable: true
---

# 植物根长度分析

使用ANOVA方差分析...
```

**与 Capabilities 的关系**：
- Skill 是 Capability 的"落地实现"
- 例如：Capability 是"差异分析"这个概念，Skill 是"植物根长分析"这个具体实现
- 一个 Capability 可以对应多个 Skills（不同领域的实现）

**Skill 执行契约**：

现有 Markdown Skills 已具备元数据和自然语言工作流描述，通过提示词注入引导 LLM 执行。Skill 执行契约在此基础上增量演进，新增以下能力：

- **步骤 DAG**：结构化步骤定义（`tool` / `capability` / `review_gate`），替代纯提示词驱动
- **风险等级**：`low` / `medium` / `high` / `critical`
- **可信度天花板**：`trust_ceiling`（T1 / T2 / T3），运行时输出不得超过此上限
- **降级策略**：插件不可用或步骤失败时的备选行为，降级后必须同步降低可信度并提示用户
- **人工复核门**：高风险输出进入可审阅或可导出前必须由人工确认

纯提示词驱动的低风险 Skill 可以继续按现有方式运行，无需强制升级。

> 完整规范见 `docs/skill-contract-spec.md`

**API 访问**：
- `GET /api/skills` - 列出所有 Skills
- `GET /api/skills/markdown/{name}` - 获取 Skill 详情
- 前端有专门的"技能管理"面板（BookOpen 图标）

---

## 4. 能力成熟度与风险分级

### 4.1 自动化等级（Lx）

| 等级 | 名称 | 定义 | Agent 行为特征 |
|------|------|------|----------------|
| **L1** | 智能对话 | 给出专业建议，不直接操作数据/文件 | 基于知识库和推理提供建议 |
| **L2** | 辅助编排 | 通过代码执行 + 提示词引导完成任务 | 调用代码执行、生成结构化文档、调用插件 |
| **L3** | 深度原生 | 有专用工具链，端到端可执行并产出标准化产物 | 专用 Tool 链、标准化输出模板 |

### 4.2 可信度等级（Tx）

| 等级 | 名称 | 定义 | 对应输出等级 |
|------|------|------|-------------|
| **T1** | 草稿级 | 本地知识或通用推理生成，仅供参考 | O1 建议级、O2 草稿级 |
| **T2** | 可审阅级 | 有来源支撑、结构较完整，适合人工审阅 | O3 可审阅级 |
| **T3** | 可复核级 | 过程可审计、证据较完整、可用于标准化导出 | O4 可导出级 |

### 4.3 输出等级

| 等级 | 名称 | 定义 | 用户预期 |
|------|------|------|----------|
| **O1** | 建议级 | 方向性意见，仅供参考 | 需要用户独立判断 |
| **O2** | 草稿级 | 可编辑初稿，结构较完整 | 需要用户修改和补充 |
| **O3** | 可审阅级 | 方法与来源信息较完整，适合人工审阅 | 需要专业人员复核 |
| **O4** | 可导出级 | 结构化产物达到导出标准 | 仍需人工终审 |

### 4.4 风险等级

能力按对研究结果、合规或用户决策的潜在影响分为四级：

| 风险等级 | 定义 | 默认可信度上限 |
|----------|------|----------------|
| **低** | 错误主要影响表达和效率，不直接影响研究判断 | T2 |
| **中** | 错误会影响草稿质量或资料完整性 | T2 |
| **高** | 错误会影响研究方法、统计判断或投稿策略 | T2 |
| **极高** | 错误可能影响患者安全、伦理合规或重大研究结论 | T1 或 T2 |

> Skill 的输出可信度不得超过其声明的 `trust_ceiling`。

### 4.5 八大研究阶段

Nini 的能力覆盖从选题到传播的完整科研闭环：

| 阶段 | 代号 | V1 成熟度 | 风险等级 |
|------|------|-----------|----------|
| ① 选题立项 | `topic_selection` | L1 / T1 | 低 |
| ② 文献调研 | `literature_review` | L2 / T2 | 中 |
| ③ 实验设计 | `experiment_design` | L2 / T2 | 高 |
| ④ 数据采集 | `data_collection` | L1 / T1 | 低 |
| ⑤ 数据分析 | `data_analysis` | L3 / T3 | 高 |
| ⑥ 论文写作 | `paper_writing` | L2 / T2 | 中 |
| ⑦ 投稿修回 | `submission` | L1 / T1 | 高 |
| ⑧ 学术传播 | `dissemination` | L1 / T1 | 低 |

## 5. 对比总结

| 维度 | Tools | Capabilities | Skills |
|------|-------|--------------|--------|
| **粒度** | 原子操作 | 领域能力编排 | 工作流模板 |
| **用户** | AI 模型 | 终端用户 | 开发者/高级用户 |
| **代码** | Python 类 | 元数据定义 | Markdown + 脚本 |
| **存储** | `tools/` 目录 | `capabilities/` 模块 | `skills/` 目录 |
| **注册** | ToolRegistry | CapabilityRegistry | 文件系统扫描 |
| **调用** | WebSocket tool_call | HTTP API / Agent 编排 | 人工触发/Agent 识别 |
| **阶段归属** | 不限定 | `phase` 字段标注 | `phase` 字段标注 |
| **风险等级** | 不标注 | `risk_level` 字段 | `risk_level` 字段 |
| **工作流类型** | 不适用 | `workflow_type` 字段 | 步骤 DAG |

---

## 6. 使用场景

### 场景 1：用户说"帮我分析两组数据的差异"

**流程**：
1. **Agent** 识别意图 → 匹配到 `difference_analysis` **Capability**
2. **Agent** 查看 Capability 的 `suggested_workflow` → 知道需要调用哪些 **Tools**
3. 依次调用 `data_summary` → `t_test` → `create_chart` **Tools**
4. 如果用户上传的是植物根长数据，Agent 可能推荐 `root-analysis` **Skill**

### 场景 2：开发者添加新的分析类型

**决策**：
- 如果只是现有 Tools 的新组合 → 添加 **Capability**
- 如果需要新的统计方法 → 添加 **Tool**
- 如果需要完整项目模板（脚本、文档、批量处理）→ 添加 **Skill**

---

## 7. 前端界面映射

| 界面元素 | 对应概念 | 图标 |
|----------|----------|------|
| 分析能力面板 | Capabilities | 紫色 Sparkles |
| 工具清单 | Tools | 灰色 Wrench |
| 技能管理 | Skills | 灰色 BookOpen |

---

## 8. 迁移历史

### Phase 1：三层架构确立（已完成）

- ✅ `SkillRegistry` → `ToolRegistry`（重命名，保持兼容）
- ✅ `skills/` 目录含义明确为"工作流项目"
- ✅ 新建 `capabilities/` 模块
- ✅ 差异分析 Capability 完整实现

### Phase 2：工具层收敛与能力扩展（已完成）

- ✅ 工具层从分散的独立工具收敛为 9 个基础工具 + 内部编排层（`dataset_catalog`、`stat_test`、`stat_model`、`chart_session`、`code_session` 等）
- ✅ 统一资源标识（`resource_id` + `resource_type`）
- ✅ 脚本会话生命周期管理（`code_session`：create → run → patch → rerun → promote）
- ✅ Capability 从 1 个扩展到 11 个（数据分析 6 个 + 全流程扩展 5 个），其中 5 个可直接执行
- ✅ 工作流类 Tool（`complete_comparison`、`complete_anova`、`correlation_analysis`、`regression_analysis`）
- ✅ 新增 `article_draft`、`citation_management`、`peer_review`、`research_planning` 等全流程 Capability

### Phase 3：Markdown Skill 体系与科研全流程扩展（已完成）

- ✅ Markdown Skill 扫描/注册/触发/启停管理机制
- ✅ YAML frontmatter 元数据（name、description、category、tags、allowed-tools）
- ✅ 7 个实际 Skill：`root-analysis`、`article-draft`、`publication_figure`、`writing-guide`、`experiment-design-helper`、`literature-review`、`literature_chart_driven_analysis`
- ✅ Recipe Center 模板（实验设计、文献综述、结果解读）
- ✅ 9 个 Specialist Agent（文献检索/精读、数据清洗、统计分析、可视化、写作、引用管理、研究规划、评审辅助）
- ✅ 分析阶段识别（`detect_phase`）
- ✅ 多 Agent 并行调度（`dispatch_agents`）
- ✅ 学术文献检索（`search_literature`，Semantic Scholar + CrossRef 降级）

### Phase 4：可信度与治理基础设施（已完成）

- ✅ 证据链系统（`query_evidence`、结论到证据的映射查询）
- ✅ 研究画像（研究领域、常用方法、输出语言、样本量偏好）
- ✅ 成本透明（Token 跟踪、USD/CNY 换算、模型分项、成本预警）
- ✅ 推理可解释性（思考过程、决策理由、推理类型、置信度展示）
- ✅ 插件系统框架（`plugins/base.py`、`plugins/registry.py`、`plugins/network.py`）
- ✅ 知识库（文档上传、混合检索、层次化索引）
- ✅ 长期记忆（跨会话提取、去重、重要性评分、向量搜索）
- ✅ 风险模型（研究阶段、风险等级、输出等级建模）
- ✅ 可信输出与人工复核交互规范（`docs/trust-output-and-human-review-interaction-spec.md`）

### 当前方向：契约驱动与 V1 能力落地

根据 `docs/nini-vision-charter.md` 第七章路线图：

- Capability 新增 `phase`（阶段归属）、`workflow_type`（工作流类型）、`risk_level`（风险等级）字段
- Skill 层演进为契约驱动的工作流模板层（步骤 DAG、降级策略、人工复核门、可观测事件流）
- 高风险能力三维评审流程落地（方法/边界/安全合规）
- 重点推进实验设计（L2/T2）、文献调研（L2/T2）、论文写作（L2/T2）三个首发场景
