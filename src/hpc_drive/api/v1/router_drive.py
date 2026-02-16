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
from ...models import User
from ...security import get_current_user, get_current_user_data_from_auth

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

    if db_item.item_type != "FILE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files can be downloaded",
        )

    if not db_item.file_metadata or not db_item.file_metadata.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Construct the absolute path from the base uploads dir and the relative path
    full_file_path = settings.UPLOADS_DIR / db_item.file_metadata.storage_path

    if not full_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    return FileResponse(
        path=str(full_file_path),
        filename=db_item.name,
        media_type=db_item.file_metadata.mime_type,
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

    # 1. Define the storage path
    item_storage_id = uuid.uuid4()
    # The relative path that will be stored in the database
    relative_dir = Path(str(current_user.user_id)) / str(item_storage_id)
    storage_dir = settings.UPLOADS_DIR / relative_dir

    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / file.filename
    db_storage_path = relative_dir / file.filename

    # 2. Save the file to disk
    try:
        with storage_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    finally:
        file.file.close()

    # 3. Get file size from the saved file
    file_size = storage_path.stat().st_size

    # Provide a default MIME type if one isn't provided
    mime_type = file.content_type if file.content_type else "application/octet-stream"

    # 4. Call the new CRUD function to create both DB records
    try:
        db_item = crud.create_file_with_metadata(
            db=db,
            owner=current_user,  # Pass the user object here
            filename=file.filename,
            parent_id=parent_id,
            mime_type=mime_type,
            size=file_size,
            storage_path=str(db_storage_path),
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
def share_an_item(
    item_id: uuid.UUID,
    share_data: schemas.ShareCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return crud.share_item(
        db=db, item_id=item_id, owner_id=current_user.user_id, share_data=share_data
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
):
    """
    Get current storage usage and limits for the user.
    """
    return {
        "used_storage": current_user.used_storage,
        "storage_quota": current_user.storage_quota,
        "max_file_size": current_user.max_file_size,
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

