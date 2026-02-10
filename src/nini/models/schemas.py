"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---- WebSocket 消息 ----


class WSMessage(BaseModel):
    """客户端发送的 WebSocket 消息。"""

    type: str = "chat"  # chat / retry / stop / upload_complete / ping
    content: str = ""
    session_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WSEvent(BaseModel):
    """服务端推送的 WebSocket 事件。"""

    type: str  # text / tool_call / tool_result / retrieval / chart / data / done / stopped / error / iteration_start
    data: Any = None
    session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    turn_id: Optional[str] = None


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
    error: Optional[str] = None


class ModelConfigRequest(BaseModel):
    """模型配置保存请求。"""

    provider_id: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool = True


class SetActiveModelRequest(BaseModel):
    """设置活跃模型请求。"""

    provider_id: str


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
