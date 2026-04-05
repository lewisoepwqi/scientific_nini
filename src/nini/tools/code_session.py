"""脚本会话基础工具。"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.models import ResourceType, ScriptSessionRecord
from nini.tools.base import Tool, ToolResult
from nini.tools.code_runtime import execute_python_code, execute_r_code
from nini.workspace import WorkspaceManager


class CodeSessionTool(Tool):
    """管理持久化脚本资源与执行历史。"""

    _LANGUAGES = {"python": "py", "r": "R"}
    _PYTHON_FILE_IO_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\bpd\.(read_csv|read_excel|read_parquet|read_json|read_pickle)\s*\("),
        re.compile(r"\bopen\s*\("),
        re.compile(r"\bPath\s*\([^)]*\)\s*\.(read_text|read_bytes|open)\s*\("),
    )

    @property
    def name(self) -> str:
        return "code_session"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "创建、读取和执行持久化脚本会话（Python/R），统一管理脚本与执行历史。\n"
            "最小示例：{operation: create_script, content: result = 42}\n"
            "传入 dataset_name 时沙箱自动注入 df（DataFrame），禁止 pd.read_csv 等文件读取。\n"
            "预注入 pd/np/plt/sns/go/px/datetime/re/json，无需 import。\n"
            "图表自动导出，禁止 plt.savefig()。禁止 import __main__ 或系统 I/O。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create_script",
                        "get_script",
                        "run_script",
                        "patch_script",
                        "rerun",
                        "promote_output",
                        "list_scripts",
                    ],
                },
                "script_id": {"type": "string"},
                "language": {"type": "string", "enum": ["python", "r"]},
                "content": {"type": "string"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["replace_range", "replace_string", "append"],
                        },
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                    "additionalProperties": False,
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"mode": {"const": "append"}},
                            "required": ["mode", "new_string"],
                        },
                        {
                            "type": "object",
                            "properties": {"mode": {"const": "replace_string"}},
                            "required": ["mode", "old_string", "new_string"],
                        },
                        {
                            "type": "object",
                            "properties": {"mode": {"const": "replace_range"}},
                            "required": ["mode", "start_line", "end_line", "new_string"],
                        },
                    ],
                },
                "dataset_name": {"type": "string"},
                "persist_df": {"type": "boolean", "default": False},
                "save_as": {
                    "type": "string",
                    "description": "将 DataFrame 结果保存为持久化数据集的名称。仅影响 DataFrame 保存，与图表导出无关。图表会自动收集导出。",
                },
                "resource_name": {"type": "string"},
                "resource_id": {"type": "string"},
                "artifact_resource_id": {"type": "string"},
                "artifact_name": {"type": "string"},
                "artifact_path": {"type": "string"},
                "purpose": {
                    "type": "string",
                    "enum": ["exploration", "visualization", "export", "transformation"],
                    "default": "exploration",
                    "description": "脚本用途。绘图时必须设为 'visualization' 并提供 label，以便图表正确命名和导出。",
                },
                "label": {"type": "string"},
                "intent": {"type": "string"},
                "auto_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "创建脚本后是否立即执行。默认 true；仅在需要先人工检查脚本时显式设为 false。",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"operation": {"const": "create_script"}},
                    "required": ["operation", "content"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "get_script"}},
                    "required": ["operation", "script_id"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "run_script"}},
                    "required": ["operation"],
                    "anyOf": [{"required": ["script_id"]}, {"required": ["content"]}],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "patch_script"}},
                    "required": ["operation", "script_id", "patch"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "rerun"}},
                    "required": ["operation", "script_id"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "promote_output"}},
                    "required": ["operation"],
                    "anyOf": [
                        {"required": ["dataset_name"]},
                        {"required": ["artifact_resource_id"]},
                        {"required": ["artifact_name"]},
                        {"required": ["artifact_path"]},
                    ],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "list_scripts"}},
                    "required": ["operation"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "create_script":
            return await self._create_script(session, **kwargs)
        if operation == "get_script":
            return self._get_script(session, **kwargs)
        if operation == "run_script":
            return await self._run_script(session, **kwargs)
        if operation == "patch_script":
            return self._patch_script(session, **kwargs)
        if operation == "rerun":
            return await self._rerun_script(session, **kwargs)
        if operation == "promote_output":
            return self._promote_output(session, **kwargs)
        if operation == "list_scripts":
            return self._list_scripts(session)
        return self._input_error(
            operation=operation,
            error_code="CODE_SESSION_OPERATION_INVALID",
            message=f"不支持的 operation: {operation}",
            expected_fields=["operation"],
            recovery_hint="请将 operation 改为 create_script、get_script、run_script、patch_script、rerun、promote_output 或 list_scripts。",
            minimal_example='{operation: "create_script", content: "result = 42"}',
        )

    async def run_ad_hoc_script(
        self,
        session: Session,
        *,
        language: str,
        content: str,
        dataset_name: str | None = None,
        persist_df: bool = False,
        save_as: str | None = None,
        purpose: str = "exploration",
        label: str | None = None,
        intent: str | None = None,
        extra_allowed_imports: list[str] | None = None,
        source_tool: str | None = None,
    ) -> ToolResult:
        """兼容旧入口：创建临时脚本并立即执行。"""
        if language not in self._LANGUAGES:
            return ToolResult(success=False, message=f"不支持的脚本语言: {language}")

        script_id = f"script_{uuid.uuid4().hex[:12]}"
        manager = WorkspaceManager(session)
        record = ScriptSessionRecord(
            id=script_id,
            session_id=session.id,
            language=language,
            content_path=str(self._content_path(manager, script_id, language)),
        )
        self._persist_script_record(manager, record, content)
        return await self._execute_record(
            session,
            record=record,
            dataset_name=dataset_name,
            persist_df=persist_df,
            save_as=save_as,
            purpose=purpose,
            label=label,
            intent=intent,
            extra_allowed_imports=extra_allowed_imports,
            source_tool=source_tool or "code_session",
            retry_of_execution_id=None,
        )

    async def _create_script(self, session: Session, **kwargs: Any) -> ToolResult:
        language = str(kwargs.get("language", "python")).strip().lower() or "python"
        if language not in self._LANGUAGES:
            return self._input_error(
                operation="create_script",
                error_code="CODE_SESSION_LANGUAGE_INVALID",
                message=f"不支持的脚本语言: {language}",
                expected_fields=["operation", "content"],
                recovery_hint="language 仅支持 python 或 r；省略时默认 python。",
                minimal_example=self._minimal_example_for_operation("create_script"),
            )

        content = str(kwargs.get("content", "") or "")
        if not content.strip():
            return self._input_error(
                operation="create_script",
                error_code="CODE_SESSION_CONTENT_REQUIRED",
                message="脚本内容不能为空",
                expected_fields=["operation", "content"],
                recovery_hint="请提供非空脚本内容；如需后续多次执行，可同时传 script_id。",
                minimal_example=self._minimal_example_for_operation("create_script"),
            )

        script_id = str(kwargs.get("script_id", "")).strip() or f"script_{uuid.uuid4().hex[:12]}"
        manager = WorkspaceManager(session)
        existing = self._load_script_record(manager, script_id)
        if existing is not None:
            return ToolResult(success=False, message=f"脚本会话已存在: {script_id}")

        record = ScriptSessionRecord(
            id=script_id,
            session_id=session.id,
            language=language,
            content_path=str(self._content_path(manager, script_id, language)),
        )
        self._persist_script_record(manager, record, content)
        auto_run = kwargs.get("auto_run", True)
        if not bool(auto_run):
            self._mark_script_pending(
                session,
                script_id=script_id,
                summary=f"脚本 {script_id} 已创建但尚未执行。",
                metadata={"language": language, "reason": "auto_run_disabled"},
            )
            return ToolResult(
                success=True,
                message=(
                    f"脚本会话已创建：{script_id}。"
                    "已按要求保留脚本但未自动执行，后续需继续运行该脚本。"
                ),
                data={
                    **self._build_script_payload(manager, record, content),
                    "auto_run": False,
                },
            )

        execution_result = await self._execute_record(
            session,
            record=record,
            dataset_name=self._resolve_dataset_name(session, kwargs.get("dataset_name")),
            persist_df=bool(kwargs.get("persist_df", False)),
            save_as=kwargs.get("save_as"),
            purpose=str(kwargs.get("purpose", "exploration")),
            label=kwargs.get("label"),
            intent=kwargs.get("intent"),
            source_tool="code_session",
            retry_of_execution_id=None,
        )
        execution_payload = execution_result.to_dict()
        execution_data = (
            dict(execution_payload.get("data", {}))
            if isinstance(execution_payload.get("data"), dict)
            else {}
        )
        execution_data["script"] = self._build_script_payload(manager, record, content)
        execution_data["auto_run"] = True
        execution_payload["data"] = execution_data
        if execution_result.success:
            self._clear_script_pending(session, script_id=script_id)
            execution_payload["message"] = f"脚本会话已创建并执行：{script_id}"
        else:
            self._mark_script_pending(
                session,
                script_id=script_id,
                summary=f"脚本 {script_id} 已创建，但自动执行失败，需要后续处理。",
                metadata={
                    "language": language,
                    "reason": "auto_run_failed",
                    "last_error": str(execution_payload.get("message", "") or ""),
                },
            )
            execution_payload["message"] = (
                f"脚本会话已创建：{script_id}，但自动执行失败。"
                f"{str(execution_payload.get('message', '') or '')}"
            ).strip()
        return ToolResult(**execution_payload)

    def _get_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        if not script_id:
            return self._input_error(
                operation="get_script",
                error_code="CODE_SESSION_GET_SCRIPT_ID_REQUIRED",
                message="get_script 操作必须提供 script_id",
                expected_fields=["operation", "script_id"],
                recovery_hint="先传入要读取的脚本会话 script_id。",
                minimal_example=self._minimal_example_for_operation("get_script"),
            )

        manager = WorkspaceManager(session)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        content = self._read_script_content(record)
        return ToolResult(
            success=True,
            message=f"已读取脚本会话 '{script_id}'",
            data=self._build_script_payload(manager, record, content),
        )

    def _list_scripts(self, session: Session) -> ToolResult:
        manager = WorkspaceManager(session)
        scripts = [
            item
            for item in manager.list_resource_summaries()
            if str(item.get("resource_type", "")).strip() == ResourceType.SCRIPT.value
        ]
        return ToolResult(
            success=True,
            message=f"已找到 {len(scripts)} 个脚本会话",
            data={"scripts": scripts},
        )

    async def _run_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        dataset_name = self._resolve_dataset_name(session, kwargs.get("dataset_name"))
        if not script_id:
            # 兼容模型误用：若提供了 content，则退化为一次性脚本执行。
            content = str(kwargs.get("content", "") or "")
            if content.strip():
                language = str(kwargs.get("language", "python")).strip().lower() or "python"
                return await self.run_ad_hoc_script(
                    session,
                    language=language,
                    content=content,
                    dataset_name=dataset_name,
                    persist_df=bool(kwargs.get("persist_df", False)),
                    save_as=kwargs.get("save_as"),
                    purpose=str(kwargs.get("purpose", "exploration")),
                    label=kwargs.get("label"),
                    intent=kwargs.get("intent"),
                    source_tool="code_session",
                )
            return self._input_error(
                operation="run_script",
                error_code="CODE_SESSION_RUN_SCRIPT_ID_OR_CONTENT_REQUIRED",
                message="run_script 操作必须提供 script_id；若要临时执行，也可直接提供 content",
                expected_fields=["operation", "script_id"],
                recovery_hint="优先提供已有脚本的 script_id；若只是临时执行，可改为传 content。",
                minimal_example=self._minimal_example_for_operation("run_script"),
            )

        manager = WorkspaceManager(session)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        content = self._read_script_content(record)
        if not content.strip():
            return ToolResult(success=False, message=f"脚本内容为空: {script_id}")

        result = await self._execute_record(
            session,
            record=record,
            dataset_name=dataset_name,
            persist_df=bool(kwargs.get("persist_df", False)),
            save_as=kwargs.get("save_as"),
            purpose=str(kwargs.get("purpose", "exploration")),
            label=kwargs.get("label"),
            intent=kwargs.get("intent"),
            source_tool="code_session",
            retry_of_execution_id=None,
        )
        if result.success:
            self._clear_script_pending(session, script_id=script_id)
        else:
            self._mark_script_pending(
                session,
                script_id=script_id,
                summary=f"脚本 {script_id} 执行失败，仍需修复后继续执行。",
                metadata={"reason": "run_failed", "last_error": result.message},
            )
        return result

    async def _rerun_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        if not script_id:
            return self._input_error(
                operation="rerun",
                error_code="CODE_SESSION_RERUN_SCRIPT_ID_REQUIRED",
                message="rerun 操作必须提供 script_id",
                expected_fields=["operation", "script_id"],
                recovery_hint="先传入已有脚本的 script_id，再重跑。",
                minimal_example=self._minimal_example_for_operation("rerun"),
            )

        manager = WorkspaceManager(session)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        result = await self._execute_record(
            session,
            record=record,
            dataset_name=self._resolve_dataset_name(session, kwargs.get("dataset_name")),
            persist_df=bool(kwargs.get("persist_df", False)),
            save_as=kwargs.get("save_as"),
            purpose=str(kwargs.get("purpose", "exploration")),
            label=kwargs.get("label"),
            intent=kwargs.get("intent"),
            source_tool="code_session",
            retry_of_execution_id=record.last_execution_id,
        )
        if result.success:
            self._clear_script_pending(session, script_id=script_id)
        else:
            self._mark_script_pending(
                session,
                script_id=script_id,
                summary=f"脚本 {script_id} 重跑失败，仍需修复后继续执行。",
                metadata={"reason": "rerun_failed", "last_error": result.message},
            )
        return result

    @staticmethod
    def _mark_script_pending(
        session: Session,
        *,
        script_id: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session.upsert_pending_action(
            action_type="script_not_run",
            key=script_id,
            status="pending",
            summary=summary,
            source_tool="code_session",
            metadata=metadata,
        )

    @staticmethod
    def _clear_script_pending(session: Session, *, script_id: str) -> None:
        session.resolve_pending_action(action_type="script_not_run", key=script_id)

    @staticmethod
    def _resolve_dataset_name(session: Session, raw_name: Any) -> str | None:
        """解析 dataset_name；缺失时若会话仅有一个数据集则自动兜底。"""
        if isinstance(raw_name, str):
            normalized = raw_name.strip()
            if normalized:
                return normalized
        if len(session.datasets) == 1:
            return next(iter(session.datasets.keys()))
        return None

    def _guard_dataset_injected_python_script(
        self,
        *,
        content: str,
        dataset_name: str | None,
    ) -> ToolResult | None:
        """在 dataset_name 已提供时，拦截仍手工读文件的脚本。"""
        if not dataset_name:
            return None

        for pattern in self._PYTHON_FILE_IO_PATTERNS:
            matched = pattern.search(content)
            if matched is None:
                continue
            return ToolResult(
                success=False,
                message=(
                    "脚本已提供 dataset_name，禁止再通过文件路径读取数据；"
                    "请直接使用沙箱注入的变量 df"
                ),
                data={
                    "error_code": "CODE_SESSION_DATASET_IO_CONFLICT",
                    "dataset_name": dataset_name,
                    "error_location": {"line": content[: matched.start()].count("\n") + 1},
                    "recovery_hint": (
                        "删除 pd.read_csv/pd.read_excel/open 等文件读取语句，"
                        f"直接对数据集 '{dataset_name}' 使用变量 df。"
                    ),
                },
                metadata={"error_code": "CODE_SESSION_DATASET_IO_CONFLICT"},
            )
        return None

    async def _execute_record(
        self,
        session: Session,
        *,
        record: ScriptSessionRecord,
        dataset_name: str | None,
        persist_df: bool,
        save_as: str | None,
        purpose: str,
        label: Any,
        intent: Any,
        source_tool: str,
        retry_of_execution_id: str | None,
        extra_allowed_imports: list[str] | None = None,
    ) -> ToolResult:
        content = self._read_script_content(record)

        if record.language == "python":
            guarded = self._guard_dataset_injected_python_script(
                content=content,
                dataset_name=dataset_name,
            )
            if guarded is not None:
                result = guarded
            else:
                result = await execute_python_code(
                    session,
                    code=content,
                    dataset_name=dataset_name,
                    persist_df=persist_df,
                    save_as=save_as,
                    purpose=purpose,
                    label=label,
                    intent=intent,
                    extra_allowed_imports=extra_allowed_imports,
                )
            language = "python"
        elif record.language == "r":
            result = await execute_r_code(
                session,
                code=content,
                dataset_name=dataset_name,
                persist_df=persist_df,
                save_as=save_as,
                purpose=purpose,
                label=label,
                intent=intent,
            )
            language = "r"
        else:
            return ToolResult(success=False, message=f"不支持的脚本语言: {record.language}")

        manager = WorkspaceManager(session)
        output_resource_ids = self._resolve_output_resource_ids(manager, result=result)
        error_location = self._extract_error_location(result)
        recovery_hint = self._build_recovery_hint(result)
        execution = manager.save_code_execution(
            code=content.rstrip(),
            output=result.message,
            status="success" if result.success else "failed",
            language=language,
            tool_name=source_tool,
            tool_args={
                "script_id": record.id,
                "dataset_name": dataset_name,
                "persist_df": persist_df,
                "save_as": save_as,
                "purpose": purpose,
                "label": label,
                "intent": intent,
            },
            intent=str(intent or label or "").strip() or None,
            script_resource_id=record.id,
            output_resource_ids=output_resource_ids,
            retry_of_execution_id=retry_of_execution_id,
            recovery_hint=recovery_hint,
            error_location=error_location,
        )
        execution_id = str(execution.get("id", "")).strip()
        if execution_id:
            record.execution_ids.append(execution_id)
            record.last_execution_id = execution_id
        record.output_resource_ids = output_resource_ids
        self._persist_script_record(manager, record, content)

        payload = result.to_dict()
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        data["script_id"] = record.id
        data["resource_id"] = record.id
        data["resource_type"] = "script"
        data["execution_id"] = execution_id
        data["output_resource_ids"] = output_resource_ids
        if error_location is not None:
            data["error_location"] = error_location
        if recovery_hint:
            data["recovery_hint"] = recovery_hint
        payload["data"] = data
        return ToolResult(**payload)

    def _patch_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        if not script_id:
            return self._input_error(
                operation="patch_script",
                error_code="CODE_SESSION_PATCH_SCRIPT_ID_REQUIRED",
                message="patch_script 操作必须提供 script_id",
                expected_fields=["operation", "script_id", "patch"],
                recovery_hint="先传入要修补的脚本 script_id，再提供 patch。",
                minimal_example=self._minimal_example_for_operation("patch_script"),
            )

        patch = kwargs.get("patch")
        if not isinstance(patch, dict):
            return self._input_error(
                operation="patch_script",
                error_code="CODE_SESSION_PATCH_REQUIRED",
                message="patch_script 操作必须提供 patch 对象",
                expected_fields=["operation", "script_id", "patch"],
                recovery_hint="patch 需包含 mode，以及对应模式所需字段。",
                minimal_example=self._minimal_example_for_operation("patch_script"),
            )

        manager = WorkspaceManager(session)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        current = self._read_script_content(record)
        try:
            updated = self._apply_patch(current, patch)
        except ValueError as exc:
            return self._patch_error(str(exc))
        self._persist_script_record(manager, record, updated)
        return ToolResult(
            success=True,
            message=f"脚本已更新：{script_id}",
            data=self._build_script_payload(manager, record, updated),
        )

    def _promote_output(self, session: Session, **kwargs: Any) -> ToolResult:
        manager = WorkspaceManager(session)
        dataset_name = str(kwargs.get("dataset_name", "")).strip()
        artifact_resource_id = str(kwargs.get("artifact_resource_id", "")).strip()
        artifact_name = str(kwargs.get("artifact_name", "")).strip()
        artifact_path = str(kwargs.get("artifact_path", "")).strip()

        if dataset_name:
            df = session.datasets.get(dataset_name)
            if not isinstance(df, pd.DataFrame):
                return ToolResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

            resource_id = (
                str(kwargs.get("resource_id", "")).strip() or f"dataset_{uuid.uuid4().hex[:12]}"
            )
            display_name = str(kwargs.get("resource_name", "")).strip() or dataset_name
            filename = f"{display_name}.csv"
            path = manager.build_managed_resource_path(
                ResourceType.DATASET,
                filename,
                default_name=f"{resource_id}.csv",
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False)
            manager.add_dataset_record(
                dataset_id=resource_id,
                name=display_name,
                file_path=path,
                file_type="csv",
                file_size=path.stat().st_size,
                row_count=len(df),
                column_count=len(df.columns),
            )
            resource = manager.get_resource_summary(resource_id)
            return ToolResult(
                success=True,
                message=f"已提升数据集输出：{display_name}",
                data={
                    "resource_id": resource_id,
                    "resource_type": "dataset",
                    "resource": resource,
                },
            )

        if artifact_resource_id:
            resource = manager.get_resource_summary(artifact_resource_id)
            if resource is None:
                return ToolResult(success=False, message=f"未找到产物资源: {artifact_resource_id}")
            return ToolResult(
                success=True,
                message=f"已确认产物资源：{artifact_resource_id}",
                data={
                    "resource_id": artifact_resource_id,
                    "resource_type": resource.get("resource_type"),
                    "resource": resource,
                },
            )

        if artifact_name or artifact_path:
            match = self._find_artifact_resource(
                manager,
                artifact_name=artifact_name or None,
                artifact_path=artifact_path or None,
            )
            if match is None:
                return ToolResult(success=False, message="未找到可提升的产物文件")
            return ToolResult(
                success=True,
                message=f"已确认产物资源：{match['id']}",
                data={
                    "resource_id": match["id"],
                    "resource_type": match.get("resource_type"),
                    "resource": match,
                },
            )

        return self._input_error(
            operation="promote_output",
            error_code="CODE_SESSION_PROMOTE_TARGET_REQUIRED",
            message="promote_output 操作必须提供 dataset_name、artifact_resource_id、artifact_name 或 artifact_path",
            expected_fields=["operation"],
            recovery_hint="请至少提供一种提升目标：dataset_name、artifact_resource_id、artifact_name 或 artifact_path。",
            minimal_example=self._minimal_example_for_operation("promote_output"),
        )

    def _record_path(self, manager: WorkspaceManager, script_id: str) -> Path:
        return manager.build_managed_resource_path(
            ResourceType.SCRIPT,
            f"{script_id}.json",
            default_name=f"{script_id}.json",
        )

    def _content_path(self, manager: WorkspaceManager, script_id: str, language: str) -> Path:
        suffix = self._LANGUAGES[language]
        return manager.build_managed_resource_path(
            ResourceType.SCRIPT,
            f"{script_id}.{suffix}",
            default_name=f"{script_id}.{suffix}",
        )

    def _load_script_record(
        self,
        manager: WorkspaceManager,
        script_id: str,
    ) -> ScriptSessionRecord | None:
        path = self._record_path(manager, script_id)
        if not path.exists():
            return None
        try:
            return ScriptSessionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _persist_script_record(
        self,
        manager: WorkspaceManager,
        record: ScriptSessionRecord,
        content: str,
    ) -> None:
        code_path = Path(record.content_path)
        code_path.parent.mkdir(parents=True, exist_ok=True)
        code_path.write_text(content.rstrip() + "\n", encoding="utf-8")

        record_path = self._record_path(manager, record.id)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manager.upsert_managed_resource(
            resource_id=record.id,
            resource_type=ResourceType.SCRIPT,
            name=code_path.name,
            path=code_path,
            source_kind="scripts",
            metadata={
                "language": record.language,
                "content_path": record.content_path,
                "record_path": str(record_path),
                "execution_ids": record.execution_ids,
                "last_execution_id": record.last_execution_id,
                "output_resource_ids": record.output_resource_ids,
            },
        )

    def _read_script_content(self, record: ScriptSessionRecord) -> str:
        return Path(record.content_path).read_text(encoding="utf-8")

    def _build_script_payload(
        self,
        manager: WorkspaceManager,
        record: ScriptSessionRecord,
        content: str,
    ) -> dict[str, Any]:
        history = [
            item
            for item in manager.list_code_executions()
            if str(item.get("script_resource_id", "")).strip() == record.id
        ]
        return {
            "script_id": record.id,
            "resource_id": record.id,
            "resource_type": "script",
            "language": record.language,
            "content": content,
            "record": record.model_dump(mode="json"),
            "resource": manager.get_resource_summary(record.id),
            "history": history,
        }

    def _resolve_output_resource_ids(
        self,
        manager: WorkspaceManager,
        *,
        result: ToolResult,
    ) -> list[str]:
        ids: list[str] = []

        data = result.data if isinstance(result.data, dict) else {}
        output_resources = data.get("output_resources") if isinstance(data, dict) else None
        if isinstance(output_resources, list):
            for item in output_resources:
                if not isinstance(item, dict):
                    continue
                resource_id = str(item.get("resource_id", "")).strip()
                if resource_id:
                    ids.append(resource_id)

        direct_resource_id = (
            str(data.get("resource_id", "")).strip() if isinstance(data, dict) else ""
        )
        direct_resource_type = (
            str(data.get("resource_type", "")).strip() if isinstance(data, dict) else ""
        )
        if direct_resource_id and direct_resource_type in {"dataset", "temp_dataset"}:
            ids.append(direct_resource_id)

        artifacts = result.artifacts if isinstance(result.artifacts, list) else []
        files = manager.list_workspace_files_with_paths()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path", "")).strip()
            name = str(artifact.get("name", "")).strip()
            for item in files:
                if path and str(item.get("path", "")).strip() == path:
                    ids.append(str(item.get("id", "")))
                    break
                if name and str(item.get("name", "")).strip() == name:
                    ids.append(str(item.get("id", "")))
                    break
        dedup: list[str] = []
        for item in ids:
            if not item or item in dedup:
                continue
            dedup.append(item)
        return dedup

    def _input_error(
        self,
        *,
        operation: str,
        error_code: str,
        message: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        payload = {
            "operation": operation,
            "error_code": error_code,
            "expected_fields": expected_fields,
            "recovery_hint": recovery_hint,
            "minimal_example": minimal_example,
        }
        return self.build_input_error(message=message, payload=payload)

    def _patch_error(self, message: str) -> ToolResult:
        code = "CODE_SESSION_PATCH_INVALID"
        expected_fields = ["patch.mode"]
        recovery_hint = "根据 patch.mode 补齐对应字段后重试。"
        if "old_string" in message:
            code = "CODE_SESSION_PATCH_OLD_STRING_REQUIRED"
            expected_fields = ["patch.mode", "patch.old_string", "patch.new_string"]
            recovery_hint = "replace_string 模式必须同时提供 old_string 和 new_string。"
        elif "start_line" in message or "end_line" in message:
            code = "CODE_SESSION_PATCH_RANGE_INVALID"
            expected_fields = [
                "patch.mode",
                "patch.start_line",
                "patch.end_line",
                "patch.new_string",
            ]
            recovery_hint = "replace_range 模式必须提供有效的 start_line、end_line 和 new_string。"
        elif "不支持的 patch 模式" in message:
            code = "CODE_SESSION_PATCH_MODE_INVALID"
            expected_fields = ["patch.mode"]
            recovery_hint = "patch.mode 仅支持 append、replace_string、replace_range。"
        elif "未找到待替换文本" in message:
            code = "CODE_SESSION_PATCH_TARGET_NOT_FOUND"
            expected_fields = ["patch.old_string"]
            recovery_hint = "请确认 old_string 与当前脚本内容完全匹配。"
        return self._input_error(
            operation="patch_script",
            error_code=code,
            message=message,
            expected_fields=expected_fields,
            recovery_hint=recovery_hint,
            minimal_example=self._minimal_example_for_operation("patch_script"),
        )

    def _minimal_example_for_operation(self, operation: str) -> str:
        examples = {
            "create_script": '{operation: "create_script", content: "result = 42"}',
            "get_script": '{operation: "get_script", script_id: "script_demo"}',
            "run_script": '{operation: "run_script", script_id: "script_demo"}',
            "patch_script": (
                '{operation: "patch_script", script_id: "script_demo", '
                'patch: {mode: "replace_string", old_string: "1 / 0", new_string: "1 / 1"}}'
            ),
            "rerun": '{operation: "rerun", script_id: "script_demo"}',
            "promote_output": '{operation: "promote_output", dataset_name: "scaled.csv"}',
            "list_scripts": '{operation: "list_scripts"}',
        }
        return examples.get(operation, '{operation: "create_script", content: "result = 42"}')

    def _apply_patch(self, content: str, patch: dict[str, Any]) -> str:
        mode = str(patch.get("mode", "")).strip()
        new_string = str(patch.get("new_string", "") or "")

        if mode == "append":
            base = content.rstrip("\n")
            if base:
                return base + "\n" + new_string.rstrip("\n") + "\n"
            return new_string.rstrip("\n") + "\n"

        if mode == "replace_string":
            old_string = str(patch.get("old_string", "") or "")
            if not old_string:
                raise ValueError("replace_string 模式必须提供 old_string")
            if old_string not in content:
                raise ValueError("未找到待替换文本")
            return content.replace(old_string, new_string)

        if mode == "replace_range":
            start_line = int(patch.get("start_line") or 0)
            end_line = int(patch.get("end_line") or 0)
            if start_line <= 0 or end_line < start_line:
                raise ValueError("replace_range 模式必须提供有效的 start_line 和 end_line")
            lines = content.splitlines()
            replacement = new_string.splitlines()
            updated = lines[: start_line - 1] + replacement + lines[end_line:]
            return "\n".join(updated).rstrip("\n") + "\n"

        raise ValueError(f"不支持的 patch 模式: {mode}")

    def _find_artifact_resource(
        self,
        manager: WorkspaceManager,
        *,
        artifact_name: str | None,
        artifact_path: str | None,
    ) -> dict[str, Any] | None:
        for item in manager.list_workspace_files_with_paths():
            item_name = str(item.get("name", "")).strip()
            item_path = str(item.get("path", "")).strip()
            if artifact_name and item_name == artifact_name:
                resource_id = str(item.get("resource_id", "")).strip()
                return manager.get_resource_summary(resource_id) if resource_id else item
            if artifact_path and item_path == artifact_path:
                resource_id = str(item.get("resource_id", "")).strip()
                return manager.get_resource_summary(resource_id) if resource_id else item
        return None

    def _extract_error_location(self, result: ToolResult) -> dict[str, Any] | None:
        if result.success:
            return None
        payload = result.data if isinstance(result.data, dict) else {}
        text = "\n".join(
            str(payload.get(key, "")).strip()
            for key in ("traceback", "stderr", "stdout")
            if str(payload.get(key, "")).strip()
        )
        if not text:
            text = result.message
        frame_matches = list(re.finditer(r'File "([^"]+)", line (\d+)', text))
        for match in reversed(frame_matches):
            path = match.group(1)
            if path == "<string>":
                return {"line": int(match.group(2))}
        for match in reversed(frame_matches):
            path = match.group(1)
            if "/src/nini/" not in path and "multiprocessing/" not in path:
                return {"line": int(match.group(2))}
        for pattern in (r"line (\d+)", r"<text>:(\d+)"):
            matched = re.search(pattern, text)
            if matched:
                return {"line": int(matched.group(1))}
        return None

    # 沙箱拦截常见模块的替代方案映射
    _SANDBOX_DENY_HINTS: dict[str, str] = {
        "pathlib": "pathlib 无需导入（如需操作文件使用 workspace_session 工具）。直接删除该 import 行即可。",
        "os": "os 被禁止。文件操作使用 workspace_session 工具；路径操作使用字符串拼接。",
        "sys": "sys 被禁止。通常无需使用，直接删除该 import 即可。",
        "shutil": "shutil 被禁止。文件复制/移动使用 workspace_session 工具。",
        "subprocess": "subprocess 被禁止。沙箱不允许执行系统命令。",
        "socket": "socket 被禁止。沙箱不允许网络操作。",
        "requests": "requests 被禁止。沙箱不允许网络请求。",
        "urllib": "urllib 被禁止。沙箱不允许网络请求。",
        "http": "http/httpx 被禁止。沙箱不允许网络请求。",
        "httpx": "httpx 被禁止。沙箱不允许网络请求。",
        "io": "io 被禁止。数据读写使用 pd.read_csv / df.to_csv 等 pandas 方法。",
        "tempfile": "tempfile 被禁止。沙箱已提供临时工作目录。",
        "pickle": "pickle 被禁止。使用 json（已预注入）进行序列化。",
        "asyncio": "asyncio 被禁止。沙箱不支持异步操作。",
        "threading": "threading 被禁止。沙箱不支持多线程。",
        "multiprocessing": "multiprocessing 被禁止。沙箱不支持多进程。",
        "importlib": "importlib 被禁止。不允许动态导入。",
        "inspect": "inspect 被禁止。不允许代码内省。",
        "ctypes": "ctypes 被禁止。不允许 FFI 调用。",
        "shlex": "shlex 被禁止。不允许 shell 解析。",
        "signal": "signal 被禁止。不允许信号处理。",
        "fcntl": "fcntl 被禁止。不允许文件锁。",
        "builtins": "builtins 无需导入。已预注入沙箱环境。",
    }

    # 沙箱已预注入的模块列表（用于通用 fallback 提示）
    _PRE_INJECTED_MODULES = (
        "pd (pandas), np (numpy), plt (matplotlib.pyplot), sns (seaborn), "
        "go/px (plotly), datetime/dt/timedelta, re, json, "
        "Counter/defaultdict/deque, combinations/permutations/product, reduce/partial"
    )

    def _build_recovery_hint(self, result: ToolResult) -> str | None:
        if result.success:
            return None
        message = result.message
        if "策略拦截" in message:
            return self._build_sandbox_recovery_hint(message)
        if "禁止再通过文件路径读取数据" in message:
            return "删除文件读取语句并直接使用注入的 df 后，用 patch_script 或 rerun 重试"
        if "数据集" in message and "不存在" in message:
            return "确认 dataset_name 或先将目标数据集提升到会话资源后重跑"
        if "除零" in message or "ZeroDivisionError" in message:
            return "修正除零计算后使用 patch_script 或 rerun 重试"
        if "执行失败" in message:
            return "修复报错行附近代码后使用 patch_script 或 rerun 重试"
        return "检查 traceback 后修复脚本并重新执行"

    def _build_sandbox_recovery_hint(self, message: str) -> str:
        """为沙箱策略拦截构建具体的恢复提示。"""
        # 提取被拦截的模块名
        module_match = re.search(r"不允许导入模块:\s*(\S+)", message)
        if module_match:
            blocked = module_match.group(1).rstrip("）")
            # 去掉"（高风险模块）"等后缀
            blocked = re.sub(r"[（(].*", "", blocked).strip()
            specific = self._SANDBOX_DENY_HINTS.get(blocked)
            if specific:
                return f"{specific} 修正后使用 patch_script 或 rerun 重试。"

        # 提取被拦截的函数调用
        call_match = re.search(r"不允许调用[:：]\s*(\S+)", message)
        if call_match:
            func_name = call_match.group(1)
            return f"{func_name} 被沙箱禁止。删除该调用后使用 patch_script 或 rerun 重试。"

        return (
            "移除受限导入或危险调用后重跑脚本。"
            f"以下已预注入无需 import: {self._PRE_INJECTED_MODULES}。"
            "图表会自动收集导出，不要手动 plt.savefig()。"
        )
