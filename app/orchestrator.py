"""Pipeline orchestrator - handles agent sequencing and human approval."""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from app.error_recovery import ErrorRecoveryManager, FALLBACK_STRATEGIES

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the 6-agent pipeline with human-in-loop support."""
    
    def __init__(self, storage, llm_client):
        self.storage = storage
        self.llm_client = llm_client
        self.agent_runners = {}
        self.error_recovery = ErrorRecoveryManager(storage)
    
    def register_agent(self, agent_id: int, runner):
        """Register an agent runner."""
        self.agent_runners[agent_id] = runner
    
    async def run_human_in_loop(self, project_id: str) -> Dict[str, Any]:
        """Run pipeline in human-in-loop mode."""
        try:
            # Get initial state
            state = await self.storage.get_state(project_id)
            if not state:
                raise ValueError(f"Project {project_id} not found")
            
            # Ensure enable_revision_loop is set
            if "ENABLE_REVISION_LOOP" not in state:
                await self.storage.update_state(project_id, ENABLE_REVISION_LOOP=True)
                state["ENABLE_REVISION_LOOP"] = True
            
            # Run Agent 1
            logger.info(f"[Pipeline] Starting Agent 1 for {project_id}")
            await self.storage.update_state(project_id, CURRENT_STEP="agent_1_running", APPROVAL_STATUS="running")
            
            agent_1_result = await self.agent_runners[1].execute(state, self.llm_client)
            
            if "error" in agent_1_result:
                await self.storage.update_state(
                    project_id,
                    CURRENT_STEP="agent_1_error",
                    APPROVAL_STATUS="error",
                    ERROR=agent_1_result["error"]
                )
                return {"status": "error", "message": agent_1_result["error"]}
            
            # Store Agent 1 outputs
            updates = {
                "CURRENT_STEP": "agent_1_pending_approval",
                "APPROVAL_STATUS": "pending_approval",
                "EDA_REPORT": agent_1_result.get("eda_report"),
                "LLM_EDA_ANALYSIS": agent_1_result.get("llm_eda_analysis"),
                "TASK_TYPE": agent_1_result.get("task_type"),
            }
            
            # Initialize approval tracking
            approvals = state.get("AGENT_APPROVALS", {})
            approvals["1"] = {
                "status": "pending",
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": 0,
            }
            updates["AGENT_APPROVALS"] = approvals
            
            await self.storage.update_state(project_id, **updates)
            
            return {
                "status": "agent_1_complete",
                "project_id": project_id,
                "current_agent": 1,
                "message": "Agent 1 complete. Awaiting approval."
            }
            
        except Exception as e:
            logger.error(f"[Pipeline] Error in human-in-loop: {e}", exc_info=True)
            await self.storage.update_state(
                project_id,
                CURRENT_STEP="pipeline_error",
                APPROVAL_STATUS="error",
                ERROR=str(e)
            )
            raise
    
    async def run_auto(self, project_id: str) -> Dict[str, Any]:
        """Run pipeline in auto mode (no human approval needed)."""
        try:
            state = await self.storage.get_state(project_id)
            if not state:
                raise ValueError(f"Project {project_id} not found")
            
            # Ensure enable_revision_loop is set
            if "ENABLE_REVISION_LOOP" not in state:
                await self.storage.update_state(project_id, ENABLE_REVISION_LOOP=True)
                state["ENABLE_REVISION_LOOP"] = True
            
            # Run all agents sequentially
            for agent_num in range(1, 6):  # Agents 1-5 (skip 6 for now)
                logger.info(f"[Pipeline] Running Agent {agent_num} for {project_id}")
                await self.storage.update_state(
                    project_id,
                    CURRENT_STEP=f"agent_{agent_num}_running",
                    APPROVAL_STATUS="running"
                )
                
                # Execute with error recovery
                async def execute_agent():
                    return await self.agent_runners[agent_num].execute(state, self.llm_client)
                
                agent_result = await self.error_recovery.execute_with_retry(
                    project_id,
                    agent_num,
                    execute_agent,
                )
                
                # Check for error
                if "error" in agent_result:
                    logger.error(f"[Pipeline] Agent {agent_num} failed: {agent_result['error']}")
                    
                    # Try fallback strategy
                    if agent_num in FALLBACK_STRATEGIES:
                        logger.info(f"[Pipeline] Attempting fallback for Agent {agent_num}")
                        try:
                            agent_result = await FALLBACK_STRATEGIES[agent_num](state)
                            logger.info(f"[Pipeline] Fallback successful for Agent {agent_num}")
                        except Exception as e:
                            logger.error(f"[Pipeline] Fallback failed for Agent {agent_num}: {e}")
                            await self.storage.update_state(
                                project_id,
                                CURRENT_STEP=f"agent_{agent_num}_error",
                                APPROVAL_STATUS="error",
                                ERROR=agent_result["error"]
                            )
                            return {"status": "error", "message": agent_result["error"]}
                    else:
                        await self.storage.update_state(
                            project_id,
                            CURRENT_STEP=f"agent_{agent_num}_error",
                            APPROVAL_STATUS="error",
                            ERROR=agent_result["error"]
                        )
                        return {"status": "error", "message": agent_result["error"]}
                
                # Store outputs
                output_fields = {
                    1: ["eda_report", "llm_eda_analysis", "task_type"],
                    2: ["cleaning_report", "cleaned_data_path"],
                    3: ["feature_engineering_plan", "selected_features", "engineered_data_path", "feature_stats"],
                    4: ["candidate_models", "split_strategy", "train_idx_path", "test_idx_path"],
                    5: ["training_results", "tuning_results"],
                }
                
                updates = {}
                for field in output_fields.get(agent_num, []):
                    if field in agent_result:
                        updates[field] = agent_result[field]
                
                await self.storage.update_state(project_id, **updates)
                state.update(updates)
            
            # Mark complete
            await self.storage.update_state(
                project_id,
                CURRENT_STEP="complete",
                APPROVAL_STATUS="complete"
            )
            
            # Get error summary
            error_summary = await self.error_recovery.get_error_summary(project_id)
            logger.info(f"[Pipeline] Complete with error summary: {error_summary}")
            
            return {"status": "pipeline_complete", "project_id": project_id}
            
        except Exception as e:
            logger.error(f"[Pipeline] Error in auto mode: {e}", exc_info=True)
            await self.storage.update_state(
                project_id,
                CURRENT_STEP="pipeline_error",
                APPROVAL_STATUS="error",
                ERROR=str(e)
            )
            raise
    
    async def approve_and_continue(self, project_id: str, agent_num: int) -> Dict[str, Any]:
        """Approve current agent and run next agent."""
        try:
            state = await self.storage.get_state(project_id)
            if not state:
                raise ValueError(f"Project {project_id} not found")
            
            # Ensure enable_revision_loop is set
            if "ENABLE_REVISION_LOOP" not in state:
                await self.storage.update_state(project_id, ENABLE_REVISION_LOOP=True)
                state["ENABLE_REVISION_LOOP"] = True
            
            # Update approval status
            approvals = state.get("AGENT_APPROVALS", {})
            approvals[str(agent_num)] = {
                "status": "approved",
                "timestamp": approvals.get(str(agent_num), {}).get("timestamp"),
                "approved_at": datetime.now().isoformat(),
            }
            
            # If last agent, mark complete
            if agent_num == 5:  # Stop at Agent 5 for now
                await self.storage.update_state(
                    project_id,
                    CURRENT_STEP="complete",
                    APPROVAL_STATUS="complete",
                    AGENT_APPROVALS=approvals
                )
                return {"status": "pipeline_complete", "project_id": project_id}
            
            # Run next agent
            next_agent = agent_num + 1
            logger.info(f"[Pipeline] Running Agent {next_agent} for {project_id}")
            
            await self.storage.update_state(
                project_id,
                CURRENT_STEP=f"agent_{next_agent}_running",
                APPROVAL_STATUS="running",
                AGENT_APPROVALS=approvals
            )
            
            # Refresh state before passing to agent
            state = await self.storage.get_state(project_id)
            
            # Execute with error recovery
            async def execute_agent():
                return await self.agent_runners[next_agent].execute(state, self.llm_client)
            
            agent_result = await self.error_recovery.execute_with_retry(
                project_id,
                next_agent,
                execute_agent,
            )
            
            # Check for error
            if "error" in agent_result:
                logger.error(f"[Pipeline] Agent {next_agent} failed: {agent_result['error']}")
                
                # Try fallback strategy
                if next_agent in FALLBACK_STRATEGIES:
                    logger.info(f"[Pipeline] Attempting fallback for Agent {next_agent}")
                    try:
                        agent_result = await FALLBACK_STRATEGIES[next_agent](state)
                        logger.info(f"[Pipeline] Fallback successful for Agent {next_agent}")
                    except Exception as e:
                        logger.error(f"[Pipeline] Fallback failed for Agent {next_agent}: {e}")
                        await self.storage.update_state(
                            project_id,
                            CURRENT_STEP=f"agent_{next_agent}_error",
                            APPROVAL_STATUS="error",
                            ERROR=agent_result["error"]
                        )
                        return {"status": "error", "message": agent_result["error"]}
                else:
                    await self.storage.update_state(
                        project_id,
                        CURRENT_STEP=f"agent_{next_agent}_error",
                        APPROVAL_STATUS="error",
                        ERROR=agent_result["error"]
                    )
                    return {"status": "error", "message": agent_result["error"]}
            
            # Store outputs
            output_fields = {
                2: ["cleaning_report", "cleaned_data_path"],
                3: ["feature_engineering_plan", "selected_features", "engineered_data_path", "feature_stats"],
                4: ["candidate_models", "split_strategy", "train_idx_path", "test_idx_path"],
                5: ["training_results", "tuning_results"],
            }
            
            updates = {
                "CURRENT_STEP": f"agent_{next_agent}_pending_approval",
                "APPROVAL_STATUS": "pending_approval",
            }
            
            for field in output_fields.get(next_agent, []):
                if field in agent_result:
                    updates[field] = agent_result[field]
            
            # Update approval tracking
            approvals[str(next_agent)] = {
                "status": "pending",
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": 0,
            }
            updates["AGENT_APPROVALS"] = approvals
            
            await self.storage.update_state(project_id, **updates)
            
            return {
                "status": f"agent_{next_agent}_complete",
                "project_id": project_id,
                "current_agent": next_agent,
                "message": f"Agent {next_agent} complete. Awaiting approval."
            }
            
        except Exception as e:
            logger.error(f"[Pipeline] Error approving agent {agent_num}: {e}", exc_info=True)
            raise
