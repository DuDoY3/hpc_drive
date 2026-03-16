import httpx
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ... import crud, schemas
from ...config import settings

# Updated imports
from ...database import get_session
from ...models import User, UserRole
from ...security import get_current_user, get_current_user_data_from_auth, oauth2_scheme, map_role

router = APIRouter(prefix="/drive", tags=["Drive"])


@router.get("/me", response_model=schemas.UserDataFromAuth)
def get_user_me(
    current_user_data: schemas.UserDataFromAuth = Depends(
        get_current_user_data_from_auth
    ),
):
    """
    Returns the raw user data payload from the Auth Service.
    This shows what data we get for the synced user.
    """
    return current_user_data


@router.post(
    "/items",
    response_model=schemas.DriveItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    item: schemas.DriveItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Create a new drive item (FILE or FOLDER) in the root
    or inside a parent folder.
    """
    # Passing 'current_user' object so CRUD can determine OwnerType
    return crud.create_drive_item(db=db, item=item, owner=current_user)


@router.get("/items", response_model=schemas.DriveItemListResponse)
def list_items_in_folder(
    parent_id: Optional[uuid.UUID] = None,  # Pass as query parameter
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    List all items for the current user within a specific folder.
    If 'parent_id' is not provided, lists items in the root.
    """
    items = crud.get_user_items_in_folder(
        db=db, owner_id=current_user.user_id, parent_id=parent_id
    )
    return {"parent_id": parent_id, "items": items}


@router.patch("/items/{item_id}/star", response_model=schemas.DriveItemResponse)
def toggle_item_star(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Toggles the is_starred status of a drive item.
    """
    return crud.toggle_star_item(
        db=db,
        item_id=item_id,
        user_id=current_user.user_id,
    )


@router.get("/items/{item_id}", response_model=schemas.DriveItemResponse)
def get_item_details(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Get the details for a single drive item.
    """
    return crud.get_drive_item(
        db=db,
        item_id=item_id,
        user_id=current_user.user_id,
    )


@router.get("/items/{item_id}/download", response_class=FileResponse)
def download_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Downloads a file.
    """
    db_item = crud.get_drive_item(
        db=db,
        item_id=item_id,
        user_id=current_user.user_id,
    )

    # db_item is now a DICT. We must use .get() instead of dot notation.
    if db_item.get("item_type") != "FILE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files can be downloaded",
        )

    file_metadata = db_item.get("file_metadata")
    if not file_metadata or not file_metadata.get("storage_path"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Construct the absolute path from the base uploads dir and the relative path
    full_file_path = settings.UPLOADS_DIR / file_metadata.get("storage_path")

    if not full_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    from urllib.parse import quote
    
    encoded_filename = quote(db_item.get("name", "downloaded_file"))
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return FileResponse(
        path=str(full_file_path),
        media_type=file_metadata.get("mime_type", "application/octet-stream"),
        headers=headers
    )


@router.post(
    "/upload",
    response_model=schemas.DriveItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_file(
    file: UploadFile = File(...),
    parent_id: Optional[uuid.UUID] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Uploads a file. This endpoint accepts multipart/form-data.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    # 0. Check System Settings constraints
    settings_data = crud.get_system_settings(db)
    
    # Extension Check
    ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ""
    blocked_exts = [e.strip().lower() for e in settings_data.blocked_extensions.split(',')]
    if ext in blocked_exts:
        raise HTTPException(status_code=400, detail=f"Định dạng file '{ext}' không được phép tải lên hệ thống.")
        
    # Owner Quota Check setup
    if current_user.is_unlimited_storage:
        user_quota = float('inf')
    else:
        user_quota = current_user.custom_storage_quota_gb * 1024**3 if current_user.custom_storage_quota_gb else settings_data.default_quota_gb * 1024**3
        
    available_quota = max(0, user_quota - (current_user.used_storage or 0))
    max_size_bytes = settings_data.max_upload_size_mb * 1024 * 1024

    # 1. Define the storage path
    item_storage_id = uuid.uuid4()
    # The relative path that will be stored in the database
    relative_dir = Path(str(current_user.user_id)) / str(item_storage_id)
    storage_dir = settings.UPLOADS_DIR / relative_dir

    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / file.filename
    db_storage_path = relative_dir / file.filename

    # 2. Save the file to disk while validating size AND calculating hash
    import hashlib
    file_hash = hashlib.sha256()
    file_size = 0
    
    try:
        with storage_path.open("wb") as buffer:
            while chunk := file.file.read(8192):
                file_size += len(chunk)
                if file_size > max_size_bytes:
                    raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of {settings_data.max_upload_size_mb} MB")
                if current_user.role != UserRole.ADMIN and file_size > available_quota:
                    raise HTTPException(status_code=400, detail="Storage Quota Exceeded")
                file_hash.update(chunk)
                buffer.write(chunk)
    except Exception as e:
        if storage_path.exists(): storage_path.unlink()
        if storage_dir.exists(): storage_dir.rmdir()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    finally:
        file.file.close()

    # Provide a default MIME type if one isn't provided
    mime_type = file.content_type if file.content_type else "application/octet-stream"

    # 3. VirusTotal Scan
    from ...scanner import check_hash_virustotal
    from ...models import ProcessStatus
    
    process_status = ProcessStatus.READY
    if settings_data.quarantine_enabled:
        process_status = check_hash_virustotal(file_hash.hexdigest())
        if process_status == ProcessStatus.INFECTED:
            # Delete file and abort
            if storage_path.exists(): storage_path.unlink()
            if storage_dir.exists(): storage_dir.rmdir()
            raise HTTPException(status_code=400, detail="Upload failed: Malware detected.")

    # 4. Call the new CRUD function to create both DB records
    try:
        db_item = crud.create_file_with_metadata(
            db=db,
            owner=current_user,
            filename=file.filename,
            parent_id=parent_id,
            mime_type=mime_type,
            size=file_size,
            storage_path=str(db_storage_path),
            process_status=process_status,
        )
        return db_item
    except HTTPException as e:
        # Cleanup if DB insert fails
        if storage_path.exists():
            storage_path.unlink()
        if storage_dir.exists():
            storage_dir.rmdir()
        raise e


@router.patch("/items/{item_id}/trash", response_model=schemas.DriveItemResponse)
def move_item_to_trash(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return crud.trash_item(db=db, item_id=item_id, owner_id=current_user.user_id)


@router.patch("/items/{item_id}/restore", response_model=schemas.DriveItemResponse)
def restore_item_from_trash(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return crud.restore_item(db=db, item_id=item_id, owner_id=current_user.user_id)


@router.get("/trash", response_model=List[schemas.DriveItemResponse])
def get_trashed_items(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_session)
):
    return crud.get_user_trash(db=db, owner_id=current_user.user_id)


@router.patch("/items/{item_id}", response_model=schemas.DriveItemResponse)
def update_item_details(
    item_id: uuid.UUID,
    update_data: schemas.DriveItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return crud.update_drive_item(
        db=db, item_id=item_id, owner_id=current_user.user_id, update_data=update_data
    )


@router.post(
    "/items/{item_id}/share",
    response_model=schemas.SharePermissionResponse,
    tags=["Sharing"],
)
async def share_an_item(
    item_id: uuid.UUID,
    share_data: schemas.ShareCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
    token: str = Depends(oauth2_scheme),
):
    # If target user doesn't exist locally, try to find them via Laravel API and auto-create
    target_user = crud.get_user_by_username(db, share_data.username)
    
    if not target_user:
        print(f"🔍 [SHARE] User '{share_data.username}' not found locally. Searching via Laravel API...")
        target_user = await _sync_user_from_laravel(db, share_data.username, token)
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy người dùng '{share_data.username}'. Hãy kiểm tra lại tên đăng nhập.",
        )
    
    return crud.share_item(
        db=db, item_id=item_id, owner_id=current_user.user_id, share_data=share_data
    )


async def _sync_user_from_laravel(db: Session, username: str, token: str) -> User | None:
    """
    Search for a user in the Laravel System-Management API via /users/search endpoint
    and auto-create them locally. This allows sharing with users who haven't opened Drive yet.
    The endpoint only requires JWT auth (no admin/lecturer role needed).
    """
    try:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        search_url = settings.AUTH_SERVICE_ME_URL.replace('/me', '/users/search')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                search_url,
                headers=headers,
                params={"username": username}
            )
            
            print(f"🔍 [SHARE] Laravel /users/search response: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                
                if data.get("found"):
                    user_id = data.get("id")
                    email = data.get("email", "")
                    is_admin = data.get("is_admin", False)
                    user_type = data.get("user_type", "student")
                    
                    new_user = User(
                        user_id=user_id,
                        username=username,
                        email=email,
                        role=map_role(user_type, is_admin),
                    )
                    db.add(new_user)
                    db.commit()
                    db.refresh(new_user)
                    print(f"✅ [SHARE] Auto-synced user '{username}' (id={user_id}, type={user_type}) from Laravel API")
                    return new_user
                else:
                    return None
            else:
                # Trả về lỗi chi tiết lên frontend để debug
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Lỗi từ Laravel API: Status {resp.status_code}. Body: {resp.text}"
                )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Lỗi kết nối đến Laravel API: {e}"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi không xác định khi tìm người dùng: {e}"
        )



@router.post(
    "/items/{item_id}/copy-to-personal",
    response_model=schemas.DriveItemResponse,
    tags=["Sharing"],
)
def copy_item_to_personal(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Copy a shared file into the current user's personal storage (root folder).
    Uses shutil.copy2 for disk-level copy — zero RAM usage, safe for large files.
    """
    return crud.copy_file_on_server(
        db=db,
        item_id=item_id,
        user_id=current_user.user_id,
        parent_id=None,  # Save to root
    )


@router.get(
    "/shared-with-me", response_model=List[schemas.DriveItemResponse], tags=["Drive"]
)
def get_items_shared_with_me(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_session)
):
    # DEBUG: Log để verify user_id đúng
    print(f"🔍 [DEBUG] get_items_shared_with_me called by user_id={current_user.user_id}, username={current_user.username}")
    
    items = crud.get_shared_with_me_items(db=db, user_id=current_user.user_id)
    
    print(f"🔍 [DEBUG] Returning {len(items)} items for user {current_user.username}")
    
    return items


@router.get("/search", response_model=List[schemas.DriveItemResponse])
def search_drive_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
    query: schemas.DriveItemSearchQuery = Depends(),
):
    return crud.search_items(db=db, user_id=current_user.user_id, query=query)


@router.delete("/trash/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    crud.delete_item_permanently(db=db, item_id=item_id, owner_id=current_user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
def empty_trash(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_session)
):
    crud.empty_user_trash(db=db, owner_id=current_user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usage", response_model=schemas.StorageUsageResponse)
def get_storage_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Get current storage usage and limits for the user.
    """
    breakdown = crud.get_user_storage_breakdown(db, current_user.user_id)
    settings_data = crud.get_system_settings(db)
    
    # Sử dụng trực tiếp trường storage_quota đã được đồng bộ ở backend
    quota = current_user.storage_quota
    
    # Max file size vẫn lấy từ system settings nếu cần, hoặc có thể lưu riêng lẻ per user
    max_file_size = current_user.max_file_size
    
    return {
        "used_storage": current_user.used_storage or 0,
        "storage_quota": quota,
        "max_file_size": max_file_size,
        "images_storage": breakdown["images_storage"],
        "documents_storage": breakdown["documents_storage"],
        "videos_storage": breakdown["videos_storage"],
        "others_storage": breakdown["others_storage"],
    }


@router.put("/items/{item_id}/content", response_model=schemas.DriveItemResponse)
async def edit_file_content(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    save_copy: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Edit file content. 
    - If editing own file or shared file with EDITOR permission: updates the file
    - If save_copy=True and file is shared: creates a copy in personal storage
    """
    # Read the uploaded file content
    new_content = await file.read()
    file_size = len(new_content)
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")
    
    # Check if user is trying to save a copy
    if save_copy:
        # Create a copy in user's personal storage
        return crud.save_shared_file_copy(
            db=db,
            item_id=item_id,
            user_id=current_user.user_id,
            new_content=new_content,
            file_size=file_size,
            filename=file.filename,
        )
    else:
        # Update the existing file
        return crud.update_file_content(
            db=db,
            item_id=item_id,
            user_id=current_user.user_id,
            new_content=new_content,
            file_size=file_size,
        )


@router.get("/items/{item_id}/can-edit")
def check_can_edit(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Check if the current user can edit a file.
    Returns can_edit status and reason.
    """
    try:
        db_item, is_owner = crud.check_edit_permission(
            db=db,
            item_id=item_id,
            user_id=current_user.user_id
        )
        
        if is_owner:
            reason = "You are the owner of this file"
        else:
            reason = "You have editor permission for this file"
        
        return {
            "can_edit": True,
            "is_owner": is_owner,
            "reason": reason,
            "current_version": db_item.file_metadata.version if db_item.file_metadata else None,
        }
    except HTTPException as e:
        return {
            "can_edit": False,
            "is_owner": False,
            "reason": e.detail,
            "current_version": None,
        }