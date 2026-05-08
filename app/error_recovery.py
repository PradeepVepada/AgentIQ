"""Advanced error recovery and retry strategies for the pipeline."""

import asyncio
import logging
import time
from typing import Dict, Any, Callable, Optional, List
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"  # Recoverable, retry immediately
    MEDIUM = "medium"  # Recoverable, retry with backoff
    HIGH = "high"  # Recoverable, retry with longer backoff
    CRITICAL = "critical"  # Not recoverable, fail immediately


class ErrorType(Enum):
    """Error types for categorization."""
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    DATA_ERROR = "data_error"
    MEMORY_ERROR = "memory_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


class RetryStrategy:
    """Retry strategy with exponential backoff."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = min(
            self.initial_delay * (self.backoff_factor ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())
        
        return delay


class ErrorRecoveryManager:
    """Manages error recovery and retry logic."""
    
    def __init__(self, storage):
        self.storage = storage
        self.retry_strategy = RetryStrategy()
        self.error_history: Dict[str, List[Dict[str, Any]]] = {}
    
    def categorize_error(self, error: Exception) -> tuple[ErrorType, ErrorSeverity]:
        """Categorize error and determine severity."""
        error_str = str(error).lower()
        error_type = error.__class__.__name__.lower()
        
        # Timeout errors
        if "timeout" in error_str or "timed out" in error_str:
            return ErrorType.TIMEOUT, ErrorSeverity.MEDIUM
        
        # API errors
        if "api" in error_str or "openai" in error_type or "429" in error_str:
            if "429" in error_str or "rate" in error_str:
                return ErrorType.API_ERROR, ErrorSeverity.HIGH
            return ErrorType.API_ERROR, ErrorSeverity.MEDIUM
        
        # Data errors
        if "data" in error_str or "csv" in error_str or "dataframe" in error_type:
            return ErrorType.DATA_ERROR, ErrorSeverity.LOW
        
        # Memory errors
        if "memory" in error_str or "memoryerror" in error_type:
            return ErrorType.MEMORY_ERROR, ErrorSeverity.CRITICAL
        
        # Validation errors
        if "validation" in error_str or "invalid" in error_str:
            return ErrorType.VALIDATION_ERROR, ErrorSeverity.LOW
        
        return ErrorType.UNKNOWN, ErrorSeverity.MEDIUM
    
    async def record_error(
        self,
        project_id: str,
        agent_id: int,
        error: Exception,
        context: Dict[str, Any] = None,
    ):
        """Record error in history."""
        error_type, severity = self.categorize_error(error)
        
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_id,
            "error_type": error_type.value,
            "severity": severity.value,
            "message": str(error),
            "context": context or {},
        }
        
        if project_id not in self.error_history:
            self.error_history[project_id] = []
        
        self.error_history[project_id].append(error_record)
        
        # Store in persistent storage
        try:
            state = await self.storage.get_state(project_id)
            error_log = state.get("ERROR_LOG", [])
            error_log.append(error_record)
            await self.storage.update_state(project_id, ERROR_LOG=error_log)
        except Exception as e:
            logger.warning(f"Failed to store error log: {e}")
    
    async def should_retry(
        self,
        project_id: str,
        agent_id: int,
        error: Exception,
        attempt: int,
    ) -> bool:
        """Determine if operation should be retried."""
        error_type, severity = self.categorize_error(error)
        
        # Critical errors never retry
        if severity == ErrorSeverity.CRITICAL:
            return False
        
        # Validation errors don't retry
        if error_type == ErrorType.VALIDATION_ERROR:
            return False
        
        # Check max retries
        if attempt >= self.retry_strategy.max_retries:
            return False
        
        # Check error frequency (circuit breaker)
        if project_id in self.error_history:
            recent_errors = [
                e for e in self.error_history[project_id]
                if e["agent_id"] == agent_id
                and (datetime.fromisoformat(e["timestamp"]) > 
                     datetime.now() - timedelta(minutes=5))
            ]
            
            # If too many errors in short time, stop retrying
            if len(recent_errors) > 5:
                logger.warning(
                    f"Circuit breaker triggered for agent {agent_id}: "
                    f"{len(recent_errors)} errors in 5 minutes"
                )
                return False
        
        return True
    
    async def execute_with_retry(
        self,
        project_id: str,
        agent_id: int,
        func: Callable,
        *args,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute function with retry logic."""
        attempt = 0
        last_error = None
        
        while attempt < self.retry_strategy.max_retries:
            try:
                logger.info(
                    f"[Agent {agent_id}] Attempt {attempt + 1}/{self.retry_strategy.max_retries}"
                )
                result = await func(*args, **kwargs)
                
                # Success
                if attempt > 0:
                    logger.info(f"[Agent {agent_id}] Recovered after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_error = e
                error_type, severity = self.categorize_error(e)
                
                logger.warning(
                    f"[Agent {agent_id}] Error (attempt {attempt + 1}): "
                    f"{error_type.value} - {str(e)[:100]}"
                )
                
                # Record error
                await self.record_error(project_id, agent_id, e)
                
                # Check if should retry
                should_retry = await self.should_retry(project_id, agent_id, e, attempt)
                
                if not should_retry:
                    logger.error(
                        f"[Agent {agent_id}] Not retrying: "
                        f"severity={severity.value}, type={error_type.value}"
                    )
                    break
                
                # Calculate delay
                delay = self.retry_strategy.get_delay(attempt)
                logger.info(f"[Agent {agent_id}] Retrying in {delay:.1f}s...")
                
                await asyncio.sleep(delay)
                attempt += 1
        
        # All retries exhausted
        logger.error(
            f"[Agent {agent_id}] Failed after {attempt} attempts: {str(last_error)}"
        )
        
        return {
            "error": str(last_error),
            "error_type": error_type.value if last_error else "unknown",
            "attempts": attempt,
            "recoverable": False,
        }
    
    async def get_error_summary(self, project_id: str) -> Dict[str, Any]:
        """Get summary of errors for a project."""
        if project_id not in self.error_history:
            return {"total_errors": 0, "by_agent": {}, "by_type": {}}
        
        errors = self.error_history[project_id]
        
        by_agent = {}
        by_type = {}
        
        for error in errors:
            agent_id = error["agent_id"]
            error_type = error["error_type"]
            
            by_agent[agent_id] = by_agent.get(agent_id, 0) + 1
            by_type[error_type] = by_type.get(error_type, 0) + 1
        
        return {
            "total_errors": len(errors),
            "by_agent": by_agent,
            "by_type": by_type,
            "recent_errors": errors[-5:],  # Last 5 errors
        }


class FallbackStrategy:
    """Fallback strategies when recovery fails."""
    
    @staticmethod
    async def fallback_agent_1(state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback for Agent 1 (EDA)."""
        logger.warning("[Agent 1] Using fallback strategy")
        
        return {
            "eda_report": {
                "overview": {
                    "rows": 0,
                    "columns": 0,
                    "total_missing": 0,
                    "duplicate_rows": 0,
                },
                "key_findings": ["Unable to complete EDA - using fallback"],
            },
            "task_type": "classification",
            "llm_eda_analysis": "Fallback analysis",
        }
    
    @staticmethod
    async def fallback_agent_2(state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback for Agent 2 (Data Prep)."""
        logger.warning("[Agent 2] Using fallback strategy")
        
        return {
            "cleaning_report": {
                "rows_processed": 0,
                "missing_handled": 0,
                "outliers_detected": 0,
                "duplicates_removed": 0,
                "cleaning_steps": ["Fallback: minimal cleaning"],
            },
            "cleaned_data_path": state.get("DATASET_PATH", ""),
        }
    
    @staticmethod
    async def fallback_agent_3(state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback for Agent 3 (Feature Engineering)."""
        logger.warning("[Agent 3] Using fallback strategy")
        
        return {
            "feature_engineering_plan": {
                "task_type": state.get("task_type", "classification"),
                "target_column": "target",
                "strategy": "fallback",
            },
            "selected_features": [],
            "engineered_data_path": state.get("cleaned_data_path", ""),
            "feature_stats": {
                "total_features": 0,
                "selected_features": 0,
                "top_features": [],
            },
        }
    
    @staticmethod
    async def fallback_agent_4(state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback for Agent 4 (Model Architecture)."""
        logger.warning("[Agent 4] Using fallback strategy")
        
        task_type = state.get("task_type", "classification")
        
        if task_type == "classification":
            models = [
                {"name": "LogisticRegression", "reason": "Fallback baseline"},
                {"name": "RandomForest", "reason": "Fallback ensemble"},
            ]
        else:
            models = [
                {"name": "Ridge", "reason": "Fallback baseline"},
                {"name": "RandomForestRegressor", "reason": "Fallback ensemble"},
            ]
        
        return {
            "candidate_models": models,
            "split_strategy": {"test_size": 0.2, "random_state": 42},
            "train_idx_path": "",
            "test_idx_path": "",
        }
    
    @staticmethod
    async def fallback_agent_5(state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback for Agent 5 (Training)."""
        logger.warning("[Agent 5] Using fallback strategy")
        
        models = state.get("candidate_models", [])
        training_results = {}
        tuning_results = {}
        
        for model in models:
            model_name = model.get("name", "Unknown")
            training_results[model_name] = {
                "cv_mean": 0.0,
                "cv_std": 0.0,
                "status": "fallback",
            }
            tuning_results[model_name] = {
                "best_score": 0.0,
                "status": "fallback",
            }
        
        return {
            "training_results": training_results,
            "tuning_results": tuning_results,
        }


# Fallback mapping
FALLBACK_STRATEGIES = {
    1: FallbackStrategy.fallback_agent_1,
    2: FallbackStrategy.fallback_agent_2,
    3: FallbackStrategy.fallback_agent_3,
    4: FallbackStrategy.fallback_agent_4,
    5: FallbackStrategy.fallback_agent_5,
}
