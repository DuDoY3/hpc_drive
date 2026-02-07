import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .config import settings
from .models import ItemType, OwnerType, Permission, ShareLevel, UserRole


def get_owner_type(role: UserRole) -> OwnerType:
    if role == UserRole.ADMIN:
        return OwnerType.ADMIN
    if role == UserRole.TEACHER:
        return OwnerType.LECTURER
    return OwnerType.STUDENT


def create_drive_item(
    db: Session, item: schemas.DriveItemCreate, owner: models.User
) -> models.DriveItem:
    """
    Creates a new DriveItem (FILE or FOLDER) in the database.
    Requires the full owner object to determine owner_type.
    """
    owner_type = get_owner_type(owner.role)

    # Create the new item instance
    db_item = models.DriveItem(
        name=item.name,
        item_type=item.item_type,
        parent_id=item.parent_id,
        owner_id=owner.user_id,
        owner_type=owner_type,
    )

    db.add(db_item)

    try:
        db.commit()
        db.refresh(db_item)
        return db_item
    except IntegrityError as e:
        db.rollback()
        print(f"Database integrity error: {e}")
        # This catches our unique constraint (uq_owner_parent_name)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with the name '{item.name}' already exists in this folder.",
        )


def get_user_items_in_folder(
    db: Session, owner_id: int, parent_id: uuid.UUID | None
) -> list[models.DriveItem]:
    """
    Gets all non-trashed items for a specific user within a specific folder.
    If parent_id is None, it fetches items from the user's root.
    """
    if parent_id is None:
        return (
            db.query(models.DriveItem)
            .options(joinedload(models.DriveItem.file_metadata))
            .filter(
                models.DriveItem.owner_id == owner_id,
                models.DriveItem.parent_id == None,
                models.DriveItem.is_trashed == False,
            )
            .order_by(models.DriveItem.item_type, models.DriveItem.name)
            .all()
        )

    # Check access to the parent folder
    parent_item = db.query(models.DriveItem).filter(models.DriveItem.item_id == parent_id).first()
    if not parent_item:
        return []

    has_access = False
    if parent_item.owner_id == owner_id:
        has_access = True
    else:
        # Check if shared
        share_entry = (
            db.query(models.SharePermission)
            .filter(
                models.SharePermission.item_id == parent_id,
                models.SharePermission.shared_with_user_id == owner_id
            )
            .first()
        )
        if share_entry:
            has_access = True
    
    if not has_access:
        return []

    # If has access, return all items in that folder
    items = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.parent_id == parent_id,
            models.DriveItem.is_trashed == False,
        )
        .order_by(models.DriveItem.item_type, models.DriveItem.name)
        .all()
    )

    # If it was a shared access, propagate the shared status and permission to children
    share_entry = None
    if parent_item.owner_id != owner_id:
         share_entry = (
            db.query(models.SharePermission)
            .filter(
                models.SharePermission.item_id == parent_id,
                models.SharePermission.shared_with_user_id == owner_id
            )
            .first()
        )

    if share_entry:
        response_items = []
        for item in items:
            pydantic_item = schemas.DriveItemResponse.model_validate(item)
            pydantic_item.is_shared = True
            pydantic_item.shared_permission = share_entry.permission_level
            response_items.append(pydantic_item)
        return response_items

    return items


def create_file_with_metadata(
    db: Session,
    owner: models.User,
    filename: str,
    parent_id: uuid.UUID | None,
    mime_type: str,
    size: int,
    storage_path: str,
) -> models.DriveItem:
    """
    Atomically creates a DriveItem (as FILE) and its FileMetadata.
    Requires the full owner object to determine owner_type.
    """

    owner_type = get_owner_type(owner.role)
    
    # 0. Quota Validation
    # Skip checks for ADMIN? User said "sinh viên và giáo viên", but usually quota applies to all non-admins.
    if owner.role != UserRole.ADMIN:
        if size > owner.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"File size exceeds the limit of {owner.max_file_size / (1024**3):.2f} GB. Please contact an admin for larger uploads."
            )
        
        if (owner.used_storage or 0) + size > owner.storage_quota:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Storage quota exceeded. Please delete some files or contact an admin to increase your quota."
            )

    # 1. Create the DriveItem
    db_item = models.DriveItem(
        name=filename,
        item_type=ItemType.FILE,
        parent_id=parent_id,
        owner_id=owner.user_id,
        owner_type=owner_type,
    )
    db.add(db_item)

    try:
        # We flush to get the db_item.item_id assigned by the DB
        db.flush()

        # 2. Create the FileMetadata using the new item_id
        db_metadata = models.FileMetadata(
            item_id=db_item.item_id,
            mime_type=mime_type,
            size=size,
            storage_path=storage_path,
        )
        db.add(db_metadata)

        # 2b. Update User Storage Usage
        # Handle possible None if column was existing and not initialized
        current_used = owner.used_storage or 0
        owner.used_storage = current_used + size
        db.add(owner)

        # 3. Commit both records at once
        db.commit()
        db.refresh(db_item)
        return db_item

        db.refresh(db_item)
        # We need to refresh the metadata relation as well
        db.refresh(db_item, ["file_metadata"])
        return db_item

    except IntegrityError:
        db.rollback()
        # This catches our unique constraint (uq_owner_parent_name)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A file with the name '{filename}' already exists in this folder.",
        )
    except Exception as e:
        db.rollback()
        # Handle other potential errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while creating the file: {e}",
        )


def get_item_for_owner(
    db: Session, item_id: uuid.UUID, owner_id: int
) -> models.DriveItem:
    """
    A helper to get an item IF the user is the owner.
    This is the base for most update/delete operations.
    """
    db_item = (
        db.query(models.DriveItem)
        .filter(
            models.DriveItem.item_id == item_id,
            models.DriveItem.owner_id == owner_id,
        )
        .first()
    )

    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or you do not have permission",
        )
    return db_item


def trash_item(db: Session, item_id: uuid.UUID, owner_id: int) -> models.DriveItem:
    """
    Moves an item (and its children, if a folder) to the trash.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)

    if db_item.is_trashed:
        return db_item

    db_item.is_trashed = True
    db_item.trashed_at = datetime.utcnow()

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def restore_item(db: Session, item_id: uuid.UUID, owner_id: int) -> models.DriveItem:
    """
    Restores an item from the trash.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)

    if not db_item.is_trashed:
        return db_item

    db_item.is_trashed = False
    db_item.trashed_at = None

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_user_trash(db: Session, owner_id: int) -> list[models.DriveItem]:
    """
    Gets all items for a user that are currently in the trash.
    """
    return (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.owner_id == owner_id, models.DriveItem.is_trashed == True
        )
        .order_by(models.DriveItem.trashed_at.desc())
        .all()
    )


def check_for_name_conflict(
    db: Session,
    owner_id: int,
    parent_id: uuid.UUID | None,
    name: str,
    exclude_item_id: uuid.UUID | None = None,
):
    """
    Helper function to check for unique constraint violations before committing.
    """
    query = db.query(models.DriveItem).filter(
        models.DriveItem.owner_id == owner_id,
        models.DriveItem.parent_id == parent_id,
        models.DriveItem.name == name,
    )

    if exclude_item_id:
        # Exclude the item itself when checking (e.g., just changing parent_id)
        query = query.filter(models.DriveItem.item_id != exclude_item_id)

    if query.first():
        # A conflict exists
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with the name '{name}' already exists in this folder.",
        )


def update_drive_item(
    db: Session, item_id: uuid.UUID, owner_id: int, update_data: schemas.DriveItemUpdate
) -> models.DriveItem:
    """
    Updates a DriveItem's name or parent folder.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)

    if update_data.name is None and update_data.parent_id is None:
        return db_item

    new_name = update_data.name if update_data.name is not None else db_item.name
    new_parent_id = (
        update_data.parent_id
        if update_data.parent_id is not None
        else db_item.parent_id
    )

    if new_name == db_item.name and new_parent_id == db_item.parent_id:
        return db_item

    check_for_name_conflict(
        db=db,
        owner_id=owner_id,
        parent_id=new_parent_id,
        name=new_name,
        exclude_item_id=item_id,
    )

    if update_data.name is not None:
        db_item.name = update_data.name

    if update_data.parent_id is not None:
        db_item.parent_id = update_data.parent_id

    db_item.updated_at = datetime.utcnow()

    try:
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with the name '{new_name}' already exists in this folder.",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e}",
        )


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def share_item(
    db: Session, item_id: uuid.UUID, owner_id: int, share_data: schemas.ShareCreate
) -> models.SharePermission:
    """
    Shares an item with another user.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)
    user_to_share_with = get_user_by_username(db, share_data.username)

    if not user_to_share_with:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{share_data.username}' not found",
        )

    if user_to_share_with.user_id == owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot share an item with yourself",
        )

    existing_share = (
        db.query(models.SharePermission)
        .filter(
            models.SharePermission.item_id == item_id,
            models.SharePermission.shared_with_user_id == user_to_share_with.user_id,
        )
        .first()
    )

    if existing_share:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item is already shared with {share_data.username}",
        )

    db_share = models.SharePermission(
        item_id=item_id,
        shared_with_user_id=user_to_share_with.user_id,
        permission_level=share_data.permission_level,
    )

    db_item.permission = Permission.SHARED

    try:
        db.add(db_share)
        db.add(db_item)
        db.commit()
        db.refresh(db_share)
        return db_share
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to share item: {e}",
        )


def get_shared_with_me_items(db: Session, user_id: int) -> list[models.DriveItem]:
    results = (
        db.query(models.DriveItem, models.SharePermission.permission_level)
        .join(models.SharePermission)
        .filter(models.SharePermission.shared_with_user_id == user_id)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(models.DriveItem.is_trashed == False)
        .all()
    )
    
    response_items = []
    for item, permission_level in results:
        # Convert to Pydantic model to ensure transient fields are included
        pydantic_item = schemas.DriveItemResponse.model_validate(item)
        pydantic_item.shared_permission = permission_level
        pydantic_item.is_shared = True
        response_items.append(pydantic_item)
        
    return response_items


def get_drive_item(
    db: Session,
    item_id: uuid.UUID,
    user_id: int,
) -> models.DriveItem:
    """
    Gets a single drive item.
    """
    db_item = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(models.DriveItem.item_id == item_id)
        .first()
    )

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if db_item.is_trashed and db_item.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Item not found")

    if db_item.owner_id == user_id:
        return db_item

    is_shared_with_user = (
        db.query(models.SharePermission)
        .filter(
            models.SharePermission.item_id == item_id,
            models.SharePermission.shared_with_user_id == user_id,
        )
        .first()
    )

    if is_shared_with_user:
        return db_item

    raise HTTPException(
        status_code=403, detail="You do not have permission to access this item"
    )


def search_items(
    db: Session, user_id: int, query: schemas.DriveItemSearchQuery
) -> list[models.DriveItem]:
    """
    Searches for items across owned and shared items.
    """
    base_query = (
        db.query(models.DriveItem)
        .outerjoin(models.SharePermission)
        .filter(
            or_(
                models.DriveItem.owner_id == user_id,
                models.SharePermission.shared_with_user_id == user_id,
            ),
            models.DriveItem.is_trashed == False,
        )
        .options(joinedload(models.DriveItem.file_metadata))
        .distinct()
    )

    if query.name:
        base_query = base_query.filter(models.DriveItem.name.ilike(f"%{query.name}%"))

    if query.item_type:
        base_query = base_query.filter(models.DriveItem.item_type == query.item_type)

    if query.mime_type:
        base_query = base_query.join(models.FileMetadata).filter(
            models.FileMetadata.mime_type.ilike(f"%{query.mime_type}%")
        )

    if query.start_date:
        base_query = base_query.filter(models.DriveItem.created_at >= query.start_date)

    if query.end_date:
        base_query = base_query.filter(models.DriveItem.created_at <= query.end_date)

    return base_query.order_by(models.DriveItem.name).all()


def admin_get_all_items(
    db: Session, skip: int = 0, limit: int = 100
) -> list[models.DriveItem]:
    return (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .order_by(models.DriveItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def admin_get_item_by_id(db: Session, item_id: uuid.UUID) -> models.DriveItem:
    db_item = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(models.DriveItem.item_id == item_id)
        .first()
    )

    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )
    return db_item


def admin_delete_item_permanently(db: Session, item_id: uuid.UUID):
    db_item = admin_get_item_by_id(db, item_id)
    try:
        db.delete(db_item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete item: {e}",
        )
    return {"detail": "Item deleted permanently"}


def get_trashed_item_for_owner(
    db: Session, item_id: uuid.UUID, owner_id: int
) -> models.DriveItem:
    db_item = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.item_id == item_id,
            models.DriveItem.owner_id == owner_id,
            models.DriveItem.is_trashed == True,
        )
        .first()
    )

    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in trash or you do not have permission",
        )
    return db_item


def delete_item_permanently(db: Session, item_id: uuid.UUID, owner_id: int):
    db_item = get_trashed_item_for_owner(db, item_id, owner_id)

    if db_item.item_type == ItemType.FILE and db_item.file_metadata:
        _delete_file_from_storage(db_item.file_metadata.storage_path)

    if db_item.item_type == ItemType.FOLDER:
        item_queue = [db_item]
        items_to_check = []

        while item_queue:
            current_item = item_queue.pop(0)
            items_to_check.append(current_item)

            if current_item.item_type == ItemType.FOLDER:
                children = (
                    db.query(models.DriveItem)
                    .options(joinedload(models.DriveItem.file_metadata))
                    .filter(models.DriveItem.parent_id == current_item.item_id)
                    .all()
                )
                item_queue.extend(children)

        for item in items_to_check:
            if item.item_type == ItemType.FILE and item.file_metadata:
                _delete_file_from_storage(item.file_metadata.storage_path)

    # Calculate total size to subtract from user usage
    total_size_deleted = 0
    if db_item.item_type == ItemType.FILE and db_item.file_metadata:
        total_size_deleted = db_item.file_metadata.size
    elif db_item.item_type == ItemType.FOLDER:
        # Re-using the same search/logic but counting size
        item_queue = [db_item]
        while item_queue:
            curr = item_queue.pop(0)
            if curr.item_type == ItemType.FILE and curr.file_metadata:
                total_size_deleted += curr.file_metadata.size
            if curr.item_type == ItemType.FOLDER:
                children = db.query(models.DriveItem).filter(models.DriveItem.parent_id == curr.item_id).all()
                item_queue.extend(children)

    try:
        # Decrement usage
        owner = db.get(models.User, owner_id)
        if owner:
            current_used = owner.used_storage or 0
            owner.used_storage = max(0, current_used - total_size_deleted)
            db.add(owner)
        
        db.delete(db_item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete item: {e}",
        )


def empty_user_trash(db: Session, owner_id: int):
    all_trashed_items = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.owner_id == owner_id,
            models.DriveItem.is_trashed == True,
        )
        .all()
    )

    if not all_trashed_items:
        return

    for item in all_trashed_items:
        if item.item_type == ItemType.FILE and item.file_metadata:
            _delete_file_from_storage(item.file_metadata.storage_path)

    top_level_trashed_items = [
        item
        for item in all_trashed_items
        if item.parent_id is None or (item.parent and not item.parent.is_trashed)
    ]

    # Calculate total size to subtract
    total_size_deleted = 0
    
    # helper for recursive size
    def get_folder_size(folder_id):
        size = 0
        items = db.query(models.DriveItem).filter(models.DriveItem.parent_id == folder_id).all()
        for it in items:
            if it.item_type == ItemType.FILE and it.file_metadata:
                size += it.file_metadata.size
            elif it.item_type == ItemType.FOLDER:
                size += get_folder_size(it.item_id)
        return size

    for item in all_trashed_items:
        if item.item_type == ItemType.FILE and item.file_metadata:
            total_size_deleted += item.file_metadata.size
        elif item.item_type == ItemType.FOLDER:
            # We only count folders that are directly in the trash (not children of trashed folders)
            # to avoid double counting if children also have is_trashed=True (though usually they don't)
            if item in top_level_trashed_items:
                total_size_deleted += get_folder_size(item.item_id)
    
    try:
        owner = db.get(models.User, owner_id)
        if owner:
            current_used = owner.used_storage or 0
            owner.used_storage = max(0, current_used - total_size_deleted)
            db.add(owner)

        for item in top_level_trashed_items:
            db.delete(item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to empty trash: {e}",
        )


def admin_get_all_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


def admin_get_user_by_id(db: Session, user_id: int) -> models.User:
    db_user = db.get(models.User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return db_user


def admin_get_items_for_user(
    db: Session, user_id: int, parent_id: uuid.UUID | None
) -> list[models.DriveItem]:
    admin_get_user_by_id(db, user_id)
    return (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.owner_id == user_id,
            models.DriveItem.parent_id == parent_id,
            models.DriveItem.is_trashed == False,
        )
        .order_by(models.DriveItem.item_type, models.DriveItem.name)
        .all()
    )


def get_items_in_folder_admin_view(
    db: Session, parent_id: uuid.UUID
) -> List[models.DriveItem]:
    """Lấy tất cả file trong folder mà không check ai là người tạo"""
    return (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .filter(
            models.DriveItem.parent_id == parent_id,
            models.DriveItem.is_trashed == False,
        )
        .all()
    )


def _delete_file_from_storage(storage_path: str | None):
    if not storage_path:
        return

    try:
        full_file_path = settings.UPLOADS_DIR / storage_path
        if full_file_path.is_file():
            full_file_path.unlink()
            try:
                full_file_path.parent.rmdir()
            except OSError:
                pass
    except Exception as e:
        print(f"Error deleting file {storage_path} from disk: {e}")


def admin_update_user_quota(
    db: Session, user_id: int, quota_data: schemas.UserQuotaUpdate
) -> models.User:
    db_user = admin_get_user_by_id(db, user_id)
    
    if quota_data.storage_quota is not None:
        db_user.storage_quota = quota_data.storage_quota
    
    if quota_data.max_file_size is not None:
        db_user.max_file_size = quota_data.max_file_size
        
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def admin_recalculate_user_storage(db: Session, user_id: int) -> models.User:
    """
    Recalculate used_storage for a user by summing up all non-trashed files.
    """
    user = admin_get_user_by_id(db, user_id)
    
    # Sum of all files owned by user that are NOT in trash
    total_size = (
        db.query(func.sum(models.FileMetadata.size))
        .join(models.DriveItem, models.DriveItem.item_id == models.FileMetadata.item_id)
        .filter(models.DriveItem.owner_id == user_id)
        .filter(models.DriveItem.is_trashed == False)
        .scalar()
    ) or 0
    
    user.used_storage = total_size
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
