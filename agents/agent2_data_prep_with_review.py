"""Agent 2 — Data Preparation with Self-Reviewing."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
import numpy as np
import pandas as pd
from langsmith import traceable

from db import firebird_client as fb
from memory.agent_memory import AgentMemory, Decision, DecisionType
from tools.data_loader import load_dataset, save_dataset
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS (Agent-specific)
# ═══════════════════════════════════════════════════════════════════════════════════════

def build_data_prep_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 2 to generate cleaning plan."""

    eda_report = state.get("eda_report") or {}
    previous_feedback = state.get("feedback", "")

    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"

    overview = eda_report.get("overview", {}) if isinstance(eda_report, dict) else {}

    # missing_analysis is a LIST of dicts [{column, missing_count, missing_pct, status}, ...]
    missing_list = eda_report.get("missing_analysis", []) if isinstance(eda_report, dict) else []
    if not isinstance(missing_list, list):
        missing_list = []
    cols_with_missing = [m for m in missing_list if isinstance(m, dict) and m.get("missing_pct", 0) > 0]
    total_missing_pct = (
        overview.get("total_missing", 0) / max(overview.get("rows", 1), 1) * 100
    )

    # outlier_analysis is a LIST of dicts [{column, outlier_count, outlier_pct, ...}, ...]
    outlier_list = eda_report.get("outlier_analysis", []) if isinstance(eda_report, dict) else []
    if not isinstance(outlier_list, list):
        outlier_list = []
    cols_with_outliers = [o for o in outlier_list if isinstance(o, dict) and float(o.get("outlier_pct", 0) or 0) > 2]

    # missing mechanisms
    mechanisms = eda_report.get("missing_mechanisms", {}) if isinstance(eda_report, dict) else {}

    prompt = f"""You are a data preparation specialist.

=== DATASET OVERVIEW ===
Rows: {overview.get('rows', 'N/A')}
Columns: {overview.get('columns', 'N/A')}
Duplicate rows: {overview.get('duplicate_rows', 0)}
Total missing: {total_missing_pct:.1f}%

=== COLUMNS WITH MISSING VALUES ===
{json.dumps(cols_with_missing[:15], indent=2) if cols_with_missing else 'None'}

=== MISSING MECHANISMS (MCAR/MAR/MNAR) ===
{json.dumps({k: v for k, v in list(mechanisms.items())[:15]}, indent=2) if mechanisms else 'None'}

=== COLUMNS WITH OUTLIERS (>2%) ===
{json.dumps(cols_with_outliers[:10], indent=2) if cols_with_outliers else 'None'}

Based on the above analysis, generate a comprehensive data cleaning plan.

Return a JSON array of cleaning steps. Each step must have:
- "action": one of ["drop_column", "impute", "remove_outliers", "remove_duplicates", "fix_types"]
- "column": column name (or null for global actions like remove_duplicates)
- "method": specific method (e.g. "median", "mean", "mode", "keep_first", "iqr_cap")
- "reason": why this step is needed

Rules:
- Always include remove_duplicates if duplicate_rows > 0
- For MCAR columns: use mean/median imputation
- For MAR columns: use median imputation
- For MNAR columns: create indicator + impute
- Cap outliers with iqr_cap rather than removing rows

Return ONLY a valid JSON array, no markdown, no extra text.{revision_note}"""

    return prompt


def build_data_prep_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 2 to review its own cleaning plan."""
    
    output = state.get("output", "")
    
    prompt = f"""Review this data cleaning plan for quality, completeness, and correctness:

CLEANING PLAN:
{output}

Evaluate:
1. Are all columns with missing values addressed?
2. Are outlier treatments appropriate?
3. Are duplicate rows handled?
4. Are data type issues fixed?
5. Is the order of operations logical?
6. Are the methods appropriate for the missing data patterns?

Reply EXACTLY with one of:
APPROVED: [brief explanation of why it's good]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""
    
    return prompt


# ═══════════════════════════════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ═══════════════════════════════════════════════════════════════════════════════════════

def build_data_prep_graph_with_review(llm_client) -> "StateGraph":
    """Build Agent 2 graph with self-review loop."""
    from agents.self_review_loop import (
        create_generate_node,
        create_review_node,
        create_conditional_edge,
    )
    from langgraph.graph import StateGraph, START, END
    
    # Create nodes
    generate = create_generate_node(
        agent_id=2,
        agent_name="Data Prep",
        generate_prompt_fn=build_data_prep_generation_prompt,
        llm_client=llm_client,
    )
    
    review = create_review_node(
        agent_id=2,
        agent_name="Data Prep",
        review_prompt_fn=build_data_prep_review_prompt,
        llm_client=llm_client,
    )
    
    # Create conditional edge
    should_revise = create_conditional_edge(agent_id=2)
    
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


# ═══════════════════════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════════════

@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 2, "agent_name": "Data Prep"})
def run_agent_2_with_review(state: Dict[str, Any], llm_client) -> Dict[str, Any]:
    """
    Run Agent 2 with self-reviewing loop.
    """
    logger.info("[Agent 2] Starting Data Prep with self-review loop")
    
    # Get dataset path
    project_id = state.get("PROJECT_ID", "")
    dataset_path = state.get("cleaned_data_path") or state.get("DATASET_PATH", "")
    
    if not dataset_path:
        logger.error("[Agent 2] No dataset path provided")
        return {"error": "No dataset path provided"}
    
    try:
        # Load dataset
        df = load_dataset(dataset_path)
        rows_before = len(df)
        cols_before = len(df.columns)
        
        logger.info(f"[Agent 2] Loaded dataset: {rows_before} rows × {cols_before} cols")
        
        # Build cleaning plan prompt
        eda_report = state.get("EDA_REPORT", {})
        prompt = build_data_prep_generation_prompt({"eda_report": eda_report})
        
        # Generate cleaning plan
        logger.info("[Agent 2] Generating cleaning plan...")
        response = llm_client.invoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        
        # Parse cleaning plan
        try:
            cleaning_plan = json.loads(output)
            if not isinstance(cleaning_plan, list):
                cleaning_plan = []
        except:
            logger.warning("[Agent 2] Failed to parse cleaning plan, using empty plan")
            cleaning_plan = []
        
        logger.info(f"[Agent 2] Generated {len(cleaning_plan)} cleaning steps")
        
        # Execute cleaning plan
        execution_log = []
        
        for step in cleaning_plan:
            action = step.get("action")
            column = step.get("column")
            method = step.get("method", "")
            
            try:
                if action == "remove_duplicates":
                    before = len(df)
                    df = df.drop_duplicates()
                    execution_log.append({"step": step, "status": "success", "rows_removed": before - len(df)})
                
                elif action == "drop_column" and column and column in df.columns:
                    df = df.drop(columns=[column])
                    execution_log.append({"step": step, "status": "success"})
                
                elif action == "impute" and column and column in df.columns:
                    if pd.api.types.is_numeric_dtype(df[column]):
                        if method == "mean":
                            df[column] = df[column].fillna(df[column].mean())
                        elif method == "median":
                            df[column] = df[column].fillna(df[column].median())
                        else:
                            mode_val = df[column].mode()
                            df[column] = df[column].fillna(mode_val.iloc[0] if not mode_val.empty else 0)
                    else:
                        mode_val = df[column].mode()
                        df[column] = df[column].fillna(mode_val.iloc[0] if not mode_val.empty else "Unknown")
                    execution_log.append({"step": step, "status": "success"})
                
                elif action == "remove_outliers" and column and column in df.columns:
                    if pd.api.types.is_numeric_dtype(df[column]):
                        if method == "iqr_cap":
                            q1, q3 = df[column].quantile(0.25), df[column].quantile(0.75)
                            iqr = q3 - q1
                            df[column] = df[column].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
                        else:
                            mean, std = df[column].mean(), df[column].std()
                            df = df[(df[column] >= mean - 3 * std) & (df[column] <= mean + 3 * std)]
                        execution_log.append({"step": step, "status": "success"})
                
                elif action == "fix_types" and column and column in df.columns:
                    try:
                        df[column] = pd.to_numeric(df[column], errors="coerce")
                        execution_log.append({"step": step, "status": "success"})
                    except Exception as e:
                        execution_log.append({"step": step, "status": "skipped", "reason": str(e)})
            
            except Exception as e:
                execution_log.append({"step": step, "status": "failed", "error": str(e)})
        
        # Save cleaned data
        os.makedirs("data/cleaned", exist_ok=True)
        cleaned_path = f"data/cleaned/cleaned_{project_id}.csv"
        save_dataset(df, cleaned_path)
        
        logger.info(f"[Agent 2] Saved cleaned data to {cleaned_path}")
        
        cleaning_report = {
            "shape_before": [rows_before, cols_before],
            "shape_after": [len(df), len(df.columns)],
            "rows_removed": rows_before - len(df),
            "steps_applied": len([e for e in execution_log if e.get("status") == "success"]),
            "execution_log": execution_log,
        }
        
        logger.info(f"[Agent 2] Complete: {len(execution_log)} steps executed")
        
        return {
            "cleaning_report": cleaning_report,
            "cleaned_data_path": cleaned_path,
        }
    
    except Exception as e:
        logger.error(f"[Agent 2] Failed: {e}", exc_info=True)
        return {"error": str(e)}


def execute_cleaning_plan(state: Dict[str, Any], cleaning_plan: List[Dict]) -> Dict[str, Any]:
    """Execute the approved cleaning plan."""
    import os
    from tools.data_loader import load_dataset, save_dataset

    project_id = state.get("PROJECT_ID", "")
    # Use cleaned path if available, else fall back to raw dataset
    dataset_path = state.get("cleaned_data_path") or state.get("DATASET_PATH", "")

    try:
        df = load_dataset(dataset_path)
        rows_before = len(df)
        cols_before = len(df.columns)
        execution_log = []

        for step in cleaning_plan:
            action = step.get("action")
            column = step.get("column")
            method = step.get("method", "")

            try:
                if action == "remove_duplicates":
                    before = len(df)
                    df = df.drop_duplicates()
                    execution_log.append({"step": step, "status": "success", "rows_removed": before - len(df)})

                elif action == "drop_column" and column and column in df.columns:
                    df = df.drop(columns=[column])
                    execution_log.append({"step": step, "status": "success"})

                elif action == "impute" and column and column in df.columns:
                    if pd.api.types.is_numeric_dtype(df[column]):
                        if method == "mean":
                            df[column] = df[column].fillna(df[column].mean())
                        elif method == "median":
                            df[column] = df[column].fillna(df[column].median())
                        else:  # mode or anything else
                            mode_val = df[column].mode()
                            df[column] = df[column].fillna(mode_val.iloc[0] if not mode_val.empty else 0)
                    else:
                        mode_val = df[column].mode()
                        df[column] = df[column].fillna(mode_val.iloc[0] if not mode_val.empty else "Unknown")
                    execution_log.append({"step": step, "status": "success"})

                elif action == "remove_outliers" and column and column in df.columns:
                    if pd.api.types.is_numeric_dtype(df[column]):
                        if method == "iqr_cap":
                            q1, q3 = df[column].quantile(0.25), df[column].quantile(0.75)
                            iqr = q3 - q1
                            df[column] = df[column].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
                        else:  # remove rows
                            mean, std = df[column].mean(), df[column].std()
                            df = df[(df[column] >= mean - 3 * std) & (df[column] <= mean + 3 * std)]
                        execution_log.append({"step": step, "status": "success"})

                elif action == "fix_types" and column and column in df.columns:
                    try:
                        df[column] = pd.to_numeric(df[column], errors="coerce")
                        execution_log.append({"step": step, "status": "success"})
                    except Exception as e:
                        execution_log.append({"step": step, "status": "skipped", "reason": str(e)})

            except Exception as e:
                execution_log.append({"step": step, "status": "failed", "error": str(e)})

        # Save cleaned data
        os.makedirs("data/cleaned", exist_ok=True)
        cleaned_path = f"data/cleaned/cleaned_{project_id}.csv"
        save_dataset(df, cleaned_path)

        cleaning_report = {
            "shape_before": [rows_before, cols_before],
            "shape_after": [len(df), len(df.columns)],
            "rows_removed": rows_before - len(df),
            "steps_applied": len([e for e in execution_log if e.get("status") == "success"]),
            "execution_log": execution_log,
        }

        return {
            "cleaning_report": cleaning_report,
            "cleaned_data_path": cleaned_path,
            "current_step": "prep_review",
        }

    except Exception as e:
        logger.error("[Agent 2] Cleaning failed: %s", e)
        return {"error": str(e), "current_step": "prep_error"}
