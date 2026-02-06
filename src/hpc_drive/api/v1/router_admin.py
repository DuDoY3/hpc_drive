import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from ...database import get_session
from ...models import User
from ...security import get_current_admin_user  # Import the new dependency
from ... import crud, schemas

router = APIRouter(prefix="/admin", tags=["Admin - Drive"])

# We use 'Depends(get_current_admin_user)' on every endpoint
# to lock this router down to admins only.


@router.get("/users", response_model=List[schemas.UserResponse])
def get_all_users(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Get a list of all users in the drive service.
    """
    return crud.admin_get_all_users(db=db)


@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user_details(
    user_id: int,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Get details for a specific user.
    """
    return crud.admin_get_user_by_id(db=db, user_id=user_id)


@router.get("/users/{user_id}/items", response_model=schemas.DriveItemListResponse)
def get_user_drive_items(
    user_id: int,
    parent_id: uuid.UUID | None = None,  # Pass as query parameter
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] List items in a specific user's drive.
    """
    items = crud.admin_get_items_for_user(db=db, user_id=user_id, parent_id=parent_id)
    return {"parent_id": parent_id, "items": items}


@router.get("/drive/items", response_model=List[schemas.DriveItemResponse])
def get_all_items(
    skip: int = 0,
    limit: int = 100,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Get a paginated list of all drive items from all users.
    """
    return crud.admin_get_all_items(db=db, skip=skip, limit=limit)


@router.get("/drive/items/{item_id}", response_model=schemas.DriveItemResponse)
def get_item_by_id(
    item_id: uuid.UUID,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Get the details for any single drive item by its ID.
    """
    return crud.admin_get_item_by_id(db=db, item_id=item_id)


@router.delete("/drive/items/{item_id}", status_code=status.HTTP_200_OK)
def delete_item_permanently(
    item_id: uuid.UUID,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Permanently delete any item. This is irreversible.
    """
    return crud.admin_delete_item_permanently(db=db, item_id=item_id)


@router.patch("/users/{user_id}/quota", response_model=schemas.UserResponse)
def update_user_quota(
    user_id: int,
    quota_data: schemas.UserQuotaUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Update a user's storage quota or max file size limit.
    """
    return crud.admin_update_user_quota(db=db, user_id=user_id, quota_data=quota_data)


@router.post("/users/{user_id}/recalculate-storage", response_model=schemas.UserResponse)
def recalculate_user_storage(
    user_id: int,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_session),
):
    """
    [ADMIN] Manually recalculate the user's used_storage based on existing files.
    """
    return crud.admin_recalculate_user_storage(db=db, user_id=user_id)
