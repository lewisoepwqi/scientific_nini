"""
应用通用 Schema 定义。
"""
from typing import Generic, TypeVar, Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """通用 API 响应包装器。"""
    success: bool = True
    message: str = "Success"
    data: Optional[T] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装器。"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """错误响应 Schema。"""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SortParams(BaseModel):
    """Sorting parameters."""
    sort_by: Optional[str] = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
