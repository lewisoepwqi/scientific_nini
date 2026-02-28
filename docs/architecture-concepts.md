# Nini 三层架构概念说明

本文档澄清 Nini 项目中 **Tools**、**Capabilities** 和 **Skills** 三个核心概念的区别与联系。

## 概览

| 层级 | 定位 | 技术形态 | 目标用户 |
|------|------|----------|----------|
| **Tools** | 原子函数 | Python 类（继承 `Skill` 基类） | AI 模型 |
| **Capabilities** | 能力封装 | 元数据（`Capability` dataclass） | 终端用户 |
| **Skills** | 工作流项目 | 目录（Markdown + 脚本 + 资源） | 开发者/高级用户 |

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
class TTestSkill(Skill):
    name = "t_test"
    description = "执行 t 检验比较两组数据"
    parameters = {...}

    async def execute(self, session, **kwargs) -> SkillResult:
        # 执行统计检验
        return SkillResult(success=True, data={...})
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

**API 访问**：
- `GET /api/skills` - 列出所有 Skills
- `GET /api/skills/markdown/{name}` - 获取 Skill 详情
- 前端有专门的"技能管理"面板（BookOpen 图标）

---

## 4. 对比总结

| 维度 | Tools | Capabilities | Skills |
|------|-------|--------------|--------|
| **粒度** | 原子操作 | 业务场景 | 完整项目 |
| **用户** | AI 模型 | 终端用户 | 开发者/高级用户 |
| **代码** | Python 类 | 元数据定义 | Markdown + 脚本 |
| **存储** | `tools/` 目录 | `capabilities/` 模块 | `skills/` 目录 |
| **注册** | ToolRegistry | CapabilityRegistry | 文件系统扫描 |
| **调用** | WebSocket tool_call | HTTP API / Agent 编排 | 人工触发/Agent 识别 |

---

## 5. 使用场景

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

## 6. 前端界面映射

| 界面元素 | 对应概念 | 图标 |
|----------|----------|------|
| 分析能力面板 | Capabilities | 紫色 Sparkles |
| 工具清单 | Tools | 灰色 Wrench |
| 技能管理 | Skills | 灰色 BookOpen |

---

## 7. 迁移历史

### Phase 1（已完成）

- ✅ `SkillRegistry` → `ToolRegistry`（重命名，保持兼容）
- ✅ `skills/` 目录含义明确为"工作流项目"
- ✅ 新建 `capabilities/` 模块
- ✅ 差异分析 Capability 完整实现

### 后续规划

- 更多 Capability 实现（相关性分析、回归分析等）
- Skill 与 Capability 的关联机制
- Capability 的参数自动生成（基于所需 Tools 的参数聚合）
