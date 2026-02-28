# Capability 开发指南

本文档指导开发者如何在 Nini 中创建新的 Capability。

## 前置条件

- 熟悉 Python 3.12+
- 理解 Nini 三层架构（Tools/Capabilities/Skills）
- 阅读 `architecture-concepts.md`

---

## 创建新 Capability 的步骤

### 步骤 1：定义 Capability 元数据

在 `capabilities/defaults.py` 中添加 Capability 定义：

```python
# capabilities/defaults.py

Capability(
    name="correlation_analysis",           # 内部标识，唯一
    display_name="相关性分析",              # 展示名称
    description="探索变量之间的相关关系",    # 简短描述
    icon="📈",                             # UI 图标（emoji）
    required_tools=[                       # 该能力所需的 Tools
        "load_dataset",
        "data_summary",
        "correlation",
        "create_chart",
    ],
    suggested_workflow=[                   # 推荐执行顺序
        "data_summary",
        "correlation",
        "create_chart",
    ],
)
```

### 步骤 2：实现 Capability 执行类（可选）

如果 Capability 需要复杂的编排逻辑，创建执行类：

```python
# capabilities/implementations/correlation_analysis.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from nini.capabilities.implementations.difference_analysis import (
    DifferenceAnalysisResult,  # 可以复用或创建新的 Result 类
)


@dataclass
class CorrelationAnalysisResult:
    """相关性分析结果。"""
    success: bool = False
    message: str = ""

    # 数据特征
    n_variables: int = 0
    variable_names: list[str] = field(default_factory=list)

    # 分析结果
    correlation_matrix: dict[str, Any] = field(default_factory=dict)
    significant_pairs: list[dict[str, Any]] = field(default_factory=list)

    # 可视化
    chart_artifact: dict[str, Any] | None = None

    # 解释
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "n_variables": self.n_variables,
            "variable_names": self.variable_names,
            "correlation_matrix": self.correlation_matrix,
            "significant_pairs": self.significant_pairs,
            "chart_artifact": self.chart_artifact,
            "interpretation": self.interpretation,
        }


class CorrelationAnalysisCapability:
    """相关性分析能力。"""

    def __init__(self, registry: Any | None = None) -> None:
        self.name = "correlation_analysis"
        self.display_name = "相关性分析"
        self.description = "探索变量之间的相关关系"
        self.icon = "📈"
        self._registry = registry

    def _get_registry(self) -> Any:
        """获取工具注册中心。"""
        if self._registry is not None:
            return self._registry
        from nini.tools.registry import create_default_tool_registry
        return create_default_tool_registry()

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        variables: list[str] | None = None,  # 要分析的变量，None 表示全部数值列
        method: str = "pearson",             # pearson, spearman, kendall
        alpha: float = 0.05,
        **kwargs: Any,
    ) -> CorrelationAnalysisResult:
        """执行相关性分析。"""
        result = CorrelationAnalysisResult()

        # Step 1: 数据验证
        df = session.datasets.get(dataset_name)
        if df is None:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return result

        # Step 2: 确定分析变量
        if variables is None:
            variables = df.select_dtypes(include=["number"]).columns.tolist()

        result.n_variables = len(variables)
        result.variable_names = variables

        # Step 3: 执行相关性分析
        registry = self._get_registry()
        stat_result = await registry.execute(
            "correlation",
            session,
            dataset_name=dataset_name,
            variables=variables,
            method=method,
        )

        # Step 4: 提取结果
        if isinstance(stat_result, dict):
            if not stat_result.get("success"):
                result.message = f"分析失败: {stat_result.get('message')}"
                return result
            data = stat_result.get("data", {})
        else:
            if not stat_result.success:
                result.message = f"分析失败: {stat_result.message}"
                return result
            data = stat_result.data

        result.correlation_matrix = data.get("correlation_matrix", {})

        # Step 5: 创建热力图
        chart_result = await registry.execute(
            "create_chart",
            session,
            dataset_name=dataset_name,
            chart_type="heatmap",
            title="相关性矩阵热力图",
        )

        if isinstance(chart_result, dict):
            if chart_result.get("success"):
                result.chart_artifact = chart_result.get("artifacts", [{}])[0]
        elif chart_result.success:
            result.chart_artifact = chart_result.artifacts[0] if chart_result.artifacts else None

        # Step 6: 生成解释
        result.interpretation = self._generate_interpretation(result)
        result.success = True
        result.message = "相关性分析完成"

        return result

    def _generate_interpretation(self, result: CorrelationAnalysisResult) -> str:
        """生成解释性报告。"""
        parts = []
        parts.append("## 相关性分析结果")
        parts.append(f"分析了 {result.n_variables} 个变量的相关性")

        # 添加具体解释...

        return "\n".join(parts)
```

### 步骤 3：添加到 `__init__.py`

```python
# capabilities/implementations/__init__.py

from nini.capabilities.implementations.correlation_analysis import (
    CorrelationAnalysisCapability,
    CorrelationAnalysisResult,
)

__all__ = [
    "DifferenceAnalysisCapability",
    "DifferenceAnalysisResult",
    "CorrelationAnalysisCapability",
    "CorrelationAnalysisResult",
]
```

### 步骤 4：添加 API 端点（可选）

如果需要 HTTP API 直接调用：

```python
# api/routes.py

@router.post("/capabilities/{name}/execute", response_model=APIResponse)
async def execute_capability(
    name: str,
    session_id: str,
    params: dict[str, Any],
):
    # ... 现有代码 ...

    if name == "correlation_analysis":
        from nini.capabilities.implementations import CorrelationAnalysisCapability
        capability = CorrelationAnalysisCapability(registry=tool_registry)
        result = await capability.execute(
            session,
            dataset_name=params.get("dataset_name"),
            variables=params.get("variables"),
            method=params.get("method", "pearson"),
            alpha=params.get("alpha", 0.05),
        )
        return APIResponse(
            success=result.success,
            data=result.to_dict(),
            message=result.message if not result.success else None,
        )
```

### 步骤 5：添加测试

```python
# tests/test_correlation_analysis_capability.py

import pytest
import pandas as pd
import numpy as np

from nini.agent.session import Session
from nini.capabilities.implementations import (
    CorrelationAnalysisCapability,
    CorrelationAnalysisResult,
)


@pytest.fixture
def sample_data_session():
    """创建包含示例数据的会话。"""
    np.random.seed(42)

    # 创建相关数据
    x = np.random.normal(0, 1, 100)
    y = x * 0.7 + np.random.normal(0, 0.5, 100)  # 与 x 相关
    z = np.random.normal(0, 1, 100)  # 独立

    df = pd.DataFrame({"x": x, "y": y, "z": z})

    session = Session()
    session.datasets["test_data"] = df
    return session


@pytest.fixture
def capability():
    from nini.tools.registry import create_default_tool_registry
    registry = create_default_tool_registry()
    return CorrelationAnalysisCapability(registry=registry)


class TestCorrelationAnalysisCapability:
    @pytest.mark.asyncio
    async def test_basic_analysis(self, capability, sample_data_session):
        result = await capability.execute(
            sample_data_session,
            dataset_name="test_data",
            variables=["x", "y", "z"],
        )

        assert isinstance(result, CorrelationAnalysisResult)
        assert result.success
        assert result.n_variables == 3
        assert "x" in result.variable_names
```

---

## 设计原则

### 1. 单一职责

- **Capability** 负责：用户意图理解、工作流编排、结果解释
- **Tool** 负责：具体执行、数据计算

### 2. 依赖注入

Capability 应该通过构造函数接收 ToolRegistry：

```python
def __init__(self, registry: Any | None = None):
    self._registry = registry

def _get_registry(self) -> Any:
    if self._registry is not None:
        return self._registry
    from nini.tools.registry import create_default_tool_registry
    return create_default_tool_registry()
```

这使得测试时可以传入 mock registry。

### 3. 结果封装

每个 Capability 应该有自己的 Result 类：

```python
@dataclass
class MyAnalysisResult:
    success: bool = False
    message: str = ""
    # ... 具体字段

    def to_dict(self) -> dict[str, Any]:
        return { ... }
```

### 4. 错误处理

- 验证失败：返回 `success=False` 并设置 `message`
- 执行异常：捕获并转为友好的错误信息
- 部分成功：根据业务决定是返回部分结果还是失败

### 5. 结果解释

每个 Capability 应该生成人类可读的解释：

```python
def _generate_interpretation(self, result: MyResult) -> str:
    parts = []
    parts.append("## 分析结果")
    # ... 根据结果生成解释
    return "\n".join(parts)
```

---

## 与 Tools 的交互模式

### 模式 1：顺序执行

```python
# 数据加载 -> 预处理 -> 分析 -> 可视化
await registry.execute("load_dataset", session, ...)
await registry.execute("clean_data", session, ...)
await registry.execute("t_test", session, ...)
await registry.execute("create_chart", session, ...)
```

### 模式 2：条件执行

```python
# 根据数据特征选择方法
if is_normal:
    await registry.execute("t_test", session, ...)
else:
    await registry.execute("mann_whitney", session, ...)
```

### 模式 3：并行执行

```python
# 同时执行多个独立的分析
results = await asyncio.gather(
    registry.execute("correlation", session, ...),
    registry.execute("anova", session, ...),
)
```

---

## 常见问题

### Q: Capability 和 Tool 的界限在哪里？

**A**:
- 如果功能可以被模型直接调用（原子操作）→ Tool
- 如果需要编排多个步骤、解释结果、面向用户 → Capability

### Q: 已有 Tool 还需要 Capability 吗？

**A**:
- Tool 是底层实现
- Capability 是用户层面的封装
- 两者相辅相成，不冲突

### Q: 如何决定 Capability 的粒度？

**A**:
- 参考用户语言：用户说"做差异分析" → 一个 Capability
- 避免过细：不要把每个 Tool 都包装成 Capability
- 避免过粗：不要把所有统计分析合并成一个 Capability

---

## 参考实现

完整的参考实现请查看：

- `capabilities/base.py` - Capability 基类
- `capabilities/defaults.py` - 默认能力定义
- `capabilities/implementations/difference_analysis.py` - 差异分析实现
- `tests/test_difference_analysis_capability.py` - 测试示例
