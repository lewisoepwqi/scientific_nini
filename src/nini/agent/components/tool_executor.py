"""AgentRunner 的工具执行逻辑。

处理工具调用、结果序列化及相关工具函数。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

from nini.agent.session import Session

logger = logging.getLogger(__name__)


async def execute_tool(
    tool_registry: Any,
    session: Session,
    name: str,
    arguments: str,
) -> Any:
    """通过工具注册中心执行工具调用。

    Args:
        tool_registry: 工具注册中心，用于执行工具调用。
        session: 当前会话上下文。
        name: 要执行的工具/函数名称。
        arguments: JSON 编码的参数字符串。

    Returns:
        工具执行结果，失败时返回错误字典。
    """
    if tool_registry is None:
        return {"error": f"技能系统未初始化，无法执行 {name}"}

    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        return {"error": f"工具参数解析失败: {arguments}"}

    try:
        result = await tool_registry.execute_with_fallback(name, session=session, **args)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("工具 %s 执行失败: %s", name, e, exc_info=True)
        return {"error": f"工具 {name} 执行失败: {e}"}


def parse_tool_arguments(arguments: str) -> dict[str, Any]:
    """解析工具参数 JSON，解析失败时返回空字典。

    Args:
        arguments: JSON 编码的参数字符串。

    Returns:
        解析后的字典，解析失败时返回空字典。
    """
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def serialize_tool_result_for_memory(result: Any, *, tool_name: str = "") -> str:
    """将工具结果序列化后存入会话记忆。

    Args:
        result: 待序列化的工具结果。
        tool_name: 工具名称，用于对特定工具结果做额外结构化提取。

    Returns:
        结果的 JSON 字符串表示。
    """
    if isinstance(result, dict):
        compact = summarize_tool_result_dict(result)
        # 对统计工具结果追加关键发现摘要
        if tool_name in ("stat_test", "stat_model"):
            findings = _extract_stat_findings(result)
            if findings:
                compact["key_findings"] = findings
        return json.dumps(compact, ensure_ascii=False, default=str)
    return compact_tool_content(result, max_chars=2000)


def compact_tool_content(content: Any, *, max_chars: int) -> str:
    """压缩工具内容以存入记忆。

    Args:
        content: 待压缩的内容。
        max_chars: 最大字符数限制。

    Returns:
        压缩后的字符串表示。
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
    """汇总工具结果字典，仅保留关键字段。

    Args:
        data: 工具结果数据。

    Returns:
        结果的精简摘要字典。
    """
    compact: dict[str, Any] = {}
    is_code_session_result = _is_code_session_result(data)

    for key in ("success", "message", "error", "status", "error_code", "recovery_hint"):
        if key in data:
            compact[key] = data[key]

    for key in ("has_chart", "has_dataframe"):
        if key in data:
            compact[key] = bool(data.get(key))

    # 提取引用摘录（如有）
    existing_excerpt = extract_reference_excerpt(
        data.get("data_excerpt"),
        max_chars=8000,
    )
    if existing_excerpt and not is_code_session_result:
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
        elif _is_statistical_result(data_obj):
            compact["stat_summary"] = _summarize_statistical_result(data_obj)
        elif _is_dataset_profile(data_obj):
            # 特殊处理数据集 profile：保留完整列信息
            compact["data_summary"] = _summarize_dataset_profile(data_obj)
        else:
            compact["data_summary"] = summarize_nested_dict(data_obj)
        excerpt = extract_reference_excerpt(
            data_obj.get("content"),
            max_chars=8000,
        )
        if excerpt and not is_code_session_result:
            compact["data_excerpt"] = excerpt

    # 特殊处理 code_session 结果：保留尾部输出而非头部截断
    if _is_code_session_result(data):
        output = str(data.get("message", "") or "")
        lines = output.split("\n")
        if len(lines) > 30:
            compact["execution_output_tail"] = "\n".join(lines[-30:])
            compact["execution_output_lines_total"] = len(lines)

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
    """提取适合上下文引用的文本摘录。

    Args:
        value: 待提取的值。
        max_chars: 最大字符数限制。

    Returns:
        提取的摘录字符串，无内容时返回空字符串。
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    # 注意：sanitize_reference_text 由调用方单独调用
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def summarize_nested_dict(data_obj: dict[str, Any]) -> dict[str, Any]:
    """对嵌套数据字典生成浅层摘要。

    Args:
        data_obj: 待摘要的数据对象。

    Returns:
        包含关键元数据字段的摘要字典。
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


def _is_dataset_profile(data_obj: dict[str, Any]) -> bool:
    """判断数据对象是否为数据集 profile 结构。"""
    return "dataset_name" in data_obj and (
        "basic" in data_obj or "columns" in data_obj or "column_names" in data_obj
    )


def _summarize_dataset_profile(data_obj: dict[str, Any]) -> dict[str, Any]:
    """提取数据集 profile 的关键信息，保留完整列名。"""
    summary: dict[str, Any] = {}

    # 数据集基本信息
    summary["dataset_name"] = data_obj.get("dataset_name", "")

    # 行列数（支持多种结构）
    basic = data_obj.get("basic", {})
    if isinstance(basic, dict):
        if "rows" in basic:
            summary["rows"] = basic["rows"]
        if "columns" in basic:
            summary["columns"] = basic["columns"]
    if "rows" in data_obj and isinstance(data_obj["rows"], int):
        summary["rows"] = data_obj["rows"]
    if "columns" in data_obj and isinstance(data_obj["columns"], int):
        summary["columns"] = data_obj["columns"]

    # 完整列名（最多 50 列）
    col_names: list[str] | None = None
    columns_value = data_obj.get("columns")
    if isinstance(data_obj.get("column_names"), list):
        col_names = [str(c) for c in data_obj["column_names"]]
    elif isinstance(columns_value, list):
        col_names = [str(c) for c in columns_value]
    elif isinstance(basic, dict) and isinstance(basic.get("column_names"), list):
        col_names = [str(c) for c in basic["column_names"]]

    if col_names is not None:
        if len(col_names) > 50:
            summary["column_names"] = col_names[:50]
            summary["column_names_truncated"] = len(col_names) - 50
        else:
            summary["column_names"] = col_names

    # 列类型信息
    dtypes = data_obj.get("dtypes") or (isinstance(basic, dict) and basic.get("dtypes"))
    if isinstance(dtypes, dict):
        summary["dtypes"] = dtypes

    # 缺失值信息
    null_counts = data_obj.get("null_counts") or (
        isinstance(basic, dict) and basic.get("null_counts")
    )
    if isinstance(null_counts, dict):
        summary["null_counts"] = null_counts

    return summary


def _is_code_session_result(data: dict[str, Any]) -> bool:
    """判断工具结果是否为 code_session 执行结果。"""
    return "execution_id" in data or "script_id" in data


def _is_statistical_result(data_obj: dict[str, Any]) -> bool:
    """判断数据对象是否为统计工具结果。"""
    if "stat_summary" in data_obj:
        return True
    return any(
        key in data_obj
        for key in (
            "p_value",
            "effect_size",
            "test_statistic",
            "correlation_matrix",
            "pvalue_matrix",
        )
    )


def _safe_number(value: Any) -> float | None:
    """安全提取有限浮点数。"""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _summarize_statistical_result(data_obj: dict[str, Any]) -> dict[str, Any]:
    """提取统计工具结果的结构化摘要。"""
    summary: dict[str, Any] = {}
    stat_summary = data_obj.get("stat_summary")
    if isinstance(stat_summary, dict):
        summary.update(
            {
                key: stat_summary[key]
                for key in ("kind", "method", "sample_size", "test_name", "significant")
                if key in stat_summary
            }
        )
        pairwise_summary = stat_summary.get("pairwise")
        if isinstance(pairwise_summary, list):
            summary["pairwise"] = [
                {
                    "var_a": str(item.get("var_a", "")).strip(),
                    "var_b": str(item.get("var_b", "")).strip(),
                    "coefficient": _safe_number(item.get("coefficient")),
                    "p_value": _safe_number(item.get("p_value")),
                    "significant": (
                        item.get("significant")
                        if isinstance(item.get("significant"), bool)
                        else None
                    ),
                }
                for item in pairwise_summary[:3]
                if isinstance(item, dict)
            ]
        if summary:
            return summary

    summary["method"] = (
        data_obj.get("requested_method") or data_obj.get("method") or data_obj.get("test_name")
    )
    sample_size = data_obj.get("sample_size")
    if isinstance(sample_size, int):
        summary["sample_size"] = sample_size
    p_value = _safe_number(data_obj.get("p_value"))
    if p_value is not None:
        summary["p_value"] = p_value
    test_statistic = _safe_number(
        data_obj.get("test_statistic") or data_obj.get("statistic") or data_obj.get("t_statistic")
    )
    if test_statistic is not None:
        summary["test_statistic"] = test_statistic
    effect_size = _safe_number(data_obj.get("effect_size") or data_obj.get("cohens_d"))
    if effect_size is not None:
        summary["effect_size"] = effect_size
    significant = data_obj.get("significant")
    if isinstance(significant, bool):
        summary["significant"] = significant

    corr_matrix = data_obj.get("correlation_matrix")
    pvalue_matrix = data_obj.get("pvalue_matrix")
    if isinstance(corr_matrix, dict) and isinstance(pvalue_matrix, dict):
        pairwise_rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for left, row in corr_matrix.items():
            if not isinstance(row, dict):
                continue
            for right, coefficient in row.items():
                left_name = str(left).strip()
                right_name = str(right).strip()
                if not left_name or not right_name or left_name == right_name:
                    continue
                pair_key = (
                    (left_name, right_name) if left_name <= right_name else (right_name, left_name)
                )
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                pair_p = None
                p_row = pvalue_matrix.get(left_name)
                if isinstance(p_row, dict):
                    pair_p = _safe_number(p_row.get(right_name))
                coefficient_value = _safe_number(coefficient)
                pairwise_rows.append(
                    {
                        "var_a": left_name,
                        "var_b": right_name,
                        "coefficient": coefficient_value,
                        "p_value": pair_p,
                        "significant": (bool(pair_p < 0.05) if pair_p is not None else None),
                    }
                )
        if pairwise_rows:
            pairwise_rows.sort(
                key=lambda item: (
                    abs(item["coefficient"]) if item["coefficient"] is not None else -1.0
                ),
                reverse=True,
            )
            summary["pairwise"] = pairwise_rows[:3]
            summary["kind"] = "correlation"

    return {key: value for key, value in summary.items() if value is not None}


def _extract_stat_findings(data: dict[str, Any]) -> str | None:
    """从统计工具结果中提取关键发现摘要。

    在 data 顶层和 data["data"] 中查找统计量字段，格式化为简洁摘要。
    无法提取到关键字段时返回 None。
    """
    # 尝试从顶层和 data 子字段中提取
    sources = [data]
    inner = data.get("data")
    if isinstance(inner, dict):
        sources.append(inner)

    if isinstance(inner, dict):
        stat_summary = _summarize_statistical_result(inner)
        pairwise_items = stat_summary.get("pairwise")
        if isinstance(pairwise_items, list) and pairwise_items:
            summary_parts = ["[关键发现]"]
            method_name = stat_summary.get("method")
            sample_size = stat_summary.get("sample_size")
            if method_name:
                summary_parts.append(f"方法: {method_name}")
            if isinstance(sample_size, int):
                summary_parts.append(f"n={sample_size}")
            pair_texts = []
            for pair in pairwise_items[:3]:
                if not isinstance(pair, dict):
                    continue
                left = str(pair.get("var_a", "")).strip()
                right = str(pair.get("var_b", "")).strip()
                if not left or not right:
                    continue
                fragment = f"{left} vs {right}"
                coefficient = pair.get("coefficient")
                pair_p_value = pair.get("p_value")
                if coefficient is not None:
                    fragment += f", r={coefficient}"
                if pair_p_value is not None:
                    fragment += f", p={pair_p_value}"
                pair_sig = pair.get("significant")
                if isinstance(pair_sig, bool):
                    fragment += ", " + ("显著" if pair_sig else "不显著")
                pair_texts.append(fragment)
            if pair_texts:
                summary_parts.append("；".join(pair_texts))
                return ", ".join(summary_parts)

    method: str | None = None
    p_value: Any = None
    statistic: Any = None
    effect_size: Any = None
    stat_name: str | None = None

    for src in sources:
        if not method:
            method = src.get("method") or src.get("test_name") or src.get("model_type")
        if p_value is None:
            p_value = src.get("p_value") or src.get("p")
        if statistic is None:
            statistic = src.get("statistic") or src.get("test_statistic")
            stat_name = src.get("statistic_name") or src.get("stat_name")
        if effect_size is None:
            effect_size = src.get("effect_size") or src.get("cohens_d") or src.get("r_squared")

    # 至少需要 p 值或统计量才生成摘要
    if p_value is None and statistic is None:
        return None

    parts: list[str] = ["[关键发现]"]
    if method:
        parts.append(f"方法: {method}")
    if statistic is not None:
        label = stat_name or "统计量"
        parts.append(f"{label}={statistic}")
    if p_value is not None:
        parts.append(f"p={p_value}")
    if effect_size is not None:
        parts.append(f"效应量={effect_size}")

    return ", ".join(parts)
