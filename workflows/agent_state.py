"""State definitions for self-reviewing agents."""
from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class ReviewStatus(Enum):
    """Status of agent review."""
    GENERATING = "generating"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    MAX_ITERATIONS = "max_iterations"


class AgentState(TypedDict, total=False):
    """Base state for all self-reviewing agents."""

    # Input/Output
    input_data: Dict[str, Any]
    output: str

    # Iteration tracking
    iterations: int
    max_iterations: int

    # Review feedback
    feedback: str
    approved: bool
    revision_count: int

    # History tracking
    generation_history: List[str]
    feedback_history: List[str]

    # Status
    status: ReviewStatus

    # Memory integration
    memory: Dict[str, Any]
    previous_decisions: List[Dict]
    dynamic_suggestions: List[str]
