"""
Pydantic schemas for Signing Workflow endpoints.

Defines request/response models for:
- Creating signing requests
- Approving/rejecting requests
- Listing requests
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid


# ===== Request Schemas =====

class SigningRequestCreate(BaseModel):
    """Create a new signing request."""
    
    drive_item_id: uuid.UUID = Field(..., description="DriveItem ID (must be PDF file)")
    approver_id: Optional[int] = Field(None, description="Specific admin to approve (optional)")


class SigningRequestUpdate(BaseModel):
    """Update signing request status (admin only)."""
    
    admin_comment: Optional[str] = Field(None, description="Admin comment for approval/rejection")


# ===== Response Schemas =====

class SigningRequestResponse(BaseModel):
    """Response for signing request."""
    
    model_config = ConfigDict(from_attributes=True)
    
    request_id: uuid.UUID
    drive_item_id: uuid.UUID
    requester_id: int
    approver_id: Optional[int]
    current_status: str  # DRAFT, PENDING, APPROVED, REJECTED
    admin_comment: Optional[str]
    signed_file_path: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    approved_at: Optional[datetime]
    
    # Related data
    file_name: Optional[str] = None
    requester_name: Optional[str] = None
    approver_name: Optional[str] = None