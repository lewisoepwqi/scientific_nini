"""
Custom exceptions for the application.
"""
from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""
    def __init__(self, status_code: int, detail: str, headers: dict = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class FileUploadException(AppException):
    """Exception for file upload errors."""
    def __init__(self, detail: str = "File upload failed"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class FileValidationException(AppException):
    """Exception for file validation errors."""
    def __init__(self, detail: str = "Invalid file"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class DataProcessingException(AppException):
    """Exception for data processing errors."""
    def __init__(self, detail: str = "Data processing failed"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class AnalysisException(AppException):
    """Exception for statistical analysis errors."""
    def __init__(self, detail: str = "Analysis failed"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class VisualizationException(AppException):
    """Exception for visualization errors."""
    def __init__(self, detail: str = "Visualization generation failed"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class NotFoundException(AppException):
    """Exception for resource not found errors."""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class AuthenticationException(AppException):
    """Exception for authentication errors."""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )
