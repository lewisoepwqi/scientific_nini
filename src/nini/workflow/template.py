"""工作流模板数据模型和序列化。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ValidationResult:
    """模板校验结果。"""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class WorkflowStep:
    """工作流中的一个步骤（兼容旧式工具调用和新式声明式字段）。"""

    id: str = ""
    skill: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    condition: str = ""
    outputs: list[dict[str, Any]] = field(default_factory=list)
    # 兼容旧字段
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.skill and self.tool_name:
            self.skill = self.tool_name
        if not self.tool_name and self.skill:
            self.tool_name = self.skill

        if not self.parameters and self.arguments:
            self.parameters = dict(self.arguments)
        if not self.arguments and self.parameters:
            self.arguments = dict(self.parameters)

    @property
    def executable_name(self) -> str:
        return self.skill or self.tool_name

    @property
    def executable_arguments(self) -> dict[str, Any]:
        return self.parameters if self.parameters else self.arguments

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.executable_name,
            "description": self.description,
            "parameters": self.executable_arguments,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "outputs": self.outputs,
            "tool_name": self.executable_name,
            "arguments": self.executable_arguments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        skill = str(data.get("skill") or data.get("tool_name") or "")
        params = data.get("parameters")
        if not isinstance(params, dict):
            params = data.get("arguments")
        if not isinstance(params, dict):
            params = {}

        raw_depends_on = data.get("depends_on", [])
        depends_on = (
            [str(x) for x in raw_depends_on]
            if isinstance(raw_depends_on, list)
            else [str(raw_depends_on)]
        )

        outputs_raw = data.get("outputs", [])
        outputs = outputs_raw if isinstance(outputs_raw, list) else []

        return cls(
            id=str(data.get("id", "")),
            skill=skill,
            description=str(data.get("description", "")),
            parameters=params,
            depends_on=depends_on,
            condition=str(data.get("condition", "")),
            outputs=outputs,
            tool_name=skill,
            arguments=params,
        )


@dataclass
class WorkflowTemplate:
    """工作流模板。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    # 兼容旧模板（dict）和 YAML 声明式模板（list）
    parameters: dict[str, Any] | list[dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    kind: str = "WorkflowTemplate"
    source_session_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        metadata = {
            "name": self.name,
            "id": self.id,
            "description": self.description,
            **self.metadata,
        }
        return {
            "version": self.version,
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "metadata": metadata,
            "steps": [s.to_dict() for s in self.steps],
            "parameters": self.parameters,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowTemplate:
        metadata_raw = data.get("metadata", {})
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        template_id = str(data.get("id") or metadata.get("id") or uuid.uuid4().hex[:12])
        name = str(data.get("name") or metadata.get("name") or "")
        description = str(data.get("description") or metadata.get("description") or "")
        version = str(data.get("version", "1.0"))
        kind = str(data.get("kind", "WorkflowTemplate"))

        params_raw = data.get("parameters", {})
        if not isinstance(params_raw, (dict, list)):
            params_raw = {}

        steps_raw = data.get("steps", [])
        steps = (
            [WorkflowStep.from_dict(s) for s in steps_raw] if isinstance(steps_raw, list) else []
        )

        return cls(
            id=template_id,
            name=name,
            description=description,
            steps=steps,
            parameters=params_raw,
            metadata=metadata,
            version=version,
            kind=kind,
            source_session_id=data.get("source_session_id"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )

    @classmethod
    def from_db_row(cls, row: Any) -> WorkflowTemplate:
        """从数据库行创建实例。"""
        steps_raw = json.loads(row[3]) if isinstance(row[3], str) else row[3]
        params_raw = json.loads(row[4]) if isinstance(row[4], str) else row[4]
        data = {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "steps": steps_raw if isinstance(steps_raw, list) else [],
            "parameters": params_raw if isinstance(params_raw, (dict, list)) else {},
            "source_session_id": row[5],
            "created_at": row[6] or "",
            "updated_at": row[7] or "",
        }
        return cls.from_dict(data)
