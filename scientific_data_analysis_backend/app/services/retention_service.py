"""
保留期清理辅助方法。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional


def calculate_expiry(days: int, now: Optional[datetime] = None) -> datetime:
    """计算保留截止时间。"""
    base_time = now or datetime.now(timezone.utc)
    return base_time + timedelta(days=days)


def is_expired(expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """判断是否已过期。"""
    if not expires_at:
        return False
    base_time = now or datetime.now(timezone.utc)
    return expires_at <= base_time
