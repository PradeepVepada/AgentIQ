"""Simple in-memory storage for thesis presentation - bypasses Firebird issues."""
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

# In-memory storage
_projects = {}
_agent_reports = {}

def create_project(project_id: str, project_goal: str, dataset_path: str = "") -> None:
    """Create a new project."""
    _projects[project_id] = {
        "PROJECT_ID": project_id,
        "PROJECT_GOAL": project_goal,
        "DATASET_PATH": dataset_path,
        "DATASET_NAME": "",
        "CURRENT_STEP": "",
        "STATUS": "pending",
        "THREAD_ID": "",
        "APPROVAL_MODE": "auto",
        "created_at": datetime.now().isoformat(),
    }

def get_state(project_id: str) -> Optional[Dict[str, Any]]:
    """Get project state."""
    return _projects.get(project_id)

def update_state(project_id: str, **kwargs) -> None:
    """Update project state."""
    if project_id in _projects:
        _projects[project_id].update(kwargs)

def list_projects() -> List[Dict[str, Any]]:
    """List all projects."""
    return list(_projects.values())

def delete_project(project_id: str) -> None:
    """Delete a project."""
    if project_id in _projects:
        del _projects[project_id]
    if project_id in _agent_reports:
        del _agent_reports[project_id]

def get_agent_reports(project_id: str, agent_id: int) -> Dict[str, Any]:
    """Get agent reports."""
    return _agent_reports.get(f"{project_id}_{agent_id}", {})

def save_agent_report(project_id: str, agent_id: int, report: Dict[str, Any]) -> None:
    """Save agent report."""
    _agent_reports[f"{project_id}_{agent_id}"] = report