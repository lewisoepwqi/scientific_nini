"""证据链与 METHODS 归一化辅助函数。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from nini.models.common import parse_optional_datetime
from nini.models.knowledge import KnowledgeDocument
from nini.models.session_resources import MethodsLedgerEntry, SourceRecord


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def normalize_source_record(
    raw: SourceRecord | KnowledgeDocument | dict[str, Any],
    *,
    default_method: str = "unknown",
) -> SourceRecord:
    """将不同来源归一化为最小溯源记录。"""
    if isinstance(raw, SourceRecord):
        return raw

    if isinstance(raw, KnowledgeDocument):
        metadata = dict(raw.metadata)
        source_time = (
            raw.updated_at
            or raw.created_at
            or parse_optional_datetime(metadata.get("published_at"))
            or parse_optional_datetime(metadata.get("source_time"))
        )
        url = _clean_text(metadata.get("url"))
        return SourceRecord(
            source_id=f"knowledge:{raw.id}",
            source_type="knowledge_document",
            title=raw.title or raw.id,
            acquisition_method=raw.source_method,
            accessed_at=utc_now(),
            source_time=source_time,
            stable_ref=raw.id,
            document_id=raw.id,
            url=url or None,
            excerpt=raw.excerpt or "",
            metadata={
                "file_type": raw.file_type,
                "domain": metadata.get("domain"),
            },
        )

    payload = dict(raw)
    source_id = _clean_text(
        payload.get("source_id") or payload.get("stable_source_id") or payload.get("stable_id")
    )
    title = _clean_text(
        payload.get("title")
        or payload.get("document_title")
        or payload.get("name")
        or payload.get("source")
        or payload.get("resource_name")
    )
    source_type = _clean_text(payload.get("source_type") or payload.get("resource_type"))
    acquisition_method = _clean_text(
        payload.get("acquisition_method")
        or payload.get("method")
        or payload.get("source_method")
        or payload.get("source_kind")
    )
    stable_ref = _clean_text(
        payload.get("stable_ref")
        or payload.get("document_id")
        or payload.get("resource_id")
        or payload.get("id")
        or payload.get("url")
    )
    document_id = _clean_text(payload.get("document_id"))
    resource_id = _clean_text(payload.get("resource_id") or payload.get("id"))
    url = _clean_text(
        payload.get("url") or payload.get("download_url") or payload.get("source_url")
    )
    excerpt = _clean_text(payload.get("excerpt") or payload.get("snippet"))

    if resource_id and (payload.get("resource_type") or payload.get("source_kind")):
        source_type = source_type or "workspace_resource"
        source_id = source_id or f"workspace:{resource_id}"
        acquisition_method = acquisition_method or "workspace"
    elif document_id:
        source_type = source_type or "knowledge_document"
        source_id = source_id or f"knowledge:{document_id}"
        acquisition_method = acquisition_method or default_method
    else:
        source_type = source_type or "external_source"
        source_id = source_id or f"source:{_stable_hash(title or url or stable_ref or 'unknown')}"
        acquisition_method = acquisition_method or default_method

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return SourceRecord(
        source_id=source_id,
        source_type=source_type,
        title=title or source_id,
        acquisition_method=acquisition_method,
        accessed_at=(
            parse_optional_datetime(payload.get("accessed_at"))
            or parse_optional_datetime(payload.get("retrieved_at"))
            or utc_now()
        ),
        source_time=(
            parse_optional_datetime(payload.get("source_time"))
            or parse_optional_datetime(payload.get("updated_at"))
            or parse_optional_datetime(payload.get("created_at"))
        ),
        stable_ref=stable_ref or None,
        document_id=document_id or None,
        resource_id=resource_id or None,
        url=url or None,
        excerpt=excerpt,
        metadata=metadata,
    )


def render_methods_v1(entries: list[MethodsLedgerEntry]) -> str:
    """根据 METHODS 台账生成 METHODS v1 文本。"""
    if not entries:
        return ""

    lines = [
        "### METHODS v1",
        "",
        "以下内容由当前会话台账自动汇总；缺失字段会显式标记。",
        "",
    ]
    for index, entry in enumerate(entries, 1):
        lines.append(f"{index}. 步骤：{entry.step_name}")
        lines.append(f"   方法/工具：{entry.method_name}")
        if entry.data_sources:
            lines.append(f"   数据来源：{', '.join(entry.data_sources)}")
        else:
            lines.append("   数据来源：未记录")
        if entry.key_parameters:
            params = ", ".join(
                f"{key}={value}" for key, value in sorted(entry.key_parameters.items())
            )
            lines.append(f"   关键参数：{params}")
        else:
            lines.append("   关键参数：未记录")
        if entry.model_name or entry.model_version:
            model_desc = " / ".join(
                part for part in [entry.model_name, entry.model_version] if part
            )
            lines.append(f"   模型版本：{model_desc}")
        else:
            lines.append("   模型版本：未记录")
        if entry.executed_at is not None:
            lines.append(f"   执行时间：{entry.executed_at.astimezone(timezone.utc).isoformat()}")
        else:
            lines.append("   执行时间：未记录")
        if entry.notes:
            lines.append(f"   说明：{entry.notes}")
        if entry.missing_fields:
            lines.append(f"   缺失字段：{', '.join(entry.missing_fields)}")
        lines.append("")
    return "\n".join(lines).strip()


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
