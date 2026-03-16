import sqlite3
import os

db_path = "/home/dudo/hpc_root/hpc_drive/drive.db"
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM drive_items")
    items_count = cursor.fetchone()[0]
    print(f"Users: {users_count}")
    print(f"Items: {items_count}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
