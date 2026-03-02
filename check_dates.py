import sqlite3

conn = sqlite3.connect("drive.db")
cursor = conn.cursor()

# Get recent items
cursor.execute("SELECT name, created_at FROM drive_items ORDER BY created_at DESC LIMIT 5")
rows = cursor.fetchall()
for row in rows:
    print(f"Name: {row[0]}, created_at: {row[1]} (type: {type(row[1])})")

conn.close()
