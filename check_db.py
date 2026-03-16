import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from hpc_drive.database import SessionLocal, engine
from hpc_drive import models
from sqlalchemy import inspect

def check_notifications():
    print("Checking database tables...")
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables found: {tables}")
    
    if 'notifications' in tables:
        print("Table 'notifications' exists.")
    else:
        print("Table 'notifications' DOES NOT exist!")
        return

    db = SessionLocal()
    try:
        count = db.query(models.Notification).count()
        print(f"Total notifications in DB: {count}")
        
        if count > 0:
            latest = db.query(models.Notification).order_by(models.Notification.created_at.desc()).limit(5).all()
            for n in latest:
                print(f"ID: {n.notification_id}, Type: {n.type}, UserID: {n.user_id}, Message: {n.message}, Read: {n.is_read}")
    except Exception as e:
        print(f"Error checking contents: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_notifications()
