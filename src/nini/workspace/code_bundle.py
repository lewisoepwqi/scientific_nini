"""代码档案 bundle 构建。

将 run_code / run_r_code / code_session 执行记录打包为可复现的 zip，供用户下载本地执行。
"""

from __future__ import annotations

import ast
import io
import re
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nini.sandbox.policy import ALLOWED_IMPORT_ROOTS, REVIEWABLE_IMPORT_ROOTS

if TYPE_CHECKING:
    from nini.workspace.manager import WorkspaceManager

_SLUG_MAX_LEN = 40

# 会被代码档案收录的工具名：历史 run_code/run_r_code + 当前主链路 code_session。
# code_session 实际承担了 CodeSessionTool 所有 run_* 操作与子 Agent 调用。
ARCHIVED_TOOL_NAMES: frozenset[str] = frozenset({"run_code", "run_r_code", "code_session"})


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
        if (
            root in _PIP_INSTALLABLE
            or root in REVIEWABLE_IMPORT_ROOTS
            or root not in ALLOWED_IMPORT_ROOTS
        ):
            candidates.add(_PYPI_ALIASES.get(root, root))

    return sorted(candidates)


_PYTHON_HEADER_TEMPLATE = """\
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
"""

_PYTHON_FOOTER = """

# --- 保存变更（若存在标准输出变量） ---
if "output_df" in dir():
    output_df.to_csv(Path(__file__).parent / "output.csv", index=False)
elif "result_df" in dir():
    result_df.to_csv(Path(__file__).parent / "result.csv", index=False)
"""

_R_HEADER_TEMPLATE = """\
# ========== Nini 代码档案 ==========
# 意图：{intent}
# 执行时间：{created_at}
# 来源会话：{session_id_short} / 执行 ID：{execution_id}
# 原始 tool：{tool_name} (purpose={purpose})
#
# 注意：R 脚本离线复现需要自行加载数据集，示例：
#   df <- read.csv("datasets/<name>.csv")
# ===================================

"""


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


def _resolve_dataset_files(ws: "WorkspaceManager", tool_args: dict[str, Any]) -> list[Path]:
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


def _resolve_output_names(ws: "WorkspaceManager", output_resource_ids: list[str]) -> list[str]:
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
            "- 图表脚本离线运行时不会自动显示，请自行追加 `fig.show()` 或 "
            '`fig.write_html("chart.html")`。'
        )
    return "\n".join(lines) + "\n"


_RUN_SH_PYTHON = """\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python script.py
"""

_RUN_SH_R = """\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
Rscript install.R
Rscript script.R
"""

_INSTALL_R_TEMPLATE = """\
# R 基础依赖（请按脚本实际 library() 调用手工补充）
install.packages(c("readr", "dplyr", "ggplot2"), repos = "https://cloud.r-project.org")
"""


def build_single_bundle(ws: "WorkspaceManager", execution_id: str) -> bytes:
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


_RUN_ALL_SH = """\
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
"""


def build_batch_bundle(ws: "WorkspaceManager") -> bytes:
    """打包会话所有代码档案记录为批量 zip。按时间升序。"""
    all_records = ws.list_code_executions(limit=500)
    records = [r for r in all_records if r.get("tool_name") in ARCHIVED_TOOL_NAMES]
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
