"""收集写作桥接所需的会话分析产物。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.memory.compression import list_session_analysis_memories
from nini.models import ReportSessionRecord, ResourceType
from nini.tools.base import Tool, ToolResult
from nini.workspace import WorkspaceManager


class CollectArtifactsTool(Tool):
    """从当前会话收集写作所需的分析素材包。"""

    @property
    def name(self) -> str:
        return "collect_artifacts"

    @property
    def description(self) -> str:
        return (
            "收集当前会话中的统计结果、图表、方法记录和数据集概要，"
            "输出可直接用于论文或报告写作的结构化素材包。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    @property
    def category(self) -> str:
        return "report"

    @property
    def is_idempotent(self) -> bool:
        return True

    @property
    def output_types(self) -> list[str]:
        return ["json"]

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        del kwargs

        statistical_results = self._collect_statistical_results(session)
        charts = self._collect_charts(session)
        methods = self._collect_methods(session)
        datasets = self._collect_datasets(session)

        has_analysis_artifacts = any((statistical_results, charts, methods))
        bundle = {
            "statistical_results": statistical_results,
            "charts": charts,
            "methods": methods,
            "datasets": datasets,
            "summary": {
                "session_id": session.id,
                "statistical_result_count": len(statistical_results),
                "chart_count": len(charts),
                "method_count": len(methods),
                "dataset_count": len(datasets),
                "has_analysis_artifacts": has_analysis_artifacts,
                "mode": "analysis_bridge" if has_analysis_artifacts else "pure_guidance",
            },
        }

        if has_analysis_artifacts or datasets:
            return ToolResult(
                success=True,
                message=(
                    "已收集写作素材包："
                    f"{len(statistical_results)} 条统计结果，"
                    f"{len(charts)} 个图表，"
                    f"{len(methods)} 条方法记录，"
                    f"{len(datasets)} 个数据集。"
                ),
                data=bundle,
            )

        return ToolResult(
            success=True,
            message="当前会话暂无分析产物，已返回空素材包，可切换为纯引导写作模式。",
            data=bundle,
        )

    def _collect_statistical_results(self, session: Session) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()

        for memory in list_session_analysis_memories(session.id):
            dataset_name = str(memory.dataset_name or "").strip() or None
            for statistic in memory.statistics:
                item = {
                    "dataset_name": dataset_name,
                    "method_name": statistic.test_name,
                    "test_statistic": statistic.test_statistic,
                    "p_value": statistic.p_value,
                    "degrees_of_freedom": statistic.degrees_of_freedom,
                    "effect_size": statistic.effect_size,
                    "effect_type": statistic.effect_type or None,
                    "significant": statistic.significant,
                    "source": "analysis_memory",
                }
                dedup_key = (
                    item["dataset_name"],
                    item["method_name"],
                    item["test_statistic"],
                    item["p_value"],
                    item["effect_size"],
                )
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                results.append(item)

        for item in self._collect_statistical_results_from_messages(session):
            dedup_key = (
                item.get("dataset_name"),
                item.get("method_name"),
                item.get("test_statistic"),
                item.get("p_value"),
                item.get("effect_size"),
            )
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            results.append(item)

        return results

    def _collect_statistical_results_from_messages(self, session: Session) -> list[dict[str, Any]]:
        tool_names_by_call_id: dict[str, str] = {}
        results: list[dict[str, Any]] = []

        for message in session.messages:
            if message.get("role") != "assistant":
                continue
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue
            for item in tool_calls:
                if not isinstance(item, dict):
                    continue
                call_id = str(item.get("id", "")).strip()
                function_info = item.get("function")
                if not call_id or not isinstance(function_info, dict):
                    continue
                tool_name = str(function_info.get("name", "")).strip()
                if tool_name:
                    tool_names_by_call_id[call_id] = tool_name

        for message in session.messages:
            if message.get("role") != "tool":
                continue
            payload = self._safe_load_json(message.get("content"))
            if not isinstance(payload, dict):
                continue
            tool_call_id = str(message.get("tool_call_id", "")).strip()
            tool_name = str(message.get("tool_name", "")).strip() or tool_names_by_call_id.get(
                tool_call_id, ""
            )
            if tool_name not in {"stat_test", "stat_model", "stat_interpret"}:
                continue
            normalized = self._normalize_statistical_result_payload(payload, tool_name=tool_name)
            if normalized is not None:
                results.append(normalized)

        return results

    def _normalize_statistical_result_payload(
        self,
        payload: dict[str, Any],
        *,
        tool_name: str,
    ) -> dict[str, Any] | None:
        data = payload.get("data")
        content = data if isinstance(data, dict) else payload

        method_name = str(
            content.get("requested_method")
            or content.get("test_name")
            or content.get("method")
            or tool_name
        ).strip()
        if not method_name:
            return None

        test_statistic = self._first_number(
            content,
            "test_statistic",
            "statistic",
            "t_statistic",
            "f_statistic",
            "coefficient",
        )
        p_value = self._first_number(content, "p_value")
        effect_size, effect_type = self._extract_effect_size(content)
        degrees_of_freedom = self._first_int(content, "degrees_of_freedom", "df")
        significant = content.get("significant")
        if not isinstance(significant, bool):
            significant = bool(p_value is not None and p_value < 0.05)

        return {
            "dataset_name": self._optional_string(content.get("dataset_name")),
            "method_name": method_name,
            "test_statistic": test_statistic,
            "p_value": p_value,
            "degrees_of_freedom": degrees_of_freedom,
            "effect_size": effect_size,
            "effect_type": effect_type,
            "significant": significant,
            "source": "tool_result",
        }

    def _collect_charts(self, session: Session) -> list[dict[str, Any]]:
        manager = WorkspaceManager(session.id)
        charts: list[dict[str, Any]] = []
        for artifact in manager.list_artifacts():
            artifact_type = str(artifact.get("type", "")).strip().lower()
            visibility = str(artifact.get("visibility", "deliverable")).strip().lower()
            if visibility == "internal":
                continue
            if artifact_type in {"code", "text_file", "report"}:
                continue

            path = Path(str(artifact.get("path", "")).strip()) if artifact.get("path") else None
            chart_type = artifact_type or self._infer_chart_type(path)
            charts.append(
                {
                    "resource_id": self._optional_string(artifact.get("id")),
                    "title": self._optional_string(artifact.get("name")) or "未命名图表",
                    "chart_type": chart_type,
                    "file_path": str(path) if path else None,
                    "download_url": self._optional_string(artifact.get("download_url")),
                    "format": self._optional_string(artifact.get("format"))
                    or (path.suffix.lstrip(".") if path and path.suffix else None),
                }
            )
        return charts

    def _collect_methods(self, session: Session) -> list[dict[str, Any]]:
        manager = WorkspaceManager(session.id)
        methods: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()

        for resource in manager.list_resource_summaries():
            if str(resource.get("resource_type", "")).strip() != ResourceType.REPORT.value:
                continue
            if str(resource.get("source_kind", "")).strip() != "reports":
                continue
            path_text = str(resource.get("path", "")).strip()
            if not path_text:
                continue
            path = Path(path_text)
            if not path.exists() or not path.is_file():
                continue
            try:
                record = ReportSessionRecord.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
            for entry in record.methods_ledger:
                item = {
                    "entry_id": entry.entry_id,
                    "step_name": entry.step_name,
                    "method_name": entry.method_name,
                    "tool_name": entry.tool_name,
                    "data_sources": list(entry.data_sources),
                    "key_parameters": dict(entry.key_parameters),
                    "model_name": entry.model_name,
                    "model_version": entry.model_version,
                    "executed_at": (
                        entry.executed_at.isoformat() if entry.executed_at is not None else None
                    ),
                    "notes": entry.notes or "",
                    "missing_fields": list(entry.missing_fields),
                    "report_id": record.id,
                    "report_title": record.title,
                }
                dedup_key = (
                    item["entry_id"],
                    item["step_name"],
                    item["method_name"],
                    item["tool_name"],
                    item["executed_at"],
                )
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                methods.append(item)
        return methods

    def _collect_datasets(self, session: Session) -> list[dict[str, Any]]:
        manager = WorkspaceManager(session.id)
        workspace_records = {
            str(item.get("name", "")).strip(): item
            for item in manager.list_datasets()
            if isinstance(item, dict)
        }
        datasets: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for name, dataframe in session.datasets.items():
            dataset_name = str(name).strip()
            if not dataset_name:
                continue
            record = workspace_records.get(dataset_name, {})
            datasets.append(
                {
                    "name": dataset_name,
                    "row_count": int(getattr(dataframe, "shape", (0, 0))[0]),
                    "column_count": int(getattr(dataframe, "shape", (0, 0))[1]),
                    "columns": [str(column) for column in list(getattr(dataframe, "columns", []))],
                    "file_type": self._optional_string(record.get("file_type")),
                    "file_path": self._optional_string(record.get("file_path")),
                    "download_url": self._build_dataset_download_url(
                        session.id,
                        record=record,
                    ),
                    "source_kind": self._optional_string(record.get("source_kind")) or "session",
                }
            )
            seen_names.add(dataset_name)

        for name, record in workspace_records.items():
            if not name or name in seen_names:
                continue
            datasets.append(
                {
                    "name": name,
                    "row_count": record.get("row_count"),
                    "column_count": record.get("column_count"),
                    "columns": [],
                    "file_type": self._optional_string(record.get("file_type")),
                    "file_path": self._optional_string(record.get("file_path")),
                    "download_url": self._build_dataset_download_url(
                        session.id,
                        record=record,
                    ),
                    "source_kind": self._optional_string(record.get("source_kind")) or "datasets",
                }
            )

        return datasets

    def _build_dataset_download_url(
        self,
        session_id: str,
        *,
        record: dict[str, Any],
    ) -> str | None:
        file_path = self._optional_string(record.get("file_path"))
        if not file_path:
            return None
        return f"/api/workspace/{session_id}/uploads/{Path(file_path).name}"

    def _extract_effect_size(self, payload: dict[str, Any]) -> tuple[float | None, str | None]:
        direct_effect_size = self._first_number(payload, "effect_size")
        if direct_effect_size is not None:
            return direct_effect_size, self._optional_string(payload.get("effect_type"))

        aliases = (
            ("cohens_d", "cohens_d"),
            ("eta_squared", "eta_squared"),
            ("r", "r"),
        )
        for field_name, effect_type in aliases:
            value = self._first_number(payload, field_name)
            if value is not None:
                return value, effect_type
        return None, None

    def _infer_chart_type(self, path: Path | None) -> str:
        if path is None:
            return "chart"
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
            return "chart"
        if suffix == ".html":
            return "interactive_chart"
        return "artifact"

    def _safe_load_json(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def _first_number(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _first_int(self, payload: dict[str, Any], *keys: str) -> int | None:
        value = self._first_number(payload, *keys)
        if value is None:
            return None
        return int(value)

    def _optional_string(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None
