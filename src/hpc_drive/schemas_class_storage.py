"""
Pydantic schemas for Class Storage endpoints.

Defines request/response models for:
- Auto-folder generation
- Class storage uploads
- Class item listings
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
import uuid


# ===== Request Schemas =====

class ClassFolderGenerateRequest(BaseModel):
    """Request to auto-generate folder structure for a class."""
    
    class_id: int = Field(..., description="Class ID from System-Management")
    semester_id: Optional[int] = Field(None, description="Specific semester to generate folders for (optional)")
    

class ClassFolderCreateRequest(BaseModel):
    """Request to create a custom folder in class storage."""
    name: str = Field(..., description="Folder name")
    parent_id: Optional[str] = Field(None, description="Parent folder ID")


class ClassStorageUploadRequest(BaseModel):
    """Metadata for uploading file to class storage."""
    
    class_id: int = Field(..., description="Class ID")
    folder_path: Optional[str] = Field(None, description="Path within class storage (e.g., 'Kỳ 1/Lập trình Python')")
    

# ===== Response Schemas =====

class ClassFolderInfo(BaseModel):
    """Information about a generated folder."""
    
    item_id: uuid.UUID
    name: str
    path: str  # Full path from class root


class ClassFolderGenerateResponse(BaseModel):
    """Response after generating class folder structure."""
    
    model_config = ConfigDict(from_attributes=True)
    
    class_id: int
    root_folder_id: uuid.UUID
    folders_created: List[ClassFolderInfo]
    message: str


class ClassItemResponse(BaseModel):
    """Response for a class storage item."""
    
    model_config = ConfigDict(from_attributes=True)
    
    item_id: uuid.UUID
    name: str
    item_type: str  # FILE or FOLDER
    is_system_generated: bool
    is_locked: bool
    folder_type: Optional[str] = None  # SUBMISSION, CLASS_INFO, NORMAL
    process_status: str
    created_at: datetime
    updated_at: Optional[datetime]
    parent_id: Optional[uuid.UUID] = None
    
    # File metadata (if type = FILE)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    
    # Owner info
    owner_id: int
    owner_name: Optional[str] = None


class ClassListResponse(BaseModel):
    """Response with list of classes user has access to."""
    
    class_id: int
    class_name: str
    class_code: str
    role: str  # LECTURER or STUDENT
    has_upload_permission: bool
    has_storage: bool = False  # True if folder structure has been generated