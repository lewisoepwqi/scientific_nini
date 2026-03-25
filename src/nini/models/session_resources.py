"""会话资源与执行记录模型。"""

from __future__ import annotations

from datetime import datetime
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


class ClaimVerificationStatus(str, Enum):
    """结论校验状态。"""

    VERIFIED = "verified"
    PENDING_VERIFICATION = "pending_verification"
    CONFLICTED = "conflicted"


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
    last_export_metadata: dict[str, Any] = Field(default_factory=dict, description="最近导出元数据")


class ReportSection(BaseModel):
    """报告章节。"""

    key: str = Field(min_length=1, description="章节键")
    title: str = Field(min_length=1, description="章节标题")
    content: str = Field(default="", description="章节内容")
    attachments: list[str] = Field(default_factory=list, description="关联资源 ID")


class SourceRecord(BaseModel):
    """最小溯源记录。"""

    source_id: str = Field(min_length=1, description="稳定来源标识")
    source_type: str = Field(min_length=1, description="来源类型")
    title: str = Field(min_length=1, description="来源标题或资源名")
    acquisition_method: str = Field(min_length=1, description="获取方式")
    accessed_at: datetime | None = Field(default=None, description="来源获取时间")
    source_time: datetime | None = Field(default=None, description="来源自身时间")
    stable_ref: str | None = Field(default=None, description="稳定外部标识")
    document_id: str | None = Field(default=None, description="知识文档 ID")
    resource_id: str | None = Field(default=None, description="工作区资源 ID")
    url: str | None = Field(default=None, description="来源 URL 或下载地址")
    excerpt: str = Field(default="", description="最小引用片段")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class EvidenceBlock(BaseModel):
    """最小证据块。"""

    claim_id: str = Field(min_length=1, description="结论稳定标识")
    claim_summary: str = Field(min_length=1, description="结论摘要")
    section_key: str | None = Field(default=None, description="所属章节键")
    sources: list[SourceRecord] = Field(default_factory=list, description="来源列表")
    verification_status: ClaimVerificationStatus = Field(
        default=ClaimVerificationStatus.PENDING_VERIFICATION,
        description="结论校验状态",
    )
    confidence_score: float = Field(default=0.0, description="置信度评分")
    reason_summary: str = Field(default="", description="状态原因摘要")
    conflict_summary: str | None = Field(default=None, description="冲突摘要")


class ClaimVerificationCandidate(BaseModel):
    """进入校验流水线的最小输入。"""

    claim_id: str = Field(min_length=1, description="结论稳定标识")
    claim_summary: str = Field(min_length=1, description="结论摘要")
    section_key: str | None = Field(default=None, description="所属章节")
    sources: list[SourceRecord] = Field(default_factory=list, description="待对齐来源")


class ProjectArtifactRecord(IdentifiedModel):
    """项目级正式产物记录。"""

    session_id: str = Field(description="所属会话 ID")
    artifact_type: str = Field(min_length=1, description="产物类型")
    name: str = Field(min_length=1, description="产物名称")
    logical_key: str = Field(min_length=1, description="版本归组键")
    version: int = Field(default=1, description="基础版本号")
    path: str = Field(min_length=1, description="工作区路径")
    format: str | None = Field(default=None, description="导出格式")
    template_id: str | None = Field(default=None, description="模板标识")
    resource_id: str | None = Field(default=None, description="关联资源 ID")
    source_task_id: str | None = Field(default=None, description="来源任务 ID")
    export_job_id: str | None = Field(default=None, description="导出作业 ID")
    idempotency_key: str | None = Field(default=None, description="幂等键")
    download_url: str | None = Field(default=None, description="下载地址")
    available_formats: list[str] = Field(default_factory=list, description="成功格式列表")
    failed_formats: list[str] = Field(default_factory=list, description="失败或降级格式列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class ExportJobRecord(IdentifiedModel):
    """导出作业记录。"""

    session_id: str = Field(description="所属会话 ID")
    target_resource_id: str | None = Field(default=None, description="目标资源 ID")
    target_resource_type: str | None = Field(default=None, description="目标资源类型")
    template_id: str | None = Field(default=None, description="模板标识")
    output_format: str = Field(min_length=1, description="目标格式")
    status: str = Field(default="pending", description="作业状态")
    source_task_id: str | None = Field(default=None, description="来源任务 ID")
    idempotency_key: str | None = Field(default=None, description="幂等键")
    output_artifact_ids: list[str] = Field(default_factory=list, description="输出产物 ID")
    message: str = Field(default="", description="状态说明")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class MethodsLedgerEntry(BaseModel):
    """METHODS 台账条目。"""

    entry_id: str | None = Field(default=None, description="条目标识")
    step_name: str = Field(min_length=1, description="步骤名称")
    method_name: str = Field(min_length=1, description="方法或工具名称")
    tool_name: str | None = Field(default=None, description="工具名称")
    data_sources: list[str] = Field(default_factory=list, description="关联来源标识")
    key_parameters: dict[str, Any] = Field(default_factory=dict, description="关键参数")
    model_name: str | None = Field(default=None, description="模型名称")
    model_version: str | None = Field(default=None, description="模型版本")
    executed_at: datetime | None = Field(default=None, description="执行时间")
    notes: str = Field(default="", description="补充说明")
    missing_fields: list[str] = Field(default_factory=list, description="缺失字段")


class ReportSessionRecord(IdentifiedModel):
    """报告会话资源。"""

    session_id: str = Field(description="所属会话 ID")
    title: str = Field(min_length=1, description="报告标题")
    sections: list[ReportSection] = Field(default_factory=list, description="章节列表")
    evidence_blocks: list[EvidenceBlock] = Field(default_factory=list, description="证据块列表")
    methods_ledger: list[MethodsLedgerEntry] = Field(
        default_factory=list,
        description="METHODS 台账",
    )
    methods_v1: str = Field(default="", description="结构化 METHODS v1 文本")
    markdown_path: str | None = Field(default=None, description="渲染后的 Markdown 路径")
    export_ids: list[str] = Field(default_factory=list, description="导出产物 ID 列表")
