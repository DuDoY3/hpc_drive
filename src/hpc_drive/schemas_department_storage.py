"""
Pydantic schemas for Department Storage endpoints.

Defines request/response models for:
- Department storage listings
- Department uploads
- Department access control
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
import uuid


# ===== Request Schemas =====

class DepartmentStorageUploadRequest(BaseModel):
    """Metadata for uploading file to department storage."""
    
    department_id: int = Field(..., description="Department ID from System-Management")
    folder_path: Optional[str] = Field(None, description="Path within department storage")


# ===== Response Schemas =====

class DepartmentItemResponse(BaseModel):
    """Response for a department storage item."""
    
    model_config = ConfigDict(from_attributes=True)
    
    item_id: uuid.UUID
    name: str
    item_type: str  # FILE or FOLDER
    is_system_generated: bool
    is_locked: bool
    process_status: str
    created_at: datetime
    updated_at: Optional[datetime]
    
    # File metadata (if type = FILE)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    
    # Owner info
    owner_id: int
    owner_name: Optional[str] = None


class DepartmentListResponse(BaseModel):
    """Response with department info."""
    
    department_id: int
    department_name: str
    has_upload_permission: bool
    is_own_department: bool