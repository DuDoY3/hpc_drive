import uuid
from pathlib import Path
import shutil
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hpc_drive.main import app
from hpc_drive.database import get_session
from hpc_drive.models import Base, User, DriveItem, FileMetadata, ItemType, OwnerType
from hpc_drive.security import get_current_user
from hpc_drive.config import settings

# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_session():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


def override_get_current_user():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    if not user:
        user = User(
            user_id=1, username="testuser", email="test@example.com", role="STUDENT"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


app.dependency_overrides[get_session] = override_get_session
app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

# --- Test Fixtures ---


def setup_function():
    Base.metadata.create_all(bind=engine)
    # Create a dummy user
    override_get_current_user()


def teardown_function():
    Base.metadata.drop_all(bind=engine)
    # Clean up uploads directory
    upload_dir = settings.UPLOADS_DIR
    if upload_dir.exists():
        shutil.rmtree(upload_dir)


# --- Tests ---


def test_download_file():
    # 1. Create a dummy file and its metadata
    db = TestingSessionLocal()
    user = override_get_current_user()

    # Create a dummy file on disk
    user_upload_dir = settings.UPLOADS_DIR / str(user.user_id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_upload_dir / "test_file.txt"
    with open(file_path, "w") as f:
        f.write("This is a test file.")

    drive_item = DriveItem(
        name="test_file.txt",
        item_type=ItemType.FILE,
        owner_id=user.user_id,
        owner_type=OwnerType.STUDENT,
    )
    db.add(drive_item)
    db.flush()

    file_metadata = FileMetadata(
        item_id=drive_item.item_id,
        mime_type="text/plain",
        size=file_path.stat().st_size,
        storage_path=str(file_path),
    )
    db.add(file_metadata)
    db.commit()
    db.refresh(drive_item)

    # 2. Make a request to the download endpoint
    response = client.get(f"/api/v1/drive/items/{drive_item.item_id}/download")

    # 3. Assert the response
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="test_file.txt"'
    )
    assert response.text == "This is a test file."

    db.close()


def test_trash_already_trashed_item():
    # 1. Create a dummy item
    db = TestingSessionLocal()
    user = override_get_current_user()

    drive_item = DriveItem(
        name="test_folder",
        item_type=ItemType.FOLDER,
        owner_id=user.user_id,
        owner_type=OwnerType.STUDENT,
    )
    db.add(drive_item)
    db.commit()
    db.refresh(drive_item)
    item_id = drive_item.item_id
    db.close()

    # 2. Trash the item
    response = client.patch(f"/api/v1/drive/items/{item_id}/trash")
    assert response.status_code == 200
    data = response.json()
    assert data["is_trashed"] == True

    # 3. Try to trash the item again - Expect success 200 (idempotent)
    response = client.patch(f"/api/v1/drive/items/{item_id}/trash")
    assert response.status_code == 200
    data = response.json()
    assert data["is_trashed"] == True


def test_restore_already_restored_item():
    # 1. Create a dummy item
    db = TestingSessionLocal()
    user = override_get_current_user()

    drive_item = DriveItem(
        name="test_folder_restore",
        item_type=ItemType.FOLDER,
        owner_id=user.user_id,
        owner_type=OwnerType.STUDENT,
    )
    db.add(drive_item)
    db.commit()
    db.refresh(drive_item)
    item_id = drive_item.item_id
    db.close()

    # 2. Try to restore the item (it is not trashed) - Expect success 200 (idempotent)
    response = client.patch(f"/api/v1/drive/items/{item_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["is_trashed"] == False
