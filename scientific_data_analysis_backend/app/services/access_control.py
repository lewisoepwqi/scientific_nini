"""
访问控制辅助方法。
"""
from typing import Iterable

from app.models.enums import SharePermission


def can_view_task(owner_id: str, user_id: str, shared_member_ids: Iterable[str]) -> bool:
    """判断用户是否可查看任务。"""
    if owner_id == user_id:
        return True
    return user_id in set(shared_member_ids)


def can_edit_task(
    owner_id: str,
    user_id: str,
    shared_permissions: Iterable[tuple[str, SharePermission]],
) -> bool:
    """判断用户是否可编辑任务。"""
    if owner_id == user_id:
        return True
    permission_map = {member_id: permission for member_id, permission in shared_permissions}
    return permission_map.get(user_id) == SharePermission.EDIT
