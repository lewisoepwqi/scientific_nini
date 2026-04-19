"""代码档案 bundle 构建。

将 run_code / run_r_code 执行记录打包为可复现的 zip，供用户下载本地执行。
"""

from __future__ import annotations

import ast
import re
import sys

from nini.sandbox.policy import ALLOWED_IMPORT_ROOTS, REVIEWABLE_IMPORT_ROOTS

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
