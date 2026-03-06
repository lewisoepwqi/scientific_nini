"""Tool execution logic for AgentRunner.

Handles tool invocation, result serialization, and related utilities.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from nini.agent.session import Session

logger = logging.getLogger(__name__)


async def execute_tool(
    skill_registry: Any,
    session: Session,
    name: str,
    arguments: str,
) -> Any:
    """Execute a tool call through the skill registry.

    Args:
        skill_registry: The skill registry to use for execution.
        session: The current session context.
        name: The tool/function name to execute.
        arguments: JSON-encoded arguments string.

    Returns:
        The tool execution result, or an error dict on failure.
    """
    if skill_registry is None:
        return {"error": f"技能系统未初始化，无法执行 {name}"}

    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        return {"error": f"工具参数解析失败: {arguments}"}

    try:
        result = await skill_registry.execute_with_fallback(name, session=session, **args)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("工具 %s 执行失败: %s", name, e, exc_info=True)
        return {"error": f"工具 {name} 执行失败: {e}"}


def parse_tool_arguments(arguments: str) -> dict[str, Any]:
    """Parse tool arguments JSON, returning empty dict on failure.

    Args:
        arguments: JSON-encoded arguments string.

    Returns:
        Parsed dict or empty dict if parsing fails.
    """
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def serialize_tool_result_for_memory(result: Any) -> str:
    """Serialize tool result for storage in conversation memory.

    Args:
        result: The tool result to serialize.

    Returns:
        JSON string representation of the result.
    """
    if isinstance(result, dict):
        compact = summarize_tool_result_dict(result)
        return json.dumps(compact, ensure_ascii=False, default=str)
    return compact_tool_content(result, max_chars=2000)


def compact_tool_content(content: Any, *, max_chars: int) -> str:
    """Compact tool content for memory storage.

    Args:
        content: The content to compact.
        max_chars: Maximum character limit.

    Returns:
        Compacted string representation.
    """
    text = "" if content is None else str(content)
    parsed: Any = None

    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None

    if isinstance(parsed, dict):
        text = json.dumps(
            summarize_tool_result_dict(parsed),
            ensure_ascii=False,
            default=str,
        )

    if len(text) > max_chars:
        return text[:max_chars] + "...(截断)"
    return text


def summarize_tool_result_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Summarize tool result dict, keeping only essential fields.

    Args:
        data: The tool result data.

    Returns:
        A compact summary of the result.
    """
    compact: dict[str, Any] = {}

    for key in ("success", "message", "error", "status", "error_code", "recovery_hint"):
        if key in data:
            compact[key] = data[key]

    for key in ("has_chart", "has_dataframe"):
        if key in data:
            compact[key] = bool(data.get(key))

    # Extract reference excerpt if present
    existing_excerpt = extract_reference_excerpt(
        data.get("data_excerpt"),
        max_chars=8000,
    )
    if existing_excerpt:
        compact["data_excerpt"] = existing_excerpt

    existing_data_summary = data.get("data_summary")
    if isinstance(existing_data_summary, dict):
        compact["data_summary"] = summarize_nested_dict(existing_data_summary)

    data_obj = data.get("data")
    if isinstance(data_obj, dict):
        # 特殊处理 ask_user_question 的结果：保留完整的 questions 和 answers
        if "questions" in data_obj and "answers" in data_obj:
            compact["data"] = {
                "questions": data_obj.get("questions"),
                "answers": data_obj.get("answers"),
            }
        else:
            compact["data_summary"] = summarize_nested_dict(data_obj)
        excerpt = extract_reference_excerpt(
            data_obj.get("content"),
            max_chars=8000,
        )
        if excerpt:
            compact["data_excerpt"] = excerpt

    artifacts = data.get("artifacts")
    if isinstance(artifacts, list):
        compact["artifact_count"] = len(artifacts)
        names = [
            str(item.get("name"))
            for item in artifacts[:5]
            if isinstance(item, dict) and item.get("name")
        ]
        if names:
            compact["artifact_names"] = names
        artifact_refs = []
        for item in artifacts[:5]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            download_url = str(item.get("download_url", "")).strip()
            if not name and not download_url:
                continue
            artifact_refs.append(
                {
                    "name": name,
                    "download_url": download_url,
                }
            )
        if artifact_refs:
            compact["artifact_refs"] = artifact_refs

    images = data.get("images")
    if isinstance(images, list):
        compact["image_count"] = len(images)
    elif isinstance(images, str) and images:
        compact["image_count"] = 1

    if not compact:
        compact["message"] = "工具执行完成"
    return compact


def extract_reference_excerpt(value: Any, *, max_chars: int) -> str:
    """Extract a text excerpt suitable for context inclusion.

    Args:
        value: The value to extract from.
        max_chars: Maximum character limit.

    Returns:
        The extracted excerpt or empty string.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    # Note: sanitize_reference_text is expected to be called separately
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def summarize_nested_dict(data_obj: dict[str, Any]) -> dict[str, Any]:
    """Create a shallow summary of nested data dict.

    Args:
        data_obj: The data object to summarize.

    Returns:
        A summary dict with key metadata fields.
    """
    summary: dict[str, Any] = {}
    for key in ("name", "dataset_name", "chart_type", "journal_style"):
        if key in data_obj:
            summary[key] = data_obj[key]

    shape = data_obj.get("shape")
    if isinstance(shape, dict):
        summary["shape"] = {
            "rows": shape.get("rows"),
            "columns": shape.get("columns"),
        }

    if "rows" in data_obj and isinstance(data_obj["rows"], int):
        summary["rows"] = data_obj["rows"]
    if "columns" in data_obj and isinstance(data_obj["columns"], int):
        summary["columns"] = data_obj["columns"]

    if "preview_rows" in data_obj and isinstance(data_obj["preview_rows"], int):
        summary["preview_rows"] = data_obj["preview_rows"]
    if "total_rows" in data_obj and isinstance(data_obj["total_rows"], int):
        summary["total_rows"] = data_obj["total_rows"]

    summary["keys"] = list(data_obj.keys())[:10]
    return summary
