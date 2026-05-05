"""Safety guards for self-review loops."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def check_loop_safety(state: Dict[str, Any], agent_id: int) -> bool:
    """
    Check if loop is safe to continue.
    
    Safety checks:
    - Max iterations not exceeded
    - Output is getting better (not stuck)
    - No infinite loops detected
    """
    
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 3)
    
    # Check 1: Max iterations
    if iterations >= max_iterations:
        logger.warning(
            f"[Agent {agent_id}] Max iterations reached, forcing approval"
        )
        state["approved"] = True
        return False
    
    # Check 2: Output quality (basic check)
    generation_history = state.get("generation_history", [])
    if len(generation_history) >= 2:
        prev_length = len(generation_history[-2])
        curr_length = len(generation_history[-1])
        
        # If output is getting shorter dramatically, might be stuck
        if curr_length < prev_length * 0.5:
            logger.warning(
                f"[Agent {agent_id}] Output degrading, might be stuck loop"
            )
    
    # Check 3: Feedback not changing (stuck)
    feedback_history = state.get("feedback_history", [])
    if len(feedback_history) >= 2:
        if feedback_history[-1] == feedback_history[-2]:
            logger.warning(
                f"[Agent {agent_id}] Same feedback twice, loop might be stuck"
            )
    
    return True


def log_revision_summary(agent_id: int, state: Dict[str, Any]) -> None:
    """Log a summary of the revision process."""
    
    iterations = state.get("iterations", 0)
    revisions = state.get("revision_count", 0)
    approved = state.get("approved", False)
    
    logger.info(
        f"\n[Agent {agent_id}] REVISION SUMMARY\n"
        f"  Iterations: {iterations}\n"
        f"  Revisions: {revisions}\n"
        f"  Status: {'✅ APPROVED' if approved else '❌ REJECTED'}\n"
        f"  Output Size: {len(state.get('output', ''))} chars"
    )
