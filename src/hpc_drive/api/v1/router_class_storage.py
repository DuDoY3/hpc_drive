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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ...database import get_session
from ...security import get_current_user, oauth2_scheme
from ...models import User, DriveItem, ItemType, RepositoryType, OwnerType, ProcessStatus, FileMetadata, FolderType
from ...schemas_class_storage import (
    ClassFolderGenerateRequest,
    ClassFolderGenerateResponse,
    ClassFolderInfo,
    ClassItemResponse,
    ClassListResponse,
    ClassFolderCreateRequest
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


@router.post("/{class_id}/folders", response_model=ClassItemResponse)
async def create_class_folder(
    class_id: int,
    request: ClassFolderCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Create a custom folder in class storage.
    
    **Permission:** Lecturer teaching the class only
    """
    logger.info(f"Creating folder '{request.name}' in class {class_id} by user {current_user.user_id}")
    
    # Permission check (lecturer only)
    await check_class_permission(current_user, class_id, token, require_upload=True)
    
    try:
        # Determine parent folder
        parent_folder = None
        if request.parent_id:
            parent_folder = session.query(DriveItem).filter(
                DriveItem.item_id == uuid.UUID(request.parent_id),
                DriveItem.repository_type == RepositoryType.CLASS,
                DriveItem.repository_context_id == class_id,
                DriveItem.item_type == ItemType.FOLDER
            ).first()
            
            if not parent_folder:
                raise HTTPException(status_code=404, detail="Parent folder not found")
        else:
            # Must have parent (normally root) for custom folders to keep it safe
            parent_folder = get_class_root_folder(session, class_id)
            if not parent_folder:
                raise HTTPException(status_code=404, detail="Class root folder not found")
                
        # Check if folder with same name exists in parent
        existing = session.query(DriveItem).filter(
            DriveItem.parent_id == parent_folder.item_id,
            DriveItem.name == request.name,
            DriveItem.is_trashed == False
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Thư mục đã tồn tại. Vui lòng chọn tên khác."
            )
            
        # Create folder
        new_folder = await create_folder(
            session=session,
            name=request.name,
            parent=parent_folder,
            class_id=class_id,
            owner=current_user,
            is_system_generated=False,
            is_locked=False
        )
        
        session.commit()
        
        return ClassItemResponse(
            item_id=new_folder.item_id,
            name=new_folder.name,
            item_type=new_folder.item_type.value,
            is_system_generated=new_folder.is_system_generated,
            is_locked=new_folder.is_locked,
            folder_type=None,
            process_status=new_folder.process_status.value,
            created_at=new_folder.created_at,
            updated_at=new_folder.updated_at,
            owner_id=new_folder.owner_id,
            parent_id=new_folder.parent_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create folder: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create folder: {str(e)}"
        )


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
        relative_dir = Path("class_storage") / str(class_id)
        # Fallback to UPLOADS_DIR if UPLOAD_DIR is not present
        base_upload_dir = Path(getattr(settings, "UPLOADS_DIR", "uploads"))
        upload_dir = base_upload_dir / relative_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Generate unique filename
        import os
        base_name, ext = os.path.splitext(file.filename)
        counter = 1
        unique_filename = file.filename
        
        while True:
            existing = session.query(DriveItem).filter(
                DriveItem.name == unique_filename,
                DriveItem.parent_id == uuid.UUID(parent_id) if parent_id else None,
                DriveItem.repository_type == RepositoryType.CLASS,
                DriveItem.repository_context_id == class_id,
                DriveItem.item_type == ItemType.FILE,
                DriveItem.is_trashed == False
            ).first()
            if not existing:
                break
            unique_filename = f"{base_name} ({counter}){ext}"
            counter += 1
            
        file.filename = unique_filename
        
        file_id = uuid.uuid4()
        storage_filename = f"{file_id}{ext}"
        storage_path = upload_dir / storage_filename
        db_storage_path = relative_dir / storage_filename
        
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
            storage_path=str(db_storage_path).replace("\\", "/"),
            version=1
        )
        
        session.add(file_metadata)

        # Bug Fix: Update the user's total used storage to reflect this upload
        current_user.used_storage = (current_user.used_storage or 0) + file_size
        session.add(current_user)

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


@router.delete("/{class_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class_item(
    class_id: int,
    item_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Delete an item from class storage.
    Lecturers only.
    """
    await check_class_permission(current_user, class_id, token, require_upload=True)

    item = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS,
        DriveItem.repository_context_id == class_id,
        DriveItem.item_id == item_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.is_locked:
        raise HTTPException(status_code=403, detail="Cannot delete a locked folder")

    # Delete the file from storage if applicable
    if item.item_type == ItemType.FILE and item.file_metadata:
        try:
            full_file_path = Path(settings.UPLOADS_DIR) / item.file_metadata.storage_path
            if full_file_path.is_file():
                full_file_path.unlink()
                # Optionally delete empty parent directory
                try:
                    full_file_path.parent.rmdir()
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"Failed to delete file from disk: {e}")

    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{class_id}/items/{item_id}/download", response_class=FileResponse)
async def download_class_item(
    class_id: int,
    item_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Download a file from class storage.
    Both students and lecturers can download.
    """
    await check_class_permission(current_user, class_id, token, require_upload=False)

    item = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS,
        DriveItem.repository_context_id == class_id,
        DriveItem.item_id == item_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.item_type != ItemType.FILE:
        raise HTTPException(status_code=400, detail="Only files can be downloaded")

    if not item.file_metadata or not item.file_metadata.storage_path:
        raise HTTPException(status_code=404, detail="File metadata not found")

    full_file_path = Path(settings.UPLOADS_DIR) / item.file_metadata.storage_path

    if not full_file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(full_file_path),
        filename=item.name,
        media_type=item.file_metadata.mime_type or "application/octet-stream"
    )


@router.get("/{class_id}/items/{item_id}/can-edit")
async def check_class_can_edit(
    class_id: int,
    item_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Check if the current user can edit a class file.
    Lecturers only.
    """
    try:
        await check_class_permission(current_user, class_id, token, require_upload=True)
        
        item = session.query(DriveItem).filter(
            DriveItem.repository_type == RepositoryType.CLASS,
            DriveItem.repository_context_id == class_id,
            DriveItem.item_id == item_id
        ).first()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        if item.item_type != ItemType.FILE:
            raise HTTPException(status_code=400, detail="Only files can be edited")

        if item.is_locked:
            raise HTTPException(status_code=403, detail="File is locked and cannot be edited")

        return {
            "can_edit": True,
            "is_owner": item.owner_id == current_user.user_id,
            "reason": "You have lecturer access to this class",
            "current_version": item.file_metadata.version if item.file_metadata else 1
        }
    except HTTPException as e:
        return {
            "can_edit": False,
            "is_owner": False,
            "reason": str(e.detail),
            "current_version": None
        }


@router.put("/{class_id}/items/{item_id}/content", response_model=ClassItemResponse)
async def map_edit_class_file_content(
    class_id: int,
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    save_copy: bool = Form(False),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    """
    Update the content of a class file.
    Lecturers only.
    """
    await check_class_permission(current_user, class_id, token, require_upload=True)

    item = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS,
        DriveItem.repository_context_id == class_id,
        DriveItem.item_id == item_id
    ).first()

    if not item or item.item_type != ItemType.FILE:
        raise HTTPException(status_code=404, detail="File not found")

    if save_copy:
        # Saving a copy to personal storage
        from ... import crud
        new_content = await file.read()
        storage_filename = f"{uuid.uuid4()}_{file.filename or item.name}"
        storage_path = Path("users") / str(current_user.user_id) / storage_filename
        
        full_path = Path(settings.UPLOADS_DIR) / storage_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("wb") as buffer:
            buffer.write(new_content)
            
        file_copy = crud.create_file_atomically(
            db=session,
            owner=current_user,
            filename=f"Copy of {file.filename or item.name}",
            parent_id=None, # Root of personal drive
            mime_type=item.file_metadata.mime_type if item.file_metadata else "application/octet-stream",
            size=len(new_content),
            storage_path=str(storage_path)
        )
        return {
            "item_id": file_copy.item_id,
            "name": file_copy.name,
            "item_type": file_copy.item_type.value,
            "is_system_generated": file_copy.is_system_generated,
            "is_locked": file_copy.is_locked,
            "folder_type": getattr(file_copy, 'folder_type', None),
            "process_status": file_copy.process_status.value if file_copy.process_status else "READY",
            "created_at": file_copy.created_at,
            "updated_at": file_copy.updated_at,
            "parent_id": file_copy.parent_id,
            "file_size": file_copy.file_metadata.size if file_copy.file_metadata else None,
            "mime_type": file_copy.file_metadata.mime_type if file_copy.file_metadata else None,
            "owner_id": file_copy.owner_id,
            "owner_name": file_copy.owner.username if getattr(file_copy, 'owner', None) else None
        }

    # Updating the original file directly
    if not item.file_metadata or not item.file_metadata.storage_path:
        raise HTTPException(status_code=404, detail="Original file metadata missing")
        
    full_file_path = Path(settings.UPLOADS_DIR) / item.file_metadata.storage_path

    try:
        new_content = await file.read()
        with full_file_path.open("wb") as buffer:
            buffer.write(new_content)
            
        item.file_metadata.size = len(new_content)
        item.file_metadata.version = (item.file_metadata.version or 1) + 1
        
        # We don't change updated_at for DriveItem typically, but let's record it
        import datetime
        item.updated_at = datetime.datetime.utcnow()
        
        session.commit()
        session.refresh(item)
        
        return {
            "item_id": item.item_id,
            "name": item.name,
            "item_type": item.item_type.value,
            "is_system_generated": item.is_system_generated,
            "is_locked": item.is_locked,
            "folder_type": item.folder_type.value if item.folder_type else None,
            "process_status": item.process_status.value if item.process_status else "READY",
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "parent_id": item.parent_id,
            "file_size": item.file_metadata.size if item.file_metadata else None,
            "mime_type": item.file_metadata.mime_type if item.file_metadata else None,
            "owner_id": item.owner_id,
            "owner_name": item.owner.username if getattr(item, 'owner', None) else None
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save class file content: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

print("=== REGISTERING ROUTE MY_CLASSES ===")
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