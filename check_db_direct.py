import sqlite3
conn = sqlite3.connect('backend/trustshield.db')
cursor = conn.cursor()

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print('Tables:', tables)

# Check users
cursor.execute('SELECT id, email, role FROM users LIMIT 5')
users = cursor.fetchall()
print('Users:', users)

# Check if tenants table has data
cursor.execute('SELECT * FROM tenants LIMIT 5')
tenants = cursor.fetchall()
print('Tenants:', tenants)
