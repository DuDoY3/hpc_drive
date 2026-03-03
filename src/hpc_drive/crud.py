import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, exists, select, union_all
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

    # Validate duplicate folder name explicitly
    if item.item_type == "FOLDER":
        existing_folder = db.query(models.DriveItem).filter(
            models.DriveItem.name == item.name,
            models.DriveItem.parent_id == item.parent_id,
            models.DriveItem.owner_id == owner.user_id,
            models.DriveItem.item_type == "FOLDER",
            models.DriveItem.is_trashed == False
        ).first()

        if existing_folder:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thư mục đã tồn tại. Vui lòng chọn tên khác."
            )

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
        .options(joinedload(models.DriveItem.owner))  # Load owner for username
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
            pydantic_item.owner_username = item.owner.username if item.owner else None
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

    import os
    
    # 0.5 Auto-rename logic for conflicts
    base_name, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    
    while True:
        existing_file = db.query(models.DriveItem).filter(
            models.DriveItem.name == unique_filename,
            models.DriveItem.parent_id == parent_id,
            models.DriveItem.owner_id == owner.user_id,
            models.DriveItem.item_type == ItemType.FILE,
            models.DriveItem.is_trashed == False
        ).first()
        
        if not existing_file:
            break
            
        unique_filename = f"{base_name} ({counter}){ext}"
        counter += 1

    filename = unique_filename

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
    Moves an item (and all its descendants recursively) to the trash.
    Uses CTE for performance. To prevent accidental restoration of previously deleted files,
    only the target folder gets a 'trashed_at' timestamp; children are marked 'is_trashed=True' 
    but keep 'trashed_at=None'.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)

    if db_item.is_trashed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item is already in trash"
        )

    # 1. Collect all descendant IDs using a recursive CTE (Performance Optimized)
    # This avoids the N+1 query problem
    id_alias = select(models.DriveItem.item_id).where(models.DriveItem.item_id == item_id).cte(name="descendants", recursive=True)
    
    # We need to use the alias to join correctly
    joined_alias = select(models.DriveItem.item_id).join(id_alias, models.DriveItem.parent_id == id_alias.c.item_id)
    id_alias = id_alias.union_all(joined_alias)
    
    # Collect all IDs in a single pass
    all_descendant_ids = [r[0] for r in db.execute(select(id_alias.c.item_id)).all()]

    # 2. Mark all descendants as trashed in a single bulk update
    db.query(models.DriveItem).filter(models.DriveItem.item_id.in_(all_descendant_ids)).update(
        {models.DriveItem.is_trashed: True}, synchronize_session=False
    )

    # 3. Explicitly set trashed_at ONLY for the root item being trashed
    # This allows us to distinguish between explicit and implicit deletions during restore
    db_item.trashed_at = datetime.utcnow()

    db.commit()
    db.refresh(db_item)
    return db_item


def restore_item(db: Session, item_id: uuid.UUID, owner_id: int) -> models.DriveItem:
    """
    Restores an item from the trash. 
    Recursively restores children only if they were 'implicitly' trashed (i.e. is_trashed=True but trashed_at=None).
    This ensures that files specifically deleted by the user before their parent folder was deleted remain trashed.
    """
    db_item = get_item_for_owner(db, item_id, owner_id)

    if not db_item.is_trashed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item is not in trash"
        )

    # 1. Collect all descendant IDs
    id_alias = select(models.DriveItem.item_id).where(models.DriveItem.item_id == item_id).cte(name="descendants", recursive=True)
    joined_alias = select(models.DriveItem.item_id).join(id_alias, models.DriveItem.parent_id == id_alias.c.item_id)
    id_alias = id_alias.union_all(joined_alias)
    
    # 2. Bulk restore only the 'implicitly' trashed descendants
    # (Those that have is_trashed=True but trashed_at IS NULL)
    db.query(models.DriveItem).filter(
        models.DriveItem.item_id.in_(select(id_alias.c.item_id)),
        models.DriveItem.is_trashed == True,
        models.DriveItem.trashed_at == None
    ).update(
        {models.DriveItem.is_trashed: False}, synchronize_session=False
    )

    # 3. Explicitly restore the target item
    db_item.is_trashed = False
    db_item.trashed_at = None

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
    print(f"🔍 [SHARE DEBUG] share_item called: item_id={item_id}, owner_id={owner_id}, target_username={share_data.username}, permission={share_data.permission_level}")
    
    db_item = get_item_for_owner(db, item_id, owner_id)
    print(f"🔍 [SHARE DEBUG] Item found: {db_item.name}")
    
    user_to_share_with = get_user_by_username(db, share_data.username)

    if not user_to_share_with:
        print(f"❌ [SHARE DEBUG] User '{share_data.username}' not found in database!")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{share_data.username}' not found",
        )
    
    print(f"🔍 [SHARE DEBUG] Target user found: id={user_to_share_with.user_id}, username={user_to_share_with.username}")

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
        print(f"⚠️ [SHARE DEBUG] Item already shared with {share_data.username}")
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
        print(f"✅ [SHARE DEBUG] Successfully shared {db_item.name} with {share_data.username}")
        return db_share
    except Exception as e:
        db.rollback()
        print(f"❌ [SHARE DEBUG] Failed to commit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to share item: {e}",
        )


def get_shared_with_me_items(db: Session, user_id: int) -> list[models.DriveItem]:
    # DEBUG: Verify user_id
    print(f"🔍 [CRUD DEBUG] get_shared_with_me_items for user_id={user_id}")
    
    results = (
        db.query(models.DriveItem, models.SharePermission.permission_level)
        .join(
            models.SharePermission,
            models.DriveItem.item_id == models.SharePermission.item_id
        )
        .filter(models.SharePermission.shared_with_user_id == user_id)
        .options(joinedload(models.DriveItem.file_metadata))
        .options(joinedload(models.DriveItem.owner))  # Load owner info
        .filter(models.DriveItem.is_trashed == False)
        .all()
    )
    
    print(f"🔍 [CRUD DEBUG] Query returned {len(results)} items")
    
    response_items = []
    for item, permission_level in results:
        # Convert to Pydantic model to ensure transient fields are included
        pydantic_item = schemas.DriveItemResponse.model_validate(item)
        pydantic_item.shared_permission = permission_level
        pydantic_item.is_shared = True
        pydantic_item.owner_username = item.owner.username if item.owner else None
        response_items.append(pydantic_item)
        
        # DEBUG: Log each item
        print(f"  - Item: {item.name}, Owner: {item.owner.username if item.owner else 'N/A'}, Permission: {permission_level}")
        
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
    Tìm kiếm items (của mình hoặc được share).
    Fix lỗi: Join rõ ràng, xử lý case-insensitive tốt hơn.
    """
    
    # 1. Base Query: Avoid duplicates using exists() for sharing check
    base_query = (
        db.query(models.DriveItem)
        .filter(
            # Condition: User is owner OR item is shared with user
            or_(
                models.DriveItem.owner_id == user_id,
                exists().where(
                    models.SharePermission.item_id == models.DriveItem.item_id,
                    models.SharePermission.shared_with_user_id == user_id,
                ),
            ),
            # Condition: Not trashed
            models.DriveItem.is_trashed == False,
        )
        .options(joinedload(models.DriveItem.file_metadata))
    )

    # 2. Filter theo tên (Case-insensitive)
    if query.name:
        # Dùng ilike để tìm không phân biệt hoa thường
        # check if query.name is not empty string
        search_term = f"%{query.name}%"
        base_query = base_query.filter(models.DriveItem.name.ilike(search_term))

    # 3. Filter theo loại item (FILE/FOLDER)
    if query.item_type:
        base_query = base_query.filter(models.DriveItem.item_type == query.item_type)

    # 4. Filter theo MIME TYPE (Chỉ áp dụng cho FILE)
    # Lưu ý: Chỉ join khi thực sự cần thiết để tránh mất Folder nếu không tìm mime_type
    if query.mime_type and query.mime_type.strip():
        base_query = base_query.join(
            models.FileMetadata,
            models.DriveItem.item_id == models.FileMetadata.item_id
        ).filter(
            models.FileMetadata.mime_type.ilike(f"%{query.mime_type}%")
        )

    # 5. Filter theo ngày
    try:
        from datetime import datetime, time
        
        if query.start_date:
            if len(query.start_date) == 10:
                start_date_parsed = datetime.strptime(query.start_date, "%Y-%m-%d").date()
                start_date_full = datetime.combine(start_date_parsed, time.min)
                base_query = base_query.filter(models.DriveItem.created_at >= start_date_full)

        if query.end_date:
            if len(query.end_date) == 10:
                end_date_parsed = datetime.strptime(query.end_date, "%Y-%m-%d").date()
                end_date_full = datetime.combine(end_date_parsed, time.max)
                base_query = base_query.filter(models.DriveItem.created_at <= end_date_full)
    except Exception as e:
        print(f"Date filter parsing error: {e}")
        pass

    # 6. Filter theo is_starred
    if query.is_starred is not None:
        base_query = base_query.filter(models.DriveItem.is_starred == query.is_starred)

    # 7. Distinct và Order
    # Distinct item_id để loại bỏ trùng lặp nếu 1 item được share nhiều lần (dù logic share không cho phép, nhưng an toàn hơn)
    return base_query.distinct().order_by(models.DriveItem.name).all()


def admin_get_all_items(
    db: Session, skip: int = 0, limit: int = 100
) -> list[models.DriveItem]:
    """[Admin] Gets all active (non-trashed) items in God Mode."""
    return (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .options(joinedload(models.DriveItem.owner))
        .filter(models.DriveItem.is_trashed == False) # Exclude trashed files by default
        .order_by(models.DriveItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def toggle_star_item(db: Session, item_id: uuid.UUID, user_id: int) -> models.DriveItem:
    """Toggles the is_starred status of a DriveItem."""
    db_item = get_drive_item(db=db, item_id=item_id, user_id=user_id)
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    db_item.is_starred = not db_item.is_starred
    db.commit()
    db.refresh(db_item)
    return db_item


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


# ===== FILE EDITING FUNCTIONS =====


def check_edit_permission(
    db: Session, item_id: uuid.UUID, user_id: int
) -> tuple[models.DriveItem, bool]:
    """
    Checks if a user can edit a file.
    Returns tuple of (DriveItem, is_owner).
    Raises HTTPException if user doesn't have edit permission.
    """
    db_item = (
        db.query(models.DriveItem)
        .options(joinedload(models.DriveItem.file_metadata))
        .options(joinedload(models.DriveItem.owner))
        .filter(models.DriveItem.item_id == item_id)
        .first()
    )

    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )

    if db_item.item_type != ItemType.FILE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files can be edited"
        )

    if db_item.is_trashed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit trashed items"
        )

    # Check if user is owner
    if db_item.owner_id == user_id:
        return db_item, True

    # Check if file is shared with user with EDITOR permission
    share_permission = (
        db.query(models.SharePermission)
        .filter(
            models.SharePermission.item_id == item_id,
            models.SharePermission.shared_with_user_id == user_id,
        )
        .first()
    )

    if share_permission:
        if share_permission.permission_level == ShareLevel.EDITOR:
            return db_item, False
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You only have viewer permission for this file"
            )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to edit this file"
    )


def update_file_content(
    db: Session,
    item_id: uuid.UUID,
    user_id: int,
    new_content: bytes,
    file_size: int,
) -> models.DriveItem:
    """
    Updates file content with quota checking and version increment.
    Works for both owner and users with EDITOR permission.
    Quota is always updated for the file owner.
    """
    # Check permission
    db_item, is_owner = check_edit_permission(db, item_id, user_id)

    if not db_item.file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File metadata not found"
        )

    # Calculate size difference
    old_size = db_item.file_metadata.size
    delta_size = file_size - old_size

    # QUOTA OVERFLOW CHECK: Only check if file is getting larger
    if delta_size > 0:
        owner = db_item.owner
        current_used = owner.used_storage or 0
        
        # Check if owner has enough quota for the increase
        if current_used + delta_size > owner.storage_quota:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Owner quota exceeded. Need {delta_size / (1024**2):.2f} MB more, but only {(owner.storage_quota - current_used) / (1024**2):.2f} MB available."
            )

    # Write new content to storage
    try:
        storage_path = settings.UPLOADS_DIR / db_item.file_metadata.storage_path
        
        if not storage_path.parent.exists():
            storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        with storage_path.open("wb") as f:
            f.write(new_content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file: {e}"
        )

    # Update database
    try:
        # Update file metadata
        db_item.file_metadata.size = file_size
        db_item.file_metadata.version += 1  # Increment version
        db_item.file_metadata.updated_at = datetime.utcnow()
        
        # Update drive item timestamp
        db_item.updated_at = datetime.utcnow()
        
        # Update owner's storage quota
        owner = db_item.owner
        current_used = owner.used_storage or 0
        owner.used_storage = current_used + delta_size
        
        db.add(db_item)
        db.add(owner)
        db.commit()
        db.refresh(db_item)
        
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update database: {e}"
        )


def save_shared_file_copy(
    db: Session,
    item_id: uuid.UUID,
    user_id: int,
    new_content: bytes,
    file_size: int,
    filename: str,
) -> models.DriveItem:
    """
    Creates a copy of a shared file in user's personal storage.
    The new file belongs to the user who is saving the copy.
    Quota is checked against the user's quota.
    """
    # First check if user has access to the original file
    original_item = get_drive_item(db, item_id, user_id)
    
    if original_item.item_type != ItemType.FILE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files can be copied"
        )
    
    if not original_item.file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File metadata not found"
        )
    
    # Get the user object
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # QUOTA CHECK for the user saving the copy
    if user.role != UserRole.ADMIN:
        if file_size > user.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"File size exceeds your limit of {user.max_file_size / (1024**3):.2f} GB."
            )
        
        current_used = user.used_storage or 0
        if current_used + file_size > user.storage_quota:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your storage quota exceeded. Please delete some files."
            )
    
    # Create new storage path
    item_storage_id = uuid.uuid4()
    relative_dir = Path(str(user_id)) / str(item_storage_id)
    storage_dir = settings.UPLOADS_DIR / relative_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    storage_path = storage_dir / filename
    db_storage_path = relative_dir / filename
    
    # Write content to new location
    try:
        with storage_path.open("wb") as f:
            f.write(new_content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}"
        )
    
    # Create new DriveItem and FileMetadata
    try:
        owner_type = get_owner_type(user.role)
        
        # Create new drive item (in user's root)
        new_item = models.DriveItem(
            name=filename,
            item_type=ItemType.FILE,
            parent_id=None,  # Save to root
            owner_id=user_id,
            owner_type=owner_type,
        )
        db.add(new_item)
        db.flush()
        
        # Create file metadata
        new_metadata = models.FileMetadata(
            item_id=new_item.item_id,
            mime_type=original_item.file_metadata.mime_type,
            size=file_size,
            storage_path=str(db_storage_path),
            version=1,  # New file starts at version 1
        )
        db.add(new_metadata)
        
        # Update user's storage quota
        current_used = user.used_storage or 0
        user.used_storage = current_used + file_size
        db.add(user)
        
        db.commit()
        db.refresh(new_item)
        
        return new_item
    except IntegrityError:
        db.rollback()
        # Cleanup file
        if storage_path.exists():
            storage_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A file with the name '{filename}' already exists in your root directory."
        )
    except Exception as e:
        db.rollback()
        # Cleanup file
        if storage_path.exists():
            storage_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create file copy: {e}"
        )


def copy_file_on_server(
    db: Session,
    item_id: uuid.UUID,
    user_id: int,
    parent_id: uuid.UUID | None = None,
) -> models.DriveItem:
    """
    Copy a shared (or owned) file into user's personal storage
    using shutil.copy2 — disk-level copy, NO RAM loading.
    Safe for files of any size (even 2GB+).
    """
    # 1. Verify the user has access to this item
    original_item = get_drive_item(db, item_id, user_id)

    if original_item.item_type != ItemType.FILE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ có thể sao chép tệp, không phải thư mục.",
        )

    if not original_item.file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy metadata của tệp gốc.",
        )

    # 2. Get the user and check quota
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng.",
        )

    file_size = original_item.file_metadata.size

    if user.role != UserRole.ADMIN:
        if file_size > user.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Kích thước tệp vượt quá giới hạn {user.max_file_size / (1024**3):.2f} GB.",
            )

        current_used = user.used_storage or 0
        if current_used + file_size > user.storage_quota:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dung lượng lưu trữ đã đầy. Hãy xóa bớt tệp.",
            )

    # 3. Resolve source file path
    source_path = settings.UPLOADS_DIR / original_item.file_metadata.storage_path

    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tệp gốc không tồn tại trên ổ đĩa.",
        )

    # 4. Create destination path
    new_storage_id = uuid.uuid4()
    relative_dir = Path(str(user_id)) / str(new_storage_id)
    dest_dir = settings.UPLOADS_DIR / relative_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / original_item.name
    db_storage_path = relative_dir / original_item.name

    # 5. Copy file on disk using shutil.copy2 (preserves metadata, zero RAM)
    try:
        shutil.copy2(str(source_path), str(dest_path))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sao chép tệp: {e}",
        )

    # 6. Create DB records
    try:
        owner_type = get_owner_type(user.role)

        new_item = models.DriveItem(
            name=original_item.name,
            item_type=ItemType.FILE,
            parent_id=parent_id,
            owner_id=user_id,
            owner_type=owner_type,
        )
        db.add(new_item)
        db.flush()

        new_metadata = models.FileMetadata(
            item_id=new_item.item_id,
            mime_type=original_item.file_metadata.mime_type,
            size=file_size,
            storage_path=str(db_storage_path),
            version=1,
        )
        db.add(new_metadata)

        # Update used storage
        user.used_storage = (user.used_storage or 0) + file_size
        db.add(user)

        db.commit()
        db.refresh(new_item)
        return new_item

    except IntegrityError:
        db.rollback()
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tệp '{original_item.name}' đã tồn tại trong thư mục đích.",
        )
    except Exception as e:
        db.rollback()
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tạo bản sao: {e}",
        )


def get_user_storage_breakdown(db: Session, user_id: int) -> dict:
    """
    Calculates the actual storage used by a user, grouped into categories:
    Images, Videos, Documents, and Others.
    """
    # Define common document MIME types
    doc_mimes = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "application/rtf"
    ]

    # Join DriveItem and FileMetadata to sum 'size' grouped by 'mime_type'
    results = (
        db.query(
            models.FileMetadata.mime_type,
            func.sum(models.FileMetadata.size).label("total_size")
        )
        .join(models.DriveItem, models.DriveItem.item_id == models.FileMetadata.item_id)
        .filter(
            models.DriveItem.owner_id == user_id,
            models.DriveItem.is_trashed == False,
            models.DriveItem.item_type == ItemType.FILE
        )
        .group_by(models.FileMetadata.mime_type)
        .all()
    )

    breakdown = {
        "images_storage": 0,
        "videos_storage": 0,
        "documents_storage": 0,
        "others_storage": 0,
    }

    for mime_type, total_size in results:
        size = total_size or 0
        if not mime_type:
            breakdown["others_storage"] += size
        elif mime_type.startswith("image/"):
            breakdown["images_storage"] += size
        elif mime_type.startswith("video/"):
            breakdown["videos_storage"] += size
        elif mime_type in doc_mimes:
            breakdown["documents_storage"] += size
        else:
            breakdown["others_storage"] += size

    return breakdown