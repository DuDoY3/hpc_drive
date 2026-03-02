import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import ItemType, Permission, RepositoryType, ShareLevel, UserRole


class AuthAccount(BaseModel):
    """
    Matches the 'account' object in the /me response
    """

    username: str
    is_admin: bool


class StudentInfo(BaseModel):
    """
    Matches the 'student_info' object
    """

    model_config = ConfigDict(extra="ignore")

    student_code: str


class LecturerInfo(BaseModel):
    """
    Matches the 'lecturer_info' object
    """

    model_config = ConfigDict(extra="ignore")

    lecturer_code: str
    # We only need the fields we plan to use


class UserDataFromAuth(BaseModel):
    """
    Matches the 'data' object in the /me response
    """

    id: int  # This will be our primary key (userId)
    full_name: str
    email: str
    user_type: str  # "student" or "lecturer"
    account: AuthAccount
    student_info: StudentInfo | None = None
    lecturer_info: LecturerInfo | None = None


class AuthMeResponse(BaseModel):
    """
    Matches the top-level structure of the /me response
    """

    message: str
    data: UserDataFromAuth


class FileMetadataResponse(BaseModel):
    """Schema for file-specific metadata"""

    model_config = ConfigDict(from_attributes=True)

    mime_type: str
    size: int
    storage_path: str
    version: int


class DriveItemBase(BaseModel):
    """Base schema for an item (file or folder)"""

    name: str
    item_type: str  # Should be "FILE" or "FOLDER"
    parent_id: uuid.UUID | None = None


class DriveItemCreate(DriveItemBase):
    """Schema used when creating a new item"""

    pass  # Same as base for now


class DriveItemResponse(DriveItemBase):
    """Schema used when returning an item to the user"""

    model_config = ConfigDict(from_attributes=True)

    item_id: uuid.UUID
    owner_id: int
    created_at: datetime
    updated_at: datetime | None = None
    is_trashed: bool
    is_starred: bool = False
    permission: Permission

    # Nested metadata, will be None if it's a folder
    file_metadata: FileMetadataResponse | None = None
    shared_permission: ShareLevel | None = None  # The permission level for the current user (if shared)
    is_shared: bool = False
    owner_username: str | None = None  # Owner's username for shared items
    repository_type: RepositoryType | None = None  # Where the item is stored (PERSONAL/CLASS/DEPARTMENT)
    repository_context_id: int | None = None  # ID of the class or department (if applicable)


class ShareCreate(BaseModel):
    """Schema for creating a new share"""

    # We'll share by username, as it's unique and in our User model
    username: str
    permission_level: ShareLevel = ShareLevel.VIEWER


class UserSimpleResponse(BaseModel):
    """Simplified user schema for share responses"""

    model_config = ConfigDict(from_attributes=True)
    user_id: int
    username: str


class SharePermissionResponse(BaseModel):
    """Schema for displaying a share permission"""

    model_config = ConfigDict(from_attributes=True)

    share_id: uuid.UUID
    item_id: uuid.UUID
    permission_level: ShareLevel
    shared_with_user: UserSimpleResponse  # Show who it's shared with


class DriveItemListResponse(BaseModel):
    """Schema for returning a list of items"""

    parent_id: uuid.UUID | None
    items: list[DriveItemResponse]


class DriveItemUpdate(BaseModel):
    """
    Schema for updating an item.
    All fields are optional.
    """

    name: str | None = None
    parent_id: uuid.UUID | None = None


class DriveItemSearchQuery(BaseModel):
    """
    Schema for search query parameters.
    All fields are optional.
    """

    name: str | None = None  # Search for a name containing this string
    item_type: ItemType | None = None  # Filter by FILE or FOLDER
    mime_type: str | None = None  # Filter by a specific MIME type
    start_date: str | None = None  # ISO format date string (YYYY-MM-DD)
    end_date: str | None = None  # ISO format date string (YYYY-MM-DD)
    is_starred: bool | None = None # Filter by starred status


class UserResponse(BaseModel):
    """Schema for returning user info to an admin"""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    email: str
    role: UserRole
    created_at: datetime
    storage_quota: int
    used_storage: int
    max_file_size: int


class UserQuotaUpdate(BaseModel):
    """Schema for admin to update user storage limits"""

    storage_quota: int | None = None
    max_file_size: int | None = None


class StorageUsageResponse(BaseModel):
    """Schema for current user to see their usage"""

    used_storage: int
    storage_quota: int
    max_file_size: int
    images_storage: int = 0
    documents_storage: int = 0
    videos_storage: int = 0
    others_storage: int = 0