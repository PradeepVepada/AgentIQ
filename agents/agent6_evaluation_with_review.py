"""Agent 6 — Evaluation & Reporting with Self-Reviewing."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv
from agents.self_review_loop import OpenAIClientWrapper
from langsmith import traceable

from db import firebird_client as fb
from memory.agent_memory import AgentMemory, Decision, DecisionType
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

def _get_module_client():
    from openai import OpenAI
    import os
    raw = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    return OpenAIClientWrapper(raw)

# ════════════════════════════════════════════════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS (Agent-specific)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════

def build_evaluation_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 6 to generate evaluation report."""
    training_results = state.get("training_results", {})
    previous_feedback = state.get("feedback", "")
    
    # On revision, include previous feedback
    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"
    
    best_model = max(
        training_results.items(),
        key=lambda x: x[1].get("cv_mean", 0),
        default=("None", {})
    )
    
    prompt = f"""You are a machine learning evaluator.

Training Results:
{json.dumps(training_results, indent=2)[:500]}

Best Model: {best_model[0]}
Best Score: {best_model[1].get('cv_mean', 0):.3f}

Generate a comprehensive evaluation report.

Return a JSON object with:
1. "best_model": the best performing model name
2. "task_type": classification or regression
3. "best_model_metrics": dict with accuracy/rmse/r2
4. "model_comparison": brief comparison of models
5. "feature_importance": top 10 features if available

Be thorough but practical.{revision_note}"""
    
    return prompt


def build_evaluation_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 6 to review its own evaluation."""
    output = state.get("output", "")
    
    prompt = f"""Review this evaluation report for quality, completeness, and correctness:

REPORT:
{output}

Evaluate:
1. Are all trained models compared?
2. Is the best model clearly identified?
3. Are metrics appropriate for the task type?
4. Is the feature importance analysis useful?
5. Is the output valid JSON?

Reply EXACTLY with one of:
APPROVED: [brief explanation of why it's good]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""
    
    return prompt


# ════════════════════════════════════════════════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ════════════════════════════════════════════════════════════════════════════════════════════════════════

def build_evaluation_graph_with_review(llm_client):
    """Build Agent 6 graph with self-review loop."""
    from agents.self_review_loop import (
        create_generate_node,
        create_review_node,
        create_conditional_edge,
    )
    from langgraph.graph import StateGraph, START, END
    
    # Create nodes
    generate = create_generate_node(
        agent_id=6,
        agent_name="Evaluation",
        generate_prompt_fn=build_evaluation_generation_prompt,
        llm_client=llm_client,
    )
    
    review = create_review_node(
        agent_id=6,
        agent_name="Evaluation",
        review_prompt_fn=build_evaluation_review_prompt,
        llm_client=llm_client,
    )
    
    # Create conditional edge
    should_revise = create_conditional_edge(agent_id=6)
    
    # Build graph
    graph = StateGraph(Dict[str, Any])
    
    # Add nodes
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    
    # Add edges
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges(
        "review",
        should_revise,
        {
            "generate": "generate",  # Loop back
            "exit": END,  # Done!
        }
    )
    
    return graph.compile()


# ════════════════════════════════════════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTION
# ════════════════════════════════════════════════════════════════════════════════════════════════════════

@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 6, "agent_name": "Evaluation"})
def run_agent_6_with_review(state: Dict[str, Any], llm_client) -> Dict[str, Any]:
    """
    Run Agent 6 with self-reviewing loop.
    """
    from workflows.agent_state import AgentState, ReviewStatus
    from agents.review_safety import check_loop_safety, log_revision_summary
    
    logger.info("[Agent 6] Starting Evaluation with self-review loop")
    
    # Initialize state for review loop
    agent_state: Dict[str, Any] = {
        **state,
        "output": "",
        "iterations": 0,
        "max_iterations": 1,
        "enable_revision_loop": True,
        "feedback": "",
        "approved": False,
        "revision_count": 0,
        "generation_history": [],
        "feedback_history": [],
        "status": ReviewStatus.GENERATING,
    }
    
    # Build and run graph
    graph = build_evaluation_graph_with_review(llm_client)
    
    # Execute graph
    final_state = graph.invoke(agent_state)
    
    # Log results
    logger.info(
        f"[Agent 6] Complete: "
        f"{final_state['iterations']} iterations, "
        f"{final_state['revision_count']} revisions, "
        f"Status: {final_state['status'].value if hasattr(final_state['status'], 'value') else final_state['status']}"
    )
    
    # Parse evaluation report from output
    try:
        evaluation_report = json.loads(final_state.get("output", "{}"))
    except:
        # Create default evaluation report
        training_results = state.get("training_results", {})
        best_model = max(
            training_results.items(),
            key=lambda x: x[1].get("cv_mean", 0),
            default=("None", {})
        )
        evaluation_report = {
            "best_model": best_model[0],
            "task_type": state.get("task_type", "classification"),
            "best_model_metrics": {"accuracy": best_model[1].get("cv_mean", 0.75)},
            "model_comparison": f"{len(training_results)} models trained",
            "feature_importance": {},
        }
    
    # Record in memory
    if "memory" in state:
        memory: AgentMemory = state["memory"]
        decision = Decision(
            agent_id=6,
            agent_name="Evaluation",
            decision_type=DecisionType.EVALUATION,
            timestamp=datetime.now().isoformat(),
            summary=f"Evaluation complete ({final_state['iterations']} iterations)",
            details={
                "iterations": final_state["iterations"],
                "revision_count": final_state["revision_count"],
                "status": final_state["status"].value if hasattr(final_state["status"], 'value') else str(final_state["status"]),
                "best_model": evaluation_report.get("best_model"),
            },
            confidence=0.95,
            reasoning="Self-reviewed evaluation",
            impact="Final pipeline output for user"
        )
        memory.record_decision(decision)
    
    # Return merged state
    return {
        **state,
        **final_state,
        "evaluation_report": evaluation_report,
        "current_step": "complete",
    }


if __name__ == "__main__":
    client = _get_module_client()
    test_state = {
        "training_results": {
            "LogisticRegression": {"cv_mean": 0.85, "cv_std": 0.02},
            "RandomForest": {"cv_mean": 0.87, "cv_std": 0.03},
        },
        "task_type": "classification",
    }
    result = run_agent_6_with_review(test_state, client)
    print("Best Model:", result.get("evaluation_report", {}).get("best_model"))
