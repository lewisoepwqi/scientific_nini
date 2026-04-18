"""兜底总结合成器。

当 agent turn 被 LoopGuard/FORCE_STOP 中断时，从 session.messages 里抓取本轮
已成功的 artifact 与 tool stdout，拼成一段 Markdown 文本交给用户。
目的：让"终止"不等于"白跑"，模型产出的结果仍可读。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any


def _stem_and_ext(name: str) -> tuple[str, str]:
    """拆 'bar_chart.pdf' -> ('bar_chart', 'pdf')。无扩展名时 ext 为 ''。"""
    if "." not in name:
        return name, ""
    stem, ext = name.rsplit(".", 1)
    return stem, ext.lower()


_FORMAT_PRIORITY = ["png", "svg", "jpg", "jpeg", "webp", "pdf"]


def _pick_preferred_format(group: list[dict[str, Any]]) -> dict[str, Any]:
    """同一 stem 的多个格式里挑优先级最高的（png > svg > jpg > pdf）。"""

    def rank(item: dict[str, Any]) -> int:
        _, ext = _stem_and_ext(str(item.get("name", "")))
        try:
            return _FORMAT_PRIORITY.index(ext)
        except ValueError:
            return len(_FORMAT_PRIORITY)

    return sorted(group, key=rank)[0]


def _collect_chart_artifacts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 assistant/artifact 事件收集 chart 类型产物，按 stem 去重后挑最佳格式。"""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        if msg.get("event_type") != "artifact":
            continue
        for art in msg.get("artifacts", []) or []:
            if art.get("type") != "chart":
                continue
            stem, _ext = _stem_and_ext(str(art.get("name", "")))
            grouped[stem].append(art)
    return [_pick_preferred_format(g) for g in grouped.values() if g]


_STDOUT_SNIPPET_RE = re.compile(r"(Mean=[^\s,\"\\]+|p\s*[=<>]\s*[\d.eE+-]+|SEM=[^\s,\"\\]+)")


def _extract_stat_lines(messages: list[dict[str, Any]]) -> list[str]:
    """从 tool 消息 content（JSON 字符串）里提取含统计数字的行。"""
    lines: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        raw = msg.get("content", "")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            parsed = json.loads(raw)
            stdout = parsed.get("message", "") if isinstance(parsed, dict) else ""
        except json.JSONDecodeError:
            stdout = raw
        for line in str(stdout).splitlines():
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            if _STDOUT_SNIPPET_RE.search(stripped):
                lines.append(stripped)
                seen.add(stripped)
    return lines


def build_fallback_summary(
    messages: list[dict[str, Any]],
    user_request: str | None = None,
) -> str | None:
    """合成兜底总结。数据不足时返回 None。"""
    charts = _collect_chart_artifacts(messages)
    stat_lines = _extract_stat_lines(messages)

    if not charts and not stat_lines:
        return None

    parts: list[str] = [
        "> ⚠️ 系统终止了自动化执行循环，以下是**兜底总结**" "（基于已生成的工具产物与统计输出）："
    ]
    if user_request:
        req = user_request.strip().splitlines()[0][:120]
        parts.append(f"\n**原始请求**：{req}")

    if stat_lines:
        parts.append("\n**关键统计结果**：")
        parts.extend(f"- {line}" for line in stat_lines[:12])

    if charts:
        parts.append("\n**生成的图表**：")
        for art in charts:
            name = str(art.get("name", "chart"))
            url = str(art.get("download_url", ""))
            parts.append(f"\n![{name}]({url})")

    return "\n".join(parts)
