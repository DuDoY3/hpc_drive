import sqlite3
import uuid

conn = sqlite3.connect('/app/data/hpc_drive.db')
c = conn.cursor()
c.execute("SELECT item_id, name, parent_id, item_type FROM drive_items WHERE repository_context_id=1")
rows = c.fetchall()
for r in rows:
    print(r)
conn.close()
