# Fix Session Data Loading Bugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复会话 5fe0f8bebb0e 中发现的 5 个根因 bug，消除 `dataset_catalog load` 静默忽略 `sheet_name`、沙箱 `KeyError` 错误消息混淆、`DUPLICATE_DATASET_PROFILE_CALL` 过激拦截等问题。

**Architecture:** 
1. P0：`dataset_catalog._load_dataset` 在 `sheet_name` 存在且 `sheet_mode` 未显式指定时自动提升为 `sheet_mode="single"`，使 `load` 与 `profile` 行为一致。
2. P1：沙箱 `KeyError` 错误消息增强，携带诊断信息而非裸数字 `"0"`。
3. P2：`DUPLICATE_DATASET_PROFILE_CALL` 增加"列名全为 Unnamed"豁免条件，允许 LLM 继续用 `preview` 查看实际数据。

**Tech Stack:** Python 3.12, pandas 2.x, pytest, pytest-asyncio

---

## 文件清单

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `src/nini/tools/dataset_catalog.py` | Modify | P0 核心修复：`_load_dataset` 自动提升 `sheet_mode` |
| `src/nini/tools/dataset_catalog.py` | Modify | P0 描述修复：`sheet_name` 参数描述补充约束说明 |
| `src/nini/sandbox/executor.py` | Modify | P1：`KeyError` 专项 catch，生成可诊断的错误消息 |
| `src/nini/agent/runner.py` | Modify | P2：`full` profile 后检测"全 Unnamed"，豁免 preview 拦截 |
| `tests/test_excel_sheet_modes.py` | Modify | P0 测试：`load` 带 `sheet_name` 不显式 `sheet_mode` 时能正确加载目标 sheet |
| `tests/test_sandbox_error_messages.py` | Create | P1 测试：验证 `KeyError` 错误消息包含可诊断内容 |
| `tests/test_duplicate_profile_guard.py` | Create | P2 测试：验证"全 Unnamed"时 preview 不被拦截 |

---

## Task 1：P0 — `dataset_catalog load` 带 `sheet_name` 时自动启用 single 模式

**Files:**
- Modify: `src/nini/tools/dataset_catalog.py:171-207`（`_load_dataset` 方法）
- Modify: `src/nini/tools/dataset_catalog.py:71-75`（`sheet_name` 参数描述）
- Test: `tests/test_excel_sheet_modes.py`

### 背景
`_load_dataset` 目前将 `sheet_mode` 默认为 `"default"`，而 `LoadDatasetTool` 的 `sheet_mode="default"` 分支完全忽略 `sheet_name`，导致 LLM 传入 `sheet_name="ALL"` 却静默加载第一个 sheet。同样的 `sheet_name` 在 `_profile_dataset` 中能正确触发 `sheet_mode="single"`，两者行为不一致。

- [ ] **Step 1：写失败测试**

在 `tests/test_excel_sheet_modes.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_load_via_dataset_catalog_with_sheet_name_no_mode() -> None:
    """dataset_catalog load 传 sheet_name 但不传 sheet_mode 时，应加载指定 sheet 而非第一个 sheet。"""
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    # 先用 default 模式加载一次，确保 session.datasets 中缓存了第一个 sheet（SheetA）
    await registry.execute(
        "dataset_catalog",
        session=session,
        operation="load",
        dataset_name="multi.xlsx",
    )
    assert "multi.xlsx" in session.datasets
    assert list(session.datasets["multi.xlsx"].columns) == ["id", "value_a"]

    # 不传 sheet_mode，只传 sheet_name="SheetB"
    result = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="load",
        dataset_name="multi.xlsx",
        sheet_name="SheetB",
    )

    assert result["success"] is True, result.get("message")
    # 应输出 SheetB 而不是默认 SheetA
    output_name = result["data"]["dataset_name"]
    # 修复后 output_name 应为 "multi.xlsx[SheetB]"
    assert "SheetB" in output_name
    assert output_name in session.datasets
    df = session.datasets[output_name]
    assert list(df.columns) == ["id", "value_b"]
    assert df["id"].tolist() == [3, 4]
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_excel_sheet_modes.py::test_load_via_dataset_catalog_with_sheet_name_no_mode -v
```

预期：`FAILED`，因为当前 `_load_dataset` 忽略 `sheet_name`，`result["data"]["dataset_name"]` 为 `"multi.xlsx"`，不含 `"SheetB"`。

- [ ] **Step 3：实现修复**

修改 `src/nini/tools/dataset_catalog.py` 的 `_load_dataset` 方法（当前第 183-191 行）：

```python
async def _load_dataset(self, session: Session, **kwargs: Any) -> ToolResult:
    dataset_name = str(kwargs.get("dataset_name", "")).strip()
    if not dataset_name:
        return self._input_error(
            operation="load",
            error_code="DATASET_CATALOG_LOAD_DATASET_NAME_REQUIRED",
            message="load 操作必须提供 dataset_name",
            expected_fields=["operation", "dataset_name"],
            recovery_hint="先传入要加载的数据集名称；如需指定 Excel sheet，可继续补充 sheet_mode/sheet_name。",
            minimal_example=self._minimal_example_for_operation("load"),
        )

    sheet_name_raw = kwargs.get("sheet_name")
    raw_sheet_mode = kwargs.get("sheet_mode")

    # 若传入了 sheet_name 但未显式指定 sheet_mode，自动提升为 single 模式。
    # 这与 _profile_dataset 的行为一致，避免 sheet_name 被静默忽略。
    if sheet_name_raw and not raw_sheet_mode:
        effective_sheet_mode = "single"
    else:
        effective_sheet_mode = raw_sheet_mode or "default"

    result = await self._loader.execute(
        session,
        dataset_name=dataset_name,
        sheet_mode=effective_sheet_mode,
        sheet_name=sheet_name_raw,
        combine_sheets=kwargs.get("combine_sheets", False),
        include_sheet_column=kwargs.get("include_sheet_column", True),
        output_dataset_name=kwargs.get("output_dataset_name"),
    )
    if not result.success:
        return result

    target_name = dataset_name
    if isinstance(result.data, dict):
        target_name = str(result.data.get("output_dataset") or dataset_name)

    manager = WorkspaceManager(session)
    record = manager.get_dataset_by_name(target_name)
    payload = result.to_dict()
    data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    data["resource_id"] = (str(record.get("id", "")).strip() or None) if record else None
    data["resource_type"] = "dataset"
    data["dataset_name"] = target_name
    payload["data"] = data
    return ToolResult(**payload)
```

- [ ] **Step 4：同时修正 `sheet_name` 参数描述**

将 `src/nini/tools/dataset_catalog.py` 中的 `sheet_name` 参数描述（当前第 72-74 行）改为：

```python
"sheet_name": {
    "type": "string",
    "description": (
        "指定 Excel 工作表名称。"
        "用于 load 操作时：直接传入即可（无需额外指定 sheet_mode），系统自动以 single 模式加载；"
        "用于 profile 操作时：同样直接传入即可。"
    ),
},
```

- [ ] **Step 5：运行测试，确认通过**

```bash
pytest tests/test_excel_sheet_modes.py -v
```

预期：全部通过（含原有 4 个测试 + 新增 1 个）。

- [ ] **Step 6：运行 schema 一致性检查 + 全量测试**

```bash
python scripts/check_event_schema_consistency.py
pytest tests/test_excel_sheet_modes.py tests/test_foundation_tools.py -q
```

预期：0 errors，全部通过。

- [ ] **Step 7：提交**

```bash
git add src/nini/tools/dataset_catalog.py tests/test_excel_sheet_modes.py
git commit -m "fix(tools): dataset_catalog load 带 sheet_name 时自动启用 single 模式"
```

---

## Task 2：P1 — 沙箱 `KeyError` 错误消息可读化

**Files:**
- Modify: `src/nini/sandbox/executor.py:706-716`（`_sandbox_worker` 的 `except Exception` 块）
- Create: `tests/test_sandbox_error_messages.py`

### 背景
`row[j]`（`j` 为整数，`row` 是字符串索引的 pandas Series）在 pandas 2.x 中触发 `KeyError(0)`。
`str(KeyError(0))` = `"0"`，最终错误消息为 `"代码执行失败: 0"`，LLM 无法从中获取任何诊断信息。

需要对 `KeyError` 单独处理，生成包含"请用 `.iloc[j]`"的提示。

- [ ] **Step 1：写失败测试**

创建 `tests/test_sandbox_error_messages.py`：

```python
"""沙箱错误消息可读性测试。"""

from __future__ import annotations

import pytest
import pandas as pd

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.tools.code_runtime import execute_python_code


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.mark.asyncio
async def test_key_error_integer_on_string_indexed_series_gives_readable_message() -> None:
    """row[j] 对字符串索引 Series 应产生包含 iloc 提示的错误消息，而非裸 '0'。"""
    session = Session()
    session.datasets["test_df"] = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})

    code = """
row = df.iloc[0]   # Series with string index ["col_a", "col_b"]
val = row[0]       # KeyError(0) — integer label lookup on string index
"""

    result = await execute_python_code(session, code=code, dataset_name="test_df")

    assert result.success is False
    message = result.message
    # 不应该是裸 "代码执行失败: 0"
    assert message != "代码执行失败: 0", f"错误消息太模糊: {message!r}"
    # 应包含可诊断内容
    assert any(
        hint in message
        for hint in ("KeyError", "iloc", "整数", "列名", "label")
    ), f"错误消息应包含诊断提示，实际: {message!r}"
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_sandbox_error_messages.py::test_key_error_integer_on_string_indexed_series_gives_readable_message -v
```

预期：`FAILED`，message 为 `"代码执行失败: 0"`，断言 `message != "代码执行失败: 0"` 失败。

- [ ] **Step 3：实现修复**

修改 `src/nini/sandbox/executor.py` 中的 `_sandbox_worker` 函数，在 `except Exception` 块前增加 `KeyError` 专项捕获（当前第 706 行之前）：

```python
    except KeyError as exc:
        # KeyError 的 str() 仅返回 key 本身（如 "0"），极难诊断。
        # 为 LLM 生成包含操作建议的可读消息。
        key = exc.args[0] if exc.args else exc
        if isinstance(key, (int, float)):
            friendly = (
                f"KeyError: 列下标 {key!r} 不在数据中。"
                f"对字符串命名的列使用整数下标会触发此错误——"
                f"请改用 .iloc[{key}] 进行位置访问，或用列名字符串访问。"
            )
        else:
            friendly = f"KeyError: 键 {key!r} 不存在。请检查列名或字典键是否正确。"
        tb = traceback.format_exc()
        conn.send(
            {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": friendly,
                "traceback": tb,
            }
        )
    except Exception as exc:
        tb = traceback.format_exc()
        conn.send(
            {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": str(exc),
                "traceback": tb,
            }
        )
```

注意：`except KeyError` 必须放在 `except Exception` **之前**，因为 `KeyError` 是 `Exception` 的子类。

- [ ] **Step 4：运行测试，确认通过**

```bash
pytest tests/test_sandbox_error_messages.py -v
```

预期：PASS，message 包含 "iloc" 或 "KeyError"。

- [ ] **Step 5：运行全量相关测试**

```bash
pytest tests/test_sandbox_error_messages.py tests/test_foundation_tools.py tests/test_excel_sheet_modes.py -q
```

预期：全部通过，无回归。

- [ ] **Step 6：提交**

```bash
git add src/nini/sandbox/executor.py tests/test_sandbox_error_messages.py
git commit -m "fix(sandbox): KeyError 专项 catch，生成包含 .iloc 提示的可读错误消息"
```

---

## Task 3：P2 — `DUPLICATE_DATASET_PROFILE_CALL` 豁免"全 Unnamed 列"场景

**Files:**
- Modify: `src/nini/agent/runner.py:1825-1831`（`max_view == "full"` 分支）
- Create: `tests/test_duplicate_profile_guard.py`

### 背景
当 `profile(view=full)` 成功后，若数据集列名全为 `Unnamed: 0`, `Unnamed: 1`, ...，说明这是无头行的仪器导出文件，LLM 尚不知道实际数据内容。此时若 LLM 请求 `profile(view=preview)` 查看实际行数据，会被 `DUPLICATE_DATASET_PROFILE_CALL` 拦截，迫使其通过多轮 `code_session` 探索数据，造成不必要的工具调用。

修复：在 `max_view == "full"` 判断中增加豁免条件——若该数据集的列名全为 Unnamed 形式，则允许 `preview` 请求通过。

- [ ] **Step 1：写失败测试**

创建 `tests/test_duplicate_profile_guard.py`：

```python
"""DUPLICATE_DATASET_PROFILE_CALL 豁免条件测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from nini.agent.runner import _parse_dataset_profile_request


@pytest.mark.parametrize(
    "args_str, expected",
    [
        (
            '{"operation":"profile","dataset_name":"foo","view":"full"}',
            ("foo", "full"),
        ),
        (
            '{"operation":"profile","dataset_name":"bar","view":"preview"}',
            ("bar", "preview"),
        ),
        (
            '{"operation":"load","dataset_name":"foo"}',
            None,
        ),
        (
            '{"operation":"profile","dataset_name":"baz"}',
            ("baz", "basic"),  # 无 view 时默认 basic
        ),
    ],
)
def test_parse_dataset_profile_request(args_str, expected) -> None:
    result = _parse_dataset_profile_request(args_str)
    assert result == expected


def test_all_unnamed_columns_detection() -> None:
    """_all_columns_unnamed 应正确识别全 Unnamed 列名的 DataFrame。"""
    from nini.agent.runner import _all_columns_unnamed

    df_unnamed = pd.DataFrame(
        [[1, 2, 3]], columns=["Unnamed: 0", "Unnamed: 1", "Unnamed: 2"]
    )
    assert _all_columns_unnamed(df_unnamed) is True

    df_mixed = pd.DataFrame([[1, 2]], columns=["Unnamed: 0", "real_col"])
    assert _all_columns_unnamed(df_mixed) is False

    df_normal = pd.DataFrame([[1, 2]], columns=["col_a", "col_b"])
    assert _all_columns_unnamed(df_normal) is False

    df_empty = pd.DataFrame()
    assert _all_columns_unnamed(df_empty) is True  # 空 DataFrame 视为 unnamed（无列信息）
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_duplicate_profile_guard.py::test_all_columns_unnamed_detection -v
```

预期：`FAILED`，`ImportError: cannot import name '_all_columns_unnamed' from 'nini.agent.runner'`。

- [ ] **Step 3：在 runner.py 中添加辅助函数**

在 `src/nini/agent/runner.py` 中，在 `_parse_dataset_profile_request` 函数（当前第 360 行附近）之后添加：

```python
def _all_columns_unnamed(df: "pd.DataFrame") -> bool:
    """判断 DataFrame 是否所有列名均为 pandas 的默认 Unnamed 格式。

    用于豁免 DUPLICATE_DATASET_PROFILE_CALL 拦截：
    当列名全为 Unnamed 时，LLM 无法从 full profile 获知实际数据内容，
    需要允许其通过 preview 查看实际行数据。
    """
    import pandas as pd

    if not isinstance(df, pd.DataFrame) or df.empty or len(df.columns) == 0:
        return True
    return all(
        str(col).startswith("Unnamed:") for col in df.columns
    )
```

- [ ] **Step 4：运行辅助函数测试，确认通过**

```bash
pytest tests/test_duplicate_profile_guard.py::test_all_columns_unnamed_detection -v
```

预期：PASS。

- [ ] **Step 5：修改 runner.py 的拦截逻辑**

找到 `src/nini/agent/runner.py` 中 `max_view == "full"` 的判断块（当前第 1825-1831 行），修改为：

```python
                    elif max_view == "full":
                        # 豁免：若数据集列名全为 Unnamed（无标题行的仪器导出文件），
                        # LLM 从 full profile 中无法获知实际数据内容，
                        # 应允许其继续使用 preview 查看实际行数据。
                        dataset_is_all_unnamed = False
                        _cached_df = session.datasets.get(dataset_name)
                        if _cached_df is None:
                            # 尝试 [sheet] 格式的 key
                            for _k, _v in session.datasets.items():
                                if str(_k).startswith(f"{dataset_name}[") or _k == dataset_name:
                                    _cached_df = _v
                                    break
                        if _cached_df is not None:
                            dataset_is_all_unnamed = _all_columns_unnamed(_cached_df)

                        if not dataset_is_all_unnamed:
                            duplicate_profile_reason = (
                                f"同一轮中已成功获得数据集 '{dataset_name}' 的完整概况(full)，"
                                f"无需再次请求 {requested_view} 视图。"
                                "full 视图是 quality/summary 的超集，已包含所有质量指标。"
                                "请直接使用已获取的数据概况继续任务。"
                            )
```

- [ ] **Step 6：添加集成测试**

在 `tests/test_duplicate_profile_guard.py` 末尾追加以下集成测试：

```python
@pytest.mark.asyncio
async def test_preview_not_blocked_after_full_profile_when_all_unnamed(
    tmp_path: Path, monkeypatch
) -> None:
    """full profile 成功后，若列全为 Unnamed，preview 请求不应被拦截。"""
    from nini.agent.session import Session, session_manager
    from nini.config import settings
    from nini.tools.registry import create_default_tool_registry

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()

    registry = create_default_tool_registry()
    session = Session()

    # 准备列名全为 Unnamed 的数据集（模拟仪器导出 Excel）
    session.datasets["instrument.xlsx"] = pd.DataFrame(
        [["Software Version", "3.13"], ["Date", "2026-04-16"]],
        columns=["Unnamed: 0", "Unnamed: 1"],
    )

    # 第一次调用 full profile（正常成功）
    result_full = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="profile",
        dataset_name="instrument.xlsx",
        view="full",
    )
    assert result_full["success"] is True

    # 第二次调用 preview — 不应被 DUPLICATE 拦截
    # （需要通过 runner 的拦截逻辑，这里直接测试 _all_columns_unnamed 的豁免效果）
    from nini.agent.runner import _all_columns_unnamed
    assert _all_columns_unnamed(session.datasets["instrument.xlsx"]) is True

    session_manager._sessions.clear()
```

- [ ] **Step 7：运行全部新测试**

```bash
pytest tests/test_duplicate_profile_guard.py -v
```

预期：全部通过。

- [ ] **Step 8：运行回归测试**

```bash
python scripts/check_event_schema_consistency.py
pytest tests/test_duplicate_profile_guard.py tests/test_excel_sheet_modes.py tests/test_sandbox_error_messages.py tests/test_foundation_tools.py -q
```

预期：0 错误，全部通过。

- [ ] **Step 9：提交**

```bash
git add src/nini/agent/runner.py tests/test_duplicate_profile_guard.py
git commit -m "fix(agent): full profile 后列名全 Unnamed 时豁免 DUPLICATE_DATASET_PROFILE_CALL 拦截"
```

---

## Task 4：整体验证 + PR

**Files:** 无新增

- [ ] **Step 1：运行完整测试套件**

```bash
python scripts/check_event_schema_consistency.py && pytest -q
```

预期：schema 一致性通过，pytest 无失败（允许因 API key 缺失的 skip）。

- [ ] **Step 2：类型检查**

```bash
mypy src/nini
```

预期：0 errors。

- [ ] **Step 3：格式检查**

```bash
black --check src tests
```

如有格式问题：`black src tests`，重新运行。

- [ ] **Step 4：最终提交（如有格式修正）**

```bash
git add -p   # 只加格式修正
git commit -m "chore: black 格式化"
```

- [ ] **Step 5：创建 PR**

```bash
git push -u origin fix/session-data-loading-bugs
gh pr create \
  --title "fix: 修复数据加载三个核心 bug（sheet_name 静默忽略 / KeyError 消息混淆 / profile 过激拦截）" \
  --body "$(cat <<'EOF'
## 变更内容

修复会话 5fe0f8bebb0e 中分析出的 3 个根因 bug：

### P0：`dataset_catalog load` 静默忽略 `sheet_name`
- `dataset_catalog._load_dataset`：当传入 `sheet_name` 但未显式指定 `sheet_mode` 时，自动提升为 `sheet_mode="single"`
- 修正 `sheet_name` 参数描述，明确说明无需额外指定 `sheet_mode`

### P1：沙箱 `KeyError` 错误消息可读化
- `_sandbox_worker`：新增 `except KeyError` 专项捕获，生成包含 `.iloc[j]` 建议的提示
- 消除 `"代码执行失败: 0"` 这类无信息量的错误输出

### P2：`DUPLICATE_DATASET_PROFILE_CALL` 过激拦截
- 列名全为 Unnamed（仪器导出文件）时，`full` profile 完成后豁免 `preview` 拦截
- 新增 `_all_columns_unnamed()` 辅助函数

## 验证方式

```bash
python scripts/check_event_schema_consistency.py
pytest tests/test_excel_sheet_modes.py tests/test_sandbox_error_messages.py tests/test_duplicate_profile_guard.py -v
```

## 风险与回滚

- `_load_dataset` 的 `sheet_mode` 自动提升：仅在 `sheet_name` 非空且 `sheet_mode` 未显式传入时触发，向后兼容
- `KeyError` 专项捕获：不影响其他异常类型，可单独回滚 `executor.py`
- profile 豁免逻辑：仅增加放行条件，不收紧拦截，最坏情况是允许了本可拦截的重复调用
EOF
)"
```

---

## 自检清单

### Spec 覆盖确认

| 根因 | 对应 Task |
|------|-----------|
| RC1：`load` 静默忽略 `sheet_name` | Task 1 |
| RC2：`sheet_name` 参数描述误导 | Task 1 Step 4 |
| RC3：`KeyError(0)` → "代码执行失败: 0" | Task 2 |
| RC4（连锁）：硬编码路径 | 由 RC3 触发，RC3 修复后消除根因 |
| RC5：`capthick` 重复传递 | **LLM 代码生成层面的偶发错误，不在代码层面修复** |
| RC6：`DUPLICATE_DATASET_PROFILE_CALL` 过激 | Task 3 |

RC5（`capthick`）是 LLM 生成的 matplotlib 代码错误，属于单次偶发，不在工具层面有系统性修复点，故不单独设 Task。

### 类型一致性

- Task 1 修改 `_load_dataset`：`effective_sheet_mode: str`，传入 `self._loader.execute(sheet_mode=effective_sheet_mode)` — 与原调用签名一致 ✓
- Task 2 新增 `except KeyError`：位于 `except Exception` 之前，不改变其他分支 ✓
- Task 3 新增 `_all_columns_unnamed`：接收 `pd.DataFrame`，返回 `bool`，在 runner.py 顶层函数级别定义，无循环依赖 ✓
