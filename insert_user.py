"""Insert a user directly into the SQLite DB."""
import sqlite3
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash("Test123!")

conn = sqlite3.connect(r"C:\Users\dell\OneDrive\Desktop\TrustShield\backend\trustshield.db")
cur = conn.cursor()

try:
    cur.execute(
        """INSERT INTO users (email, hashed_password, full_name, role, is_active, token_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, 1, datetime('now'), datetime('now'))""",
        ("directuser@test.com", hashed, "Direct User", "analyst"),
    )
    conn.commit()
    print("User created successfully")
except Exception as e:
    print(f"Error creating user: {e}")

cur.execute("SELECT id, email, full_name, role, tenant_id FROM users")
users = cur.fetchall()
for u in users:
    print(f"  id={u[0]}, email={u[1]}, name={u[2]}, role={u[3]}, tenant_id={u[4]}")
conn.close()
