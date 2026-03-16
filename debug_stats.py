from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
import os
import sys

# Add the project root to sys.path
sys.path.append('//wsl.localhost/Ubuntu-22.04/home/dudo/hpc_root/hpc_drive/src')

from hpc_drive import models, crud
from hpc_drive.database import SessionLocal

def test_admin_stats():
    db = SessionLocal()
    try:
        items, total, file_count, folder_count, total_size = crud.admin_get_all_items(db)
        print(f"Total: {total}")
        print(f"Files: {file_count}")
        print(f"Folders: {folder_count}")
        print(f"Total Size: {total_size}")
        
        # Test individual counts
        real_files = db.query(models.DriveItem).filter(models.DriveItem.item_type == 'FILE', models.DriveItem.is_trashed == False).count()
        real_folders = db.query(models.DriveItem).filter(models.DriveItem.item_type == 'FOLDER', models.DriveItem.is_trashed == False).count()
        print(f"Real Files: {real_files}")
        print(f"Real Folders: {real_folders}")
        
    finally:
        db.close()

if __name__ == "__main__":
    test_admin_stats()
