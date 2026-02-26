import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from hpc_drive.database import SessionLocal
from hpc_drive.models import DriveItem, RepositoryType
def cleanup():
    session = SessionLocal()
    items = session.query(DriveItem).filter(
        DriveItem.repository_type == RepositoryType.CLASS
    ).all()
    print("Deleting CLASS items:", len(items))
    for item in items:
        session.delete(item)
    session.commit()
    print("Cleanup done.")
    session.close()

if __name__ == "__main__":
    cleanup()
