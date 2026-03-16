import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ... import crud, models, schemas
from ...config import settings
from ...database import get_session
from ...security import get_current_user

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])

ROOT_CURRICULUM_NAME = "Curriculum"


async def check_student_enrollment_from_remote(
    student_id: int, subject_code: str, auth_token: str
) -> bool:
    # URL gọi sang service Laravel
    url = f"{settings.LEARNING_SERVICE_URL}/api/v1/attendance/students/{student_id}/courses"
    headers = {"Authorization": f"Bearer {auth_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            return False

        data = response.json()
        if not data.get("success"):
            return False

        courses = data.get("data", [])
        for course in courses:
            if str(course.get("code", "")).lower() == subject_code.lower():
                return True
        return False
    except Exception as e:
        print(f"Check enrollment error: {e}")
        return False


def _get_system_folder(
    db: Session, folder_name: str, parent_id: Optional[uuid.UUID] = None
) -> Optional[models.DriveItem]:
    item = (
        db.query(models.DriveItem)
        .filter(
            models.DriveItem.name == folder_name,
            models.DriveItem.parent_id == parent_id,
            models.DriveItem.is_trashed == False,
            models.DriveItem.item_type == models.ItemType.FOLDER,  # Dùng Enum ItemType
        )
        .first()
    )
    return item


def _ensure_curriculum_structure(
    db: Session, subject_code: str, owner: models.User
) -> models.DriveItem:
    root = _get_system_folder(db, ROOT_CURRICULUM_NAME)
    if not root:
        root_schema = schemas.DriveItemCreate(
            name=ROOT_CURRICULUM_NAME, item_type=models.ItemType.FOLDER, parent_id=None
        )
        root = crud.create_drive_item(db, root_schema, owner)

    subject_folder = _get_system_folder(db, subject_code, parent_id=root.item_id)
    if not subject_folder:
        sub_schema = schemas.DriveItemCreate(
            name=subject_code, item_type=models.ItemType.FOLDER, parent_id=root.item_id
        )
        subject_folder = crud.create_drive_item(db, sub_schema, owner)

    return subject_folder


def save_upload_file_to_disk(upload_file: UploadFile) -> str:
    """Lưu file xuống đĩa và trả về relative path"""
    # Tạo thư mục theo ngày để tránh quá tải folder: uploads/2023/10/15/...
    today = datetime.now()
    relative_folder = Path(str(today.year)) / str(today.month) / str(today.day)
    full_folder_path = settings.UPLOADS_DIR / relative_folder
    full_folder_path.mkdir(parents=True, exist_ok=True)  # Tạo folder nếu chưa có

    # Tạo tên file unique
    file_ext = Path(upload_file.filename).suffix if upload_file.filename else ""
    unique_name = f"{uuid.uuid4()}{file_ext}"
    relative_path = relative_folder / unique_name
    full_path = settings.UPLOADS_DIR / relative_path

    with open(full_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    return str(relative_path)


@router.post("/{subject_code}/upload", response_model=schemas.DriveItemResponse)
def upload_curriculum_material(
    subject_code: str,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    # 1. Check quyền (so sánh với enum value, không phải string)
    if current_user.role not in (models.UserRole.TEACHER, models.UserRole.ADMIN):
        raise HTTPException(
            status_code=403, detail="Chỉ giảng viên được quyền upload tài liệu."
        )

    # 2. Đảm bảo cấu trúc folder
    subject_folder = _ensure_curriculum_structure(db, subject_code, current_user)

    # 3. Lưu file xuống ổ cứng (Thay thế hàm crud không tồn tại)
    try:
        storage_path = save_upload_file_to_disk(file)

        # Lấy size file
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()

        # 4. Lưu vào DB
        new_item = crud.create_file_with_metadata(
            db=db,
            owner=current_user,
            filename=file.filename or "unknown",
            parent_id=subject_folder.item_id,
            mime_type=file.content_type or "application/octet-stream",
            size=file_size,
            storage_path=storage_path,
        )
        return new_item

    except Exception as e:
        # Nếu lỗi DB thì nên xóa file rác đã lưu (TODO)
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi lưu file giáo trình")


@router.get("/{subject_code}", response_model=List[schemas.DriveItemResponse])
async def list_curriculum_materials(
    subject_code: str,
    authorization: str = Header(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    role = str(current_user.role)

    if role == "STUDENT":
        token = (
            authorization.split(" ")[1]
            if authorization and " " in authorization
            else authorization
        )

        is_enrolled = await check_student_enrollment_from_remote(
            current_user.user_id, subject_code, token
        )

        if not is_enrolled:
            raise HTTPException(status_code=403, detail="Bạn chưa đăng ký môn học này.")

    root = _get_system_folder(db, ROOT_CURRICULUM_NAME)
    if not root:
        return []

    subject_folder = _get_system_folder(db, subject_code, parent_id=root.item_id)
    if not subject_folder:
        return []

    items = crud.get_items_in_folder_admin_view(db, subject_folder.item_id)
    return crud.populate_stars_to_dicts(db, current_user.user_id, items)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    item_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    if str(current_user.role) not in ["TEACHER", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Không có quyền xóa.")

    crud.trash_item(db, item_id, current_user.user_id)
    return None


@router.get("/{item_id}/download")
async def download_curriculum_material(
    item_id: uuid.UUID,
    authorization: str = Header(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Download a curriculum file. 
    - Teachers/Admins can download any curriculum file
    - Students can download if enrolled in the subject
    """
    from fastapi.responses import FileResponse
    
    # Get the item without ownership check (curriculum files are shared)
    item = db.query(models.DriveItem).filter(
        models.DriveItem.item_id == item_id,
        models.DriveItem.is_trashed == False
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="File không tồn tại.")
    
    if item.item_type != models.ItemType.FILE:
        raise HTTPException(status_code=400, detail="Chỉ có thể tải file.")
    
    # Check if this is a curriculum file (parent folder structure: Curriculum/{subject_code})
    parent_folder = db.query(models.DriveItem).filter(
        models.DriveItem.item_id == item.parent_id
    ).first()
    
    if not parent_folder:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục.")
    
    # Get the Curriculum root folder
    curriculum_root = db.query(models.DriveItem).filter(
        models.DriveItem.item_id == parent_folder.parent_id
    ).first()
    
    # Verify this is under Curriculum folder
    if not curriculum_root or curriculum_root.name != ROOT_CURRICULUM_NAME:
        raise HTTPException(status_code=403, detail="Không có quyền tải file này.")
    
    subject_code = parent_folder.name
    
    # For students, check enrollment
    role = str(current_user.role)
    if role == "STUDENT":
        token = (
            authorization.split(" ")[1]
            if authorization and " " in authorization
            else authorization
        )
        
        is_enrolled = await check_student_enrollment_from_remote(
            current_user.user_id, subject_code, token
        )
        
        if not is_enrolled:
            raise HTTPException(status_code=403, detail="Bạn chưa đăng ký môn học này.")
    
    # Get file metadata
    file_meta = db.query(models.FileMetadata).filter(
        models.FileMetadata.item_id == item_id
    ).first()
    
    if not file_meta or not file_meta.storage_path:
        raise HTTPException(status_code=404, detail="Không tìm thấy file.")
    
    # Construct full path
    full_path = settings.UPLOADS_DIR / file_meta.storage_path
    
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại trên server.")
    
    return FileResponse(
        path=str(full_path),
        filename=item.name,
        media_type=file_meta.mime_type or "application/octet-stream",
    )