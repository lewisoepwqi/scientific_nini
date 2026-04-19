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
        if root in _PIP_INSTALLABLE or root in REVIEWABLE_IMPORT_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
            candidates.add(_PYPI_ALIASES.get(root, root))

    return sorted(candidates)
