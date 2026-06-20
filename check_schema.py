import sqlite3
conn = sqlite3.connect('backend/trustshield.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%session%'")
for row in cursor.fetchall():
    print('Table:', row)
cursor.execute('PRAGMA table_info(revoked_sessions)')
for col in cursor.fetchall():
    print('Col:', col)
