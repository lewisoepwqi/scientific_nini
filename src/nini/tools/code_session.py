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
            "创建、读取和执行持久化脚本会话，统一管理 Python/R 脚本与执行历史。"
            "当传入 dataset_name 时，沙箱自动将数据注入为 pandas DataFrame 变量 df，"
            "【禁止】在代码中使用 pd.read_csv/read_excel/open 等文件读取语句，直接使用 df 操作数据。"
            "沙箱已预注入 pd/np/plt/sns/go/px/datetime/re/json 等，无需 import。"
            "图表在代码执行后自动收集导出，不要手动调用 plt.savefig()。"
            "禁止通过 import __main__ 或系统级 I/O 探测数据路径。"
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
            },
            "required": ["operation"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()
        if operation == "create_script":
            return self._create_script(session, **kwargs)
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
        return ToolResult(success=False, message=f"不支持的 operation: {operation}")

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
        manager = WorkspaceManager(session.id)
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

    def _create_script(self, session: Session, **kwargs: Any) -> ToolResult:
        language = str(kwargs.get("language", "python")).strip().lower() or "python"
        if language not in self._LANGUAGES:
            return ToolResult(success=False, message=f"不支持的脚本语言: {language}")

        content = str(kwargs.get("content", "") or "")
        if not content.strip():
            return ToolResult(success=False, message="脚本内容不能为空")

        script_id = str(kwargs.get("script_id", "")).strip() or f"script_{uuid.uuid4().hex[:12]}"
        manager = WorkspaceManager(session.id)
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
        return ToolResult(
            success=True,
            message=f"脚本会话已创建：{script_id}",
            data=self._build_script_payload(manager, record, content),
        )

    def _get_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        if not script_id:
            return ToolResult(success=False, message="get_script 操作必须提供 script_id")

        manager = WorkspaceManager(session.id)
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
        manager = WorkspaceManager(session.id)
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
            return ToolResult(success=False, message="run_script 操作必须提供 script_id")

        manager = WorkspaceManager(session.id)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        content = self._read_script_content(record)
        if not content.strip():
            return ToolResult(success=False, message=f"脚本内容为空: {script_id}")

        return await self._execute_record(
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

    async def _rerun_script(self, session: Session, **kwargs: Any) -> ToolResult:
        script_id = str(kwargs.get("script_id", "")).strip()
        if not script_id:
            return ToolResult(success=False, message="rerun 操作必须提供 script_id")

        manager = WorkspaceManager(session.id)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        return await self._execute_record(
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

        manager = WorkspaceManager(session.id)
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
            return ToolResult(success=False, message="patch_script 操作必须提供 script_id")

        patch = kwargs.get("patch")
        if not isinstance(patch, dict):
            return ToolResult(success=False, message="patch_script 操作必须提供 patch 对象")

        manager = WorkspaceManager(session.id)
        record = self._load_script_record(manager, script_id)
        if record is None:
            return ToolResult(success=False, message=f"未找到脚本会话: {script_id}")

        current = self._read_script_content(record)
        try:
            updated = self._apply_patch(current, patch)
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))
        self._persist_script_record(manager, record, updated)
        return ToolResult(
            success=True,
            message=f"脚本已更新：{script_id}",
            data=self._build_script_payload(manager, record, updated),
        )

    def _promote_output(self, session: Session, **kwargs: Any) -> ToolResult:
        manager = WorkspaceManager(session.id)
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

        return ToolResult(
            success=False,
            message="promote_output 操作必须提供 dataset_name、artifact_resource_id、artifact_name 或 artifact_path",
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
