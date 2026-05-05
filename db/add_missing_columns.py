"""Add missing columns to Firebird PROJECT_STATE table."""
import fdb
from dotenv import load_dotenv
import os

load_dotenv()

DSN = r"C:\Users\santosh Arsid\YOURDB2.fdb"
USER = "SYSDBA"
PASSWORD = "gorillagear"

# Columns to add (based on state dict keys from streamlit_app.py)
COLUMNS_TO_ADD = {
    "DATASET_NAME": "VARCHAR(500)",
    "CURRENT_STEP": "VARCHAR(50)",
    "ERRORS": "BLOB SUB_TYPE TEXT",
    "EDA_PLAN": "BLOB SUB_TYPE TEXT",
    "EDA_PLAN_APPROVED": "INTEGER DEFAULT 0",
    "EDA_PLAN_FEEDBACK": "BLOB SUB_TYPE TEXT",
    "EDA_APPROVED": "INTEGER DEFAULT 0",
    "EDA_FEEDBACK": "BLOB SUB_TYPE TEXT",
    "PINNED_PROJECTS": "BLOB SUB_TYPE TEXT",
    "SELECTED_SUGGESTION": "INTEGER",
    "STAGE": "VARCHAR(50)",
    # Human-in-loop approval columns
    "APPROVAL_MODE": "VARCHAR(50) DEFAULT 'auto'",
    "AGENT_APPROVALS": "BLOB SUB_TYPE TEXT",
    "CLEANED_DATA_PATH": "VARCHAR(500)",
    "ENGINEERED_DATA_PATH": "VARCHAR(500)",
    "LLM_EDA_ANALYSIS": "BLOB SUB_TYPE TEXT",
    "TASK_TYPE": "VARCHAR(50)",
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
for col in existing:
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
