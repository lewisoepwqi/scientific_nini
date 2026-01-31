"""
分享包 Schema。
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class ExportPackageResponse(BaseModel):
    """分享包响应。"""

    id: str
    visualization_id: str
    dataset_version_ref: str
    config_snapshot: Dict[str, Any]
    render_log_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
