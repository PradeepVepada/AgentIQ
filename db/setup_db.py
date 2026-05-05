"""One-time Firebird schema setup for AgentIQ.

Run this once:
    python -m db.setup_db

It is idempotent — skips creation if tables already exist.
"""
from __future__ import annotations

import fdb
import os
from dotenv import load_dotenv

load_dotenv()

DSN = os.getenv("FIREBIRD_DSN", r"C:\Users\santosh Arsid\YOURDB2.fdb")
USER = os.getenv("FIREBIRD_USER", "SYSDBA")
PASSWORD = os.getenv("FIREBIRD_PASSWORD", "gorillagear")

DDL_STATEMENTS = [
    # ── Sequences ────────────────────────────────────────────────────────────
    "CREATE SEQUENCE project_state_seq",
    "CREATE SEQUENCE agent_reports_seq",

    # ── project_state ────────────────────────────────────────────────────────
    """
    CREATE TABLE PROJECT_STATE (
        ID               INTEGER        NOT NULL PRIMARY KEY,
        PROJECT_ID       VARCHAR(36)    NOT NULL UNIQUE,
        PROJECT_GOAL     VARCHAR(500),
        DATASET_PATH     VARCHAR(500),

        EDA_REPORT       BLOB SUB_TYPE TEXT,
        LLM_EDA_ANALYSIS BLOB SUB_TYPE TEXT,
        CLEANING_PLAN    BLOB SUB_TYPE TEXT,
        CLEANING_REPORT  BLOB SUB_TYPE TEXT,

        CURRENT_AGENT_ID INTEGER        DEFAULT 1,
        APPROVAL_STATUS  VARCHAR(50)    DEFAULT 'pending',
        HUMAN_FEEDBACK   BLOB SUB_TYPE TEXT,
        THREAD_ID        VARCHAR(100),

        FEATURE_ENGINEERING_PLAN BLOB SUB_TYPE TEXT,
        SELECTED_FEATURES       BLOB SUB_TYPE TEXT,
        SCALING_REQUIREMENTS    BLOB SUB_TYPE TEXT,
        ENGINEERED_DATA_PATH    VARCHAR(500),

        SPLIT_STRATEGY   BLOB SUB_TYPE TEXT,
        CANDIDATE_MODELS BLOB SUB_TYPE TEXT,
        TRAIN_IDX_PATH   VARCHAR(500),
        TEST_IDX_PATH    VARCHAR(500),
        TASK_TYPE        VARCHAR(50),

        TRAINING_RESULTS BLOB SUB_TYPE TEXT,
        TUNING_RESULTS   BLOB SUB_TYPE TEXT,

        EVALUATION_REPORT BLOB SUB_TYPE TEXT,

        RETRY_COUNT      INTEGER        DEFAULT 0,
        LANGSMITH_TRACE_ID VARCHAR(255),

        CREATED_AT       TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
        UPDATED_AT       TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── agent_reports ────────────────────────────────────────────────────────
    """
    CREATE TABLE AGENT_REPORTS (
        ID                 INTEGER      NOT NULL PRIMARY KEY,
        PROJECT_ID         VARCHAR(36)  NOT NULL,
        AGENT_ID           INTEGER,
        AGENT_NAME         VARCHAR(100),
        REPORT             BLOB SUB_TYPE TEXT,
        STATUS             VARCHAR(50)  DEFAULT 'pending',
        ERROR_MESSAGE      BLOB SUB_TYPE TEXT,
        LANGSMITH_TRACE_ID VARCHAR(255),
        EXECUTION_TIME_MS  INTEGER,
        RETRY_COUNT        INTEGER      DEFAULT 0,
        CREATED_AT         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def _table_exists(cur: fdb.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?",
        (name.upper(),),
    )
    return cur.fetchone()[0] > 0


def _sequence_exists(cur: fdb.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM RDB$GENERATORS WHERE RDB$GENERATOR_NAME = ?",
        (name.upper(),),
    )
    return cur.fetchone()[0] > 0


def setup():
    conn = fdb.connect(dsn=DSN, user=USER, password=PASSWORD)
    cur = conn.cursor()

    # Sequences
    for seq in ("project_state_seq", "agent_reports_seq"):
        if not _sequence_exists(cur, seq):
            cur.execute(f"CREATE SEQUENCE {seq}")
            print(f"  [OK] Sequence {seq} created.")
        else:
            print(f"  [--] Sequence {seq} already exists.")

    # Tables
    for stmt in DDL_STATEMENTS:
        stmt = stmt.strip()
        if not stmt.startswith("CREATE TABLE"):
            continue
        table_name = stmt.split("TABLE")[1].strip().split("(")[0].strip()
        if not _table_exists(cur, table_name):
            cur.execute(stmt)
            print(f"  [OK] Table {table_name} created.")
        else:
            print(f"  [--] Table {table_name} already exists.")

    # Triggers for auto-increment
    for table, seq in [
        ("PROJECT_STATE", "project_state_seq"),
        ("AGENT_REPORTS", "agent_reports_seq"),
    ]:
        trigger_name = f"BI_{table}"
        cur.execute(
            "SELECT COUNT(*) FROM RDB$TRIGGERS WHERE RDB$TRIGGER_NAME = ?",
            (trigger_name,),
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                f"""
                CREATE TRIGGER {trigger_name} FOR {table}
                ACTIVE BEFORE INSERT POSITION 0
                AS BEGIN
                  IF (NEW.ID IS NULL) THEN
                    NEW.ID = NEXT VALUE FOR {seq};
                END
                """
            )
            print(f"  [OK] Trigger {trigger_name} created.")
        else:
            print(f"  [--] Trigger {trigger_name} already exists.")

    conn.commit()
    conn.close()
    print("\nDatabase setup complete.")


if __name__ == "__main__":
    print("Setting up AgentIQ Firebird schema...\n")
    setup()
