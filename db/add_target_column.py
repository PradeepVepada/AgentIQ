"""Add missing TARGET_COLUMN to PROJECT_STATE table."""
import fdb
from dotenv import load_dotenv
import os

load_dotenv()

DSN = r"C:\Users\santosh Arsid\YOURDB2.fdb"
USER = "SYSDBA"
PASSWORD = "gorillagear"

conn = fdb.connect(dsn=DSN, user=USER, password=PASSWORD)
cur = conn.cursor()

# Check if TARGET_COLUMN exists
cur.execute(
    "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
    "WHERE RDB$RELATION_NAME = 'PROJECT_STATE'"
)
existing = [row[0].strip() for row in cur.fetchall()]

if "TARGET_COLUMN" not in existing:
    try:
        cur.execute("ALTER TABLE PROJECT_STATE ADD TARGET_COLUMN VARCHAR(500)")
        conn.commit()
        print("[OK] Added TARGET_COLUMN")
    except Exception as e:
        print(f"[ERR] {e}")
else:
    print("[--] TARGET_COLUMN already exists")

conn.close()
print("Done!")
