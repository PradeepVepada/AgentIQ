"""In-memory storage implementation."""
from datetime import datetime
from typing import Dict, Any, Optional, List
from .storage import Storage


class MemoryStorage(Storage):
    """Fast in-memory storage for development and thesis presentation."""
    
    def __init__(self):
        self._projects: Dict[str, Dict[str, Any]] = {}
    
    async def create_project(self, project_id: str, project_goal: str, dataset_path: str = "") -> None:
        """Create a new project."""
        self._projects[project_id] = {
            "PROJECT_ID": project_id,
            "PROJECT_GOAL": project_goal,
            "DATASET_PATH": dataset_path,
            "DATASET_NAME": "",
            "CURRENT_STEP": "",
            "APPROVAL_STATUS": "pending",
            "APPROVAL_MODE": "human_in_loop",
            "THREAD_ID": "",
            "created_at": datetime.now().isoformat(),
            "AGENT_APPROVALS": {},
            "ERROR": None,
        }
    
    async def get_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project state."""
        return self._projects.get(project_id)
    
    async def update_state(self, project_id: str, **kwargs) -> None:
        """Update project state (only changed fields)."""
        if project_id in self._projects:
            self._projects[project_id].update(kwargs)
    
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        return list(self._projects.values())
    
    async def delete_project(self, project_id: str) -> None:
        """Delete a project."""
        if project_id in self._projects:
            del self._projects[project_id]
