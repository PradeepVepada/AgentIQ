"""Unified agent runner - single entry point for all 6 agents."""
import asyncio
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class AgentRunner:
    """Runs any agent with consistent error handling and state management."""
    
    def __init__(self, agent_id: int, name: str, run_fn: Callable):
        self.agent_id = agent_id
        self.name = name
        self.run_fn = run_fn
    
    async def execute(self, state: Dict[str, Any], llm_client) -> Dict[str, Any]:
        """Execute agent with error handling."""
        try:
            logger.info(f"[Agent {self.agent_id}] {self.name} starting")
            
            # Run agent in thread pool (blocking I/O)
            result = await asyncio.to_thread(self.run_fn, state, llm_client)
            
            logger.info(f"[Agent {self.agent_id}] {self.name} complete")
            return result
            
        except Exception as e:
            logger.error(f"[Agent {self.agent_id}] {self.name} failed: {e}", exc_info=True)
            return {
                "error": str(e),
                "agent_id": self.agent_id,
                "status": "failed"
            }


# Agent configurations
AGENTS = {
    1: {
        "name": "Data Intake & EDA",
        "output_fields": ["eda_report", "llm_eda_analysis", "task_type"],
    },
    2: {
        "name": "Data Preparation",
        "output_fields": ["cleaning_report", "cleaned_data_path"],
    },
    3: {
        "name": "Feature Engineering",
        "output_fields": ["feature_engineering_plan", "selected_features", "engineered_data_path"],
    },
    4: {
        "name": "Model Architecture",
        "output_fields": ["candidate_models", "split_strategy", "train_idx_path", "test_idx_path"],
    },
    5: {
        "name": "Training & Tuning",
        "output_fields": ["training_results", "tuning_results"],
    },
    6: {
        "name": "Evaluation & Report",
        "output_fields": ["evaluation_report"],
    },
}


def extract_agent_outputs(result: Dict[str, Any], agent_id: int) -> Dict[str, Any]:
    """Extract only relevant output fields from agent result."""
    if "error" in result:
        return result
    
    output_fields = AGENTS[agent_id]["output_fields"]
    return {field: result.get(field) for field in output_fields if field in result}
