"""
Department Storage API Router

Provides endpoints for department-based document storage:
1. List items in department storage
2. Upload files (lecturer of department only)
3. Download files
4. Get my department

Permission model:
- LECTURER (in department): Can upload, download
- LECTURER (other department): Cannot access
- STUDENT: Cannot access
- ADMIN: Can do anything
"""

import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ...database import get_session
from ...security import get_current_user, oauth2_scheme, get_current_user_data_from_auth
from ...models import User, DriveItem, ItemType, RepositoryType, OwnerType, ProcessStatus, FileMetadata
from ...schemas_department_storage import (
    DepartmentStorageUploadRequest,
    DepartmentItemResponse,
    DepartmentListResponse
)
from ...integrations import system_management_service
from ...config import settings
from ...schemas import UserDataFromAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/department-storage", tags=["Department Storage"])


# ===== Helper Functions =====

def check_department_permission(
    user: User,
    user_data: UserDataFromAuth,
    department_id: int,
    require_upload: bool = False
) -> bool:
    """
    Check if user has permission to access department storage.
    
    Permission rules:
    - Admin: Full access to all departments
    - Lecturer: Access only to their own department
    - Student: No access
    """
    # Admin can do anything
    if user.role.value == "ADMIN":
        return True
    
    # Students cannot access department storage
    if user.role.value == "STUDENT":
        raise HTTPException(
            status_code=403,
            detail="Students cannot access department storage"
        )
    
    # Lecturers can only access their own department
    if user.role.value == "TEACHER":
        # Get lecturer's department from JWT
        lecturer_dept_id = None
        if user_data.lecturer_info:
            lecturer_dept_id = user_data.lecturer_info.department_id
        
        if lecturer_dept_id is None:
            raise HTTPException(
                status_code=400,
                detail="Lecturer department information not found"
            )
        
        if lecturer_dept_id != department_id:
            raise HTTPException(
                status_code=403,
                detail=f"You can only access your own department storage (department {lecturer_dept_id})"
            )
    
    return True


def get_department_root_folder(session: Session, department_id: int) -> Optional[DriveItem]:
    """Get the root folder for a department storage."""
    return session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.DEPARTMENT,
        DriveItem.repository_context_id == department_id,
        DriveItem.parent_id == None,
        DriveItem.name == f"Department_{department_id}_Root"
    ).first()


# ===== Endpoints =====

@router.get("/{department_id}/items", response_model=List[DepartmentItemResponse])
async def list_department_items(
    department_id: int,
    parent_id: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    user_data: UserDataFromAuth = Depends(get_current_user_data_from_auth)
):
    """
    List items in department storage.
    
    **Permission:** Admin or Lecturer from the department
    """
    logger.info(f"Listing items for department {department_id}")
    
    # Permission check
    check_department_permission(current_user, user_data, department_id, require_upload=False)
    
    # Build query
    query = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.DEPARTMENT,
        DriveItem.repository_context_id == department_id,
        DriveItem.is_trashed == False
    )
    
    if parent_id:
        query = query.filter(DriveItem.parent_id == uuid.UUID(parent_id))
    else:
        # Get root folder
        root = get_department_root_folder(session, department_id)
        if root:
            query = query.filter(DriveItem.parent_id == root.item_id)
        else:
            query = query.filter(DriveItem.parent_id == None)
    
    items = query.all()
    
    # Convert to response
    result = []
    for item in items:
        item_dict = {
            "item_id": item.item_id,
            "name": item.name,
            "item_type": item.item_type.value,
            "is_system_generated": item.is_system_generated,
            "is_locked": item.is_locked,
            "process_status": item.process_status.value,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "owner_id": item.owner_id
        }
        
        # Add file metadata
        if item.item_type == ItemType.FILE and item.file_metadata:
            item_dict["file_size"] = item.file_metadata.size
            item_dict["mime_type"] = item.file_metadata.mime_type
        
        result.append(DepartmentItemResponse(**item_dict))
    
    return result


@router.post("/{department_id}/upload")
async def upload_to_department_storage(
    department_id: int,
    file: UploadFile = File(...),
    parent_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    user_data: UserDataFromAuth = Depends(get_current_user_data_from_auth)
):
    """
    Upload a file to department storage.
    
    **Permission:** Admin or Lecturer from the department
    """
    logger.info(f"Upload to department {department_id} by user {current_user.user_id}: {file.filename}")
    
    # Permission check
    check_department_permission(current_user, user_data, department_id, require_upload=True)
    
    try:
        # 1. Create storage directory
        upload_dir = Path(settings.UPLOADS_DIR) / "department_storage" / str(department_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Generate unique filename
        file_id = uuid.uuid4()
        file_ext = Path(file.filename).suffix
        storage_filename = f"{file_id}{file_ext}"
        storage_path = upload_dir / storage_filename
        
        # 3. Save file
        with open(storage_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(storage_path)
        
        # 4. Create DriveItem
        drive_item = DriveItem(
            item_id=file_id,
            name=file.filename,
            item_type=ItemType.FILE,
            repository_type=RepositoryType.DEPARTMENT,
            repository_context_id=department_id,
            owner_id=current_user.user_id,
            owner_type=OwnerType.LECTURER if current_user.role.value == "TEACHER" else OwnerType.ADMIN,
            parent_id=uuid.UUID(parent_id) if parent_id else None,
            process_status=ProcessStatus.READY,  # Mock scanning
            is_system_generated=False,
            is_locked=False
        )
        
        session.add(drive_item)
        session.flush()
        
        # 5. Create FileMetadata
        file_metadata = FileMetadata(
            item_id=file_id,
            mime_type=file.content_type or "application/octet-stream",
            size=file_size,
            storage_path=str(storage_path),
            version=1
        )
        
        session.add(file_metadata)

        # Bug Fix: Update the user's total used storage to reflect this upload
        current_user.used_storage = (current_user.used_storage or 0) + file_size
        session.add(current_user)

        session.commit()
        
        logger.info(f"File uploaded successfully: {file_id}")
        
        return {
            "message": "File uploaded successfully",
            "item_id": str(file_id),
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        session.rollback()
        logger.error(f"Upload failed: {e}")
        
        # Clean up file if it was saved
        if 'storage_path' in locals() and storage_path.exists():
            storage_path.unlink()
        
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/my-department", response_model=DepartmentListResponse)
async def get_my_department(
    current_user: User = Depends(get_current_user),
    user_data: UserDataFromAuth = Depends(get_current_user_data_from_auth),
    token: str = Depends(oauth2_scheme)
):
    """
    Get current lecturer's department information.
    
    **Permission:** Lecturer only
    """
    if current_user.role.value != "TEACHER":
        raise HTTPException(
            status_code=403,
            detail="Only lecturers have department information"
        )
    
    if not user_data.lecturer_info:
        raise HTTPException(
            status_code=400,
            detail="Lecturer information not found"
        )
    
    dept_id = user_data.lecturer_info.department_id
    
    # Get department name from System-Management
    try:
        dept = await system_management_service.get_department(token, dept_id)
        
        return DepartmentListResponse(
            department_id=dept_id,
            department_name=dept.get("name", f"Department {dept_id}"),
            has_upload_permission=True,
            is_own_department=True
        )
    except Exception as e:
        logger.error(f"Failed to get department info: {e}")
        # Return basic info even if API fails
        return DepartmentListResponse(
            department_id=dept_id,
            department_name=f"Department {dept_id}",
            has_upload_permission=True,
            is_own_department=True
        )