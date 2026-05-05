"""Agent 1 — Data Intake & EDA with self-reviewing loop."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict

from langsmith import traceable
from langgraph.graph import StateGraph, START, END

from workflows.agent_state import AgentState, ReviewStatus
from agents.self_review_loop import (
    create_generate_node,
    create_review_node,
    create_conditional_edge,
)
from tools.eda_tools import compile_full_eda, detect_column_types
from tools.data_loader import load_dataset
from memory.agent_memory import AgentMemory, Decision, DecisionType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def build_eda_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt using real EDA data already computed from the dataset."""
    eda_data = state.get("_eda_data", {})
    overview = eda_data.get("overview", {})
    col_types = eda_data.get("column_types", {})
    missing = eda_data.get("missing_analysis", [])
    outliers = eda_data.get("outlier_analysis", [])
    correlations = eda_data.get("correlation_analysis", [])
    stats = eda_data.get("statistical_analysis", [])
    mechanisms = eda_data.get("missing_mechanisms", {})
    previous_feedback = state.get("feedback", "")

    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"

    # Summarise missing columns
    high_missing = [m for m in missing if m.get("missing_pct", 0) > 5]
    high_missing_summary = json.dumps(high_missing[:10], indent=2) if high_missing else "None"

    # Summarise outliers
    high_outliers = [o for o in outliers if float(o.get("outlier_pct", 0) or 0) > 5]
    outlier_summary = json.dumps(high_outliers[:10], indent=2) if high_outliers else "None"

    # Summarise correlations
    corr_summary = json.dumps(correlations[:10], indent=2) if correlations else "None"

    # Stats summary (first 5 numeric cols)
    stats_summary = json.dumps(stats[:5], indent=2) if stats else "None"

    prompt = f"""You are a senior data scientist performing exploratory data analysis.

=== DATASET OVERVIEW ===
Rows: {overview.get('rows', 0):,}
Columns: {overview.get('columns', 0)}
Duplicate rows: {overview.get('duplicate_rows', 0)}
Total missing values: {overview.get('total_missing', 0)}
Numeric columns: {overview.get('numeric_count', 0)}
Categorical columns: {overview.get('categorical_count', 0)}
ID columns: {overview.get('id_count', 0)}

=== COLUMN TYPES ===
Numeric: {col_types.get('numeric', [])}
Categorical: {col_types.get('categorical', [])}
Date: {col_types.get('date', [])}
ID: {col_types.get('id', [])}

=== MISSING VALUES (columns with >5% missing) ===
{high_missing_summary}

=== MISSING MECHANISMS (MCAR/MAR/MNAR) ===
{json.dumps(dict(list(mechanisms.items())[:10]), indent=2)}

=== STATISTICAL SUMMARY (first 5 numeric cols) ===
{stats_summary}

=== OUTLIERS (columns with >5% outliers) ===
{outlier_summary}

=== STRONG CORRELATIONS (|r| >= 0.7) ===
{corr_summary}

Based on the above real data analysis, generate a comprehensive EDA report as a JSON object with these keys:
- "overview": summary of dataset shape, quality
- "data_quality": {{"score": 0-10, "issues": [list of issues]}}
- "missing_analysis_summary": key findings about missing data
- "outlier_summary": key findings about outliers
- "correlation_summary": key findings about correlations
- "key_findings": list of 5-7 most important findings
- "recommendations": list of actionable recommendations for data preparation
- "target_column_suggestion": most likely target column based on column names
- "task_type_suggestion": "classification", "regression", or "clustering"

Return ONLY valid JSON, no markdown, no extra text.{revision_note}"""

    return prompt


def build_eda_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 1 to review its own EDA."""
    output = state.get("output", "")

    prompt = f"""Review this EDA report for quality, completeness, and accuracy:

REPORT:
{output[:3000]}

Evaluate:
1. Does it include data quality score (0-10)?
2. Are key findings specific and actionable?
3. Are missing data mechanisms (MCAR/MAR/MNAR) addressed?
4. Is a target column and task type suggested?
5. Is the output valid JSON?

Reply EXACTLY with one of:
APPROVED: [brief explanation]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""

    return prompt


# ═══════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ═══════════════════════════════════════════════════════════════

def build_eda_graph_with_review(llm_client) -> StateGraph:
    """Build Agent 1 graph with self-review loop."""
    generate = create_generate_node(
        agent_id=1,
        agent_name="EDA",
        generate_prompt_fn=build_eda_generation_prompt,
        llm_client=llm_client,
    )
    review = create_review_node(
        agent_id=1,
        agent_name="EDA",
        review_prompt_fn=build_eda_review_prompt,
        llm_client=llm_client,
    )
    should_revise = create_conditional_edge(agent_id=1)

    graph = StateGraph(dict)
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges("review", should_revise, {"generate": "generate", "exit": END})
    return graph.compile()


# ═══════════════════════════════════════════════════════════════
# INTEGRATION WITH MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════

def run_agent_1_with_review(state: dict, llm_client) -> dict:
    """
    Run Agent 1: load dataset, run full EDA, then use LLM to generate
    a structured analysis report with self-review.
    """
    logger.info("[Agent 1] Starting EDA with self-review loop")

    project_id = state.get("PROJECT_ID", "")
    dataset_path = state.get("DATASET_PATH", "")

    # ── Step 1: Load dataset and run statistical EDA ──────────────────────
    eda_data = {}
    try:
        logger.info("[Agent 1] Loading dataset from: %s", dataset_path)
        df = load_dataset(dataset_path)
        logger.info("[Agent 1] Dataset loaded: %d rows × %d cols", len(df), len(df.columns))
        logger.info("[Agent 1] Starting statistical EDA...")
        eda_data = compile_full_eda(df)
        logger.info("[Agent 1] Statistical EDA complete")
    except Exception as e:
        logger.error("[Agent 1] Failed to load/analyse dataset: %s", e, exc_info=True)
        eda_data = {
            "overview": {"rows": 0, "columns": 0, "error": str(e)},
            "column_types": {},
            "missing_analysis": [],
            "statistical_analysis": [],
            "univariate_analysis": [],
            "outlier_analysis": [],
            "correlation_analysis": [],
            "categorical_summary": [],
            "missing_mechanisms": {},
        }

    # ── Step 2: Run LLM self-review loop ──────────────────────────────────
    agent_state: Dict[str, Any] = {
        **state,
        "_eda_data": eda_data,          # real data for prompt building
        "output": "",
        "iterations": 0,
        "max_iterations": 1,  # Single iteration for speed
        "enable_revision_loop": False,  # Disabled for thesis presentation speed
        "feedback": "",
        "approved": False,
        "revision_count": 0,
        "generation_history": [],
        "feedback_history": [],
        "status": ReviewStatus.GENERATING,
    }

    graph = build_eda_graph_with_review(llm_client)
    final_state = graph.invoke(agent_state)

    logger.info(
        "[Agent 1] Complete: %d iterations, %d revisions, status=%s",
        final_state.get("iterations", 0),
        final_state.get("revision_count", 0),
        final_state.get("status"),
    )

    # ── Step 3: Parse LLM output and merge with statistical EDA ───────────
    llm_analysis = {}
    try:
        raw_output = final_state.get("output", "")
        # Strip markdown fences if present
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_output:
            raw_output = raw_output.split("```")[1].split("```")[0].strip()
        llm_analysis = json.loads(raw_output)
    except Exception as e:
        logger.warning("[Agent 1] Could not parse LLM JSON output: %s", e)
        llm_analysis = {"raw_output": final_state.get("output", ""), "parse_error": str(e)}

    # Merge statistical EDA with LLM analysis
    full_eda_report = {
        **eda_data,
        "llm_analysis": llm_analysis,
        "target_column_suggestion": llm_analysis.get("target_column_suggestion"),
        "task_type_suggestion": llm_analysis.get("task_type_suggestion", "classification"),
        "data_quality": llm_analysis.get("data_quality", {"score": 0, "issues": []}),
        "key_findings": llm_analysis.get("key_findings", []),
        "recommendations": llm_analysis.get("recommendations", []),
    }

    # ── Step 4: Record in memory ───────────────────────────────────────────
    if "memory" in state and state["memory"] is not None:
        try:
            memory: AgentMemory = state["memory"]
            decision = Decision(
                agent_id=1,
                agent_name="EDA",
                decision_type=DecisionType.ANALYSIS,
                timestamp=datetime.now().isoformat(),
                summary=f"EDA complete ({final_state.get('iterations', 0)} iterations)",
                details={
                    "iterations": final_state.get("iterations", 0),
                    "revision_count": final_state.get("revision_count", 0),
                    "rows": eda_data.get("overview", {}).get("rows", 0),
                    "columns": eda_data.get("overview", {}).get("columns", 0),
                    "total_missing_pct": (
                        eda_data.get("overview", {}).get("total_missing", 0) /
                        max(eda_data.get("overview", {}).get("rows", 1), 1) * 100
                    ),
                    "duplicate_rows": eda_data.get("overview", {}).get("duplicate_rows", 0),
                    "quality_score": llm_analysis.get("data_quality", {}).get("score", 0),
                },
                confidence=0.95,
                reasoning="Self-reviewed EDA analysis with real statistical data",
                impact="Informs Agent 2 data cleaning strategy",
            )
            memory.record_decision(decision)
        except Exception as e:
            logger.warning("[Agent 1] Memory record failed: %s", e)

    return {
        **state,
        "eda_report": full_eda_report,
        "llm_eda_analysis": llm_analysis,
        "current_step": "eda_review",
        "task_type": llm_analysis.get("task_type_suggestion", "classification"),
    }
