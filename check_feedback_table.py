import sqlite3

conn = sqlite3.connect('C:/Users/dell/OneDrive/Desktop/TrustShield/backend/trustshield.db')
cursor = conn.cursor()

# Get the schema of feedback_labels table
cursor.execute("PRAGMA table_info(feedback_labels)")
columns = cursor.fetchall()
print("feedback_labels table schema:")
for col in columns:
    print(f"  {col}")

conn.close()
