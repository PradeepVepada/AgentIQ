"""Firebird state-store client for the AgentIQ pipeline.

All agents read/write the shared project_state through this module.
Firebird replaces PostgreSQL as the concurrency-safe state store.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, Optional

import fdb
from dotenv import load_dotenv

load_dotenv()

_DSN = os.getenv("FIREBIRD_DSN", r"C:\Users\santosh Arsid\YOURDB2.fdb")
_USER = os.getenv("FIREBIRD_USER", "SYSDBA")
_PASSWORD = os.getenv("FIREBIRD_PASSWORD", "gorillagear")


# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_connection() -> Generator[fdb.Connection, None, None]:
    """Yield an auto-committing Firebird connection."""
    conn = fdb.connect(dsn=_DSN, user=_USER, password=_PASSWORD)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json_dump(obj: Any) -> Optional[str]:
    import numpy as np
    if obj is None:
        return None
    # Convert booleans to 0/1 FIRST (before JSON serialization)
    if isinstance(obj, bool):
        return "1" if obj else "0"
    if isinstance(obj, np.bool_):
        return "1" if obj else "0"
    # Convert numpy types to Python native types
    if isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return str(int(obj))
    if isinstance(obj, (np.float64, np.float32, np.float16)):
        return str(float(obj))
    if isinstance(obj, np.ndarray):
        obj = obj.tolist()
    if isinstance(obj, dict):
        obj = {k: _convert_value(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        obj = [_convert_value(v) for v in obj]
    else:
        obj = _convert_value(obj)
    return json.dumps(obj)

def _convert_value(val):
    import numpy as np
    if val is None:
        return None
    if isinstance(val, bool):          # ← NEW: handle booleans FIRST
        return "1" if val else "0"
    if isinstance(val, np.bool_):
        return "1" if val else "0"
    if isinstance(val, (np.int64, np.int32, np.int16, np.int8)):
        return int(val)
    if isinstance(val, (np.float64, np.float32, np.float16)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    if isinstance(val, dict):
        return {k: _convert_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_convert_value(v) for v in val]
    return val


def _json_load(raw: Any) -> Optional[Dict]:
    if raw is None:
        return None
    if isinstance(raw, fdb.BlobReader):
        raw = raw.read()
    return json.loads(raw)


# ── Project-state CRUD ────────────────────────────────────────────────────────

def create_project(project_id: str, goal: str, dataset_path: str) -> None:
    """Insert a new project_state row."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO PROJECT_STATE
                (PROJECT_ID, PROJECT_GOAL, DATASET_PATH,
                 CURRENT_AGENT_ID, APPROVAL_STATUS, RETRY_COUNT)
            VALUES (?, ?, ?, 1, 'pending', 0)
            """,
            (project_id, goal, dataset_path),
        )


def get_state(project_id: str) -> Optional[Dict[str, Any]]:
    """Return the full project state as a Python dict."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM PROJECT_STATE WHERE PROJECT_ID = ?",
            (project_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        raw = dict(zip(cols, row))

    # Deserialise BLOB columns
    for blob_col in (
        "EDA_REPORT",
        "LLM_EDA_ANALYSIS",
        "CLEANING_PLAN",
        "CLEANING_REPORT",
        "HUMAN_FEEDBACK",
        "FEATURE_ENGINEERING_PLAN",
        "SELECTED_FEATURES",
        "SCALING_REQUIREMENTS",
        "SPLIT_STRATEGY",
        "CANDIDATE_MODELS",
        "TRAINING_RESULTS",
        "TUNING_RESULTS",
        "EVALUATION_REPORT",
        "AGENT_APPROVALS",  # New: approval tracking
    ):
        raw[blob_col] = _json_load(raw.get(blob_col))

    return raw


def update_state(project_id: str, **kwargs) -> None:
    """Update arbitrary fields in project_state."""
    if not kwargs:
        return

    import logging
    logger = logging.getLogger(__name__)

    # Get existing columns in PROJECT_STATE
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS "
            "WHERE RDB$RELATION_NAME = 'PROJECT_STATE'"
        )
        existing_cols = {row[0].strip() for row in cur.fetchall()}

    values = []
    set_clauses = []
    
    for key, val in kwargs.items():
        col = key.upper()
        # Skip columns that don't exist in the database
        if col not in existing_cols:
            logger.warning(f"Skipping unknown column: {col}")
            continue
        
        # Handle None values
        if val is None:
            set_clauses.append(f"{col} = ?")
            values.append(None)
            continue
            
        # Serialize any non-string value to JSON (lists, dicts, etc.)
        if not isinstance(val, str):
            val = _json_dump(val)
            logger.debug(f"Serialized {key}: {len(val) if val else 0} chars")
        
        set_clauses.append(f"{col} = ?")
        values.append(val)

    if not set_clauses:
        logger.warning(f"No valid columns to update for {project_id}")
        return

    set_clauses.append("UPDATED_AT = ?")
    values.append(datetime.utcnow())
    values.append(project_id)

    sql = f"UPDATE PROJECT_STATE SET {', '.join(set_clauses)} WHERE PROJECT_ID = ?"
    logger.debug(f"Running SQL for {project_id}")
    try:
        with get_connection() as conn:
            conn.cursor().execute(sql, values)
            conn.commit()
        logger.debug(f"Update completed for {project_id}")
    except Exception as e:
        logger.error(f"update_state failed: {e}")
        raise


# ── Agent-report logging ───────────────────────────────────────────────────────

def log_agent_report(
    project_id: str,
    agent_id: int,
    agent_name: str,
    report: Dict[str, Any],
    status: str = "success",
    error_message: Optional[str] = None,
    trace_id: Optional[str] = None,
    execution_time_ms: Optional[int] = None,
    retry_count: int = 0,
) -> None:
    with get_connection() as conn:
        conn.cursor().execute(
            """
            INSERT INTO AGENT_REPORTS
                (PROJECT_ID, AGENT_ID, AGENT_NAME, REPORT,
                 STATUS, ERROR_MESSAGE, LANGSMITH_TRACE_ID,
                 EXECUTION_TIME_MS, RETRY_COUNT)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                agent_id,
                agent_name,
                _json_dump(report),
                status,
                error_message,
                trace_id,
                execution_time_ms,
                retry_count,
            ),
        )


def get_agent_reports(project_id: str, agent_id: int) -> list:
    """Return previous run reports for a given agent (latest first)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT REPORT, STATUS, ERROR_MESSAGE, CREATED_AT
            FROM AGENT_REPORTS
            WHERE PROJECT_ID = ? AND AGENT_ID = ?
            ORDER BY CREATED_AT DESC
            ROWS 10
            """,
            (project_id, agent_id),
        )
        rows = cur.fetchall()

    return [
        {
            "report": _json_load(r[0]),
            "status": r[1],
            "error": r[2],
            "created_at": str(r[3]),
        }
        for r in rows
    ]


# ── Project listing & deletion ───────────────────────────────────────────────

def list_projects() -> list:
    """Return all projects (id, goal, dataset_name, stage) for sidebar."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT PROJECT_ID, PROJECT_GOAL, DATASET_NAME, 
                   CURRENT_STEP, STAGE, APPROVAL_STATUS, CREATED_AT
            FROM PROJECT_STATE
            ORDER BY CREATED_AT DESC
            """
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    projects = []
    for r in rows:
        d = dict(zip(cols, r))
        projects.append({
            "project_id": d["PROJECT_ID"],
            "project_goal": d["PROJECT_GOAL"] or "",
            "dataset_name": d["DATASET_NAME"] or "",
            "current_step": d["CURRENT_STEP"] or "",
            "stage": d["STAGE"] or "",
            "approval_status": d["APPROVAL_STATUS"] or "",
            "created_at": str(d["CREATED_AT"]),
        })
    return projects


def delete_project(project_id: str) -> None:
    """Delete project and all its agent reports."""
    import logging
    logger = logging.getLogger(__name__)
    
    with get_connection() as conn:
        cur = conn.cursor()
        # Delete agent reports first (foreign key)
        cur.execute("DELETE FROM AGENT_REPORTS WHERE PROJECT_ID = ?", (project_id,))
        # Delete project state
        cur.execute("DELETE FROM PROJECT_STATE WHERE PROJECT_ID = ?", (project_id,))
        conn.commit()
        logger.debug(f"Deleted project {project_id}")
