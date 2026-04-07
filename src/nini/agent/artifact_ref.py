"""产物引用结构 —— 子 Agent 产物的轻量文件系统引用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ArtifactRef:
    """子 Agent 产物的轻量引用结构。

    存储产物的路径引用，而非产物内容本身，避免大型对象占用上下文窗口。
    path 为相对于父会话 workspace 根目录的路径。
    """

    path: str       # 相对于父会话 workspace 的路径，如 artifacts/agent_id/chart.json
    type: str       # "chart" | "dataset" | "report" | "file"
    summary: str    # 一句话描述，供融合引擎生成摘要
    agent_id: str   # 生成者 agent_id（由 spawner 填充）

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于跨进程传递或持久化。"""
        return {
            "path": self.path,
            "type": self.type,
            "summary": self.summary,
            "agent_id": self.agent_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactRef:
        """从字典反序列化。"""
        return cls(
            path=str(data.get("path", "")),
            type=str(data.get("type", "file")),
            summary=str(data.get("summary", "")),
            agent_id=str(data.get("agent_id", "")),
        )
