"""
Class Storage API Router

Provides endpoints for class-based document storage:
1. Auto-generate folder structure (semesters, courses)
2. List items in class storage
3. Upload files (lecturer only)
4. Download files  
5. List classes user has access to

Permission model:
- LECTURER (teaching the class): Can upload, download, delete
- STUDENT (in the class): Can download only
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
from ...security import get_current_user, oauth2_scheme
from ...models import User, DriveItem, ItemType, RepositoryType, OwnerType, ProcessStatus, FileMetadata, FolderType
from ...schemas_class_storage import (
    ClassFolderGenerateRequest,
    ClassFolderGenerateResponse,
    ClassFolderInfo,
    ClassItemResponse,
    ClassListResponse
)
from ...integrations import system_management_service
from ...config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/class-storage", tags=["Class Storage"])


# ===== Helper Functions =====

async def check_class_permission(
    user: User,
    class_id: int,
    token: str,
    require_upload: bool = False
) -> bool:
    """
    Check if user has permission to access class storage.
    
    Args:
        user: Current user
        class_id: Class ID
        token: JWT token
        require_upload: If True, checks for upload permission (lecturer only)
    
Returns:
        True if permitted, raises HTTPException if not
    """
    # Admin can do anything
    if user.role.value == "ADMIN":
        return True
    
    # For upload permission, must be lecturer teaching the class
    if require_upload:
        if user.role.value != "TEACHER":
            raise HTTPException(
                status_code=403,
                detail="Only lecturers can upload to class storage"
            )
        
        # Check if lecturer teaches this class
        try:
            teaches_class = await system_management_service.check_lecturer_teaches_class(
                token=token,
                lecturer_id=user.user_id,
                class_id=class_id
            )
        except Exception as e:
            logger.warning(f"Failed to verify lecturer-class via Laravel API: {e}")
            logger.info(f"Fallback: allowing lecturer {user.user_id} access to class {class_id}")
            teaches_class = True  # Allow in dev when Laravel is unavailable
        
        if not teaches_class:
            raise HTTPException(
                status_code=403,
                detail=f"You do not teach class {class_id}"
            )
    
    # For view/download, students and lecturers allowed
    # TODO: In production, verify student is in the class
    return True


def get_class_root_folder(session: Session, class_id: int) -> Optional[DriveItem]:
    """Get the root folder for a class storage."""
    return session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS,
        DriveItem.repository_context_id == class_id,
        DriveItem.parent_id == None
    ).first()


async def create_folder(
    session: Session,
    name: str,
    parent: Optional[DriveItem],
    class_id: int,
    owner: User,
    is_system_generated: bool = False,
    is_locked: bool = False,
    folder_type: Optional[FolderType] = None
) -> DriveItem:
    """
    Create a folder in class storage.
    
    Args:
        session: Database session
        name: Folder name
        parent: Parent folder (None for root)
        class_id: Class ID
        owner: Owner user
        is_system_generated: Mark as system-generated
        is_locked: Lock from user deletion
        folder_type: Folder type (SUBMISSION, CLASS_INFO, etc.)
    
    Returns:
        Created DriveItem
    """
    folder = DriveItem(
        item_id=uuid.uuid4(),
        name=name,
        item_type=ItemType.FOLDER,
        repository_type=RepositoryType.CLASS,
        repository_context_id=class_id,
        owner_id=owner.user_id,
        owner_type=OwnerType.ADMIN if owner.role.value == "ADMIN" else OwnerType.LECTURER,
        parent_id=parent.item_id if parent else None,
        is_system_generated=is_system_generated,
        is_locked=is_locked,
        folder_type=folder_type,
        process_status=ProcessStatus.READY
    )
    
    session.add(folder)
    session.flush()  # Get ID without committing
    
    return folder


# ===== Endpoints =====

@router.post("/auto-generate/{class_id}", response_model=ClassFolderGenerateResponse)
async def auto_generate_class_folders(
    class_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Auto-generate folder structure for a class.
    
    Creates:
    - Root folder for class
    - "Thông tin lớp học" with 3 subfolders
    - Semester folders (Kỳ 1, Kỳ 2, Kỳ 3, Kỳ 4)
    - Course folders (from System-Management API)
    - 5 standard subfolders per course: Bài giảng, Tài liệu tham khảo, 
      Bài tập & Đề cương, Đề thi mẫu, Nộp bài
    
    **Permission:** Admin or Lecturer teaching the class
    """
    logger.info(f"Auto-generating folders for class {class_id} by user {current_user.user_id}")
    
    # Permission check
    await check_class_permission(current_user, class_id, token, require_upload=True)
    
    # Check if root already exists
    existing_root = get_class_root_folder(session, class_id)
    if existing_root:
        raise HTTPException(
            status_code=400,
            detail=f"Folders for class {class_id} already exist"
        )
    
    folders_created: List[ClassFolderInfo] = []
    
    try:
        # Fetch class name from API system management
        class_name = f"Class_{class_id}_Root" # Fallback
        try:
            classes = await system_management_service.get_lecturer_classes(
                token=token,
                lecturer_id=current_user.user_id
            )
            for c in classes:
                if c.get("id") == class_id:
                    class_name = c.get("class_name", class_name)
                    break
        except Exception as e:
            logger.warning(f"Failed to fetch class details for root folder name: {e}")
            
        # 1. Create root folder
        root = await create_folder(
            session=session,
            name=class_name,
            parent=None,
            class_id=class_id,
            owner=current_user,
            is_system_generated=True,
            is_locked=True
        )
        
        folders_created.append(ClassFolderInfo(
            item_id=root.item_id,
            name=root.name,
            path="/"
        ))
        
        # 2. Create "Thông tin lớp học" folder with subfolders
        class_info_folder = await create_folder(
            session=session,
            name="Thông tin lớp học",
            parent=root,
            class_id=class_id,
            owner=current_user,
            is_system_generated=True,
            is_locked=True,
            folder_type=FolderType.CLASS_INFO
        )
        
        folders_created.append(ClassFolderInfo(
            item_id=class_info_folder.item_id,
            name=class_info_folder.name,
            path="/Thông tin lớp học"
        ))
        
        # 2.1 Create subfolders under "Thông tin lớp học"
        class_info_subfolders = [
            "Danh sách lớp",
            "Thời khóa biểu", 
            "Biểu mẫu sinh viên"
        ]
        
        for subfolder_name in class_info_subfolders:
            subfolder = await create_folder(
                session=session,
                name=subfolder_name,
                parent=class_info_folder,
                class_id=class_id,
                owner=current_user,
                is_system_generated=True,
                is_locked=True,
                folder_type=FolderType.CLASS_INFO
            )
            
            folders_created.append(ClassFolderInfo(
                item_id=subfolder.item_id,
                name=subfolder.name,
                path=f"/Thông tin lớp học/{subfolder_name}"
            ))
        
        # 3. Create semester folders and their contents
        for semester_num in range(1, 5):  # Kỳ 1 đến Kỳ 4
            semester_folder = await create_folder(
                session=session,
                name=f"Kỳ {semester_num}",
                parent=root,
                class_id=class_id,
                owner=current_user,
                is_system_generated=True,
                is_locked=True
            )
            
            folders_created.append(ClassFolderInfo(
                item_id=semester_folder.item_id,
                name=semester_folder.name,
                path=f"/Kỳ {semester_num}"
            ))
            
            # 4. Create 4 STANDARD subfolders directly under each semester
            semester_subfolders = [
                ("Bài giảng (Lectures / Slides)", None),
                ("Tài liệu tham khảo (References)", None),
                ("Bài tập & Đồ án (Assignments)", None),
                ("Nộp bài tập (Submissions)", FolderType.SUBMISSION)
            ]
            
            for subfolder_name, folder_type in semester_subfolders:
                subfolder = await create_folder(
                    session=session,
                    name=subfolder_name,
                    parent=semester_folder,
                    class_id=class_id,
                    owner=current_user,
                    is_system_generated=True,
                    is_locked=folder_type is None,  # Lock standard folders, but leave Submission folder customizable if needed
                    folder_type=folder_type
                )
                
                folders_created.append(ClassFolderInfo(
                    item_id=subfolder.item_id,
                    name=subfolder.name,
                    path=f"/Kỳ {semester_num}/{subfolder_name}"
                ))
        
        # Commit all changes
        session.commit()
        
        logger.info(f"Created {len(folders_created)} folders for class {class_id}")
        
        return ClassFolderGenerateResponse(
            class_id=class_id,
            root_folder_id=root.item_id,
            folders_created=folders_created,
            message=f"Successfully created {len(folders_created)} folders"
        )
    
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to generate folders: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate folders: {str(e)}"
        )


@router.get("/{class_id}/items", response_model=List[ClassItemResponse])
async def list_class_items(
    class_id: int,
    parent_id: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    List items in class storage.
    
    **Parameters:**
    - `class_id`: Class ID
    - `parent_id`: Parent folder ID (optional, defaults to root)
    
    **Returns:** List of files and folders
    
    **Permission:** Anyone in the class (students, lecturers)
    
    **Security:** Students can only see their own files in submission folders
    """
    logger.info(f"Listing items for class {class_id}, parent={parent_id}")
    
    # Permission check
    await check_class_permission(current_user, class_id, token, require_upload=False)
    
    # Determine parent folder context
    current_folder = None
    if parent_id:
        current_folder = session.query(DriveItem).filter(
            DriveItem.item_id == uuid.UUID(parent_id)
        ).first()
    
    # Build query
    query = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS,
        DriveItem.repository_context_id == class_id,
        DriveItem.is_trashed == False
    )
    
    if parent_id:
        query = query.filter(DriveItem.parent_id == uuid.UUID(parent_id))
    else:
        query = query.filter(DriveItem.parent_id == None)
    
    # SECURITY FIX: Filter submission folder for students
    # Students can only see their own files in SUBMISSION folders
    if current_folder and current_folder.folder_type == FolderType.SUBMISSION:
        if current_user.role.value == "STUDENT":
            query = query.filter(DriveItem.owner_id == current_user.user_id)
            logger.info(f"Applied SUBMISSION filter for student {current_user.user_id}")
    
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
            "folder_type": item.folder_type.value if item.folder_type else None,
            "process_status": item.process_status.value,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "owner_id": item.owner_id,
            "parent_id": item.parent_id
        }
        
        # Add file metadata if it's a file
        if item.item_type == ItemType.FILE and item.file_metadata:
            item_dict["file_size"] = item.file_metadata.size
            item_dict["mime_type"] = item.file_metadata.mime_type
        
        result.append(ClassItemResponse(**item_dict))
    
    return result


@router.post("/{class_id}/upload")
async def upload_to_class_storage(
    class_id: int,
    file: UploadFile = File(...),
    parent_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Upload a file to class storage.
    
    **Permission:** Lecturer teaching the class only
    
    **Workflow:**
    1. Check permission
    2. Save file to storage
    3. Create DriveItem + FileMetadata
    4. Notify all students in class
    """
    logger.info(f"Upload to class {class_id} by user {current_user.user_id}: {file.filename}")
    
    # Permission check (lecturer only)
    await check_class_permission(current_user, class_id, token, require_upload=True)
    
    try:
        # 1. Create storage directory
        upload_dir = Path(settings.UPLOAD_DIR) / "class_storage" / str(class_id)
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
            repository_type=RepositoryType.CLASS,
            repository_context_id=class_id,
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
        session.commit()
        
        # 6. Smart notification system with context-aware priority
        try:
            # Detect parent folder for priority
            priority = "NORMAL"
            notification_icon = "📄"
            folder_context = "tài liệu"
            
            if parent_id:
                parent_folder = session.query(DriveItem).filter(
                    DriveItem.item_id == uuid.UUID(parent_id)
                ).first()
                
                if parent_folder:
                    # Skip notification for submission folders (student uploads)
                    if parent_folder.folder_type == FolderType.SUBMISSION:
                        logger.info("Skipping notification for submission folder")
                        return {
                            "message": "File uploaded successfully",
                            "item_id": str(file_id),
                            "filename": file.filename,
                            "size": file_size
                        }
                    
                    # Set priority based on folder name
                    folder_name = parent_folder.name.lower()
                    
                    if "đề thi" in folder_name or "exam" in folder_name:
                        priority = "URGENT"
                        notification_icon = "🔴"
                        folder_context = "đề thi"
                    elif "bài tập" in folder_name or "assignment" in folder_name:
                        priority = "HIGH"
                        notification_icon = "📝"
                        folder_context = "bài tập"
                    elif "bài giảng" in folder_name or "slide" in folder_name:
                        notification_icon = "📊"
                        folder_context = "bài giảng"
                    elif "tài liệu" in folder_name:
                        notification_icon = "📚"
                        folder_context = "tài liệu tham khảo"
            
            await system_management_service.notify_class_students(
                token=token,
                class_id=class_id,
                title=f"{notification_icon} Tài liệu mới: {file.filename}",
                message=f"{current_user.username} đã upload {folder_context} mới vào lớp học",
                type="FILE_UPLOAD",
                priority=priority,
                metadata={
                    "class_id": class_id,
                    "drive_item_id": str(file_id),
                    "filename": file.filename,
                    "folder_type": folder_context
                }
            )
            logger.info(f"Notification sent for file upload: {file_id} with priority: {priority}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            # Continue - upload was successful
        
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
        if storage_path.exists():
            storage_path.unlink()
        
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/my-classes", response_model=List[ClassListResponse])
async def get_my_classes(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
):
    """
    Get list of classes the current user has access to.
    
    **Returns:**
    - For LECTURER: Classes they teach
    - For STUDENT: Classes they're enrolled in
    - For ADMIN: All classes (TODO)
    """
    logger.info(f"Getting classes for user {current_user.user_id}")
    
    def check_has_storage(class_id: int) -> bool:
        """Check if class already has auto-generated folder structure."""
        root = session.query(DriveItem).filter(
            DriveItem.repository_type == RepositoryType.CLASS,
            DriveItem.repository_context_id == class_id,
            DriveItem.parent_id == None
        ).first()
        return root is not None
    
    try:
        if current_user.role.value == "TEACHER":
            # Get classes lecturer teaches
            try:
                classes = await system_management_service.get_lecturer_classes(
                    token=token,
                    lecturer_id=current_user.user_id
                )
            except Exception as e:
                logger.warning(f"Failed to fetch lecturer classes from Laravel API: {e}")
                logger.info("Falling back to mock data for lecturer")
                # Fallback mock data when Laravel API is unavailable
                classes = [
                    {
                        "id": 1,
                        "class_name": "Lớp CNTT K65",
                        "class_code": "CNTT65"
                    }
                ]
            
            return [
                ClassListResponse(
                    class_id=cls.get("id"),
                    class_name=cls.get("class_name", "Unknown"),
                    class_code=cls.get("class_code", ""),
                    role="LECTURER",
                    has_upload_permission=True,
                    has_storage=check_has_storage(cls.get("id"))
                )
                for cls in classes
            ]
        
        elif current_user.role.value == "STUDENT":
            # TODO: Get classes student is enrolled in from Laravel API
            # For now, return mock data based on seeder
            
            logger.info(f"Returning mock class data for student {current_user.user_id}")
            
            # Mock data matching AdminSeeder.php
            class_id = 1
            return [
                ClassListResponse(
                    class_id=class_id,
                    class_name="Lớp CNTT K65",
                    class_code="CNTT65",
                    role="STUDENT",
                    has_upload_permission=False,
                    has_storage=check_has_storage(class_id)
                )
            ]
        
        else:  # ADMIN
            # TODO: Get all classes
            return []
    
    except Exception as e:
        logger.error(f"Failed to get classes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get classes: {str(e)}"
        )

