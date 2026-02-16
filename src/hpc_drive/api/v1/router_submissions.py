"""
Submissions API Router

Provides endpoints for student assignment submissions with blind upload:
1. Submit assignment (student only) - auto-renames with student ID
2. Get all submissions (lecturer only)
3. Get my submissions (student only)

Permission model:
- STUDENT: Can upload to submission folder, see only their own files
- LECTURER: Can view all student submissions
- ADMIN: Can do anything
"""

import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ...database import get_session
from ...security import get_current_user, oauth2_scheme
from ...models import User, DriveItem, ItemType, RepositoryType, OwnerType, ProcessStatus, FileMetadata, FolderType
from ...config import settings
from .router_class_storage import check_class_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["Submissions"])


# ===== Helper Functions =====

def get_submission_folder(session: Session, course_folder_id: uuid.UUID) -> Optional[DriveItem]:
    """
    Get the "Nộp bài" submission folder for a course.
    
    Args:
        session: Database session
        course_folder_id: UUID of the course folder
    
    Returns:
        DriveItem of submission folder or None
    """
    course_folder = session.query(DriveItem).filter(
        DriveItem.item_id == course_folder_id
    ).first()
    
    if not course_folder:
        return None
    
    # Find "Nộp bài" subfolder
    submission_folder = session.query(DriveItem).filter(
        DriveItem.parent_id == course_folder_id,
        DriveItem.folder_type == FolderType.SUBMISSION,
        DriveItem.is_trashed == False
    ).first()
    
    return submission_folder


# ===== Endpoints =====

@router.post("/{class_id}/courses/{course_folder_id}/submit")
async def submit_assignment(
    class_id: int,
    course_folder_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Student submission with blind upload and auto-rename.
    
    **Workflow:**
    1. Check user is STUDENT in this class
    2. Find "Nộp bài" folder under course
    3. Auto-rename file with student ID prefix: {user_id}_{filename}
    4. Upload file to submission folder
    5. Notify lecturer (optional)
    
    **Permission:** STUDENT enrolled in class
    """
    logger.info(f"Student {current_user.user_id} submitting to course {course_folder_id}")
    
    # Permission check - students only
    if current_user.role.value != "STUDENT":
        raise HTTPException(
            status_code=403,
            detail="Only students can submit assignments"
        )
    
    # Basic class permission check
    await check_class_permission(current_user, class_id, token, require_upload=False)
    
    try:
        # 1. Get submission folder
        submission_folder = get_submission_folder(session, uuid.UUID(course_folder_id))
        
        if not submission_folder:
            raise HTTPException(
                status_code=404,
                detail="Submission folder not found for this course"
            )
        
        # 2. Create storage directory
        upload_dir = Path(settings.UPLOAD_DIR) / "class_storage" / str(class_id) / "submissions"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. Generate unique filename with student ID prefix
        file_id = uuid.uuid4()
        file_ext = Path(file.filename).suffix
        original_name = file.filename
        
        # AUTO-RENAME with student ID to prevent conflicts
        renamed_file = f"{current_user.user_id}_{original_name}"
        storage_filename = f"{file_id}{file_ext}"
        storage_path = upload_dir / storage_filename
        
        # 4. Save file
        with open(storage_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(storage_path)
        
        # 5. Create DriveItem with renamed display name
        drive_item = DriveItem(
            item_id=file_id,
            name=renamed_file,  # Display with student ID prefix
            item_type=ItemType.FILE,
            repository_type=RepositoryType.CLASS,
            repository_context_id=class_id,
            owner_id=current_user.user_id,
            owner_type=OwnerType.STUDENT,
            parent_id=submission_folder.item_id,
            process_status=ProcessStatus.READY,
            is_system_generated=False,
            is_locked=False
        )
        
        session.add(drive_item)
        session.flush()
        
        # 6. Create FileMetadata
        file_metadata = FileMetadata(
            item_id=file_id,
            mime_type=file.content_type or "application/octet-stream",
            size=file_size,
            storage_path=str(storage_path),
            version=1
        )
        
        session.add(file_metadata)
        session.commit()
        
        logger.info(f"Student {current_user.user_id} submitted: {renamed_file}")
        
        return {
            "message": "Assignment submitted successfully",
            "item_id": str(file_id),
            "filename": renamed_file,
            "original_filename": original_name,
            "size": file_size,
            "submitted_at": drive_item.created_at
        }
    
    except Exception as e:
        session.rollback()
        logger.error(f"Submission failed: {e}")
        
        # Clean up file if it was saved
        if 'storage_path' in locals() and storage_path.exists():
            storage_path.unlink()
        
        raise HTTPException(
            status_code=500,
            detail=f"Submission failed: {str(e)}"
        )


@router.get("/{class_id}/courses/{course_folder_id}/all")
async def get_all_submissions(
    class_id: int,
    course_folder_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Get all student submissions for a course.
    
    **Permission:** LECTURER teaching class or ADMIN
    
    **Returns:** List of all submissions with student info
    """
    logger.info(f"Lecturer {current_user.user_id} viewing all submissions for course {course_folder_id}")
    
    # Check lecturer permission
    await check_class_permission(current_user, class_id, token, require_upload=True)
    
    # Get submission folder
    submission_folder = get_submission_folder(session, uuid.UUID(course_folder_id))
    
    if not submission_folder:
        raise HTTPException(
            status_code=404,
            detail="Submission folder not found"
        )
    
    # Get all files in submission folder
    submissions = session.query(DriveItem).filter(
        DriveItem.parent_id == submission_folder.item_id,
        DriveItem.item_type == ItemType.FILE,
        DriveItem.is_trashed == False
    ).all()
    
    result = []
    for item in submissions:
        submission_dict = {
            "item_id": str(item.item_id),
            "filename": item.name,
            "student_id": item.owner_id,
            "submitted_at": item.created_at,
            "updated_at": item.updated_at
        }
        
        if item.file_metadata:
            submission_dict["size"] = item.file_metadata.size
            submission_dict["mime_type"] = item.file_metadata.mime_type
        
        result.append(submission_dict)
    
    logger.info(f"Found {len(result)} submissions")
    return result


@router.get("/{class_id}/courses/{course_folder_id}/my-submissions")
async def get_my_submissions(
    class_id: int,
    course_folder_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Get current student's submissions for a course.
    
    **Permission:** STUDENT enrolled in class
    
    **Returns:** List of own submissions only
    """
    logger.info(f"Student {current_user.user_id} viewing own submissions")
    
    # Permission check
    await check_class_permission(current_user, class_id, token, require_upload=False)
    
    # Get submission folder
    submission_folder = get_submission_folder(session, uuid.UUID(course_folder_id))
    
    if not submission_folder:
        raise HTTPException(
            status_code=404,
            detail="Submission folder not found"
        )
    
    # Get only current student's files
    submissions = session.query(DriveItem).filter(
        DriveItem.parent_id == submission_folder.item_id,
        DriveItem.item_type == ItemType.FILE,
        DriveItem.owner_id == current_user.user_id,
        DriveItem.is_trashed == False
    ).all()
    
    result = []
    for item in submissions:
        submission_dict = {
            "item_id": str(item.item_id),
            "filename": item.name,
            "submitted_at": item.created_at,
            "updated_at": item.updated_at
        }
        
        if item.file_metadata:
            submission_dict["size"] = item.file_metadata.size
            submission_dict["mime_type"] = item.file_metadata.mime_type
        
        result.append(submission_dict)
    
    return result
