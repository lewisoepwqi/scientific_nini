# 代码档案面板重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工作区「执行历史」面板重构为「代码档案」，聚焦 `run_code` / `run_r_code` 记录，支持单条与批量可复现 zip 下载。

**Architecture:** 新增后端模块 `src/nini/workspace/code_bundle.py` 做流式 zip 构建，两个新 GET 端点挂在 `workspace_routes.py`。前端 `CodeExecutionPanel.tsx` 重写文案+过滤+下载按钮，新增 `downloadBundle.ts` 工具。R 脚本 MVP 仅产出最小 bundle（完整支持留作后续）。

**Tech Stack:** Python 3.12 + FastAPI + stdlib `zipfile` + `ast`；React + TypeScript + Vitest；pytest + pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-04-19-code-archive-redesign-design.md`

---

## File Structure

### 新建

- `src/nini/workspace/code_bundle.py` — bundle 构建核心，纯同步函数，单独模块不污染 manager
- `tests/test_code_bundle.py` — 后端单元测试
- `web/src/components/downloadBundle.ts` — 前端下载触发工具

### 修改

- `src/nini/api/workspace_routes.py` — 新增 2 个下载路由
- `web/src/components/CodeExecutionPanel.tsx` — 重写面板（过滤、文案、下载按钮）
- `web/src/components/CodeExecutionPanel.test.tsx`（如不存在则新建） — 前端测试
- `web/src/components/WorkspaceSidebar.tsx` — Tab 显示名改为"代码档案"

### 不改

- `src/nini/workspace/manager.py` — 不扩张（已 2000+ 行）
- `src/nini/models/session_resources.py` — `CodeExecutionRecord` 字段结构保持不变
- `save_code_execution` 写路径 — 不动

---

## Task 1: `_make_slug` 工具

**Files:**
- Create: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_code_bundle.py` 新建：

```python
"""代码档案 bundle 构建测试。"""

from nini.workspace.code_bundle import _make_slug


def test_make_slug_prefers_intent():
    assert _make_slug("X 列标准化", None, "exploration") == "x-列标准化"


def test_make_slug_falls_back_to_label():
    assert _make_slug(None, "Sales Chart", "visualization") == "sales-chart"


def test_make_slug_falls_back_to_purpose():
    assert _make_slug(None, None, "visualization") == "visualization"


def test_make_slug_truncates_long_text():
    long = "a" * 100
    result = _make_slug(long, None, "exploration")
    assert len(result) <= 40


def test_make_slug_sanitizes_special_chars():
    assert _make_slug("a/b c!@#d", None, "exploration") == "a-b-c-d"


def test_make_slug_handles_empty_strings():
    assert _make_slug("   ", "", "exploration") == "exploration"
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ModuleNotFoundError: No module named 'nini.workspace.code_bundle'`

- [ ] **Step 3: 实现最小版本**

创建 `src/nini/workspace/code_bundle.py`：

```python
"""代码档案 bundle 构建。

将 run_code / run_r_code 执行记录打包为可复现的 zip，供用户下载本地执行。
"""

from __future__ import annotations

import re


_SLUG_MAX_LEN = 40


def _make_slug(intent: str | None, label: str | None, purpose: str) -> str:
    """生成安全的文件名 slug。

    优先级：intent > label > purpose。
    非字母数字和中文的字符统一替换为 '-'，截断到 40 字符。
    """
    source = ""
    for candidate in (intent, label, purpose):
        if isinstance(candidate, str) and candidate.strip():
            source = candidate.strip()
            break
    if not source:
        source = "execution"
    # 保留字母数字、中文和连字符，其余替换为 '-'
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", source, flags=re.UNICODE)
    slug = slug.strip("-_").lower()
    if not slug:
        slug = "execution"
    return slug[:_SLUG_MAX_LEN]
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：6 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 _make_slug 工具函数"
```

---

## Task 2: `_extract_dependencies` 依赖识别

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_code_bundle.py` 追加：

```python
from nini.workspace.code_bundle import _extract_dependencies


def test_extract_deps_empty_script():
    assert _extract_dependencies("", "python") == []


def test_extract_deps_stdlib_filtered():
    code = "import json\nimport re\nimport math"
    assert _extract_dependencies(code, "python") == []


def test_extract_deps_scientific_packages():
    code = "import pandas as pd\nimport numpy as np"
    deps = _extract_dependencies(code, "python")
    assert sorted(deps) == ["numpy", "pandas"]


def test_extract_deps_from_import():
    code = "from sklearn.linear_model import LinearRegression"
    assert _extract_dependencies(code, "python") == ["scikit-learn"]


def test_extract_deps_alias_mapping():
    code = "import cv2\nfrom PIL import Image"
    deps = _extract_dependencies(code, "python")
    assert sorted(deps) == ["Pillow", "opencv-python"]


def test_extract_deps_deduplicates():
    code = "import pandas\nimport pandas as pd\nfrom pandas import DataFrame"
    assert _extract_dependencies(code, "python") == ["pandas"]


def test_extract_deps_r_returns_empty_mvp():
    # MVP: R 依赖识别尚未实现，返回空清单（由 install.R 模板提供基础依赖）
    assert _extract_dependencies("library(ggplot2)", "r") == []


def test_extract_deps_syntax_error_returns_empty():
    # 语法错误不应抛，返回空列表，README 会提示用户手工核对
    assert _extract_dependencies("def broken(", "python") == []
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name '_extract_dependencies'`

- [ ] **Step 3: 实现**

在 `src/nini/workspace/code_bundle.py` 追加：

```python
import ast
import sys

# 从 sandbox policy 导入允许的科学栈根模块
from nini.sandbox.policy import ALLOWED_IMPORT_ROOTS, REVIEWABLE_IMPORT_ROOTS

# 需要 pip 安装的包（Tier3 科学栈 + Tier4 可审查）
_PIP_INSTALLABLE: set[str] = {
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "sklearn",
    "matplotlib",
    "plotly",
    "seaborn",
    "plotnine",
    "sympy",
}

# 顶层 import 名 → pypi 包名
_PYPI_ALIASES: dict[str, str] = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
}


def _extract_dependencies(code: str, language: str) -> list[str]:
    """从脚本抽取需要 pip 安装的依赖。

    - 只处理 Python（R 返回空，由模板提供基础依赖）
    - stdlib 和内置模块过滤掉
    - 顶层 import 名经 _PYPI_ALIASES 映射为 pypi 包名
    - 语法错误返回空列表
    """
    if language != "python" or not code.strip():
        return []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])

    stdlib_names = set(sys.stdlib_module_names) | {"__future__"}
    candidates: set[str] = set()
    for root in roots:
        if root in stdlib_names:
            continue
        if root in _PIP_INSTALLABLE or root in REVIEWABLE_IMPORT_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
            candidates.add(_PYPI_ALIASES.get(root, root))

    return sorted(candidates)
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：14 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 _extract_dependencies 依赖识别"
```

---

## Task 3: `_patch_script` Python 脚本前导注入

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_code_bundle.py` 追加：

```python
from nini.workspace.code_bundle import _patch_script


def test_patch_script_includes_metadata_header():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "abc123",
        "session_id": "sess7890",
        "created_at": "2026-04-18T03:56:56Z",
        "intent": "x 列标准化",
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert "意图：x 列标准化" in result
    assert "执行 ID：abc123" in result
    assert "purpose=exploration" in result


def test_patch_script_injects_df_when_dataset_name_set():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {"execution_id": "a", "session_id": "s", "created_at": "t", "intent": None, "tool_name": "run_code"}
    result = _patch_script(code, "python", tool_args, meta)
    assert 'datasets = {p.stem: pd.read_csv(p) for p in _DATASETS_DIR.glob("*.csv")}' in result
    assert 'df = datasets["raw"].copy()' in result


def test_patch_script_skips_df_binding_when_no_dataset():
    code = "print('hello')"
    tool_args = {"purpose": "exploration"}
    meta = {"execution_id": "a", "session_id": "s", "created_at": "t", "intent": None, "tool_name": "run_code"}
    result = _patch_script(code, "python", tool_args, meta)
    assert "datasets =" in result  # 仍加载空字典
    assert "df = datasets[" not in result


def test_patch_script_preserves_original_code():
    code = "output_df = df.copy()\noutput_df['x_norm'] = output_df['x'] * 2"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {"execution_id": "a", "session_id": "s", "created_at": "t", "intent": None, "tool_name": "run_code"}
    result = _patch_script(code, "python", tool_args, meta)
    assert "output_df = df.copy()" in result
    assert "output_df['x_norm'] = output_df['x'] * 2" in result


def test_patch_script_appends_to_csv_fallback():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {"execution_id": "a", "session_id": "s", "created_at": "t", "intent": None, "tool_name": "run_code"}
    result = _patch_script(code, "python", tool_args, meta)
    assert 'if "output_df" in dir()' in result
    assert 'output_df.to_csv' in result


def test_patch_script_r_minimal_header_only():
    # MVP：R 脚本仅附带元信息头部，不做变量注入
    code = "df %>% mutate(x_norm = scale(x))"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {"execution_id": "a", "session_id": "s", "created_at": "t", "intent": "test", "tool_name": "run_r_code"}
    result = _patch_script(code, "r", tool_args, meta)
    assert "# 意图：test" in result
    assert "df %>% mutate" in result
    # R MVP 不注入 df / datasets，README 会提示用户手工 read_csv
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name '_patch_script'`

- [ ] **Step 3: 实现**

在 `src/nini/workspace/code_bundle.py` 追加：

```python
_PYTHON_HEADER_TEMPLATE = '''\
# ========== Nini 代码档案 ==========
# 意图：{intent}
# 执行时间：{created_at}
# 来源会话：{session_id_short} / 执行 ID：{execution_id}
# 原始 tool：{tool_name} (purpose={purpose})
# ===================================

from pathlib import Path
import pandas as pd

# --- 自动加载输入数据（Nini 沙盒注入变量的离线等价） ---
_DATASETS_DIR = Path(__file__).parent / "datasets"
datasets = {{p.stem: pd.read_csv(p) for p in _DATASETS_DIR.glob("*.csv")}}
{df_binding}

# --- 原始代码 ---
'''

_PYTHON_FOOTER = '''

# --- 保存变更（若存在标准输出变量） ---
if "output_df" in dir():
    output_df.to_csv(Path(__file__).parent / "output.csv", index=False)
elif "result_df" in dir():
    result_df.to_csv(Path(__file__).parent / "result.csv", index=False)
'''

_R_HEADER_TEMPLATE = '''\
# ========== Nini 代码档案 ==========
# 意图：{intent}
# 执行时间：{created_at}
# 来源会话：{session_id_short} / 执行 ID：{execution_id}
# 原始 tool：{tool_name} (purpose={purpose})
#
# 注意：R 脚本离线复现需要自行加载数据集，示例：
#   df <- read.csv("datasets/<name>.csv")
# ===================================

'''


def _patch_script(
    code: str,
    language: str,
    tool_args: dict,
    meta: dict,
) -> str:
    """在原始脚本前后追加元信息头部、数据加载前导、输出落盘代码。

    Python：完整 patch（头部 + df 加载 + 原代码 + to_csv 落盘）
    R：MVP 仅附带元信息头部，不做变量注入
    """
    intent = meta.get("intent") or "未命名"
    session_id = str(meta.get("session_id") or "")
    session_id_short = session_id[:8] if session_id else "unknown"
    fields = {
        "intent": intent,
        "created_at": meta.get("created_at") or "",
        "session_id_short": session_id_short,
        "execution_id": meta.get("execution_id") or "",
        "tool_name": meta.get("tool_name") or "run_code",
        "purpose": tool_args.get("purpose") or "exploration",
    }

    if language == "r":
        return _R_HEADER_TEMPLATE.format(**fields) + code.rstrip() + "\n"

    dataset_name = tool_args.get("dataset_name")
    if isinstance(dataset_name, str) and dataset_name.strip():
        stem = dataset_name.rsplit(".", 1)[0]
        df_binding = f'df = datasets["{stem}"].copy()'
    else:
        df_binding = ""

    header = _PYTHON_HEADER_TEMPLATE.format(df_binding=df_binding, **fields)
    return header + code.rstrip() + _PYTHON_FOOTER
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：20 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 _patch_script 脚本前导注入"
```

---

## Task 4: 资源反查工具

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_code_bundle.py` 追加（顶部 `import pytest`）：

```python
import pytest
from pathlib import Path

from nini.workspace import WorkspaceManager
from nini.workspace.code_bundle import _resolve_dataset_files, _resolve_output_names


@pytest.fixture
def workspace_with_dataset(tmp_path, monkeypatch):
    """生成临时工作区，含一个 CSV 数据集。"""
    from nini.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    ws = WorkspaceManager("sess12345678")
    ws.ensure_dirs()
    csv_path = ws.datasets_dir / "raw.csv"
    csv_content = "x,y\n1,2\n3,4\n"
    csv_path.write_text(csv_content, encoding="utf-8")
    ws.add_dataset_record(
        dataset_id="ds_raw_test",
        name="raw.csv",
        file_path=csv_path,
        file_type="csv",
        file_size=len(csv_content.encode("utf-8")),
        row_count=2,
        column_count=2,
    )
    return ws


def test_resolve_dataset_files_by_name(workspace_with_dataset):
    ws = workspace_with_dataset
    tool_args = {"dataset_name": "raw.csv"}
    files = _resolve_dataset_files(ws, tool_args)
    assert len(files) == 1
    assert files[0].name == "raw.csv"
    assert files[0].exists()


def test_resolve_dataset_files_no_match(workspace_with_dataset):
    tool_args = {"dataset_name": "nonexistent.csv"}
    assert _resolve_dataset_files(workspace_with_dataset, tool_args) == []


def test_resolve_dataset_files_no_dataset_arg(workspace_with_dataset):
    assert _resolve_dataset_files(workspace_with_dataset, {}) == []


def test_resolve_output_names_uses_index(workspace_with_dataset):
    ws = workspace_with_dataset
    # 注入一个伪造 artifact
    index = ws._load_index()
    index.setdefault("artifacts", []).append({
        "id": "art_xyz",
        "name": "sales_chart.png",
        "file_type": "png",
    })
    ws._save_index(index)
    names = _resolve_output_names(ws, ["art_xyz", "unknown_id"])
    assert "sales_chart.png" in names
    assert "unknown_id" in names  # 未找到保留原 ID
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name '_resolve_dataset_files'`

- [ ] **Step 3: 实现**

先检查 `WorkspaceManager` 是否有 `register_dataset` 和 `_save_index` 方法；若签名不同按实际调整测试固件。

在 `src/nini/workspace/code_bundle.py` 追加：

```python
from pathlib import Path
from typing import Any

from nini.workspace import WorkspaceManager


def _resolve_dataset_files(
    ws: WorkspaceManager, tool_args: dict[str, Any]
) -> list[Path]:
    """根据 tool_args.dataset_name 定位物理 CSV 文件。"""
    name = tool_args.get("dataset_name")
    if not isinstance(name, str) or not name.strip():
        return []
    record = ws.get_dataset_by_name(name.strip())
    if record is None:
        return []
    path_str = str(record.get("file_path", "")).strip()
    if not path_str:
        return []
    path = Path(path_str)
    return [path] if path.exists() else []


def _resolve_output_names(
    ws: WorkspaceManager, output_resource_ids: list[str]
) -> list[str]:
    """将资源 ID 列表反查为人类可读名称。未找到的保留原 ID。"""
    if not output_resource_ids:
        return []

    id_to_name: dict[str, str] = {}
    for item in ws.list_datasets():
        rid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if rid:
            id_to_name[rid] = name or rid
    for item in ws.list_artifacts():
        rid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if rid:
            id_to_name[rid] = name or rid

    return [id_to_name.get(rid, rid) for rid in output_resource_ids]
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：24 passed

注：`add_dataset_record` 是 manager 的真实 API（见 `src/nini/workspace/manager.py:935`），`_save_index` 签名为 `_save_index(data: dict)`，已在测试中使用正确姿势。

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增资源反查工具"
```

---

## Task 5: README 渲染

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

```python
from nini.workspace.code_bundle import _render_single_readme, _render_batch_readme


def test_render_single_readme_includes_key_sections():
    record = {
        "id": "abc123",
        "session_id": "sess7890abcdef",
        "created_at": "2026-04-18T03:56:56Z",
        "language": "python",
        "intent": "x 列标准化",
        "tool_args": {"purpose": "exploration", "dataset_name": "raw.csv"},
    }
    readme = _render_single_readme(
        record, dataset_files=["raw.csv"], output_names=["normalized.csv"]
    )
    assert "# x 列标准化" in readme
    assert "sess7890" in readme
    assert "abc123" in readme
    assert "datasets/raw.csv" in readme
    assert "normalized.csv" in readme
    assert "bash run.sh" in readme


def test_render_single_readme_visualization_caveat():
    record = {
        "id": "a", "session_id": "s", "created_at": "t", "language": "python",
        "intent": "销售图表",
        "tool_args": {"purpose": "visualization"},
    }
    readme = _render_single_readme(record, dataset_files=[], output_names=[])
    assert "fig.show()" in readme or "fig.write_html" in readme


def test_render_batch_readme_lists_all_steps():
    records = [
        {
            "id": "a1", "created_at": "2026-04-18T01:00:00Z",
            "intent": "步骤1", "language": "python",
            "tool_args": {"purpose": "exploration"},
        },
        {
            "id": "a2", "created_at": "2026-04-18T02:00:00Z",
            "intent": "步骤2", "language": "python",
            "tool_args": {"purpose": "visualization"},
        },
    ]
    slugs = ["01_步骤1", "02_步骤2"]
    readme = _render_batch_readme(records, slugs, session_id="sess7890abcdef")
    assert "步骤1" in readme
    assert "步骤2" in readme
    assert "01_步骤1/script" in readme
    assert "02_步骤2/script" in readme
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name '_render_single_readme'`

- [ ] **Step 3: 实现**

```python
_PURPOSE_ZH = {
    "exploration": "探索分析",
    "visualization": "图表",
    "export": "导出",
    "transformation": "数据转换",
}


def _render_single_readme(
    record: dict[str, Any],
    *,
    dataset_files: list[str],
    output_names: list[str],
) -> str:
    """渲染单条 bundle 的 README.md。"""
    intent = record.get("intent") or "未命名代码归档"
    session_id = str(record.get("session_id") or "")
    session_id_short = session_id[:8] if session_id else "unknown"
    purpose = str(record.get("tool_args", {}).get("purpose") or "exploration")
    purpose_zh = _PURPOSE_ZH.get(purpose, purpose)
    language = str(record.get("language") or "python")

    lines = [
        f"# {intent}",
        "",
        f"来源：Nini 会话 `{session_id_short}` · 执行 ID `{record.get('id', '')}`",
        f"时间：{record.get('created_at', '')}",
        f"类型：{purpose_zh}",
        f"语言：{language}",
        "",
        "## 输入数据",
        "",
    ]
    if dataset_files:
        for name in dataset_files:
            lines.append(f"- `datasets/{name}`")
    else:
        lines.append("- 无输入数据")
    lines += ["", "## 预期产出", ""]
    if output_names:
        for name in output_names:
            lines.append(f"- {name}")
    else:
        lines.append("- 无持久化产出")
    lines += [
        "",
        "## 运行",
        "",
        "```bash",
        "bash run.sh",
        "```",
        "",
        "需要 Python >= 3.11。依赖见 `requirements.txt`。",
        "",
        "## 已知约束",
        "",
        "- 本压缩包内含输入数据集，分享前请确认不含敏感信息。",
    ]
    if purpose == "visualization":
        lines.append(
            "- 图表脚本离线运行时不会自动显示，请自行追加 `fig.show()` 或 `fig.write_html(\"chart.html\")`。"
        )
    return "\n".join(lines) + "\n"


def _render_batch_readme(
    records: list[dict[str, Any]],
    slugs: list[str],
    *,
    session_id: str,
) -> str:
    """渲染批量 bundle 的 README.md。"""
    session_id_short = session_id[:8] if session_id else "unknown"
    lines = [
        f"# Nini 代码档案（会话 {session_id_short}）",
        "",
        f"共 {len(records)} 份代码归档，按时间升序排列。",
        "",
        "## 运行",
        "",
        "```bash",
        "bash run_all.sh",
        "```",
        "",
        "## 步骤列表",
        "",
    ]
    for idx, (record, slug) in enumerate(zip(records, slugs), 1):
        intent = record.get("intent") or "未命名"
        purpose = str(record.get("tool_args", {}).get("purpose") or "exploration")
        purpose_zh = _PURPOSE_ZH.get(purpose, purpose)
        language = str(record.get("language") or "python")
        ext = "R" if language == "r" else "py"
        lines.append(
            f"{idx}. **{intent}**（{purpose_zh}）· "
            f"{record.get('created_at', '')} · `{slug}/script.{ext}`"
        )
    lines += [
        "",
        "## 已知约束",
        "",
        "- 本压缩包内含输入数据集，分享前请确认不含敏感信息。",
        "- R 脚本的数据加载需要手工补充 `read.csv(...)`。",
    ]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：27 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 README 渲染"
```

---

## Task 6: `build_single_bundle`

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

```python
import io
import zipfile

from nini.workspace.code_bundle import build_single_bundle


def test_build_single_bundle_contains_all_files(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code="output_df = df.copy()\noutput_df['y2'] = output_df['y'] * 2",
        output="已保存",
        status="success",
        language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="测试归档",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "README.md" in names
    assert "script.py" in names
    assert "requirements.txt" in names
    assert "run.sh" in names
    assert "datasets/raw.csv" in names


def test_build_single_bundle_script_has_patch_header(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code="output_df = df.copy()",
        output="",
        status="success",
        language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="测试",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        script = zf.read("script.py").decode("utf-8")
    assert "Nini 代码档案" in script
    assert 'df = datasets["raw"].copy()' in script
    assert "output_df = df.copy()" in script


def test_build_single_bundle_missing_execution_raises(workspace_with_dataset):
    with pytest.raises(ValueError, match="不存在"):
        build_single_bundle(workspace_with_dataset, "nonexistent_id")


def test_build_single_bundle_r_script_uses_r_extension(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code='df <- data.frame(x=1:3)',
        output="",
        status="success",
        language="r",
        tool_name="run_r_code",
        tool_args={"purpose": "exploration"},
        intent="r 测试",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "script.R" in names
    assert "script.py" not in names
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name 'build_single_bundle'`

- [ ] **Step 3: 实现**

```python
import io
import zipfile

_RUN_SH_PYTHON = '''\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python script.py
'''

_RUN_SH_R = '''\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
Rscript install.R
Rscript script.R
'''

_INSTALL_R_TEMPLATE = '''\
# R 基础依赖（请按脚本实际 library() 调用手工补充）
install.packages(c("readr", "dplyr", "ggplot2"), repos = "https://cloud.r-project.org")
'''


def build_single_bundle(ws: WorkspaceManager, execution_id: str) -> bytes:
    """打包单条执行记录为可复现 zip。返回 zip 字节。"""
    record = ws.get_code_execution(execution_id)
    if record is None:
        raise ValueError(f"执行记录 '{execution_id}' 不存在")

    language = str(record.get("language") or "python")
    code = str(record.get("code") or "")
    tool_args = record.get("tool_args") or {}
    meta = {
        "execution_id": record.get("id"),
        "session_id": record.get("session_id"),
        "created_at": record.get("created_at"),
        "intent": record.get("intent"),
        "tool_name": record.get("tool_name"),
    }

    patched = _patch_script(code, language, tool_args, meta)
    deps = _extract_dependencies(code, language)
    dataset_paths = _resolve_dataset_files(ws, tool_args)
    output_names = _resolve_output_names(ws, record.get("output_resource_ids") or [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        script_name = "script.R" if language == "r" else "script.py"
        zf.writestr(script_name, patched)
        zf.writestr(
            "README.md",
            _render_single_readme(
                record,
                dataset_files=[p.name for p in dataset_paths],
                output_names=output_names,
            ),
        )
        if language == "r":
            zf.writestr("install.R", _INSTALL_R_TEMPLATE)
            zf.writestr("run.sh", _RUN_SH_R)
        else:
            zf.writestr("requirements.txt", "\n".join(deps) + ("\n" if deps else ""))
            zf.writestr("run.sh", _RUN_SH_PYTHON)
        for path in dataset_paths:
            zf.write(path, arcname=f"datasets/{path.name}")

    return buf.getvalue()
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：31 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 build_single_bundle 单条打包"
```

---

## Task 7: `build_batch_bundle`

**Files:**
- Modify: `src/nini/workspace/code_bundle.py`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

```python
from nini.workspace.code_bundle import build_batch_bundle


def test_build_batch_bundle_orders_by_time_ascending(workspace_with_dataset):
    ws = workspace_with_dataset
    # 插入 3 条（manager 内会写文件，created_at 顺序可控）
    for i in range(3):
        ws.save_code_execution(
            code=f"x = {i}",
            output="",
            status="success",
            language="python",
            tool_name="run_code",
            tool_args={"purpose": "exploration"},
            intent=f"步骤{i}",
        )
    zip_bytes = build_batch_bundle(ws)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = sorted(n for n in zf.namelist() if n.startswith("0"))
    # 目录前缀按时间升序应为 01_ / 02_ / 03_
    assert any(n.startswith("01_") for n in names)
    assert any(n.startswith("02_") for n in names)
    assert any(n.startswith("03_") for n in names)


def test_build_batch_bundle_filters_non_run_code_tools(workspace_with_dataset):
    ws = workspace_with_dataset
    ws.save_code_execution(
        code="x = 1", output="", status="success", language="python",
        tool_name="run_code", tool_args={"purpose": "exploration"}, intent="保留",
    )
    ws.save_code_execution(
        code="noise", output="", status="success", language="python",
        tool_name="stat_test", tool_args={}, intent="过滤掉",
    )
    zip_bytes = build_batch_bundle(ws)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        readme = zf.read("README.md").decode("utf-8")
    assert "保留" in readme
    assert "过滤掉" not in readme


def test_build_batch_bundle_deduplicates_datasets(workspace_with_dataset):
    ws = workspace_with_dataset
    ws.save_code_execution(
        code="a=1", output="", status="success", language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="步骤1",
    )
    ws.save_code_execution(
        code="b=2", output="", status="success", language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="步骤2",
    )
    zip_bytes = build_batch_bundle(ws)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_entries = [n for n in zf.namelist() if n.startswith("datasets/")]
    assert csv_entries.count("datasets/raw.csv") == 1


def test_build_batch_bundle_empty_when_no_records(workspace_with_dataset):
    # 新建一个无记录的会话
    from nini.workspace import WorkspaceManager
    ws2 = WorkspaceManager("empty_session_xxx")
    ws2.ensure_dirs()
    zip_bytes = build_batch_bundle(ws2)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert names == ["README.md"]
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：`ImportError: cannot import name 'build_batch_bundle'`

- [ ] **Step 3: 实现**

```python
_RUN_ALL_SH = '''\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
for dir in */; do
  script_py="$dir/script.py"
  script_r="$dir/script.R"
  if [ -f "$script_py" ]; then
    echo ">>> 执行 $script_py"
    python "$script_py"
  elif [ -f "$script_r" ]; then
    echo ">>> 执行 $script_r"
    Rscript "$script_r"
  fi
done
'''


def build_batch_bundle(ws: WorkspaceManager) -> bytes:
    """打包会话所有 run_code / run_r_code 记录为批量 zip。按时间升序。"""
    # manager 返回降序，反转为升序
    all_records = ws.list_code_executions(limit=500)
    records = [
        r for r in all_records
        if r.get("tool_name") in {"run_code", "run_r_code"}
    ]
    records.sort(key=lambda r: str(r.get("created_at", "")))

    if not records:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "README.md",
                _render_batch_readme([], [], session_id=ws.session_id),
            )
        return buf.getvalue()

    slugs: list[str] = []
    all_deps: set[str] = set()
    seen_datasets: set[str] = set()
    dataset_paths_global: list[Path] = []

    for idx, record in enumerate(records, 1):
        tool_args = record.get("tool_args") or {}
        slug_base = _make_slug(
            record.get("intent"),
            tool_args.get("label"),
            str(tool_args.get("purpose") or "exploration"),
        )
        slugs.append(f"{idx:02d}_{slug_base}")

        deps = _extract_dependencies(
            str(record.get("code") or ""),
            str(record.get("language") or "python"),
        )
        all_deps.update(deps)

        for path in _resolve_dataset_files(ws, tool_args):
            if path.name not in seen_datasets:
                seen_datasets.add(path.name)
                dataset_paths_global.append(path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.md",
            _render_batch_readme(records, slugs, session_id=ws.session_id),
        )
        zf.writestr(
            "requirements.txt",
            "\n".join(sorted(all_deps)) + ("\n" if all_deps else ""),
        )
        zf.writestr("run_all.sh", _RUN_ALL_SH)

        for record, slug in zip(records, slugs):
            language = str(record.get("language") or "python")
            code = str(record.get("code") or "")
            tool_args = record.get("tool_args") or {}
            meta = {
                "execution_id": record.get("id"),
                "session_id": record.get("session_id"),
                "created_at": record.get("created_at"),
                "intent": record.get("intent"),
                "tool_name": record.get("tool_name"),
            }
            patched = _patch_script(code, language, tool_args, meta)
            script_name = "script.R" if language == "r" else "script.py"
            zf.writestr(f"{slug}/{script_name}", patched)

        for path in dataset_paths_global:
            zf.write(path, arcname=f"datasets/{path.name}")

    return buf.getvalue()
```

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：35 passed

- [ ] **Step 5: 提交**

```bash
git add src/nini/workspace/code_bundle.py tests/test_code_bundle.py
git commit -m "feat(code-bundle): 新增 build_batch_bundle 批量打包"
```

---

## Task 8: 后端 API 路由

**Files:**
- Modify: `src/nini/api/workspace_routes.py:59-69`
- Test: `tests/test_code_bundle.py`

- [ ] **Step 1: 追加失败测试**

```python
from fastapi.testclient import TestClient


def test_api_single_bundle_returns_zip(tmp_path, monkeypatch):
    from nini.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    # 创建会话 + 执行记录
    from nini.agent.session import session_manager
    session_manager.create_session("apitest12")
    ws = WorkspaceManager("apitest12")
    ws.ensure_dirs()
    exec_record = ws.save_code_execution(
        code="x=1", output="", status="success", language="python",
        tool_name="run_code", tool_args={"purpose": "exploration"},
        intent="api 测试",
    )

    from nini.api.routes import app  # 复用主应用
    client = TestClient(app)
    response = client.get(
        f"/api/workspace/apitest12/executions/{exec_record['id']}/bundle"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers.get("content-disposition", "")


def test_api_batch_bundle_returns_zip(tmp_path, monkeypatch):
    from nini.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from nini.agent.session import session_manager
    session_manager.create_session("batchapi8")
    ws = WorkspaceManager("batchapi8")
    ws.ensure_dirs()
    ws.save_code_execution(
        code="x=1", output="", status="success", language="python",
        tool_name="run_code", tool_args={"purpose": "exploration"},
        intent="批量测试",
    )

    from nini.api.routes import app
    client = TestClient(app)
    response = client.get("/api/workspace/batchapi8/executions/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_api_bundle_missing_session_404(tmp_path, monkeypatch):
    from nini.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from nini.api.routes import app
    client = TestClient(app)
    response = client.get("/api/workspace/notexist/executions/bundle")
    assert response.status_code == 404


def test_api_single_bundle_missing_execution_404(tmp_path, monkeypatch):
    from nini.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from nini.agent.session import session_manager
    session_manager.create_session("sess404a")
    from nini.api.routes import app
    client = TestClient(app)
    response = client.get("/api/workspace/sess404a/executions/xxxxxx/bundle")
    assert response.status_code == 404
```

- [ ] **Step 2: 运行验证失败**

```bash
pytest tests/test_code_bundle.py -v
```
预期：404 或路由未注册失败

- [ ] **Step 3: 实现**

在 `src/nini/api/workspace_routes.py` 末尾追加（如果 `routes.py` 使用不同的 app 导入路径，按实际调整测试）：

```python
from fastapi.responses import Response

from nini.workspace.code_bundle import build_batch_bundle, build_single_bundle


@router.get("/workspace/{session_id}/executions/bundle")
async def download_executions_bundle(session_id: str) -> Response:
    """批量下载会话所有 run_code / run_r_code 记录的可复现 zip。"""
    _ensure_workspace_session_exists(session_id)
    ws = WorkspaceManager(session_id)
    zip_bytes = build_batch_bundle(ws)
    filename = f"code-archive-{session_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/workspace/{session_id}/executions/{execution_id}/bundle")
async def download_execution_bundle(session_id: str, execution_id: str) -> Response:
    """下载单条执行记录的可复现 zip。"""
    _ensure_workspace_session_exists(session_id)
    ws = WorkspaceManager(session_id)
    try:
        zip_bytes = build_single_bundle(ws, execution_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    filename = f"execution-{execution_id[:8]}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**路由顺序重要**：`/executions/bundle` 必须在 `/executions/{execution_id}/bundle` 之前声明，否则 `bundle` 会被吃为 execution_id 参数。

- [ ] **Step 4: 运行验证通过**

```bash
pytest tests/test_code_bundle.py -v
```
预期：39 passed

若 `from nini.api.routes import app` 路径不对，需要先 `rg "FastAPI\(" src/nini/api/` 找到真实入口。

- [ ] **Step 5: 提交**

```bash
git add src/nini/api/workspace_routes.py tests/test_code_bundle.py
git commit -m "feat(api): 新增代码档案 bundle 下载路由"
```

---

## Task 9: 前端下载工具

**Files:**
- Create: `web/src/components/downloadBundle.ts`

- [ ] **Step 1: 写实现**

```typescript
/**
 * 代码档案 bundle 下载工具：通过浏览器触发 zip 下载。
 */
import { downloadFileFromUrl } from './downloadUtils'

export function downloadSingleBundle(sessionId: string, executionId: string): Promise<void> {
  const url = `/api/workspace/${sessionId}/executions/${executionId}/bundle`
  return downloadFileFromUrl(url, `execution-${executionId.slice(0, 8)}.zip`)
}

export function downloadBatchBundle(sessionId: string): Promise<void> {
  const url = `/api/workspace/${sessionId}/executions/bundle`
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  return downloadFileFromUrl(url, `code-archive-${sessionId.slice(0, 8)}-${date}.zip`)
}
```

- [ ] **Step 2: 手工验证**

无独立测试文件；通过 Task 10 集成到面板后在 Task 11 前端测试中验证调用。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/downloadBundle.ts
git commit -m "feat(ui): 新增前端 bundle 下载工具"
```

---

## Task 10: 前端面板重写（过滤 + 文案 + 标题生成）

**Files:**
- Modify: `web/src/components/CodeExecutionPanel.tsx`（整体替换）

- [ ] **Step 1: 替换文件**

将 `web/src/components/CodeExecutionPanel.tsx` 整体替换为：

```tsx
/**
 * 代码档案面板 —— 聚焦 run_code / run_r_code 记录，支持单条与批量下载。
 */
import { useEffect, useCallback, useState } from "react";
import { useStore, type CodeExecution } from "../store";
import {
  Copy,
  Check,
  AlertCircle,
  CheckCircle,
  Terminal,
  RotateCcw,
  BarChart3,
  Package,
  Wrench,
  Search,
  Download,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import Button from "./ui/Button";
import { downloadSingleBundle, downloadBatchBundle } from "./downloadBundle";

/** purpose → 图标 + 中文前缀 + 域色 token */
const PURPOSE_META: Record<
  string,
  { icon: React.ElementType; label: string; color: string }
> = {
  visualization: { icon: BarChart3, label: "图表", color: "var(--domain-analysis)" },
  export: { icon: Package, label: "导出", color: "var(--domain-report)" },
  transformation: { icon: Wrench, label: "数据转换", color: "var(--domain-profile)" },
  exploration: { icon: Search, label: "探索分析", color: "var(--domain-analysis)" },
};

type Tone = "accent" | "success" | "warning" | "error";

function toneToken(tone: Tone): string {
  switch (tone) {
    case "success": return "var(--success)";
    case "warning": return "var(--warning)";
    case "error": return "var(--error)";
    default: return "var(--accent)";
  }
}

function toneSurfaceStyle(tone: Tone, weight = 10) {
  return {
    backgroundColor: `color-mix(in srgb, ${toneToken(tone)} ${weight}%, var(--bg-base))`,
  };
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function getCardTitle(exec: CodeExecution): { prefix: string; intent: string; Icon: React.ElementType; color: string } {
  const purpose = String((exec.tool_args as any)?.purpose || "exploration");
  const meta = PURPOSE_META[purpose] ?? PURPOSE_META.exploration;
  const intent =
    exec.intent?.trim() ||
    (exec.tool_args as any)?.label ||
    (exec.tool_args as any)?.intent ||
    "未命名";
  return { prefix: meta.label, intent, Icon: meta.icon, color: meta.color };
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 回退方案
    }
  }, [text]);
  return (
    <Button variant="ghost" onClick={handleCopy} className="p-0.5 rounded" title="复制" aria-label="复制">
      {copied
        ? <Check size={12} className="text-[var(--success)]" />
        : <Copy size={12} className="text-[var(--text-muted)]" />}
    </Button>
  );
}

function StatusIcon({ status }: { status: string }) {
  const isError = status === "error";
  const isRunning = status === "running";
  return (
    <div
      className={`w-6 h-6 rounded-full border flex items-center justify-center flex-shrink-0 z-10 ${
        isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
      }`}
      style={isError ? toneSurfaceStyle("error", 12) : { backgroundColor: "var(--bg-elevated)" }}
    >
      {isRunning
        ? <Loader2 size={16} className="text-[var(--accent)] animate-spin" />
        : isError
          ? <AlertCircle size={16} className="text-[var(--error)]" />
          : <CheckCircle size={16} className="text-[var(--success)]" />}
    </div>
  );
}

function ExecutionItem({ exec, sessionId }: { exec: CodeExecution; sessionId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [argsExpanded, setArgsExpanded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const isError = exec.status === "error";
  const isRetry = !!exec.retry_of_execution_id;
  const { prefix, intent, Icon, color } = getCardTitle(exec);
  const cardStyle = isError ? toneSurfaceStyle("error", 8) : undefined;
  const headerStyle = isError ? toneSurfaceStyle("error", 10) : undefined;

  const handleDownload = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setDownloading(true);
    try {
      await downloadSingleBundle(sessionId, exec.id);
    } finally {
      setDownloading(false);
    }
  }, [sessionId, exec.id]);

  return (
    <div className="flex gap-3 items-start">
      <div className="flex-shrink-0 flex flex-col items-center w-6 pt-1.5">
        <StatusIcon status={exec.status} />
      </div>
      <div
        className={`flex-1 min-w-0 rounded-md border overflow-hidden mb-1 shadow-sm ${
          isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
        }`}
        style={cardStyle}
      >
        <div
          className={`w-full flex items-center gap-2 px-3 h-9 transition-colors ${
            isError ? "hover:opacity-90" : "hover:bg-[var(--bg-hover)]"
          }`}
          style={headerStyle}
        >
          <button
            onClick={() => setExpanded(v => !v)}
            className="flex items-center gap-2 flex-1 min-w-0 text-left cursor-pointer"
          >
            <Icon size={14} className="flex-shrink-0" style={{ color }} />
            <span className="text-xs font-medium text-[var(--text-primary)] truncate">
              {prefix}：{intent}
            </span>
            {exec.language && (
              <span className="text-[10px] text-[var(--text-muted)] font-mono">
                ({exec.language})
              </span>
            )}
            {isRetry && (
              <RotateCcw size={10} className="text-[var(--accent)] flex-shrink-0" aria-label="重试执行" />
            )}
            <span className="text-[10px] text-[var(--text-muted)] ml-auto flex-shrink-0">
              {formatTime(exec.created_at)}
            </span>
          </button>
          <Button
            variant="ghost"
            onClick={handleDownload}
            disabled={downloading}
            className="p-0.5 rounded flex-shrink-0"
            title="下载可复现 zip"
            aria-label="下载"
          >
            {downloading
              ? <Loader2 size={12} className="animate-spin text-[var(--text-muted)]" />
              : <Download size={12} className="text-[var(--text-muted)]" />}
          </Button>
          <button onClick={() => setExpanded(v => !v)} className="cursor-pointer">
            {expanded
              ? <ChevronUp size={14} className="text-[var(--text-muted)]" />
              : <ChevronDown size={14} className="text-[var(--text-muted)]" />}
          </button>
        </div>

        {expanded && (
          <div className="border-t border-[var(--border-default)]">
            {(exec.tool_args as any)?.dataset_name && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--domain-profile)] flex items-center gap-2"
                style={toneSurfaceStyle("accent", 8)}
              >
                <span className="font-medium">输入数据：</span>
                <code className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                  {(exec.tool_args as any).dataset_name}
                </code>
              </div>
            )}

            {exec.output_resource_ids && exec.output_resource_ids.length > 0 && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--success)] flex items-center gap-2 flex-wrap"
                style={toneSurfaceStyle("success", 9)}
              >
                <span className="font-medium">生成产物：</span>
                {exec.output_resource_ids.map(id => (
                  <code key={id} className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                    {id.slice(0, 10)}
                  </code>
                ))}
              </div>
            )}

            {exec.code && (
              <div className="relative">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span className="text-[10px] text-[var(--text-muted)] font-medium">代码</span>
                  <CopyButton text={exec.code} />
                </div>
                <pre className="text-xs font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-[200px] overflow-y-auto">
                  {exec.code}
                </pre>
              </div>
            )}

            {exec.output && (
              <div className="relative border-t border-[var(--border-default)]">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span className={`text-[10px] font-medium ${isError ? "text-[var(--error)]" : "text-[var(--text-muted)]"}`}>
                    运行结果
                  </span>
                </div>
                <pre
                  className={`text-xs font-mono px-3 py-2 overflow-x-auto max-h-[200px] overflow-y-auto whitespace-pre-wrap break-words ${
                    isError ? "text-[var(--error)]" : "bg-[var(--bg-base)] text-[var(--text-secondary)]"
                  }`}
                  style={isError ? toneSurfaceStyle("error", 12) : undefined}
                >
                  {exec.output}
                </pre>
              </div>
            )}

            {exec.tool_args && Object.keys(exec.tool_args).length > 0 && (
              <div className="border-t border-[var(--border-default)]">
                <button
                  onClick={() => setArgsExpanded(v => !v)}
                  className="w-full flex items-center gap-1 px-3 py-1 bg-[var(--bg-elevated)] text-[10px] text-[var(--text-muted)] font-medium hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                >
                  <span>{argsExpanded ? "▼" : "▶"}</span>
                  <span>参数详情</span>
                </button>
                {argsExpanded && (
                  <pre className="text-[11px] font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-32 overflow-y-auto">
                    {JSON.stringify(exec.tool_args, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CodeExecutionPanel() {
  const sessionId = useStore(s => s.sessionId);
  const codeExecutions = useStore(s => s.codeExecutions);
  const fetchCodeExecutions = useStore(s => s.fetchCodeExecutions);
  const [batchDownloading, setBatchDownloading] = useState(false);

  useEffect(() => {
    if (sessionId) fetchCodeExecutions();
  }, [sessionId, fetchCodeExecutions]);

  const filtered = codeExecutions.filter(
    e => e.tool_name === "run_code" || e.tool_name === "run_r_code",
  );

  const handleBatchDownload = useCallback(async () => {
    if (!sessionId) return;
    setBatchDownloading(true);
    try {
      await downloadBatchBundle(sessionId);
    } finally {
      setBatchDownloading(false);
    }
  }, [sessionId]);

  if (filtered.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[var(--text-muted)] text-xs px-4">
        <Terminal size={24} className="mb-2 opacity-50" />
        <p>暂无代码记录</p>
        <p className="text-[10px] mt-1 text-center">
          当 Agent 运行分析或绘制图表时，
          <br />
          执行过的 Python / R 代码会归档于此，可下载复现
        </p>
      </div>
    );
  }

  return (
    <div className="px-3 py-2">
      <div className="flex items-center justify-between px-1 py-1 mb-2">
        <span className="text-[11px] text-[var(--text-muted)]">
          共 {filtered.length} 份代码归档
        </span>
        <Button
          variant="ghost"
          onClick={handleBatchDownload}
          disabled={batchDownloading || !sessionId}
          className="text-[11px] flex items-center gap-1 px-2 py-0.5"
          title="下载全部代码档案"
        >
          {batchDownloading
            ? <Loader2 size={12} className="animate-spin" />
            : <Download size={12} />}
          <span>全部下载</span>
        </Button>
      </div>
      <div className="relative">
        <div
          className="absolute left-[11px] top-6 bottom-4 w-0.5"
          style={{ background: "var(--border-default)" }}
        />
        <div className="flex flex-col">
          {filtered.map(exec => (
            <ExecutionItem key={exec.id} exec={exec} sessionId={sessionId || ""} />
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 验证构建**

```bash
cd web && npm run build
```
预期：TypeScript 编译通过，Vite 构建成功。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/CodeExecutionPanel.tsx
git commit -m "feat(ui): 代码档案面板重写（过滤+文案+下载按钮）"
```

---

## Task 11: 前端面板测试

**Files:**
- Create (或 Modify): `web/src/components/CodeExecutionPanel.test.tsx`

- [ ] **Step 1: 检查是否已有测试文件**

```bash
ls web/src/components/CodeExecutionPanel.test.tsx 2>/dev/null
```

- [ ] **Step 2: 写测试**

创建或覆盖 `web/src/components/CodeExecutionPanel.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CodeExecutionPanel from './CodeExecutionPanel'
import { useStore, type CodeExecution } from '../store'

vi.mock('./downloadBundle', () => ({
  downloadSingleBundle: vi.fn().mockResolvedValue(undefined),
  downloadBatchBundle: vi.fn().mockResolvedValue(undefined),
}))

import { downloadSingleBundle, downloadBatchBundle } from './downloadBundle'

function makeExec(overrides: Partial<CodeExecution>): CodeExecution {
  return {
    id: 'abc12345',
    session_id: 'sess',
    code: 'x = 1',
    output: 'ok',
    status: 'success',
    language: 'python',
    tool_name: 'run_code',
    tool_args: { purpose: 'exploration' },
    created_at: '2026-04-19T10:00:00Z',
    output_resource_ids: [],
    intent: '测试',
    ...overrides,
  } as CodeExecution
}

describe('CodeExecutionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useStore.setState({
      sessionId: 'sess',
      codeExecutions: [],
      fetchCodeExecutions: vi.fn(),
    } as any)
  })

  it('shows empty state with new copy when no records', () => {
    render(<CodeExecutionPanel />)
    expect(screen.getByText('暂无代码记录')).toBeInTheDocument()
  })

  it('filters out non run_code / run_r_code tool records', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'keep1', tool_name: 'run_code', intent: '保留' }),
        makeExec({ id: 'drop1', tool_name: 'stat_test', intent: '过滤' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/保留/)).toBeInTheDocument()
    expect(screen.queryByText(/过滤/)).not.toBeInTheDocument()
  })

  it('renders purpose-based title for visualization', () => {
    useStore.setState({
      codeExecutions: [makeExec({
        tool_args: { purpose: 'visualization' },
        intent: '销售图表',
      })],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/图表：销售图表/)).toBeInTheDocument()
  })

  it('calls downloadSingleBundle on single download click', async () => {
    useStore.setState({
      codeExecutions: [makeExec({ id: 'exec999' })],
    } as any)
    render(<CodeExecutionPanel />)
    const btn = screen.getByTitle('下载可复现 zip')
    fireEvent.click(btn)
    await waitFor(() => {
      expect(downloadSingleBundle).toHaveBeenCalledWith('sess', 'exec999')
    })
  })

  it('calls downloadBatchBundle on batch download click', async () => {
    useStore.setState({
      codeExecutions: [makeExec({})],
    } as any)
    render(<CodeExecutionPanel />)
    const btn = screen.getByTitle('下载全部代码档案')
    fireEvent.click(btn)
    await waitFor(() => {
      expect(downloadBatchBundle).toHaveBeenCalledWith('sess')
    })
  })

  it('shows count with new copy', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'a' }),
        makeExec({ id: 'b' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/共 2 份代码归档/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: 运行测试**

```bash
cd web && npm test -- CodeExecutionPanel
```
预期：6 passed

- [ ] **Step 4: 提交**

```bash
git add web/src/components/CodeExecutionPanel.test.tsx
git commit -m "test(ui): 代码档案面板测试覆盖过滤、文案、下载"
```

---

## Task 12: WorkspaceSidebar Tab 名

**Files:**
- Modify: `web/src/components/WorkspaceSidebar.tsx:239`

- [ ] **Step 1: 找到行号**

```bash
rg -n "执行历史" web/src/components/WorkspaceSidebar.tsx
```
预期输出：两处（注释 + Tab 按钮文案）

- [ ] **Step 2: 替换**

将 `web/src/components/WorkspaceSidebar.tsx` 里 Tab 按钮内显示 "执行历史" 的那行改为 "代码档案"。注释里出现的"执行历史"可一并更新为"代码档案"以保持一致，但 `workspacePanelTab === 'executions'` **不改**（保持枚举稳定，避免牵连 store）。

示例 edit：

旧：
```tsx
<Terminal size={13} />
执行历史
</Button>
```
新：
```tsx
<Terminal size={13} />
代码档案
</Button>
```

注释同步：
```tsx
/**
 * 独立工作区侧边栏 —— 右侧面板，包含 Tab 切换（文件 / 代码档案 / 任务），支持列表/树状视图切换。
 */
```

- [ ] **Step 3: 构建验证**

```bash
cd web && npm run build
```
预期：通过。

- [ ] **Step 4: 提交**

```bash
git add web/src/components/WorkspaceSidebar.tsx
git commit -m "feat(ui): sidebar Tab 重命名 执行历史 → 代码档案"
```

---

## Task 13: 全量验证

**Files:** 无

- [ ] **Step 1: 后端全量测试 + schema 一致性**

```bash
python scripts/check_event_schema_consistency.py
pytest -q
```
预期：schema 一致，pytest 全绿。

- [ ] **Step 2: 前端构建 + 测试**

```bash
cd web && npm run build && npm test
```
预期：build 成功，测试全绿。

- [ ] **Step 3: 格式化 + 类型检查**

```bash
black src tests
black --check src tests
mypy src/nini
```
预期：无改动，mypy 通过。

- [ ] **Step 4: 端到端手动验证**

```bash
nini start --reload
# 浏览器打开工作区面板，切到"代码档案"Tab，验证：
# 1. 空态文案正确
# 2. 如有记录，过滤生效（只显示 run_code/run_r_code）
# 3. 卡片标题按 purpose 展示（图表 / 探索分析 / 数据转换 / 导出）
# 4. 单条下载按钮触发 zip 下载，解压后 README / script.py / requirements.txt / run.sh / datasets/ 齐全
# 5. bash run.sh 可在干净环境执行（需要 Python）
# 6. 顶部"全部下载"触发 batch zip，解压后目录按时间升序编号
```

- [ ] **Step 5: 最终提交（如有格式化改动）**

```bash
git status --short
# 如无改动则跳过；有改动则：
git add -u && git commit -m "chore: 代码档案格式化收尾"
```

---

## Self-Review

### Spec 覆盖检查

| Spec 节 | 实现任务 |
|---|---|
| 一、面板重命名与文案 | Task 10 / Task 12 |
| 二、卡片标题生成规则 | Task 10（`getCardTitle` + `PURPOSE_META`）|
| 三、过滤规则 + 删除僵尸映射 | Task 10 |
| 四、bundle 结构（单条/批量/patch/依赖/run.sh/R） | Task 3 / Task 6 / Task 7 |
| 五、README 生成 | Task 5 |
| 六、接口 | Task 8 |
| 七、后端模块拆分 | Tasks 1-7（`code_bundle.py`）|
| 八、前端改动 | Task 9 / Task 10 / Task 12 |
| 九、测试 | Tasks 1-8（后端）/ Task 11（前端）|

### 风险缓解检查

- 数据集隐私提示：README 在 Task 5 实现（`本压缩包内含输入数据集，分享前请确认不含敏感信息`）
- 依赖识别不准：Task 2 未识别时保留原名；无 `# unknown` 注释（为简化）
- plotly 离线不显示：Task 5 visualization README 追加提示
- R 脚本 MVP：Task 3 仅头部注入；Task 6 script.R + install.R 基础包

### Placeholder 扫描

- 无 TBD / TODO
- 所有测试带代码
- 所有实现步骤带代码
- 命令行带预期输出

### 类型一致性

- `_patch_script(code, language, tool_args, meta)` 签名贯穿 Task 3 / Task 6 / Task 7
- `downloadSingleBundle(sessionId, executionId)` / `downloadBatchBundle(sessionId)` Task 9 定义、Task 10 使用、Task 11 mock 校验一致
- `build_single_bundle(ws, execution_id)` / `build_batch_bundle(ws)` Task 6/7 定义，Task 8 路由调用一致
