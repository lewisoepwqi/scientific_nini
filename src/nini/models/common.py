"""数据模型公共约定。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


class TimestampedModel(BaseModel):
    """带 UTC 时间戳的轻量基础模型。"""

    created_at: datetime = Field(default_factory=utc_now, description="创建时间")
    updated_at: datetime = Field(default_factory=utc_now, description="更新时间")


class IdentifiedModel(TimestampedModel):
    """带 ID 的基础模型。"""

    id: str = Field(description="唯一标识")


def parse_optional_datetime(value: Any) -> datetime | None:
    """兼容解析 ISO 时间字符串。"""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None
