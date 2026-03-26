"""证据链收集器。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nini.models.session_resources import EvidenceChain, EvidenceNode, EvidenceNodeType


class EvidenceCollector:
    """管理会话内证据链节点的收集与回溯。"""

    def __init__(self, session_id: str) -> None:
        self._chain = EvidenceChain(
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
        self._node_index: dict[str, EvidenceNode] = {}

    @property
    def chain(self) -> EvidenceChain:
        """返回当前会话的完整证据链。"""
        return self._chain

    def add_data_node(
        self,
        dataset_name: str,
        *,
        source_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        """添加数据来源节点。"""
        return self._add_node(
            node_type="data",
            label=dataset_name,
            source_ref=source_ref or dataset_name,
            metadata=metadata,
        )

    def add_analysis_node(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        result_ref: str | None = None,
        parent_ids: list[str] | None = None,
        *,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        """添加分析节点。"""
        merged_metadata = dict(metadata or {})
        if params:
            merged_metadata.setdefault("params", params)
        if result_ref:
            merged_metadata.setdefault("result_ref", result_ref)
        return self._add_node(
            node_type="analysis",
            label=label or tool_name,
            source_ref=result_ref or tool_name,
            parent_ids=parent_ids,
            metadata=merged_metadata,
        )

    def add_chart_node(
        self,
        chart_path: str,
        parent_ids: list[str] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        """添加图表节点。"""
        return self._add_node(
            node_type="chart",
            label=chart_path,
            source_ref=chart_path,
            parent_ids=parent_ids,
            metadata=metadata,
        )

    def add_conclusion_node(
        self,
        claim: str,
        parent_ids: list[str] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        """添加结论节点。"""
        return self._add_node(
            node_type="conclusion",
            label=claim,
            source_ref=None,
            parent_ids=parent_ids,
            metadata=metadata,
        )

    def find_nodes(self, query: str, *, node_type: EvidenceNodeType | None = None) -> list[EvidenceNode]:
        """按关键词检索节点。"""
        normalized_query = query.strip().lower()
        matches: list[EvidenceNode] = []
        for node in self._chain.nodes:
            if node_type and node.node_type != node_type:
                continue
            if not normalized_query:
                matches.append(node)
                continue
            source_ref = (node.source_ref or "").lower()
            if normalized_query in node.label.lower() or normalized_query in source_ref:
                matches.append(node)
        return matches

    def latest_node_ids(self, *node_types: EvidenceNodeType) -> list[str]:
        """返回最近添加的节点 ID。"""
        nodes = self._chain.nodes
        if node_types:
            allowed = set(node_types)
            nodes = [node for node in nodes if node.node_type in allowed]
        if not nodes:
            return []
        return [nodes[-1].id]

    def get_chain_for(self, node_id: str) -> EvidenceChain:
        """获取指定节点及其全部上游节点。"""
        visited: set[str] = set()
        ordered_nodes: list[EvidenceNode] = []

        def visit(current_id: str) -> None:
            if current_id in visited:
                return
            node = self._node_index.get(current_id)
            if node is None:
                return
            visited.add(current_id)
            ordered_nodes.append(node)
            for parent_id in node.parent_ids:
                visit(parent_id)

        visit(node_id)
        return EvidenceChain(
            session_id=self._chain.session_id,
            nodes=ordered_nodes,
            created_at=self._chain.created_at,
        )

    def _add_node(
        self,
        *,
        node_type: EvidenceNodeType,
        label: str,
        source_ref: str | None = None,
        parent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        valid_parent_ids = [
            parent_id for parent_id in (parent_ids or []) if parent_id in self._node_index
        ]
        node = EvidenceNode(
            id=uuid4().hex,
            node_type=node_type,
            label=label,
            source_ref=source_ref,
            parent_ids=valid_parent_ids,
            metadata=dict(metadata or {}),
        )
        self._chain.nodes.append(node)
        self._node_index[node.id] = node
        return node
