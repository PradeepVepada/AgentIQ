"""LangGraph pipeline state schema.

All six agents read from and write to this TypedDict.
Firebird is the persistence layer; this dict travels inside LangGraph.

For cross-agent memory integration, see memory/agent_memory.py
(Integration Option 2: Keep My Simple Memory + Your LangGraph)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class PipelineState(TypedDict, total=False):
    # ── Project identity ─────────────────────────────────────────────────────
    project_id: str
    project_goal: str
    dataset_path: str
    dataset_name: str
    target_column: Optional[str]
    problem_type: Optional[str]

    # ── Cross-Agent Memory (Decision Journal) ───────────────────────────────
    # Note: memory field holds an AgentMemory instance (see memory/agent_memory.py)
    memory: Optional[Any]
    dynamic_suggestions: List[str]
    previous_decisions: List[Dict[str, Any]]
    known_issues: List[str]
    recovery_hints: List[str]

    # ── EDA Plan (from friend's workflow) ──────────────────────────────────
    eda_plan: Optional[Dict[str, Any]]
    eda_plan_approved: bool
    eda_plan_feedback: Optional[str]

    # ── Agent 1 outputs ──────────────────────────────────────────────────────
    eda_report: Optional[Dict[str, Any]]
    llm_eda_analysis: Optional[Dict[str, Any]]
    eda_approved: bool
    eda_feedback: Optional[str]

    # ── Agent 2 inputs/outputs ───────────────────────────────────────────────
    cleaning_plan: Optional[List[Dict[str, Any]]]
    cleaning_report: Optional[Dict[str, Any]]
    cleaned_data_path: Optional[str]

    # ── Agent 3 outputs ──────────────────────────────────────────────────────
    feature_engineering_plan: Optional[Dict[str, Any]]
    selected_features: Optional[List[str]]
    scaling_requirements: Optional[Dict[str, bool]]
    engineered_data_path: Optional[str]

    # ── Agent 4 outputs ──────────────────────────────────────────────────────
    split_strategy: Optional[Dict[str, Any]]
    candidate_models: Optional[Dict[str, Any]]
    train_idx_path: Optional[str]
    test_idx_path: Optional[str]
    task_type: Optional[str]

    # ── Agent 5 outputs ──────────────────────────────────────────────────────
    training_results: Optional[Dict[str, Any]]
    tuning_results: Optional[Dict[str, Any]]

    # ── Agent 6 outputs ─────────────────────────────────────────────────────
    evaluation_report: Optional[Dict[str, Any]]

    # ── State machine ────────────────────────────────────────────────────────
    current_agent_id: int
    current_step: str
    approval_status: str
    thread_id: Optional[str]

    # ── Human-in-the-loop ───────────────────────────────────────────────────
    human_feedback: Optional[Dict[str, Any]]

    # ── Error / retry ───────────────────────────────────────────────────────
    error: Optional[str]
    errors: List[str]
    retry_count: int
    langsmith_trace_id: Optional[str]
