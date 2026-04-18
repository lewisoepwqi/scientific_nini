# 会话 03fe97617ddf 问题修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复会话 03fe97617ddf 暴露的 5 个问题：Excel sheet 大小写敏感、沙箱返回 `fig` 时的模糊错误、prompt 对 `result = fig` 的引导缺失、总结未内嵌 artifact、GLM-5 输出非标准 Markdown 表格分隔行。

**Architecture:** 纯后端修复：`data_ops` 加一层大小写不敏感解析；`sandbox.executor` 在子进程侧拦截非白名单 result 类型并回传结构化提示；两个 prompt 组件文件新增明确规则；新增 `utils/markdown_fixups` 在 `build_text_event` 出口做表格分隔行的兜底修复。所有改动向后兼容，不改变事件 schema。

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, pandas, pydantic v2。

**前置说明：** 本计划建议在 `feature/fix-session-03fe97617ddf-issues` 分支执行（CLAUDE.md 强制），单独 PR 提交。

---

## 文件结构

| 文件 | 角色 | 动作 |
|---|---|---|
| `src/nini/tools/data_ops.py` | Excel sheet 加载 | 修改：`sheet_mode=single` 前对 `sheet_name` 大小写不敏感解析 |
| `tests/test_excel_sheet_modes.py` | Excel sheet 测试 | 修改：补充大小写不敏感测试 |
| `src/nini/sandbox/executor.py` | 沙箱执行器 | 修改：子进程侧对 `result_obj` 做类型白名单校验，非法类型用结构化字符串替代 |
| `tests/test_sandbox_error_messages.py` | 沙箱错误测试 | 修改：补充 `result = fig` 场景的断言 |
| `data/prompt_components/strategy_sandbox.md` | 沙箱策略 prompt 组件 | 修改：新增 "不要 `result = fig`" 规则 |
| `data/prompt_components/strategy_visualization.md` | 可视化策略 prompt 组件 | 修改：新增 "总结中用 `![](download_url)` 引用 artifact" 规则 |
| `src/nini/utils/markdown_fixups.py` | Markdown 兜底工具 | 新建：`fix_markdown_table_separator(text) -> str` |
| `src/nini/agent/event_builders.py` | 事件构造器 | 修改：`build_text_event` 调用 `fix_markdown_table_separator` |
| `tests/test_markdown_fixups.py` | Markdown 工具测试 | 新建：表格分隔行修复的 TDD 测试 |

---

## Task 1: Excel sheet 名称大小写不敏感解析

**Files:**
- Modify: `src/nini/tools/data_ops.py:204-219`
- Test: `tests/test_excel_sheet_modes.py`（末尾追加）

背景：会话中用户写 `sheet_name="all"`，实际为 `"ALL"`，`read_excel_sheet_dataframe` 抛 `Worksheet 'all' not found`。在调用前先做大小写不敏感匹配。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_excel_sheet_modes.py`：

```python
@pytest.mark.asyncio
async def test_load_dataset_sheet_name_case_insensitive() -> None:
    """sheet_name 大小写不一致时应自动解析到真实 sheet 名。"""
    session = session_manager.create_session()
    _prepare_multi_sheet_excel(session)

    registry = create_default_tool_registry()
    load_tool = registry.get_tool("load_dataset")
    assert load_tool is not None

    # 真实 sheet 为 "SheetA"，用户写小写 "sheeta"
    result = await load_tool.execute(
        session,
        dataset_name="multi.xlsx",
        sheet_mode="single",
        sheet_name="sheeta",
    )

    assert result.success, result.message
    assert isinstance(result.data, dict)
    assert result.data["sheet_name"] == "SheetA"  # 解析到真实名称
    assert result.data["output_dataset"] == "multi.xlsx[SheetA]"


@pytest.mark.asyncio
async def test_load_dataset_sheet_name_not_found_lists_available() -> None:
    """不存在的 sheet 名应在错误消息中提示可用 sheet 列表。"""
    session = session_manager.create_session()
    _prepare_multi_sheet_excel(session)

    registry = create_default_tool_registry()
    load_tool = registry.get_tool("load_dataset")
    assert load_tool is not None

    result = await load_tool.execute(
        session,
        dataset_name="multi.xlsx",
        sheet_mode="single",
        sheet_name="does_not_exist",
    )

    assert not result.success
    assert "可用 sheet" in result.message
    assert "SheetA" in result.message
    assert "SheetB" in result.message
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_excel_sheet_modes.py::test_load_dataset_sheet_name_case_insensitive -v`
Expected: FAIL，报 `Worksheet named 'sheeta' not found`。

- [ ] **Step 3: 在 `data_ops.py` 中加入大小写不敏感解析**

将 `src/nini/tools/data_ops.py` 第 204-219 行的 `sheet_mode == "single"` 分支替换为：

```python
        if sheet_mode == "single":
            try:
                available_sheets = list_excel_sheet_names(file_path, ext)
            except Exception:
                available_sheets = []
            if not isinstance(sheet_name_raw, str) or not sheet_name_raw.strip():
                extra = f"；可用 sheet: {', '.join(available_sheets)}" if available_sheets else ""
                return ToolResult(
                    success=False, message=f"sheet_mode=single 时必须提供 sheet_name{extra}"
                )
            sheet_name = sheet_name_raw.strip()

            # 大小写不敏感解析：若 sheet_name 与 available_sheets 里某项忽略大小写相等，替换为真实名
            if available_sheets and sheet_name not in available_sheets:
                lowered = sheet_name.lower()
                matches = [s for s in available_sheets if s.lower() == lowered]
                if len(matches) == 1:
                    sheet_name = matches[0]

            try:
                df_sheet = read_excel_sheet_dataframe(file_path, ext, sheet_name=sheet_name)
            except Exception as exc:
                extra = f"；可用 sheet: {', '.join(available_sheets)}" if available_sheets else ""
                return ToolResult(success=False, message=f"读取 sheet 失败: {exc}{extra}")
```

不改其他内容。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_excel_sheet_modes.py -v`
Expected: 所有测试 PASS（含新加两条）。

- [ ] **Step 5: 提交**

```bash
git add src/nini/tools/data_ops.py tests/test_excel_sheet_modes.py
git commit -m "fix(data_ops): Excel sheet 名称大小写不敏感解析"
```

---

## Task 2: 沙箱 result 对象类型白名单 + 清晰错误

**Files:**
- Modify: `src/nini/sandbox/executor.py`（子进程 `_execute_in_sandbox` 体内 `_try_pickleable` 调用前）
- Test: `tests/test_sandbox_error_messages.py`

背景：用户脚本写 `result = fig`（matplotlib Figure），父进程 `_RestrictedUnpickler` 抛 `不允许从沙箱反序列化类型: matplotlib.figure.Figure`，外层 catch 包成模糊的 "沙箱返回了不允许的数据类型"。模型看不到具体类型，难以恢复。修复方向：在**子进程侧**就检测到非法类型，把 `result_obj` 替换为结构化字符串提示；父进程侧的 fallback 兜底报错消息也写清楚。

- [ ] **Step 1: 写失败测试**

在 `tests/test_sandbox_error_messages.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_result_as_matplotlib_figure_returns_hint(tmp_path: Path) -> None:
    """result = fig 时，沙箱应返回结构化提示而不是模糊错误。"""
    from nini.sandbox.executor import SandboxExecutor

    executor = SandboxExecutor(timeout_seconds=30)
    code = (
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.bar([1, 2, 3], [4, 5, 6])\n"
        "result = fig\n"
    )
    outcome = await executor.execute(code=code, datasets={}, working_dir=tmp_path)

    assert outcome["success"] is True, outcome
    # result 不应是 Figure 对象；应被替换为含提示的字符串
    result_repr = str(outcome.get("result") or "")
    assert "Figure" in result_repr
    assert "result = fig" in result_repr  # 提示语包含正确写法
    # 图表仍然通过 figures 通道导出
    assert outcome.get("figures"), "matplotlib Figure 应被自动收集到 figures 通道"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sandbox_error_messages.py::test_result_as_matplotlib_figure_returns_hint -v`
Expected: FAIL 或 ERROR，取决于 `SandboxExecutor.execute` 的错误包装；当前行为是父进程抛异常或返回 `success=False, error="沙箱返回了不允许的数据类型"`。

- [ ] **Step 3: 在子进程 result 序列化路径加入类型白名单**

查看 `src/nini/sandbox/executor.py` 现有 `_try_pickleable` 与 `_collect_figures`，在 `_try_pickleable` 旁新增辅助函数（放在 `_try_pickleable` 正下方）：

```python
def _sanitize_result_for_transport(value: Any) -> Any:
    """拦截 result 对象中不适合跨进程传输的类型（如 Figure），替换为结构化提示。

    白名单：None/bool/int/float/complex/str/bytes/list/tuple/dict/set/
    pandas.DataFrame/Series/Index, numpy.ndarray, datetime 族。
    其他类型（尤其是 matplotlib/plotly Figure、Axes）一律改为带修复建议的字符串。
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, complex, str, bytes, bytearray)):
        return value
    if isinstance(value, (list, tuple, dict, set, frozenset)):
        return value
    if isinstance(value, (pd.DataFrame, pd.Series, pd.Index)):
        return value
    if isinstance(value, np.ndarray):
        return value

    cls_name = type(value).__name__
    module_name = type(value).__module__ or ""
    if module_name.startswith("matplotlib") and cls_name in {"Figure", "Axes", "SubFigure"}:
        return (
            f"[沙箱提示] 检测到 result 被赋值为 matplotlib {cls_name} 对象，这是常见错误。"
            "图表会通过 figures 通道自动导出，不要写 `result = fig`。"
            "如需返回数据，请把 result 设为 DataFrame/字符串/数字/None。"
        )
    if module_name.startswith("plotly") and cls_name == "Figure":
        return (
            "[沙箱提示] 检测到 result 被赋值为 plotly Figure 对象。"
            "图表会通过 figures 通道自动导出，不要写 `result = fig`。"
        )

    return (
        f"[沙箱提示] result 类型 {module_name}.{cls_name} 不在允许跨进程传输的白名单内，"
        "已自动转为文本；如需把结果传给后续步骤，请赋值为 DataFrame、字符串、数字、list/dict 等 JSON 可表达类型。"
    )
```

把现有构造 payload 的位置：

```python
        payload = {
            "success": True,
            ...
            "result": _try_pickleable(result_obj),
            ...
        }
```

改为：

```python
        payload = {
            "success": True,
            ...
            "result": _try_pickleable(_sanitize_result_for_transport(result_obj)),
            ...
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_sandbox_error_messages.py::test_result_as_matplotlib_figure_returns_hint -v`
Expected: PASS。

- [ ] **Step 5: 同时更新父进程兜底错误消息**

找到 `src/nini/sandbox/executor.py` 第 889-894 和 906-911 两处 `"error": "沙箱返回了不允许的数据类型"`，改为：

```python
                    payload = {
                        "success": False,
                        "error": (
                            "沙箱返回了不允许的数据类型（跨进程反序列化被拒绝）。"
                            "常见原因：代码里写了 `result = fig`（matplotlib/plotly Figure 对象）。"
                            "请去掉该赋值——图表会通过 figures 通道自动导出。"
                        ),
                        "stdout": "",
                        "stderr": "",
                    }
```

两处都改（保持一致）。

- [ ] **Step 6: 跑完整沙箱测试套确保无回归**

Run: `pytest tests/test_sandbox_error_messages.py tests/test_sandbox_executor_observability.py -v`
Expected: 所有 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/nini/sandbox/executor.py tests/test_sandbox_error_messages.py
git commit -m "fix(sandbox): result 对象类型白名单 + Figure 场景清晰提示"
```

---

## Task 3: prompt 组件 `strategy_sandbox.md` 补充 `result = fig` 警示

**Files:**
- Modify: `data/prompt_components/strategy_sandbox.md:18-21`

背景：现有"图表自动导出机制"段落说了 "不要手动 savefig"，但没禁止 `result = fig`。本次事故正是此遗漏。

- [ ] **Step 1: 修改组件文件**

定位 `data/prompt_components/strategy_sandbox.md` 中的段落：

```markdown
### 图表自动导出机制

- **不要手动调用 `plt.savefig()` 或 `fig.write_image()`**。沙箱执行完毕后会自动检测所有 Figure 对象并导出。
- 使用 code_session 绘图时，设置 `purpose='visualization'` 并提供 `label` 描述图表用途。
```

替换为：

```markdown
### 图表自动导出机制

- **不要手动调用 `plt.savefig()` 或 `fig.write_image()`**。沙箱执行完毕后会自动检测所有 Figure 对象并导出。
- **不要写 `result = fig`**。Figure 对象不可跨进程传输；图表会通过独立的 figures 通道自动导出。若需返回数据，把 result 赋值为 DataFrame/字符串/数字即可；不需要返回时直接不赋值 result。
- 使用 code_session 绘图时，设置 `purpose='visualization'` 并提供 `label` 描述图表用途。
```

- [ ] **Step 2: 跑上下文相关测试确认 prompt 可正确加载**

Run: `pytest tests/test_context_components.py -v`
Expected: PASS（若无此测试则跳过本步）。

- [ ] **Step 3: 提交**

```bash
git add data/prompt_components/strategy_sandbox.md
git commit -m "docs(prompt): 禁止 result = fig 写法"
```

---

## Task 4: prompt 组件 `strategy_visualization.md` 补充 artifact 引用规则

**Files:**
- Modify: `data/prompt_components/strategy_visualization.md`（末尾追加段落）

背景：会话最终总结只有文字描述，未用 Markdown 图片语法引用已生成的 artifact。模型缺乏显式指令。

- [ ] **Step 1: 在文件末尾追加新段落**

在 `data/prompt_components/strategy_visualization.md` 末尾追加（保留原有全部内容）：

```markdown

最终总结引用规则（必须遵循）：
- 当本轮已通过 code_session/chart_session 生成 artifact（type=chart）时，最终总结文本中必须用 Markdown 图片语法引用：`![简短描述](<artifact.download_url>)`。
- 引用必须放在与该图表直接相关的分析段落附近，而不是统一堆在末尾。
- 若同一图表有多种格式（png/svg/pdf），优先引用 png。
- 不要在总结中复述所有生成过程；用户看得到事件流，只需引用结果。
```

- [ ] **Step 2: 提交**

```bash
git add data/prompt_components/strategy_visualization.md
git commit -m "docs(prompt): 最终总结必须引用已生成 artifact"
```

---

## Task 5: Markdown 表格分隔行兜底修复

**Files:**
- Create: `src/nini/utils/markdown_fixups.py`
- Modify: `src/nini/agent/event_builders.py:551-565`
- Test: `tests/test_markdown_fixups.py`（新建）

背景：GLM-5 输出 `|:|:|:|:|:|:|` 分隔行，不符合 GFM。Prompt 层 `strategy_core.md` 已有相应规则但模型仍违反。在事件出口做幂等正则兜底。

- [ ] **Step 1: 写测试（新建文件）**

创建 `tests/test_markdown_fixups.py`：

```python
"""Markdown 兜底修复测试。"""

from __future__ import annotations

from nini.utils.markdown_fixups import fix_markdown_table_separator


def test_fix_colon_only_separator_to_left_aligned() -> None:
    """|:|:|:| 应被修复为 |:---|:---|:---|。"""
    src = (
        "| a | b | c |\n"
        "|:|:|:|\n"
        "| 1 | 2 | 3 |\n"
    )
    out = fix_markdown_table_separator(src)
    assert "|:---|:---|:---|" in out
    assert "|:|:|:|" not in out


def test_fix_bare_colon_and_dash_mix() -> None:
    """|:|---|:| 里只修复单冒号单元，不动合规单元。"""
    src = "|:|---|:|"
    out = fix_markdown_table_separator(src)
    assert out == "|:---|---|:---|"


def test_preserves_valid_separators() -> None:
    """合规分隔行不变。"""
    src = "|:---|:---:|---:|"
    assert fix_markdown_table_separator(src) == src


def test_non_separator_lines_untouched() -> None:
    """正文中的 |:| 若非分隔行不动。"""
    src = "some text with |:| inside that is not a table separator"
    assert fix_markdown_table_separator(src) == src


def test_idempotent() -> None:
    """函数幂等，反复调用结果相同。"""
    src = "| a | b |\n|:|:|\n| 1 | 2 |\n"
    once = fix_markdown_table_separator(src)
    twice = fix_markdown_table_separator(once)
    assert once == twice


def test_empty_and_none_safe() -> None:
    assert fix_markdown_table_separator("") == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_markdown_fixups.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'nini.utils.markdown_fixups'`。

- [ ] **Step 3: 新建模块**

创建 `src/nini/utils/markdown_fixups.py`：

```python
"""Markdown 兜底修复工具。

目前只处理一类模型常见输出缺陷：GFM 表格分隔行写成纯冒号（如 `|:|:|`），
不符合 CommonMark/GFM 规范，在严格解析器下渲染失败。
"""

from __future__ import annotations

import re

# 一个"仅含 | 和 : 和空白，至少两个 | "的整行判定为疑似分隔行。
# 真正的 GFM 分隔行也允许 - 与 :，此处仅当行里完全没有 - 时才触发修复。
_SEPARATOR_LINE_RE = re.compile(r"^\s*\|(?:\s*:?\s*\|){2,}\s*$")
_BARE_COLON_CELL_RE = re.compile(r"\|\s*:\s*(?=\|)")


def fix_markdown_table_separator(text: str) -> str:
    """把疑似表格分隔行里的 `|:` 扩展为 `|:---`。

    幂等：合规分隔行与正文不变。
    """
    if not text:
        return text

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "-" in line:
            continue  # 已有短横线的分隔行视为合规，跳过
        if not _SEPARATOR_LINE_RE.match(line):
            continue
        # 将每个形如 "|:" + 右侧紧跟 "|" 的单元改为 "|:---"
        lines[i] = _BARE_COLON_CELL_RE.sub("|:---", line)
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_markdown_fixups.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 在 `build_text_event` 中接入修复**

修改 `src/nini/agent/event_builders.py` 第 551-565 行：

```python
def build_text_event(
    content: str, *, turn_id: str | None = None, metadata: dict[str, Any] | None = None, **extra
) -> AgentEvent:
    """构造 TEXT 事件。"""
    from nini.utils.markdown_fixups import fix_markdown_table_separator

    sanitized_content = fix_markdown_table_separator(content) if isinstance(content, str) else content
    event_data = TextEventData(content=sanitized_content, output_level=None)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TEXT,
        data=data,
        turn_id=turn_id,
        metadata=metadata or {},
    )
```

函数内部延迟 import 以避免循环依赖风险。

- [ ] **Step 6: 跑事件构造器测试**

Run: `pytest tests/test_event_builders.py tests/test_markdown_fixups.py -v`
Expected: 全部 PASS。

- [ ] **Step 7: 写一条端到端断言测试**

在 `tests/test_markdown_fixups.py` 末尾追加：

```python
def test_build_text_event_applies_fixup() -> None:
    """build_text_event 产出的事件 content 已通过分隔行修复。"""
    from nini.agent.event_builders import build_text_event

    ev = build_text_event("| a | b |\n|:|:|\n| 1 | 2 |\n")
    assert "|:---|:---|" in ev.data["content"]
    assert "|:|:|" not in ev.data["content"]
```

Run: `pytest tests/test_markdown_fixups.py::test_build_text_event_applies_fixup -v`
Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add src/nini/utils/markdown_fixups.py src/nini/agent/event_builders.py tests/test_markdown_fixups.py
git commit -m "feat(markdown): 文本事件出口兜底修复 GFM 表格分隔行"
```

---

## Task 6: 全量验证与 schema 一致性

**Files:** 无代码改动，仅校验。

- [ ] **Step 1: 事件 schema 一致性**

Run: `python scripts/check_event_schema_consistency.py`
Expected: 退出码 0。

- [ ] **Step 2: 格式与类型**

Run: `black --check src tests && mypy src/nini`
Expected: 均通过。

- [ ] **Step 3: 跑全部后端测试**

Run: `pytest -q`
Expected: 全绿。

- [ ] **Step 4: 提交前快照检查**

Run: `git status && git log --oneline -10`
Expected: 工作区干净；最近 5 个 commit 为本计划的 1-5 号任务。

---

## Self-Review

**Spec coverage（发现问题 → 任务映射）：**
- ① sheet 名大小写 → Task 1 ✅
- ② 沙箱 `result = fig` → Task 2 + Task 3 ✅（代码拦截 + prompt 预防）
- ③ 总结未引用 artifact → Task 4 ✅
- ④ Markdown 表格分隔行 → Task 5 ✅
- 未覆盖：模型幻觉（`df_all`、`get_handles_labels`）、重复 profile 调用 — 按"不修"分类已说明。

**Placeholder scan：** 无 TODO/TBD/待补；每个 step 都给了具体代码与命令。

**Type consistency：**
- `fix_markdown_table_separator` 签名 `(str) -> str`，调用侧传入 `content: str`，一致。
- `_sanitize_result_for_transport` 签名 `(Any) -> Any`，紧接 `_try_pickleable(Any) -> Any`，调用链类型一致。
- Task 1 新增测试使用的 `load_dataset` 工具名与 `data_ops.py` 注册一致（从现有 test 同文件复制）。

无遗漏。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-fix-session-03fe97617ddf-issues.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
