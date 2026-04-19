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
