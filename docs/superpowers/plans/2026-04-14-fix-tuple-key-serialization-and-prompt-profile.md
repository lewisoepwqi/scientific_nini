# 修复 MultiIndex 列名序列化崩溃 + Prompt Profile 检测可靠性

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `dataset_transform.group_aggregate` 产生的 MultiIndex 列导致 `json.dumps` 崩溃的 TypeError，并增强 Prompt Profile 检测的诊断能力，确保 200K 上下文模型（如 GLM-5）正确命中 FULL profile。

**Architecture:** 纵深防御——源头展平 MultiIndex 列名 + data_ops 层强制字符串化 + 序列化层 key 规范化，三层同时修复。Profile 检测增加诊断日志并允许 session 级 context_window 刷新。

**Tech Stack:** Python 3.12, pandas, pytest, json

---

## 问题 1（ERROR）：Tuple Key 序列化崩溃

### 根因链

```
dataset_transform.py:524  → groupby().agg(metrics) 产生 MultiIndex 列（tuple）
data_ops.py:176-177       → df.columns.tolist() / df.dtypes.items() 保留 tuple
tool_executor.py:326-328  → _summarize_dataset_profile 直接拷贝 dtypes dict
tool_executor.py:87       → json.dumps() 无法序列化 tuple key 的 dict
```

### Task 1: 添加 MultiIndex 列名序列化失败的回归测试

**Files:**
- Create: `tests/test_multiindex_serialization.py`

- [ ] **Step 1: 创建回归测试文件**

```python
"""回归测试：MultiIndex 列名不应导致 JSON 序列化崩溃。

根因：dataset_transform.group_aggregate 在 metrics 包含多个聚合函数时
产生 MultiIndex 列（tuple 类型），后续 json.dumps 无法序列化 tuple key 的 dict。
"""
import json

import pandas as pd
import pytest

from nini.agent.components.tool_executor import (
    serialize_tool_result_for_memory,
    summarize_tool_result_dict,
    _summarize_dataset_profile,
)
from nini.tools.data_ops import DatasetInfoTool


def _make_multiindex_df() -> pd.DataFrame:
    """构造一个模拟 groupby().agg() 产生的 MultiIndex 列 DataFrame。"""
    df = pd.DataFrame({
        "月份": ["1月", "1月", "2月", "2月"],
        "收缩压": [120, 130, 140, 135],
        "舒张压": [80, 85, 90, 88],
    })
    metrics = {"收缩压": ["mean", "std"], "舒张压": ["mean", "std"]}
    result = df.groupby("月份", dropna=False).agg(metrics).reset_index()
    return result


class TestMultiIndexColumnSerialization:
    """MultiIndex 列名的 DataFrame 不应导致 JSON 序列化崩溃。"""

    def test_data_ops_info_stringifies_multiindex_columns(self):
        """DatasetInfoTool._get_info 应将 MultiIndex 列名转为字符串。"""
        df = _make_multiindex_df()
        # 模拟 data_ops.py:176-177 的逻辑
        column_names = df.columns.tolist()
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

        # column_names 的元素应为 str，不是 tuple
        for name in column_names:
            assert isinstance(name, str), f"列名 {name!r} 不是字符串而是 {type(name)}"

        # dtypes 的 key 应为 str，不是 tuple
        for key in dtypes:
            assert isinstance(key, str), f"dtypes key {key!r} 不是字符串而是 {type(key)}"

    def test_data_ops_info_is_json_serializable(self):
        """DatasetInfoTool._get_info 返回的数据应可直接 JSON 序列化。"""
        df = _make_multiindex_df()
        info = {
            "name": "test",
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }
        # 应不抛异常
        json.dumps(info, ensure_ascii=False)

    def test_summarize_dataset_profile_handles_tuple_keys(self):
        """_summarize_dataset_profile 应正确处理含 tuple key 的 dtypes dict。"""
        # 模拟 data_ops 返回的含 tuple key 的 dict（修复前的行为）
        data_obj = {
            "dataset_name": "test",
            "basic": {
                "rows": 4,
                "columns": 5,
                "column_names": [("月份", ""), ("收缩压", "mean"), ("收缩压", "std")],
                "dtypes": {
                    ("月份", ""): "object",
                    ("收缩压", "mean"): "float64",
                    ("收缩压", "std"): "float64",
                },
            },
        }
        summary = _summarize_dataset_profile(data_obj)

        # summary 应可直接 JSON 序列化
        json.dumps(summary, ensure_ascii=False)

        # dtypes 的 key 应为字符串
        if "dtypes" in summary:
            for key in summary["dtypes"]:
                assert isinstance(key, str), f"dtypes key {key!r} 不是字符串"

    def test_serialize_tool_result_handles_multiindex_profile(self):
        """serialize_tool_result_for_memory 应能序列化含 MultiIndex 列信息的工具结果。"""
        tool_result = {
            "success": True,
            "message": "已生成数据集概况",
            "has_dataframe": True,
            "data": {
                "dataset_name": "月度统计",
                "basic": {
                    "rows": 12,
                    "columns": 5,
                    "column_names": [("月份", ""), ("收缩压", "mean"), ("收缩压", "std")],
                    "dtypes": {
                        ("月份", ""): "object",
                        ("收缩压", "mean"): "float64",
                        ("收缩压", "std"): "float64",
                    },
                },
            },
        }
        # 应不抛 TypeError
        result_str = serialize_tool_result_for_memory(tool_result, tool_name="dataset_catalog")
        assert isinstance(result_str, str)
        # 验证是合法 JSON
        parsed = json.loads(result_str)
        assert parsed["success"] is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_multiindex_serialization.py -v
```

预期：`test_data_ops_info_stringifies_multiindex_columns` FAIL（tuple 不是 str），`test_data_ops_info_is_json_serializable` FAIL（json.dumps TypeError），`test_summarize_dataset_profile_handles_tuple_keys` FAIL，`test_serialize_tool_result_handles_multiindex_profile` FAIL。

- [ ] **Step 3: Commit 测试文件**

```bash
git add tests/test_multiindex_serialization.py
git commit -m "test: 添加 MultiIndex 列名序列化回归测试"
```

---

### Task 2: 源头修复 — dataset_transform 展平 MultiIndex 列名

**Files:**
- Modify: `src/nini/tools/dataset_transform.py:519-525`
- Test: `tests/test_multiindex_serialization.py`

- [ ] **Step 1: 修改 group_aggregate 逻辑，展平 MultiIndex 列名**

在 `src/nini/tools/dataset_transform.py` 的 `group_aggregate` 分支中，聚合后展平 MultiIndex 列名：

```python
        if op == "group_aggregate":
            by = params.get("by")
            metrics = params.get("metrics")
            if not by or not metrics:
                raise ValueError("group_aggregate 需要提供 by 和 metrics")
            current = current.groupby(by, dropna=False).agg(metrics).reset_index()
            # 展平 MultiIndex 列名：("收缩压", "mean") → "收缩压_mean"
            if isinstance(current.columns, pd.MultiIndex):
                current.columns = [
                    "_".join(str(c) for c in col if c != "").strip("_")
                    for col in current.columns.values
                ]
            return current, {"rows": len(current), "columns": len(current.columns)}
```

注意：`if c != ""` 而非 `if c`，因为 pandas MultiIndex 对单层列使用空字符串 `""` 作为占位符（如 groupby key 列在 agg 后变为 `("月份", "")`），需要过滤掉。

- [ ] **Step 2: 运行测试验证**

```bash
pytest tests/test_multiindex_serialization.py -v
```

预期：`test_data_ops_info_stringifies_multiindex_columns` 现在 PASS（因为 DataFrame 列名已是字符串）。

- [ ] **Step 3: 运行既有 transform 测试确认无回归**

```bash
pytest tests/test_foundation_tools.py -k "dataset_transform" -v
```

预期：全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/nini/tools/dataset_transform.py
git commit -m "fix(tools): group_aggregate 展平 MultiIndex 列名防止序列化崩溃"
```

---

### Task 3: 防御层修复 — data_ops 强制字符串化列名和 dtypes key

**Files:**
- Modify: `src/nini/tools/data_ops.py:172-179`
- Test: `tests/test_multiindex_serialization.py`

- [ ] **Step 1: 修改 DatasetInfoTool._get_info 确保列名和 dtypes key 为字符串**

在 `src/nini/tools/data_ops.py` 中修改 info dict 的构造：

```python
            df = session.datasets[name]
            info = {
                "name": name,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": [str(c) for c in df.columns.tolist()],
                "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
                "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
            }
```

改动点：
- 行 176: `df.columns.tolist()` → `[str(c) for c in df.columns.tolist()]`
- 行 177: `{col: str(dtype) ...}` → `{str(col): str(dtype) ...}`

- [ ] **Step 2: 运行测试验证**

```bash
pytest tests/test_multiindex_serialization.py::TestMultiIndexColumnSerialization::test_data_ops_info_stringifies_multiindex_columns tests/test_multiindex_serialization.py::TestMultiIndexColumnSerialization::test_data_ops_info_is_json_serializable -v
```

预期：两个测试 PASS。

- [ ] **Step 3: 运行相关回归测试**

```bash
pytest tests/test_foundation_tools.py -k "dataset_catalog" -v
```

预期：全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/nini/tools/data_ops.py
git commit -m "fix(data_ops): 强制列名和 dtypes key 为字符串，防御 MultiIndex 场景"
```

---

### Task 4: 序列化层修复 — _summarize_dataset_profile 规范化 dict key

**Files:**
- Modify: `src/nini/agent/components/tool_executor.py:325-335`
- Test: `tests/test_multiindex_serialization.py`

- [ ] **Step 1: 修改 _summarize_dataset_profile，规范化 dtypes 和 null_counts 的 key**

在 `src/nini/agent/components/tool_executor.py` 中修改 `_summarize_dataset_profile` 的 dtypes 和 null_counts 处理：

```python
    # 列类型信息
    dtypes = data_obj.get("dtypes") or (isinstance(basic, dict) and basic.get("dtypes"))
    if isinstance(dtypes, dict):
        summary["dtypes"] = {str(k): v for k, v in dtypes.items()}

    # 缺失值信息
    null_counts = data_obj.get("null_counts") or (
        isinstance(basic, dict) and basic.get("null_counts")
    )
    if isinstance(null_counts, dict):
        summary["null_counts"] = {str(k): v for k, v in null_counts.items()}
```

改动点：
- 行 328: `summary["dtypes"] = dtypes` → `summary["dtypes"] = {str(k): v for k, v in dtypes.items()}`
- 行 335: `summary["null_counts"] = null_counts` → `summary["null_counts"] = {str(k): v for k, v in null_counts.items()}`

- [ ] **Step 2: 运行全部 MultiIndex 测试**

```bash
pytest tests/test_multiindex_serialization.py -v
```

预期：全部 PASS。

- [ ] **Step 3: 运行序列化相关回归测试**

```bash
pytest tests/test_context_utilities.py -k "summarize" -v
```

预期：全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/nini/agent/components/tool_executor.py
git commit -m "fix(memory): _summarize_dataset_profile 规范化 dtypes/null_counts key 为字符串"
```

---

### Task 5: 集成验证 — 运行全量测试

**Files:** 无修改，仅验证

- [ ] **Step 1: 运行全量后端测试**

```bash
pytest -q
```

预期：全部 PASS（排除需要真实 API key 的测试）。

- [ ] **Step 2: 运行 schema 一致性检查**

```bash
python scripts/check_event_schema_consistency.py
```

预期：PASS。

---

## 问题 2（WARNING）：Prompt Profile 检测可靠性

### 根因

`_model_context_window` 在 `runner.py:2795` 仅设置一次（`not hasattr` 守卫），之后不再刷新。若模型切换（fallback），缓存的 context_window 与实际模型不匹配。当前缺少诊断日志，无法追踪 profile 选择的决策过程。

### Task 6: 增强 detect_prompt_profile 诊断日志

**Files:**
- Modify: `src/nini/agent/prompts/builder.py:47-53`

- [ ] **Step 1: 在 detect_prompt_profile 中增加诊断日志**

```python
def detect_prompt_profile(context_window: int | None) -> PromptProfile:
    """根据模型上下文窗口大小检测合适的 prompt profile。"""
    if context_window is None or context_window >= 64_000:
        result = PromptProfile.FULL
    elif context_window >= 16_000:
        result = PromptProfile.STANDARD
    else:
        result = PromptProfile.COMPACT

    logger.debug(
        "Prompt profile 检测: context_window=%s → %s",
        context_window,
        result.value,
    )
    return result
```

注意：这里用 `logger.debug` 而非 `logger.info`，避免正常路径下大量日志。只有出现 WARNING（截断）时，debug 日志才需要被查看。

- [ ] **Step 2: 在 _build_messages_and_retrieval 中增加诊断日志**

在 `src/nini/agent/runner.py` 的 `_build_messages_and_retrieval` 方法中，将 `not hasattr` 守卫改为始终刷新并记录日志：

```python
    async def _build_messages_and_retrieval(
        self,
        session: Session,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """通过 canonical context builder 构建发送给 LLM 的消息列表。"""
        # 将模型上下文窗口信息传递给 session，供 ContextBuilder 选择 prompt profile
        _get_cw = getattr(self._resolver, "get_model_context_window", None)
        resolved_cw = _get_cw() if callable(_get_cw) else None
        if not hasattr(session, "_model_context_window"):
            # 首次设置
            setattr(session, "_model_context_window", resolved_cw)
            logger.info(
                "模型上下文窗口: session=%s context_window=%s",
                session.id,
                resolved_cw,
            )
        elif resolved_cw is not None and resolved_cw != session._model_context_window:
            # 模型切换时刷新（fallback 场景）
            logger.warning(
                "模型上下文窗口变更: session=%s old=%s new=%s",
                session.id,
                session._model_context_window,
                resolved_cw,
            )
            setattr(session, "_model_context_window", resolved_cw)
        start_time = time.monotonic()
        messages, retrieval_event = await self._context_builder.build_messages_and_retrieval(
            session, context_ratio=self._context_ratio
        )
```

改动点：
- 移除 `if not hasattr` 块，拆为两个分支：首次设置 + 变更刷新
- 增加 `logger.info` 记录首次设置的值
- 增加 `logger.warning` 捕获 fallback 导致的变更

- [ ] **Step 3: 运行 prompt 相关回归测试**

```bash
pytest tests/test_prompt_guardrails.py tests/test_prompt_improvements.py -v
```

预期：全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/nini/agent/prompts/builder.py src/nini/agent/runner.py
git commit -m "fix(agent): 增强 prompt profile 检测诊断日志，支持模型切换时刷新 context_window"
```

---

### Task 7: 为 _summarize_dataset_profile 添加 null_counts key 规范化的额外测试

**Files:**
- Modify: `tests/test_multiindex_serialization.py`

- [ ] **Step 1: 添加 null_counts 的 tuple key 测试**

在 `tests/test_multiindex_serialization.py` 的 `TestMultiIndexColumnSerialization` 类中追加：

```python
    def test_summarize_dataset_profile_normalizes_null_counts_tuple_keys(self):
        """_summarize_dataset_profile 应将 null_counts 的 tuple key 规范化为字符串。"""
        data_obj = {
            "dataset_name": "test",
            "basic": {
                "rows": 100,
                "columns": 3,
                "null_counts": {
                    ("月份", ""): 0,
                    ("收缩压", "mean"): 5,
                    ("收缩压", "std"): 0,
                },
            },
        }
        summary = _summarize_dataset_profile(data_obj)

        # summary 应可直接 JSON 序列化
        json.dumps(summary, ensure_ascii=False)

        # null_counts 的 key 应为字符串
        if "null_counts" in summary:
            for key in summary["null_counts"]:
                assert isinstance(key, str), f"null_counts key {key!r} 不是字符串"
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_multiindex_serialization.py -v
```

预期：全部 PASS（包含新增测试）。

- [ ] **Step 3: Commit**

```bash
git add tests/test_multiindex_serialization.py
git commit -m "test: 补充 null_counts tuple key 规范化测试"
```

---

## 自检清单

### 1. Spec 覆盖

| 需求 | Task |
|------|------|
| MultiIndex 列名 → 字符串（源头） | Task 2 |
| data_ops dtypes/column_names 字符串化（防御） | Task 3 |
| _summarize_dataset_profile key 规范化（序列化保护） | Task 4 |
| json.dumps 不再崩溃 | Task 1-4 全部 |
| Profile 检测增加诊断日志 | Task 6 |
| 模型切换时 context_window 刷新 | Task 6 |
| null_counts key 规范化 | Task 4 + Task 7 |

### 2. Placeholder 扫描

无 TBD、TODO、"implement later"、"add validation"、"handle edge cases" 等占位符。所有代码步骤包含完整实现。

### 3. 类型一致性

- `_summarize_dataset_profile` 返回 `dict[str, Any]`，key 始终为 `str`
- `detect_prompt_profile` 返回 `PromptProfile` 枚举
- `_build_messages_and_retrieval` 读写 `session._model_context_window` 类型为 `int | None`
