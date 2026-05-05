"""Firebird database storage implementation."""
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from .storage import Storage

try:
    import fdb
except ImportError:
    fdb = None

logger = logging.getLogger(__name__)


class FirebirdStorage(Storage):
    """Firebird database storage for persistent project state."""
    
    def __init__(self, dsn: str, user: str, password: str):
        """Initialize Firebird storage.
        
        Args:
            dsn: Database path (e.g., 'C:\\path\\to\\db.fdb')
            user: Database user (default: SYSDBA)
            password: Database password
        """
        if not fdb:
            raise ImportError("fdb package required for Firebird storage. Install with: pip install fdb")
        
        self.dsn = dsn
        self.user = user
        self.password = password
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create database and tables if they don't exist."""
        try:
            # Try to connect to existing database
            con = fdb.connect(
                dsn=self.dsn,
                user=self.user,
                password=self.password
            )
            con.close()
        except fdb.DatabaseError:
            # Database doesn't exist, create it
            logger.info(f"Creating new Firebird database at {self.dsn}")
            con = fdb.create_database(
                f"CREATE DATABASE '{self.dsn}' USER '{self.user}' PASSWORD '{self.password}'"
            )
            con.close()
        
        # Ensure tables exist
        self._create_tables()
    
    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            # Create projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id VARCHAR(36) PRIMARY KEY,
                    project_goal VARCHAR(500),
                    dataset_path VARCHAR(500),
                    dataset_name VARCHAR(255),
                    current_step VARCHAR(100),
                    approval_status VARCHAR(50),
                    approval_mode VARCHAR(50),
                    thread_id VARCHAR(100),
                    created_at TIMESTAMP,
                    error_message VARCHAR(1000)
                )
            """)
            
            # Create state table for storing JSON state
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_state (
                    project_id VARCHAR(36) PRIMARY KEY,
                    state_json BLOB SUB_TYPE TEXT,
                    updated_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                )
            """)
            
            con.commit()
            logger.info("Firebird tables created/verified")
        except Exception as e:
            logger.warning(f"Table creation: {e}")
            con.rollback()
        finally:
            cur.close()
            con.close()
    
    async def create_project(self, project_id: str, project_goal: str, dataset_path: str = "") -> None:
        """Create a new project."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            now = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO projects 
                (project_id, project_goal, dataset_path, dataset_name, current_step, 
                 approval_status, approval_mode, created_at)
                VALUES (?, ?, ?, '', '', 'pending', 'human_in_loop', ?)
            """, (project_id, project_goal, dataset_path, now))
            
            # Initialize state
            initial_state = {
                "PROJECT_ID": project_id,
                "PROJECT_GOAL": project_goal,
                "DATASET_PATH": dataset_path,
                "DATASET_NAME": "",
                "CURRENT_STEP": "",
                "APPROVAL_STATUS": "pending",
                "APPROVAL_MODE": "human_in_loop",
                "THREAD_ID": "",
                "created_at": now,
                "AGENT_APPROVALS": {},
                "ERROR": None,
            }
            
            import json
            state_json = json.dumps(initial_state)
            cur.execute("""
                INSERT INTO project_state (project_id, state_json, updated_at)
                VALUES (?, ?, ?)
            """, (project_id, state_json, now))
            
            con.commit()
            logger.info(f"Created project {project_id} in Firebird")
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            con.rollback()
            raise
        finally:
            cur.close()
            con.close()
    
    async def get_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project state."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            cur.execute("SELECT state_json FROM project_state WHERE project_id = ?", (project_id,))
            row = cur.fetchone()
            
            if row:
                import json
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"Error getting state: {e}")
            return None
        finally:
            cur.close()
            con.close()
    
    async def update_state(self, project_id: str, **kwargs) -> None:
        """Update project state (only changed fields)."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            # Get current state
            cur.execute("SELECT state_json FROM project_state WHERE project_id = ?", (project_id,))
            row = cur.fetchone()
            
            if row:
                import json
                state = json.loads(row[0])
                state.update(kwargs)
                
                # Update state
                state_json = json.dumps(state)
                cur.execute("""
                    UPDATE project_state 
                    SET state_json = ?, updated_at = ?
                    WHERE project_id = ?
                """, (state_json, datetime.now().isoformat(), project_id))
                
                # Update projects table with key fields
                if "CURRENT_STEP" in kwargs or "APPROVAL_STATUS" in kwargs:
                    cur.execute("""
                        UPDATE projects
                        SET current_step = ?, approval_status = ?
                        WHERE project_id = ?
                    """, (
                        kwargs.get("CURRENT_STEP", ""),
                        kwargs.get("APPROVAL_STATUS", ""),
                        project_id
                    ))
                
                con.commit()
                logger.info(f"Updated state for project {project_id}")
            else:
                logger.warning(f"Project {project_id} not found for update")
        except Exception as e:
            logger.error(f"Error updating state: {e}")
            con.rollback()
            raise
        finally:
            cur.close()
            con.close()
    
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            cur.execute("""
                SELECT p.project_id, p.project_goal, p.dataset_name, 
                       p.current_step, p.approval_status, p.created_at
                FROM projects p
                ORDER BY p.created_at DESC
            """)
            
            projects = []
            for row in cur.fetchall():
                projects.append({
                    "PROJECT_ID": row[0],
                    "PROJECT_GOAL": row[1],
                    "DATASET_NAME": row[2],
                    "CURRENT_STEP": row[3],
                    "APPROVAL_STATUS": row[4],
                    "created_at": row[5],
                })
            
            return projects
        except Exception as e:
            logger.error(f"Error listing projects: {e}")
            return []
        finally:
            cur.close()
            con.close()
    
    async def delete_project(self, project_id: str) -> None:
        """Delete a project."""
        con = fdb.connect(
            dsn=self.dsn,
            user=self.user,
            password=self.password
        )
        cur = con.cursor()
        
        try:
            # Delete state first (foreign key)
            cur.execute("DELETE FROM project_state WHERE project_id = ?", (project_id,))
            # Delete project
            cur.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            con.commit()
            logger.info(f"Deleted project {project_id}")
        except Exception as e:
            logger.error(f"Error deleting project: {e}")
            con.rollback()
            raise
        finally:
            cur.close()
            con.close()
