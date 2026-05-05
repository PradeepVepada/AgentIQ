"""Add PROBLEM_TYPE and other missing columns to PROJECT_STATE table."""
import fdb
from dotenv import load_dotenv
import os

load_dotenv()

DSN = r"C:\Users\santosh Arsid\YOURDB2.fdb"
USER = "SYSDBA"
PASSWORD = "gorillagear"

# All possible columns from state dict keys (converted to uppercase)
COLUMNS_TO_ADD = {
    "PROBLEM_TYPE": "VARCHAR(50)",
    "PINNED_PROJECTS": "BLOB SUB_TYPE TEXT",  # JSON list
    "SELECTED_SUGGESTION": "INTEGER",
    "STAGE": "VARCHAR(50)",
}

conn = fdb.connect(dsn=DSN, user=USER, password=PASSWORD)
cur = conn.cursor()

# Get existing columns
cur.execute(
    "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
    "WHERE RDB$RELATION_NAME = 'PROJECT_STATE'"
)
existing = [row[0].strip() for row in cur.fetchall()]

print("Existing columns:")
for col in sorted(existing):
    print(f"  - {col}")

print("\nAdding missing columns...")
for col_name, col_type in COLUMNS_TO_ADD.items():
    if col_name not in existing:
        try:
            cur.execute(f"ALTER TABLE PROJECT_STATE ADD {col_name} {col_type}")
            print(f"  [OK] Added {col_name}")
        except Exception as e:
            print(f"  [ERR] {col_name}: {e}")
    else:
        print(f"  [--] {col_name} already exists")

conn.commit()
conn.close()
print("\nDone!")
