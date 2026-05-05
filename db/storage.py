"""Abstract storage interface for in-memory and Firebird backends."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class Storage(ABC):
    """Abstract storage interface."""
    
    @abstractmethod
    async def create_project(self, project_id: str, project_goal: str, dataset_path: str = "") -> None:
        pass
    
    @abstractmethod
    async def get_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def update_state(self, project_id: str, **kwargs) -> None:
        pass
    
    @abstractmethod
    async def list_projects(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        pass
