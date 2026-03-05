"""会话资源与执行记录模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from nini.models.common import IdentifiedModel


class ResourceType(str, Enum):
    """统一会话资源类型。"""

    DATASET = "dataset"
    TEMP_DATASET = "temp_dataset"
    STAT_RESULT = "stat_result"
    CHART = "chart"
    REPORT = "report"
    SCRIPT = "script"
    FILE = "file"


class SessionResourceSummary(IdentifiedModel):
    """会话资源摘要。"""

    session_id: str = Field(description="所属会话 ID")
    resource_type: ResourceType = Field(description="资源类型")
    name: str = Field(min_length=1, description="展示名称")
    source_kind: str = Field(default="", description="来源桶类型，如 datasets/artifacts/notes")
    path: str | None = Field(default=None, description="资源文件路径")
    download_url: str | None = Field(default=None, description="下载地址")
    mime_type: str | None = Field(default=None, description="可选 MIME 类型")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class ExecutionErrorLocation(BaseModel):
    """执行错误定位。"""

    line: int | None = Field(default=None, description="错误行号")
    column: int | None = Field(default=None, description="错误列号")
    end_line: int | None = Field(default=None, description="结束行号")
    end_column: int | None = Field(default=None, description="结束列号")
    symbol: str | None = Field(default=None, description="相关符号")


class CodeExecutionRecord(IdentifiedModel):
    """统一代码执行记录。"""

    session_id: str = Field(description="所属会话 ID")
    code: str = Field(description="执行代码")
    output: str = Field(default="", description="执行输出")
    status: str = Field(default="success", description="执行状态")
    language: str = Field(default="python", description="代码语言")
    tool_name: str | None = Field(default=None, description="来源工具名")
    tool_args: dict[str, Any] | None = Field(default=None, description="来源工具参数")
    context_token_count: int | None = Field(default=None, description="上下文 token 数")
    intent: str | None = Field(default=None, description="执行意图")
    script_resource_id: str | None = Field(default=None, description="关联脚本资源 ID")
    output_resource_ids: list[str] = Field(default_factory=list, description="输出资源 ID 列表")
    retry_of_execution_id: str | None = Field(default=None, description="重试前的执行 ID")
    recovery_hint: str | None = Field(default=None, description="恢复提示")
    error_location: ExecutionErrorLocation | None = Field(
        default=None,
        description="错误定位信息",
    )


class ScriptSessionRecord(IdentifiedModel):
    """脚本会话资源。"""

    session_id: str = Field(description="所属会话 ID")
    language: str = Field(default="python", description="脚本语言")
    content_path: str = Field(description="脚本内容文件路径")
    execution_ids: list[str] = Field(default_factory=list, description="关联执行记录 ID")
    last_execution_id: str | None = Field(default=None, description="最近一次执行 ID")
    output_resource_ids: list[str] = Field(
        default_factory=list,
        description="最近一次执行产生的资源 ID 列表",
    )


class ChartSessionRecord(IdentifiedModel):
    """图表会话资源。"""

    session_id: str = Field(description="所属会话 ID")
    dataset_name: str = Field(description="数据集名称")
    chart_type: str = Field(description="图表类型")
    spec: dict[str, Any] = Field(default_factory=dict, description="图表规格")
    render_engine: str = Field(default="auto", description="渲染引擎")
    artifact_ids: list[str] = Field(default_factory=list, description="关联产物 ID")
    last_export_ids: list[str] = Field(default_factory=list, description="最近导出产物 ID")


class ReportSection(BaseModel):
    """报告章节。"""

    key: str = Field(min_length=1, description="章节键")
    title: str = Field(min_length=1, description="章节标题")
    content: str = Field(default="", description="章节内容")
    attachments: list[str] = Field(default_factory=list, description="关联资源 ID")


class ReportSessionRecord(IdentifiedModel):
    """报告会话资源。"""

    session_id: str = Field(description="所属会话 ID")
    title: str = Field(min_length=1, description="报告标题")
    sections: list[ReportSection] = Field(default_factory=list, description="章节列表")
    markdown_path: str | None = Field(default=None, description="渲染后的 Markdown 路径")
    export_ids: list[str] = Field(default_factory=list, description="导出产物 ID 列表")
