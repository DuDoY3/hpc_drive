import uuid
from enum import Enum
from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Boolean,
    BigInteger,
    UniqueConstraint,
    UUID,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase
from sqlalchemy.sql import func


# --- Base Class ---
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# --- Python Enums (Unchanged, as they are classes) ---
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class ItemType(str, Enum):
    FILE = "FILE"
    FOLDER = "FOLDER"


class Permission(str, Enum):
    PRIVATE = "PRIVATE"
    SHARED = "SHARED"


class ShareLevel(str, Enum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"


class DocumentType(str, Enum):
    PDF = "PDF"
    WORD = "WORD"
    EXCEL = "EXCEL"
    POWERPOINT = "POWERPOINT"
    OTHER = "OTHER"


# ===== NEW ENUMS FOR PHASE 1 =====


class RepositoryType(str, Enum):
    """Type of repository where the item is stored."""
    PERSONAL = "PERSONAL"
    CLASS = "CLASS"
    DEPARTMENT = "DEPARTMENT"


class OwnerType(str, Enum):
    """Type of owner for quick permission checks."""
    STUDENT = "STUDENT"
    LECTURER = "LECTURER"
    ADMIN = "ADMIN"


class ProcessStatus(str, Enum):
    """Processing status for malware scanning workflow."""
    PENDING_UPLOAD = "PENDING_UPLOAD"
    SCANNING = "SCANNING"
    SCAN_PENDING = "SCAN_PENDING"
    READY = "READY"
    INFECTED = "INFECTED"
    ERROR = "ERROR"


class SigningStatus(str, Enum):
    """Status of signing request workflow."""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FolderType(str, Enum):
    """Type of folder for special permission handling."""
    NORMAL = "NORMAL"
    SUBMISSION = "SUBMISSION"
    CLASS_INFO = "CLASS_INFO"
    # Future expansion: EXAM_BANK = "EXAM_BANK" (lecturer-only access)



# --- Models (CONVERTED TO SNAKE_CASE) ---


class User(Base):
    """
    Local cache of a user from the Auth Service.
    All attributes are snake_case.
    """

    __tablename__: str = "users"

    # 'sub' from auth service
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Storage Quota Management
    # Default 10GB = 10 * 1024 * 1024 * 1024 bytes
    storage_quota: Mapped[int] = mapped_column(BigInteger, default=10737418240)
    # Total bytes used by non-trashed files
    used_storage: Mapped[int] = mapped_column(BigInteger, default=0)
    # Max size for a single file upload, default 2GB = 2 * 1024 * 1024 * 1024
    max_file_size: Mapped[int] = mapped_column(BigInteger, default=2147483648)

    # ===== NEW FIELDS FOR PHASE 1 =====
    custom_storage_quota_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_unlimited_storage: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relations
    owned_items: Mapped[list["DriveItem"]] = relationship(back_populates="owner")
    shared_with_me: Mapped[list["SharePermission"]] = relationship(
        back_populates="shared_with_user"
    )
    starred_items: Mapped[list["StarredItem"]] = relationship(back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class DriveItem(Base):
    """
    Represents a file or folder in the drive.
    All attributes are snake_case.
    """

    __tablename__: str = "drive_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    item_type: Mapped[ItemType] = mapped_column(SAEnum(ItemType))
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime)
    permission: Mapped[Permission] = mapped_column(
        SAEnum(Permission), default=Permission.PRIVATE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    # ===== NEW FIELDS FOR PHASE 1 =====
    
    # Repository type and context
    repository_type: Mapped[RepositoryType] = mapped_column(
        SAEnum(RepositoryType), default=RepositoryType.PERSONAL
    )
    repository_context_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Owner type for quick permission checks
    owner_type: Mapped[OwnerType] = mapped_column(
        SAEnum(OwnerType), default=OwnerType.STUDENT, server_default="STUDENT"
    )
    
    # Process status for malware scanning
    process_status: Mapped[ProcessStatus] = mapped_column(
        SAEnum(ProcessStatus), default=ProcessStatus.PENDING_UPLOAD
    )
    
    # System-generated folder management
    is_system_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Folder type for special permission handling (SUBMISSION, CLASS_INFO, etc.)
    folder_type: Mapped[FolderType | None] = mapped_column(
        SAEnum(FolderType), nullable=True, default=None
    )

    # Foreign Keys
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("drive_items.item_id", ondelete="SET NULL")
    )

    # Relations
    owner: Mapped["User"] = relationship(back_populates="owned_items")

    parent: Mapped["DriveItem | None"] = relationship(
        back_populates="children", remote_side="DriveItem.item_id"
    )
    children: Mapped[list["DriveItem"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )

    file_metadata: Mapped["FileMetadata | None"] = relationship(
        back_populates="drive_item", cascade="all, delete-orphan"
    )
    share_permissions: Mapped[list["SharePermission"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    starred_by: Mapped[list["StarredItem"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    # Unique constraint (owner_id, parent_id, name)
    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_owner_parent_name"),
    )


class FileMetadata(Base):
    """
    Stores metadata for items of type FILE.
    All attributes are snake_case.
    """

    __tablename__: str = "file_metadata"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drive_items.item_id", ondelete="CASCADE"), primary_key=True
    )

    mime_type: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True)
    document_type: Mapped[DocumentType | None] = mapped_column(SAEnum(DocumentType))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    # Relations
    drive_item: Mapped["DriveItem"] = relationship(back_populates="file_metadata")


class SharePermission(Base):
    """
    Represents the permission granted to a user for a specific DriveItem.
    All attributes are snake_case.
    """

    __tablename__: str = "share_permissions"

    share_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    permission_level: Mapped[ShareLevel] = mapped_column(SAEnum(ShareLevel))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Foreign Keys
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drive_items.item_id", ondelete="CASCADE")
    )
    shared_with_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE")
    )

    # Relations
    item: Mapped["DriveItem"] = relationship(back_populates="share_permissions")
    shared_with_user: Mapped["User"] = relationship(back_populates="shared_with_me")

    # Unique constraint (item_id, shared_with_user_id)
    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("item_id", "shared_with_user_id", name="uq_item_shared_user"),
    )


class SigningRequest(Base):
    """
    Represents a signing request for PDF documents.
    Lecturers create requests, Admins approve/reject.
    All attributes are snake_case.
    """

    __tablename__: str = "signing_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Current status of the signing request
    current_status: Mapped[SigningStatus] = mapped_column(
        SAEnum(SigningStatus), default=SigningStatus.DRAFT
    )
    
    # Admin comment when approving/rejecting
    admin_comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    
    # Path to signed file after approval
    signed_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Foreign Keys
    drive_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drive_items.item_id", ondelete="CASCADE")
    )
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE")
    )
    approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )

    # Relations
    drive_item: Mapped["DriveItem"] = relationship()
    requester: Mapped["User"] = relationship(foreign_keys=[requester_id])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approver_id])


class SystemSetting(Base):
    """
    Global system settings as key-value pairs.
    All attributes are snake_case.
    """
    __tablename__: str = "system_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class StarredItem(Base):
    """
    Junction table for user-specific starring of items.
    """

    __tablename__: str = "starred_items"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drive_items.item_id", ondelete="CASCADE"), primary_key=True
    )

    # Relations (Optional but helpful)
    user: Mapped["User"] = relationship(back_populates="starred_items")
    item: Mapped["DriveItem"] = relationship(back_populates="starred_by")


class Notification(Base):
    """
    Stores system and admin notifications for users.
    """
    __tablename__: str = "notifications"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    
    # Type of notification (e.g., 'QUOTA_CHANGE', 'FILE_DELETED', 'SYSTEM_UPDATE')
    type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(1000))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relations
    user: Mapped["User"] = relationship(back_populates="notifications")