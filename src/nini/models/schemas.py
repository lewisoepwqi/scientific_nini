"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---- WebSocket 消息 ----


class WSMessage(BaseModel):
    """客户端发送的 WebSocket 消息。"""

    type: str = "chat"  # chat / retry / stop / ask_user_question_answer / upload_complete / ping
    content: str = ""
    session_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WSEvent(BaseModel):
    """服务端推送的 WebSocket 事件。"""

    type: str  # text / tool_call / tool_result / ask_user_question / retrieval / chart / data / analysis_plan / plan_step_update / plan_progress / task_attempt / done / stopped / error / iteration_start
    data: Any = None
    session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    turn_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---- HTTP 响应 ----


class SessionInfo(BaseModel):
    """会话信息。"""

    id: str
    title: str = "新会话"
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DatasetInfo(BaseModel):
    """数据集信息。"""

    id: str
    session_id: str
    name: str
    file_path: str
    file_type: str
    file_size: int = 0
    row_count: int = 0
    column_count: int = 0


class UploadResponse(BaseModel):
    """文件上传响应。"""

    success: bool
    dataset: Optional[DatasetInfo] = None
    workspace_file: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class APIResponse(BaseModel):
    """通用 API 响应。"""

    success: bool = True
    data: Any = None
    message: Optional[str] = None
    error: Optional[str] = None


class ModelConfigRequest(BaseModel):
    """模型配置保存请求。"""

    provider_id: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    priority: Optional[int] = None
    is_active: bool = True


class ModelPrioritiesRequest(BaseModel):
    """模型优先级批量更新请求。"""

    priorities: dict[str, int] = Field(default_factory=dict)


class SetActiveModelRequest(BaseModel):
    """设置活跃模型请求。"""

    provider_id: str


class ModelPurposeRouteRequest(BaseModel):
    """单个用途的模型路由配置。"""

    provider_id: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class ModelRoutingRequest(BaseModel):
    """用途模型路由配置请求。"""

    preferred_provider: Optional[str] = None
    purpose_routes: dict[str, ModelPurposeRouteRequest] = Field(default_factory=dict)
    # 兼容旧版前端：仅提供 provider 映射
    purpose_providers: dict[str, Optional[str]] = Field(default_factory=dict)


class SessionUpdateRequest(BaseModel):
    """会话更新请求。"""

    title: Optional[str] = None


class SaveWorkspaceTextRequest(BaseModel):
    """保存工作空间文本文件请求。"""

    content: str
    filename: Optional[str] = None


class FileRenameRequest(BaseModel):
    """文件重命名请求。"""

    name: str


class MarkdownSkillUpdateRequest(BaseModel):
    """Markdown Skill 编辑请求。"""

    description: str = Field(min_length=1)
    category: str = Field(default="other")
    content: str = ""


class MarkdownSkillEnabledRequest(BaseModel):
    """Markdown Skill 启用状态更新请求。"""

    enabled: bool


class MarkdownSkillFileWriteRequest(BaseModel):
    """Markdown Skill 文件写入请求。"""

    path: str = Field(min_length=1)
    content: str = ""


class MarkdownSkillDirCreateRequest(BaseModel):
    """Markdown Skill 目录创建请求。"""

    path: str = Field(min_length=1)


class MarkdownSkillPathDeleteRequest(BaseModel):
    """Markdown Skill 文件/目录删除请求。"""

    path: str = Field(min_length=1)


# ---- ResearchProfile 研究画像 ----


class ResearchProfileData(BaseModel):
    """研究画像数据。"""

    user_id: str
    domain: str = "general"
    research_interest: str = ""
    significance_level: float = 0.05
    preferred_correction: str = "bonferroni"
    confidence_interval: float = 0.95
    journal_style: str = "nature"
    color_palette: str = "default"
    figure_width: int = 800
    figure_height: int = 600
    figure_dpi: int = 300
    auto_check_assumptions: bool = True
    include_effect_size: bool = True
    include_ci: bool = True
    include_power_analysis: bool = False
    total_analyses: int = 0
    favorite_tests: list[str] = Field(default_factory=list)
    recent_datasets: list[str] = Field(default_factory=list)
    research_domains: list[str] = Field(default_factory=list)
    preferred_methods: dict[str, float] = Field(default_factory=dict)
    output_language: str = "zh"
    report_detail_level: str = "standard"
    typical_sample_size: str = ""
    research_notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ResearchProfileUpdateRequest(BaseModel):
    """研究画像更新请求。"""

    domain: Optional[str] = None
    research_interest: Optional[str] = None
    significance_level: Optional[float] = None
    preferred_correction: Optional[str] = None
    confidence_interval: Optional[float] = None
    journal_style: Optional[str] = None
    color_palette: Optional[str] = None
    figure_width: Optional[int] = None
    figure_height: Optional[int] = None
    figure_dpi: Optional[int] = None
    auto_check_assumptions: Optional[bool] = None
    include_effect_size: Optional[bool] = None
    include_ci: Optional[bool] = None
    include_power_analysis: Optional[bool] = None
    research_domains: Optional[list[str]] = None
    preferred_methods: Optional[dict[str, float]] = None
    output_language: Optional[str] = None
    report_detail_level: Optional[str] = None
    typical_sample_size: Optional[str] = None
    research_notes: Optional[str] = None


# ---- Report Generation 报告生成 ----


class ReportGenerateRequest(BaseModel):
    """报告生成请求。"""

    title: str = "科研数据分析报告"
    template: str = "default"  # nature/science/cell/nejm/lancet/apa/ieee/default
    sections: list[str] = Field(
        default_factory=lambda: ["abstract", "introduction", "methods", "results", "discussion"]
    )
    detail_level: str = "standard"  # brief/standard/detailed
    include_figures: bool = True
    include_tables: bool = True
    dataset_names: Optional[list[str]] = None


class ReportExportRequest(BaseModel):
    """报告导出请求。"""

    format: str = "md"  # md/docx/pdf
    filename: Optional[str] = None


