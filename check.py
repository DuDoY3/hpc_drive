import sqlite3
import pprint

try:
    conn = sqlite3.connect('/app/data/drive.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, name, parent_id, repository_type, repository_context_id FROM drive_items WHERE repository_type='CLASS'")
    items = cursor.fetchall()
    print("Found CLASS items:", len(items))
    for row in items:
        print(row)
except Exception as e:
    print("Error:", e)
