"""
Health check endpoint.
"""
from fastapi import APIRouter, status

from app.schemas.common import APIResponse

router = APIRouter()


@router.get("/", response_model=APIResponse[dict])
async def health_check():
    """Health check endpoint."""
    return APIResponse(
        success=True,
        message="Service is healthy",
        data={
            "status": "healthy",
            "version": "1.0.0"
        }
    )


@router.get("/ping", response_model=APIResponse[str])
async def ping():
    """Simple ping endpoint."""
    return APIResponse(
        success=True,
        message="pong",
        data="pong"
    )
