"""工作流模板的数据库持久化层。"""

from __future__ import annotations

import json
import logging
from typing import Any

from nini.models.database import get_db
from nini.workflow.template import WorkflowTemplate

logger = logging.getLogger(__name__)


async def save_template(template: WorkflowTemplate) -> None:
    """保存工作流模板到数据库。"""
    db = await get_db()
    try:
        steps_json = json.dumps(
            [s.to_dict() for s in template.steps], ensure_ascii=False
        )
        params_json = json.dumps(template.parameters, ensure_ascii=False)

        await db.execute(
            """
            INSERT INTO workflow_templates (id, name, description, steps, parameters, source_session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                steps = excluded.steps,
                parameters = excluded.parameters,
                updated_at = datetime('now')
            """,
            (
                template.id,
                template.name,
                template.description,
                steps_json,
                params_json,
                template.source_session_id,
            ),
        )
        await db.commit()
        logger.info("已保存工作流模板: %s (%s)", template.name, template.id)
    finally:
        await db.close()


async def list_templates() -> list[dict[str, Any]]:
    """列出所有工作流模板。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, description, steps, parameters, source_session_id, created_at, updated_at "
            "FROM workflow_templates ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [WorkflowTemplate.from_db_row(row).to_dict() for row in rows]
    finally:
        await db.close()


async def get_template(template_id: str) -> WorkflowTemplate | None:
    """获取指定模板。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, description, steps, parameters, source_session_id, created_at, updated_at "
            "FROM workflow_templates WHERE id = ?",
            (template_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return WorkflowTemplate.from_db_row(row)
    finally:
        await db.close()


async def delete_template(template_id: str) -> bool:
    """删除指定模板。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM workflow_templates WHERE id = ?", (template_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
