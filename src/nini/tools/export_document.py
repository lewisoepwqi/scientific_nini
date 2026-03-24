"""工作区文档导出工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.export_report import export_workspace_document


class ExportDocumentTool(Tool):
    """将工作区中的文档导出为 PDF 或 DOCX。"""

    @property
    def name(self) -> str:
        return "export_document"

    @property
    def category(self) -> str:
        return "export"

    @property
    def expose_to_llm(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return (
            "将工作区中的文档文件导出为 PDF 或 DOCX。"
            "适用于 Markdown、纯文本、HTML 等文档，不要求必须由 generate_report 生成。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "要导出的工作区文档相对路径，或文档文件名。",
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx"],
                    "description": "导出格式。",
                },
                "filename": {
                    "type": "string",
                    "description": "可选。导出后的文件名（不含扩展名也可）。",
                },
            },
            "required": ["source_path", "format"],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        source_path = kwargs.get("source_path")
        output_format = kwargs.get("format")
        filename = kwargs.get("filename")
        if not isinstance(source_path, str) or not source_path.strip():
            return ToolResult(success=False, message="source_path 不能为空。")
        if not isinstance(output_format, str) or not output_format.strip():
            return ToolResult(success=False, message="format 不能为空。")

        return await export_workspace_document(
            session,
            source_ref=source_path.strip(),
            output_format=output_format.strip(),
            filename=str(filename).strip() if isinstance(filename, str) else None,
            prefer_latest_report=False,
        )
