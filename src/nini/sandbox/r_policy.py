"""R 沙箱安全策略：包白名单与危险调用静态校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# R 基础包 + 数据分析常用包 + Bioconductor 常用包（按需扩充）
ALLOWED_R_PACKAGES: set[str] = {
    # Base / 推荐包
    "base",
    "utils",
    "stats",
    "graphics",
    "grDevices",
    "methods",
    "datasets",
    "grid",
    "splines",
    "parallel",
    "stats4",
    "tcltk",
    # 数据处理
    "dplyr",
    "tidyr",
    "tibble",
    "readr",
    "stringr",
    "forcats",
    "purrr",
    "data.table",
    "janitor",
    "lubridate",
    "zoo",
    # 可视化
    "ggplot2",
    "scales",
    "patchwork",
    "cowplot",
    "ggpubr",
    "viridis",
    "plotly",
    # 统计建模
    "broom",
    "car",
    "lme4",
    "nlme",
    "emmeans",
    "survival",
    "forecast",
    "MASS",
    "mgcv",
    # 生物信息常用
    "BiocManager",
    "Biobase",
    "BiocGenerics",
    "S4Vectors",
    "IRanges",
    "GenomicRanges",
    "SummarizedExperiment",
    "DESeq2",
    "edgeR",
    "limma",
    "clusterProfiler",
    "org.Hs.eg.db",
    "MetaCycle",
    "JTK_CYCLE",
    "ComplexHeatmap",
    "GSVA",
    # 结果序列化
    "jsonlite",
}

# 直接禁止调用的危险函数（含基础系统调用、动态执行、网络下载等）
BANNED_R_CALLS: set[str] = {
    "system",
    "system2",
    "shell",
    "shell.exec",
    "file.remove",
    "file.rename",
    "file.copy",
    "unlink",
    "download.file",
    "url",
    "curl",
    "browseURL",
    "eval",
    "parse",
    "source",
    "Sys.getenv",
    "Sys.setenv",
    ".Internal",
    ".Call",
    ".External",
}

_PACKAGE_CALL_RE = re.compile(
    r"\b(?:library|require|requireNamespace)\s*\(\s*['\"]?([A-Za-z][A-Za-z0-9._]*)['\"]?",
    flags=re.IGNORECASE,
)


@dataclass
class RPolicyViolation:
    """R 策略违规信息。"""

    message: str
    lineno: int | None = None


class RSandboxPolicyError(ValueError):
    """R 沙箱策略校验失败。"""


def _strip_inline_comment(line: str) -> str:
    # R 中 # 为行注释起点；静态校验采用保守策略，忽略注释段。
    return line.split("#", 1)[0]


def _check_banned_calls(line: str, lineno: int) -> RPolicyViolation | None:
    stripped = line.strip()
    if not stripped:
        return None

    for call_name in BANNED_R_CALLS:
        pattern = rf"(?<![A-Za-z0-9_.]){re.escape(call_name)}\s*\("
        if re.search(pattern, stripped):
            return RPolicyViolation(
                message=f"不允许调用函数: {call_name}",
                lineno=lineno,
            )
    return None


def _check_allowed_packages(line: str, lineno: int) -> RPolicyViolation | None:
    for matched in _PACKAGE_CALL_RE.finditer(line):
        package_name = matched.group(1)
        if package_name and package_name not in ALLOWED_R_PACKAGES:
            return RPolicyViolation(
                message=f"不允许使用 R 包: {package_name}",
                lineno=lineno,
            )
    return None


def validate_r_code(code: str) -> None:
    """校验 R 代码是否满足沙箱策略。"""
    violations: list[RPolicyViolation] = []

    for lineno, raw_line in enumerate(code.splitlines(), start=1):
        line = _strip_inline_comment(raw_line)
        if not line.strip():
            continue

        banned_violation = _check_banned_calls(line, lineno)
        if banned_violation is not None:
            violations.append(banned_violation)
            continue

        package_violation = _check_allowed_packages(line, lineno)
        if package_violation is not None:
            violations.append(package_violation)

    if violations:
        first = violations[0]
        where = f" (第 {first.lineno} 行)" if first.lineno else ""
        raise RSandboxPolicyError(f"{first.message}{where}")
