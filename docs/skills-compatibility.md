# Nini Skills 与 Claude Code Skills 兼容性分析

## 概述

本文档分析 Nini 内置技能系统与 Claude Code Skills 的架构差异，并提出统一技能描述协议（Skill Manifest）的设计方案。

---

## 架构对比

| 维度 | Nini Skills | Claude Code Skills |
|------|-------------|-------------------|
| **载体** | Python 类（继承 `Skill` 基类） | Markdown 文件（`.md`） |
| **执行方式** | LLM 通过 function calling 调用 → 代码执行 | LLM 解释 Markdown 描述 → 使用内置工具执行 |
| **参数定义** | JSON Schema（`parameters` 属性） | 自然语言描述 |
| **输出格式** | 结构化 `SkillResult`（data、chart、artifacts） | 文本响应 + 工具调用结果 |
| **注册机制** | `SkillRegistry.register()` | 文件系统发现（`~/.claude/skills/`） |
| **调用协议** | OpenAI function calling | `Skill` 工具 + skill 名称 |
| **状态访问** | 直接访问 `Session` 对象（DataFrame、上下文） | 通过 Read/Write/Bash 工具间接访问文件系统 |

## Nini Skills 架构详情

### 基类接口

```python
class Skill(ABC):
    name: str           # 技能名称（工具调用标识）
    description: str    # 技能描述（LLM 理解用）
    parameters: dict    # JSON Schema 参数定义
    is_idempotent: bool # 是否幂等

    async def execute(session: Session, **kwargs) -> SkillResult
    def get_tool_definition() -> dict  # OpenAI function calling 格式
    def to_manifest() -> SkillManifest # 导出为统一清单
```

### 内置技能清单（12 个）

| 技能 | 分类 | 描述 |
|------|------|------|
| `load_dataset` | 数据操作 | 加载会话中的数据集 |
| `preview_data` | 数据操作 | 预览数据集前 N 行 |
| `data_summary` | 数据操作 | 生成数据集统计摘要 |
| `t_test` | 统计分析 | t 检验（独立/配对/单样本） |
| `anova` | 统计分析 | 单因素方差分析 + Tukey HSD |
| `correlation` | 统计分析 | 相关性分析（Pearson/Spearman/Kendall） |
| `regression` | 统计分析 | 回归分析（线性/多元/逻辑） |
| `create_chart` | 可视化 | 创建交互式图表 |
| `export_chart` | 导出 | 导出图表为图片文件 |
| `clean_data` | 数据操作 | 数据清洗与预处理 |
| `generate_report` | 报告 | 生成分析报告 |
| `run_code` | 代码执行 | 在沙箱中执行 Python 代码 |

## Claude Code Skills 架构详情

### 特点

- **声明式**：Markdown 文件描述工作流程和上下文，不包含可执行代码
- **工具依赖**：依赖 Claude Code 的内置工具（Read、Write、Bash、Grep 等）
- **无结构化参数**：通过自然语言传递参数（`args` 字符串）
- **无状态**：不直接访问应用状态，通过文件系统间接交互

### 示例结构

```markdown
# skill-name

Use this skill when [trigger description].

## Workflow

1. Step one description
2. Step two description

## Context

- Relevant background information
- File patterns to look for
```

## 核心差异分析

### 不可直接互通的原因

1. **执行模型不同**：Nini Skills 是编程接口（function calling），Claude Code Skills 是提示词模板
2. **状态模型不同**：Nini Skills 直接操作内存中的 DataFrame，Claude Code Skills 通过文件 I/O
3. **参数传递不同**：JSON Schema vs 自然语言字符串
4. **输出格式不同**：结构化 SkillResult vs 文本流

### 可互通的层面

1. **技能描述**：两者都有名称、描述、使用场景——可以统一为 Skill Manifest
2. **能力发现**：两者都需要让 LLM 了解可用技能——可以统一文档格式
3. **使用示例**：两者都受益于示例驱动——可以共享示例库

## 统一技能描述协议（Skill Manifest）

### 设计目标

- 不强制互通两个运行时，而是统一**技能描述层**
- Nini Skills 可导出为 Claude Code 可读的文档
- Claude Code Skills 的描述可导入为 Nini 的提示词增强

### SkillManifest 数据类

```python
@dataclass
class SkillManifest:
    name: str                          # 技能名称
    description: str                   # 功能描述
    parameters: dict[str, Any]         # JSON Schema 参数（可选）
    category: str                      # 分类（数据操作/统计分析/可视化/导出）
    examples: list[str]                # 使用示例
    is_idempotent: bool               # 是否幂等
    output_types: list[str]           # 输出类型（chart/dataframe/report/artifact）
```

### 导出为 Claude Code 格式

`export_to_claude_code(manifest)` 将 SkillManifest 转换为 Markdown：

```markdown
# t_test

执行 t 检验。支持三种模式...

**分类**: 统计分析

## 参数

- **dataset_name** (`string`) （必填）: 数据集名称
- **value_column** (`string`) （必填）: 数值列名
- **group_column** (`string`) （可选）: 分组列名

## 使用示例

- 对 treatment 组和 control 组做独立样本 t 检验
- 检验某列均值是否等于 0

**输出类型**: data
```

### 从 Markdown 导入

`import_from_markdown(md_content)` 解析 Markdown 并生成 SkillManifest，用于：

- 将外部技能描述注入 Nini 的系统提示词
- 丰富 LLM 对可用工具的理解

## 使用方式

### 导出所有 Nini Skills

```python
from nini.skills.registry import create_default_registry
from nini.skills.manifest import export_to_claude_code

registry = create_default_registry()
for name in registry.list_skills():
    skill = registry.get(name)
    manifest = skill.to_manifest()
    md = export_to_claude_code(manifest)
    print(md)
```

### 在 Claude Code 中引用

将导出的 Markdown 放入 `.claude/skills/` 目录，Claude Code 会自动发现并在匹配场景下建议使用。

## 未来演进方向

1. **双向同步**：Nini CLI 命令 `nini skills export --format=claude-code` 自动生成
2. **MCP 桥接**：通过 MCP Server 将 Nini Skills 暴露为 Claude Code 可调用的工具
3. **混合执行**：Claude Code 通过 MCP 调用 Nini 后端执行统计分析，结合自身工具处理文件
