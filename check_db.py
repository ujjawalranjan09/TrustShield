import sqlite3

conn = sqlite3.connect('C:/Users/dell/OneDrive/Desktop/TrustShield/backend/trustshield.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Check if specific tables exist
required_tables = ['flagged_entities', 'entity_reports', 'intel_shared_entities', 'feedback_labels']
for table in required_tables:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
    exists = cursor.fetchone()
    print(f"{table}: {'EXISTS' if exists else 'MISSING'}")

conn.close()
