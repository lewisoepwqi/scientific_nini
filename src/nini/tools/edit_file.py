"""文件编辑工具 - 支持读写追加和编辑文件内容。

该模块提供 EditFile 工具，支持：
1. read: 读取文件内容
2. write: 完全覆盖写入
3. append: 追加到文件末尾
4. edit: 编辑文件（替换特定文本或行号范围）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import Skill, SkillResult
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class EditFile(Skill):
    """编辑工作区文件内容。

    提供读取、写入、追加和编辑文件的功能。
    支持文本匹配替换和行号范围替换。
    """

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "编辑工作区文件内容。支持读取(read)、写入(write)、追加(append)和编辑(edit)操作。"
            "可用于修改生成的文章、更新文档、添加内容等。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件相对路径（相对于工作区根目录）",
                },
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "append", "edit"],
                    "description": "操作类型: read(读取), write(覆盖写入), append(追加), edit(编辑替换)",
                },
                "content": {
                    "type": "string",
                    "description": "写入/追加/编辑的内容（write/append/edit操作需要）",
                },
                "old_string": {
                    "type": "string",
                    "description": "edit操作：要替换的文本（与new_string配合使用）",
                },
                "new_string": {
                    "type": "string",
                    "description": "edit操作：替换后的文本（与old_string配合使用）",
                },
                "start_line": {
                    "type": "integer",
                    "description": "edit操作：起始行号（1-based，可选，与end_line配合使用）",
                },
                "end_line": {
                    "type": "integer",
                    "description": "edit操作：结束行号（1-based，可选，与start_line配合使用）",
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码",
                    "default": "utf-8",
                },
                "create_if_missing": {
                    "type": "boolean",
                    "description": "如果文件不存在是否创建（仅write/append操作）",
                    "default": True,
                },
            },
            "required": ["file_path", "operation"],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def is_idempotent(self) -> bool:
        return False

    @property
    def typical_use_cases(self) -> list[str]:
        return [
            "读取工作区文件内容",
            "修改生成的文章初稿",
            "追加内容到现有文件",
            "替换文件中的特定文本",
            "删除文件的特定行",
        ]

    @property
    def output_types(self) -> list[str]:
        return ["text", "file"]

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行文件编辑操作。

        Args:
            session: 当前会话
            **kwargs: 操作参数

        Returns:
            SkillResult: 操作结果
        """
        try:
            file_path = kwargs.get("file_path", "")
            operation = kwargs.get("operation", "")
            encoding = kwargs.get("encoding", "utf-8")
            create_if_missing = kwargs.get("create_if_missing", True)

            # 验证参数
            if not file_path:
                return SkillResult(success=False, message="文件路径不能为空")

            if operation not in ["read", "write", "append", "edit"]:
                return SkillResult(success=False, message=f"不支持的操作类型: {operation}")

            # 构建完整路径
            full_path = self._resolve_path(session, file_path)
            if full_path is None:
                return SkillResult(
                    success=False,
                    message=f"文件路径无效或超出工作区范围: {file_path}",
                )

            # 根据操作类型执行相应逻辑
            if operation == "read":
                return await self._do_read(full_path, encoding)
            elif operation == "write":
                content = kwargs.get("content", "")
                return await self._do_write(session, full_path, content, encoding, create_if_missing)
            elif operation == "append":
                content = kwargs.get("content", "")
                return await self._do_append(session, full_path, content, encoding, create_if_missing)
            elif operation == "edit":
                old_string = kwargs.get("old_string")
                new_string = kwargs.get("new_string", "")
                start_line = kwargs.get("start_line")
                end_line = kwargs.get("end_line")
                return await self._do_edit(
                    session, full_path, old_string, new_string, start_line, end_line, encoding
                )

            return SkillResult(success=False, message=f"未知操作: {operation}")

        except Exception as e:
            logger.exception("文件编辑操作失败")
            return SkillResult(success=False, message=f"操作失败: {str(e)}")

    def _resolve_path(self, session: Session, file_path: str) -> Path | None:
        """解析并验证文件路径。

        Args:
            session: 当前会话
            file_path: 相对路径

        Returns:
            Path: 完整路径，如果无效则返回None
        """
        # 清理路径，防止目录遍历攻击（实际安全防护由下方 resolve + startswith 完成）
        file_path = file_path.strip()

        # 构建工作区路径
        workspace_path = settings.sessions_dir / session.id / "workspace"
        full_path = workspace_path / file_path

        # 规范化路径并检查是否在工作区内
        try:
            full_path = full_path.resolve()
            workspace_resolved = workspace_path.resolve()

            # 安全检查：确保文件在工作区内
            if not str(full_path).startswith(str(workspace_resolved)):
                logger.warning(f"尝试访问工作区外的路径: {full_path}")
                return None

            return full_path
        except Exception as e:
            logger.error(f"路径解析失败: {e}")
            return None

    async def _do_read(self, file_path: Path, encoding: str) -> SkillResult:
        """读取文件内容。"""
        if not file_path.exists():
            return SkillResult(
                success=False,
                message=f"文件不存在: {file_path.name}",
            )

        if not file_path.is_file():
            return SkillResult(
                success=False,
                message=f"路径不是文件: {file_path.name}",
            )

        try:
            content = file_path.read_text(encoding=encoding)
            lines = content.split("\n")

            # 构建带行号的内容预览
            numbered_lines = []
            for i, line in enumerate(lines, 1):
                numbered_lines.append(f"{i:4d}: {line}")

            preview = "\n".join(numbered_lines[:50])  # 前50行
            if len(lines) > 50:
                preview += f"\n... (共 {len(lines)} 行)"

            return SkillResult(
                success=True,
                message=f"文件读取成功: {file_path.name} ({len(lines)} 行, {len(content)} 字符)",
                data={
                    "content": content,
                    "line_count": len(lines),
                    "char_count": len(content),
                    "preview": preview,
                    "file_path": str(file_path.name),
                },
            )
        except Exception as e:
            return SkillResult(
                success=False,
                message=f"读取文件失败: {str(e)}",
            )

    async def _do_write(
        self, session: Session, file_path: Path, content: str, encoding: str, create_if_missing: bool
    ) -> SkillResult:
        """写入文件内容（覆盖）。"""
        try:
            # 确保父目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 检查文件是否已存在
            file_existed = file_path.exists()

            file_path.write_text(content, encoding=encoding)

            # 添加到工作区索引，使文件在前端可见
            try:
                self._sync_text_document_record(session, file_path)
            except Exception as e:
                logger.warning(f"添加到工作区索引失败: {e}")

            lines = content.split("\n")
            action = "更新" if file_existed else "创建"

            return SkillResult(
                success=True,
                message=f"文件{action}成功: {file_path.name} ({len(lines)} 行)",
                data={
                    "file_path": str(file_path.name),
                    "line_count": len(lines),
                    "char_count": len(content),
                    "action": action.lower(),
                },
            )
        except Exception as e:
            return SkillResult(
                success=False,
                message=f"写入文件失败: {str(e)}",
            )

    async def _do_append(
        self, session: Session, file_path: Path, content: str, encoding: str, create_if_missing: bool
    ) -> SkillResult:
        """追加内容到文件。"""
        try:
            if not file_path.exists():
                if not create_if_missing:
                    return SkillResult(
                        success=False,
                        message=f"文件不存在且不允许创建: {file_path.name}",
                    )
                # 创建新文件
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding=encoding)

                # 添加到工作区索引，使文件在前端可见
                try:
                    self._sync_text_document_record(session, file_path)
                except Exception as e:
                    logger.warning(f"添加到工作区索引失败: {e}")

                lines = content.split("\n")
                return SkillResult(
                    success=True,
                    message=f"文件创建成功: {file_path.name} ({len(lines)} 行)",
                    data={
                        "file_path": str(file_path.name),
                        "line_count": len(lines),
                        "char_count": len(content),
                        "action": "create",
                    },
                )

            existing_content = file_path.read_text(encoding=encoding)
            separator = "\n" if existing_content and not existing_content.endswith("\n") else ""
            new_content = existing_content + separator + content
            file_path.write_text(new_content, encoding=encoding)
            try:
                self._sync_text_document_record(session, file_path)
            except Exception as e:
                logger.warning(f"同步工作区索引失败: {e}")
            lines = new_content.split("\n")
            appended_lines = content.split("\n")

            return SkillResult(
                success=True,
                message=f"内容追加成功: {file_path.name} (+{len(appended_lines)} 行, 共 {len(lines)} 行)",
                data={
                    "file_path": str(file_path.name),
                    "line_count": len(lines),
                    "appended_lines": len(appended_lines),
                    "action": "append",
                },
            )
        except Exception as e:
            return SkillResult(
                success=False,
                message=f"追加内容失败: {str(e)}",
            )

    async def _do_edit(
        self,
        session: Session,
        file_path: Path,
        old_string: str | None,
        new_string: str,
        start_line: int | None,
        end_line: int | None,
        encoding: str,
    ) -> SkillResult:
        """编辑文件内容（替换）。

        支持两种方式：
        1. 文本替换: old_string + new_string
        2. 行号范围替换: start_line + end_line + new_string
        """
        if not file_path.exists():
            return SkillResult(
                success=False,
                message=f"文件不存在: {file_path.name}",
            )

        try:
            content = file_path.read_text(encoding=encoding)
            lines = content.split("\n")
            original_line_count = len(lines)

            # 方式1: 基于行号范围替换
            if start_line is not None:
                # 转换为0-based索引
                start_idx = max(0, start_line - 1)
                end_idx = end_line if end_line is not None else len(lines)
                end_idx = min(end_idx, len(lines))

                # 构建新内容
                new_lines = lines[:start_idx] + new_string.split("\n") + lines[end_idx:]
                new_content = "\n".join(new_lines)

                file_path.write_text(new_content, encoding=encoding)
                try:
                    self._sync_text_document_record(session, file_path)
                except Exception as e:
                    logger.warning(f"同步工作区索引失败: {e}")

                return SkillResult(
                    success=True,
                    message=f"文件编辑成功: {file_path.name} (替换第 {start_line}-{end_line or start_line} 行)",
                    data={
                        "file_path": str(file_path.name),
                        "original_line_count": original_line_count,
                        "new_line_count": len(new_lines),
                        "replaced_lines": end_idx - start_idx,
                        "method": "line_range",
                    },
                )

            # 方式2: 基于文本匹配替换
            if old_string is not None:
                if old_string not in content:
                    return SkillResult(
                        success=False,
                        message=f"未找到要替换的文本: {old_string[:50]}...",
                    )

                # 替换所有匹配（通常是第一个）
                new_content = content.replace(old_string, new_string, 1)
                file_path.write_text(new_content, encoding=encoding)
                try:
                    self._sync_text_document_record(session, file_path)
                except Exception as e:
                    logger.warning(f"同步工作区索引失败: {e}")

                # 统计变更
                old_lines = old_string.split("\n")
                new_lines_count = len(new_string.split("\n"))

                return SkillResult(
                    success=True,
                    message=f"文件编辑成功: {file_path.name} (替换 {len(old_lines)} 行为 {new_lines_count} 行)",
                    data={
                        "file_path": str(file_path.name),
                        "original_line_count": original_line_count,
                        "new_line_count": len(new_content.split("\n")),
                        "replaced_text_length": len(old_string),
                        "method": "text_replace",
                    },
                )

            return SkillResult(
                success=False,
                message="edit操作需要指定 old_string 或 start_line/end_line 参数",
            )

        except Exception as e:
            return SkillResult(
                success=False,
                message=f"编辑文件失败: {str(e)}",
            )

    def _sync_text_document_record(self, session: Session, file_path: Path) -> None:
        """同步 edit_file 创建/更新的文本文件索引，使其在工作区按文稿展示。"""
        workspace_path = settings.sessions_dir / session.id / "workspace"
        relative_path = file_path.resolve().relative_to(workspace_path.resolve()).as_posix()
        WorkspaceManager(session.id).sync_text_document_record(relative_path)
