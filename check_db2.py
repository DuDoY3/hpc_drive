import sqlite3

with open('/app/db_output.txt', 'w') as f:
    conn = sqlite3.connect('/app/data/hpc_drive.db')
    c = conn.cursor()
    c.execute("SELECT item_id, name, parent_id, item_type FROM drive_items WHERE repository_context_id=1")
    rows = c.fetchall()
    for r in rows:
        f.write(str(r) + '\n')
    conn.close()
