import sys
import uuid
import os
import argparse

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from hpc_drive.database import SessionLocal, engine
from hpc_drive.models import DriveItem, RepositoryType, ProcessStatus

def test_insert():
    session = SessionLocal()
    print("Testing insert...")
    new_item = DriveItem(
        item_id=uuid.uuid4(),
        name="TEST_CLASS_ROOT",
        item_type="FOLDER",
        repository_type=RepositoryType.CLASS,
        repository_context_id=1,
        owner_id=6,
        owner_type="LECTURER",
        parent_id=None,
        is_system_generated=True,
        is_locked=True,
        process_status=ProcessStatus.READY
    )
    try:
        session.add(new_item)
        session.commit()
        print("Success inserted DriveItem", new_item.item_id)
    except Exception as e:
        session.rollback()
        print("Exception:", e)
    finally:
        session.close()

if __name__ == "__main__":
    test_insert()
