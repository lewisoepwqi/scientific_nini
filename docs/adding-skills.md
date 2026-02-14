# 新增技能开发指南

本文档说明如何为 Nini 添加新技能，包括 Function Skill（Python 类）和 Markdown Skill（声明式文档）。

---

## 技能类型

| 类型 | 载体 | 适用场景 | 可被 LLM 调用 |
|------|------|----------|--------------|
| **Function Skill** | Python 类 | 需要执行代码、操作数据的场景 | 是（function calling） |
| **Markdown Skill** | Markdown 文件 | 提示词增强、工作流指导 | 否（注入系统提示词） |

## 标准分类

所有技能必须使用以下标准分类之一：

| 分类 | 说明 | 示例技能 |
|------|------|----------|
| `data` | 数据加载、预览、清洗、质量评估 | load_dataset, clean_data |
| `statistics` | 统计分析、检验、回归 | t_test, anova, correlation |
| `visualization` | 图表创建 | create_chart |
| `export` | 图表/数据导出 | export_chart |
| `report` | 报告生成 | generate_report |
| `workflow` | 工作流模板、复合分析 | save_workflow, complete_comparison |
| `utility` | 通用工具 | run_code, fetch_url, organize_workspace |
| `other` | 未分类（应尽量避免） | — |

---

## 方式一：使用 CLI 脚手架（推荐）

### 创建 Function Skill

```bash
nini skills create my_analysis --type function --category statistics --description "执行自定义分析"
```

生成文件：`src/nini/skills/my_analysis.py`

### 创建 Markdown Skill

```bash
nini skills create journal_checklist --type markdown --category report --description "期刊投稿检查清单"
```

生成文件：`skills/journal_checklist/SKILL.md`

### 查看已有技能

```bash
nini skills list                          # 全部技能（表格）
nini skills list --category statistics    # 按分类筛选
nini skills list --type markdown          # 按类型筛选
nini skills list --format json            # JSON 输出
```

### 导出技能定义

```bash
nini skills export --format mcp           # MCP 格式
nini skills export --format openai        # OpenAI Function 格式
nini skills export --format claude-code   # Claude Code Markdown 格式
nini skills export --format mcp -o tools.json  # 输出到文件
```

---

## 方式二：手动创建 Function Skill

### 1. 创建技能文件

在 `src/nini/skills/` 下创建 Python 文件，继承 `Skill` 基类：

```python
"""技能：我的分析技能"""

from __future__ import annotations
from typing import Any

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


class MyAnalysisSkill(Skill):
    """执行自定义分析。"""

    @property
    def name(self) -> str:
        return "my_analysis"  # 技能名称，snake_case

    @property
    def category(self) -> str:
        return "statistics"  # 必须为 VALID_CATEGORIES 之一

    @property
    def description(self) -> str:
        return "执行自定义统计分析"  # LLM 看到的功能描述

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称",
                },
                "column": {
                    "type": "string",
                    "description": "分析的目标列",
                },
            },
            "required": ["dataset_name", "column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs.get("dataset_name", "")
        column = kwargs.get("column", "")

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 未加载")

        # ... 执行分析逻辑 ...

        return SkillResult(
            success=True,
            message="分析完成",
            data={"result": "..."},
        )
```

### 2. 注册技能

在 `src/nini/skills/registry.py` 的 `create_default_registry()` 中添加：

```python
from nini.skills.my_analysis import MyAnalysisSkill

def create_default_registry() -> SkillRegistry:
    registry = SkillRegistry()
    # ... 现有注册 ...
    registry.register(MyAnalysisSkill())
    # ...
```

### 3. 添加测试

在 `tests/` 下创建测试文件：

```python
import pytest
import pandas as pd
from nini.agent.session import Session
from nini.skills.registry import create_default_registry


def test_my_analysis_registered():
    registry = create_default_registry()
    assert "my_analysis" in registry.list_skills()


@pytest.mark.asyncio
async def test_my_analysis_execution():
    registry = create_default_registry()
    session = Session()
    session.datasets["test.csv"] = pd.DataFrame({"col": [1, 2, 3]})

    result = await registry.execute(
        "my_analysis", session=session, dataset_name="test.csv", column="col"
    )
    assert result["success"] is True
```

---

## 方式三：手动创建 Markdown Skill

### 1. 创建技能目录和文件

在项目根目录 `skills/` 下创建：

```
skills/
  my_guide/
    SKILL.md
```

### 2. 编写 SKILL.md

**必须包含 YAML Frontmatter**，至少包含 `name` 和 `description`：

```markdown
---
name: my_guide
description: 自定义分析指南
category: workflow
---

# 自定义分析指南

## 适用场景

- 用户需要执行特定类型的分析时

## 步骤

1. 第一步：...
2. 第二步：...

## 注意事项

- 注意事项 1
- 注意事项 2
```

### 3. Frontmatter 字段

| 字段 | 必须 | 说明 |
|------|------|------|
| `name` | 是 | 技能名称（snake_case），缺失时回退到文件夹名 |
| `description` | 是 | 技能描述，缺失时回退到正文首行 |
| `category` | 否 | 分类（默认 `other`），必须为标准分类之一 |

Markdown Skill 会在启动时被自动扫描并注册，无需修改代码。

---

## SkillResult 返回值

Function Skill 的 `execute()` 方法返回 `SkillResult`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `message` | str | 结果消息（展示给用户） |
| `data` | Any | 结构化数据 |
| `has_chart` | bool | 是否包含图表 |
| `chart_data` | Any | Plotly JSON 图表数据 |
| `has_dataframe` | bool | 是否包含数据表 |
| `dataframe_preview` | Any | DataFrame 预览数据 |
| `artifacts` | list[dict] | 产物列表（文件路径等） |
| `metadata` | dict | 扩展元数据 |

---

## 可选属性

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `is_idempotent` | `False` | 是否幂等（多次调用结果相同） |
| `expose_to_llm` | `True` | 是否暴露给 LLM 作为工具。设为 `False` 可隐藏内部辅助技能 |

---

## 自检清单

新增技能前请确认：

- [ ] 技能名称为 snake_case 格式
- [ ] `category` 使用标准分类
- [ ] `parameters` 使用正确的 JSON Schema 格式
- [ ] `execute()` 方法处理了缺失数据集等边界情况
- [ ] 已添加单元测试
- [ ] 已在 `create_default_registry()` 中注册（Function Skill）
- [ ] 已运行 `pytest -q` 和 `black --check src tests` 确认无问题
