"""Generic self-reviewing loop implementation for all agents."""
import logging
import os
import json
from typing import Callable, Dict, Any, Tuple
from enum import Enum
from datetime import datetime

from workflows.agent_state import ReviewStatus

logger = logging.getLogger(__name__)


class OpenAIClientWrapper:
    """
    Thin wrapper that makes a raw openai.OpenAI client compatible with
    the LangChain-style `.invoke(prompt)` interface expected by the
    generate/review nodes.
    """

    def __init__(self, openai_client, model: str | None = None):
        self._client = openai_client
        # Use OpenAI by default, fallback to NVIDIA if needed
        self._model = model or os.getenv(
            "OPENAI_MODEL", "gpt-4o-mini"  # Fast and cheap model
        )

    def invoke(self, prompt: str) -> "OpenAIClientWrapper._Response":
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        return self._Response(response.choices[0].message.content)

    class _Response:
        def __init__(self, content: str):
            self.content = content


class ReviewResult(Enum):
    """Review decision."""
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    MAX_ITERATIONS_REACHED = "max_iterations"


def _generate_fallback_eda_analysis(eda_data: Dict[str, Any]) -> str:
    """Generate fallback EDA analysis from statistical data when LLM fails."""
    overview = eda_data.get("overview", {})
    missing = eda_data.get("missing_analysis", [])
    outliers = eda_data.get("outlier_analysis", [])
    correlations = eda_data.get("correlation_analysis", [])
    stats = eda_data.get("statistical_analysis", [])
    
    # Calculate data quality score
    total_cells = overview.get("rows", 1) * overview.get("columns", 1)
    missing_pct = (overview.get("total_missing", 0) / total_cells * 100) if total_cells > 0 else 0
    duplicate_pct = (overview.get("duplicate_rows", 0) / overview.get("rows", 1) * 100) if overview.get("rows", 0) > 0 else 0
    
    quality_score = 10
    if missing_pct > 20: quality_score -= 3
    elif missing_pct > 10: quality_score -= 2
    elif missing_pct > 5: quality_score -= 1
    
    if duplicate_pct > 5: quality_score -= 2
    elif duplicate_pct > 1: quality_score -= 1
    
    quality_score = max(0, min(10, quality_score))
    
    # Generate key findings
    findings = []
    
    # Missing data findings
    high_missing = [m for m in missing if m.get("missing_pct", 0) > 5]
    if high_missing:
        findings.append(f"Dataset has {len(high_missing)} columns with >5% missing values, requiring imputation strategy")
    
    # Outlier findings
    high_outliers = [o for o in outliers if float(o.get("outlier_pct", 0) or 0) > 5]
    if high_outliers:
        findings.append(f"Detected {len(high_outliers)} columns with significant outliers (>5%), may need robust scaling")
    
    # Correlation findings
    if correlations:
        findings.append(f"Found {len(correlations)} strong correlations (|r| >= 0.7), consider feature selection to avoid multicollinearity")
    
    # Distribution findings
    skewed_cols = [s for s in stats if s.get("skewness") and abs(float(s.get("skewness", 0))) > 1]
    if skewed_cols:
        findings.append(f"{len(skewed_cols)} numeric columns show significant skewness, log transformation recommended")
    
    # Size findings
    findings.append(f"Dataset contains {overview.get('rows', 0):,} rows and {overview.get('columns', 0)} columns, suitable for most ML algorithms")
    
    # Categorical findings
    cat_cols = overview.get("categorical_count", 0)
    if cat_cols > 0:
        findings.append(f"Dataset has {cat_cols} categorical columns requiring encoding before modeling")
    
    # Recommendations
    recommendations = [
        "Handle missing values using appropriate imputation strategy based on missing mechanism (MCAR/MAR/MNAR)",
        "Apply feature scaling (StandardScaler or RobustScaler) to normalize numeric features",
        "Encode categorical variables using one-hot encoding or label encoding as appropriate",
        "Remove or handle duplicate rows to ensure data integrity",
        "Consider log transformation for skewed numeric features",
        "Perform feature selection to reduce dimensionality and multicollinearity",
        "Split data into train/validation/test sets before model training"
    ]
    
    analysis = {
        "overview": f"Dataset with {overview.get('rows', 0):,} rows and {overview.get('columns', 0)} columns",
        "data_quality": {
            "score": quality_score,
            "issues": [x for x in [
                f"{missing_pct:.1f}% missing values" if missing_pct > 0 else None,
                f"{duplicate_pct:.1f}% duplicate rows" if duplicate_pct > 0 else None,
            ] if x]
        },
        "missing_analysis_summary": f"{len(high_missing)} columns with >5% missing values",
        "outlier_summary": f"{len(high_outliers)} columns with >5% outliers",
        "correlation_summary": f"{len(correlations)} strong correlations detected",
        "key_findings": findings[:7],
        "recommendations": recommendations,
        "target_column_suggestion": None,
        "task_type_suggestion": "classification"
    }
    
    return json.dumps(analysis)


def create_generate_node(
    agent_id: int,
    agent_name: str,
    generate_prompt_fn: Callable,
    llm_client,
) -> Callable:
    """
    Create a GENERATE node for an agent.
    
    Args:
        agent_id: Agent number (1-6)
        agent_name: Human readable name
        generate_prompt_fn: Function that builds the generation prompt
        llm_client: LLM client (Claude, etc.)
    
    Returns:
        Node function for LangGraph
    """
    
    def generate_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate initial output."""
        
        logger.info(f"[Agent {agent_id}] GENERATE: Starting generation")
        
        # Check iteration count (safety guard)
        # Default to 1 iteration for faster execution, configurable via state
        iterations = state.get("iterations", 0)
        max_iterations = state.get("max_iterations", 1)  # Default: 1 iteration for speed
        
        if iterations >= max_iterations:
            logger.warning(
                f"[Agent {agent_id}] Max iterations ({max_iterations}) reached"
            )
            state["status"] = ReviewStatus.MAX_ITERATIONS
            state["approved"] = True  # Force approval
            return state
        
        # Build prompt using agent-specific function
        try:
            prompt = generate_prompt_fn(state)
        except Exception as e:
            logger.error(f"[Agent {agent_id}] Prompt building failed: {e}")
            state["output"] = ""
            state["status"] = ReviewStatus.APPROVED
            return state
        
        # Call LLM
        output = ""
        try:
            response = llm_client.invoke(prompt)
            output = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"[Agent {agent_id}] LLM call failed: {e}")
            # Fallback for Agent 1 EDA: generate from statistical data
            if agent_id == 1 and "_eda_data" in state:
                logger.info(f"[Agent {agent_id}] Using fallback analysis from statistical EDA data")
                output = _generate_fallback_eda_analysis(state.get("_eda_data", {}))
            else:
                output = ""
            state["status"] = ReviewStatus.APPROVED
        
        # Store in history
        generation_history = state.get("generation_history", [])
        generation_history.append(output)
        
        # Update state
        state["output"] = output
        state["generation_history"] = generation_history
        state["status"] = ReviewStatus.GENERATING
        state["iterations"] = iterations + 1
        
        logger.info(
            f"[Agent {agent_id}] Generated {len(output)} chars (iteration {iterations + 1})"
        )
        
        return state
    
    return generate_node


def create_review_node(
    agent_id: int,
    agent_name: str,
    review_prompt_fn: Callable,
    llm_client,
) -> Callable:
    """
    Create a REVIEW node for an agent.
    
    The review node makes the agent critique its own output.
    
    Args:
        agent_id: Agent number (1-6)
        agent_name: Human readable name
        review_prompt_fn: Function that builds the review prompt
        llm_client: LLM client
    
    Returns:
        Node function for LangGraph
    """
    
    def review_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """Review and critique own output."""
        
        logger.info(f"[Agent {agent_id}] REVIEW: Critiquing output")
        
        # Build review prompt
        try:
            prompt = review_prompt_fn(state)
        except Exception as e:
            logger.error(f"[Agent {agent_id}] Review prompt failed: {e}")
            state["approved"] = True
            state["status"] = ReviewStatus.APPROVED
            return state
        
        # Call LLM to critique
        try:
            response = llm_client.invoke(prompt)
            critique = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"[Agent {agent_id}] Review LLM call failed: {e}")
            state["approved"] = True
            state["status"] = ReviewStatus.APPROVED
            return state
        
        # Parse review response
        # Expected format: "APPROVED: ..." or "NEEDS_REVISION: ..."
        is_approved = critique.strip().upper().startswith("APPROVED")
        
        # Store feedback
        feedback_history = state.get("feedback_history", [])
        feedback_history.append(critique)
        
        # Update state
        state["feedback"] = critique
        state["feedback_history"] = feedback_history
        state["approved"] = is_approved
        
        if is_approved:
            state["status"] = ReviewStatus.APPROVED
            logger.info(f"[Agent {agent_id}] ✅ APPROVED")
        else:
            state["status"] = ReviewStatus.NEEDS_REVISION
            state["revision_count"] = state.get("revision_count", 0) + 1
            logger.info(f"[Agent {agent_id}] 🔄 NEEDS REVISION (attempt {state['revision_count']})")
        
        return state
    
    return review_node


def create_conditional_edge(agent_id: int) -> Callable:
    """
    Create conditional logic: approve or loop back to generate.
    
    Args:
        agent_id: Agent number
        
    Returns:
        Function that decides next node
    """
    
    def conditional_edge(state: Dict[str, Any]) -> str:
        """Decide: approve and exit, or loop back for revision."""
        
        # Skip review loop if disabled (for thesis presentation speed)
        if not state.get("enable_revision_loop", True):
            logger.info(f"[Agent {agent_id}] → Review loop disabled, auto-approving")
            state["approved"] = True
            return "exit"
        
        if state.get("approved"):
            logger.info(f"[Agent {agent_id}] → Exiting to next agent")
            return "exit"  # Go to END node
        else:
            logger.info(f"[Agent {agent_id}] → Looping back to generate")
            return "generate"  # Loop back to GENERATE node
    
    return conditional_edge
