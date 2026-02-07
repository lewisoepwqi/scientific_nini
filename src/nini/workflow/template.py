"""工作流模板数据模型和序列化。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class WorkflowStep:
    """工作流中的一个步骤（工具调用）。"""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            tool_name=data["tool_name"],
            arguments=data.get("arguments", {}),
            description=data.get("description", ""),
        )


@dataclass
class WorkflowTemplate:
    """工作流模板。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    source_session_id: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "parameters": self.parameters,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_row(cls, row: Any) -> WorkflowTemplate:
        """从数据库行创建实例。"""
        steps_raw = json.loads(row[3]) if isinstance(row[3], str) else row[3]
        params_raw = json.loads(row[4]) if isinstance(row[4], str) else row[4]
        return cls(
            id=row[0],
            name=row[1],
            description=row[2] or "",
            steps=[WorkflowStep.from_dict(s) for s in steps_raw],
            parameters=params_raw or {},
            source_session_id=row[5],
            created_at=row[6] or "",
            updated_at=row[7] or "",
        )
