"""
File upload and management service.
"""
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, List
import aiofiles
from fastapi import UploadFile

import pandas as pd

from app.core.config import settings
from app.core.exceptions import FileUploadException, FileValidationException


class FileService:
    """Service for handling file uploads and management."""
    
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = settings.MAX_UPLOAD_SIZE
        self.allowed_extensions = settings.allowed_extensions_list
    
    def validate_file(self, file: UploadFile) -> None:
        """Validate uploaded file."""
        if not file.filename:
            raise FileValidationException("No filename provided")
        
        # Check extension
        ext = file.filename.split(".")[-1].lower()
        if ext not in self.allowed_extensions:
            raise FileValidationException(
                f"Invalid file type: .{ext}. "
                f"Allowed types: {', '.join(self.allowed_extensions)}"
            )
        
        # Check content type
        allowed_content_types = [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
            "text/csv",
            "text/plain",
            "application/octet-stream"
        ]
        if file.content_type and file.content_type not in allowed_content_types:
            if not any(ct in (file.content_type or "") for ct in ["excel", "csv", "spreadsheet"]):
                pass  # Allow for now, we'll validate by trying to read
    
    async def save_file(self, file: UploadFile, dataset_id: str) -> dict:
        """Save uploaded file to disk."""
        self.validate_file(file)
        
        # Generate unique filename
        original_ext = file.filename.split(".")[-1].lower()
        unique_filename = f"{dataset_id}.{original_ext}"
        file_path = self.upload_dir / unique_filename
        
        try:
            # Read and save file
            content = await file.read()
            
            # Check file size
            if len(content) > self.max_size:
                raise FileUploadException(
                    f"File too large: {len(content)} bytes. "
                    f"Maximum: {self.max_size} bytes"
                )
            
            # Save file
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
            
            return {
                "filename": file.filename,
                "file_path": str(file_path),
                "file_size": len(content),
                "file_type": original_ext
            }
            
        except Exception as e:
            # Clean up on error
            if file_path.exists():
                file_path.unlink()
            raise FileUploadException(f"Failed to save file: {str(e)}")
        finally:
            await file.close()
    
    def read_dataframe(self, file_path: str, **kwargs) -> pd.DataFrame:
        """Read file into pandas DataFrame."""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        try:
            if ext in [".xlsx", ".xls"]:
                return pd.read_excel(path, **kwargs)
            elif ext == ".csv":
                return pd.read_csv(path, **kwargs)
            elif ext in [".tsv", ".txt"]:
                return pd.read_csv(path, sep="\t", **kwargs)
            else:
                raise FileValidationException(f"Unsupported file extension: {ext}")
        except Exception as e:
            raise FileValidationException(f"Failed to read file: {str(e)}")
    
    def delete_file(self, file_path: str) -> bool:
        """Delete file from disk."""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False
    
    def get_file_info(self, file_path: str) -> dict:
        """Get file information."""
        path = Path(file_path)
        if not path.exists():
            raise FileValidationException(f"File not found: {file_path}")
        
        stat = path.stat()
        return {
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "extension": path.suffix.lower()
        }


# Singleton instance
file_service = FileService()
