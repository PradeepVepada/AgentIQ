"""Agent 3 — Feature Engineering with Self-Reviewing."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from agents.self_review_loop import OpenAIClientWrapper
import numpy as np
import pandas as pd
from langsmith import traceable

from db import firebird_client as fb
from memory.agent_memory import AgentMemory, Decision, DecisionType
from tools.data_loader import load_dataset
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

# Module-level client — used only when agents are run standalone (not via main.py)
def _get_module_client():
    from openai import OpenAI
    import os
    raw = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    return OpenAIClientWrapper(raw)

# ════════════════════════════════════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS (Agent-specific)
# ════════════════════════════════════════════════════════════════════════════════════════════

def build_feature_eng_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 3 using real column names from EDA."""

    eda_report = state.get("eda_report") or {}
    previous_feedback = state.get("feedback", "")

    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"

    overview = eda_report.get("overview", {}) if isinstance(eda_report, dict) else {}
    col_types = eda_report.get("column_types", {}) if isinstance(eda_report, dict) else {}
    numeric_cols = col_types.get("numeric", [])
    cat_cols = col_types.get("categorical", [])
    id_cols = col_types.get("id", [])

    # Get LLM suggestions from agent 1
    llm_analysis = eda_report.get("llm_analysis", {}) if isinstance(eda_report, dict) else {}
    target_suggestion = eda_report.get("target_column_suggestion") or llm_analysis.get("target_column_suggestion", "")
    task_suggestion = eda_report.get("task_type_suggestion") or state.get("task_type", "classification")

    # Correlation info
    corr_list = eda_report.get("correlation_analysis", []) if isinstance(eda_report, dict) else []
    high_corr = [c for c in corr_list if isinstance(c, dict) and abs(float(c.get("correlation", 0) or 0)) >= 0.8]

    prompt = f"""You are a feature engineer.

=== DATASET INFO ===
Rows: {overview.get('rows', 'N/A')}
Columns: {overview.get('columns', 'N/A')}
Suggested target column: {target_suggestion}
Suggested task type: {task_suggestion}

=== NUMERIC COLUMNS ===
{numeric_cols}

=== CATEGORICAL COLUMNS ===
{cat_cols}

=== ID COLUMNS (exclude from features) ===
{id_cols}

=== HIGH CORRELATIONS (|r| >= 0.8, consider dropping one) ===
{json.dumps(high_corr[:10], indent=2) if high_corr else 'None'}

Generate a feature engineering plan. Return a JSON object with:
1. "target_column": the target column name (from the numeric/categorical list above)
2. "task_type": "classification" or "regression"
3. "selected_features": list of feature column names to use (exclude target and ID columns)
4. "encode_columns": list of categorical columns to one-hot encode
5. "scale_columns": list of numeric columns that need scaling
6. "drop_columns": list of columns to drop (high correlation duplicates, IDs)
7. "correlation_threshold": 0.85
8. "notes": brief explanation of choices

Return ONLY valid JSON, no markdown.{revision_note}"""

    return prompt


def build_feature_eng_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 3 to review its own feature engineering."""
    
    output = state.get("output", "")
    
    prompt = f"""Review this feature engineering plan for quality, completeness, and correctness:

PLAN:
{output}

Evaluate:
1. Are all relevant features included?
2. Is the target column correct?
3. Are feature selection methods appropriate?
4. Is the polynomial degree reasonable?
5. Are correlation thresholds appropriate?

Reply EXACTLY with one of:
APPROVED: [brief explanation of why it's good]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""
    
    return prompt


# ════════════════════════════════════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ════════════════════════════════════════════════════════════════════════════════════════════

def build_feature_eng_graph_with_review(llm_client):
    """Build Agent 3 graph with self-review loop."""
    from agents.self_review_loop import (
        create_generate_node,
        create_review_node,
        create_conditional_edge,
    )
    from langgraph.graph import StateGraph, START, END
    
    # Create nodes
    generate = create_generate_node(
        agent_id=3,
        agent_name="Feature Engineering",
        generate_prompt_fn=build_feature_eng_generation_prompt,
        llm_client=llm_client,
    )
    
    review = create_review_node(
        agent_id=3,
        agent_name="Feature Engineering",
        review_prompt_fn=build_feature_eng_review_prompt,
        llm_client=llm_client,
    )
    
    # Create conditional edge
    should_revise = create_conditional_edge(agent_id=3)
    
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


# ════════════════════════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION FUNCTION
# ════════════════════════════════════════════════════════════════════════════════════════════

@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 3, "agent_name": "Feature Engineering"})
def run_agent_3_with_review(state: Dict[str, Any], llm_client) -> Dict[str, Any]:
    """
    Run Agent 3 with self-reviewing loop.
    """
    logger.info("[Agent 3] Starting Feature Engineering with self-review loop")
    
    project_id = state.get("PROJECT_ID", "")
    data_path = state.get("cleaned_data_path") or state.get("DATASET_PATH", "")
    
    if not data_path:
        logger.error("[Agent 3] No data path provided")
        return {"error": "No data path provided"}
    
    try:
        # Load cleaned data
        df = load_dataset(data_path)
        logger.info(f"[Agent 3] Loaded data: {len(df)} rows × {len(df.columns)} cols")
        
        # ========== DETERMINISTIC FEATURE SELECTION ==========
        import numpy as np
        
        eda_report = state.get("EDA_REPORT", {})
        if isinstance(eda_report, str):
            try:
                eda_report = json.loads(eda_report)
            except:
                eda_report = {}
        
        # Get target column
        target = eda_report.get("target_column_suggestion")
        
        # Separate numeric and categorical
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        # Calculate correlation with target
        feature_importance = {}
        if target and target in numeric_cols:
            for col in numeric_cols:
                if col != target:
                    try:
                        corr = df[col].corr(df[target])
                        feature_importance[col] = abs(corr) if not pd.isna(corr) else 0
                    except:
                        feature_importance[col] = 0
        
        # Sort by importance
        sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
        
        # Select top 15 numeric features
        top_n = min(15, len(sorted_features))
        selected_numeric = [f[0] for f in sorted_features[:top_n]]
        
        # Remove highly correlated duplicates
        corr_matrix = df[numeric_cols].corr().abs()
        upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        to_drop = [col for col in upper_tri.columns if any(upper_tri[col] > 0.85)]
        selected_numeric = [f for f in selected_numeric if f not in to_drop]
        
        deterministic_features = selected_numeric + categorical_cols
        
        logger.info(f"[Agent 3] Deterministic selection: {len(deterministic_features)} features")
        
        # Store stats for dashboard
        feature_stats = {
            "total_features": len(df.columns) - 1,
            "selected_features": len(deterministic_features),
            "top_features": sorted_features[:10]
        }
        
        # ========== BUILD FEATURE PLAN ==========
        prompt = build_feature_eng_generation_prompt({"eda_report": eda_report})
        
        # Generate feature engineering plan
        logger.info("[Agent 3] Generating feature engineering plan...")
        response = llm_client.invoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        
        # Parse feature plan
        try:
            feature_plan = json.loads(output)
            if not isinstance(feature_plan, dict):
                feature_plan = {}
        except:
            logger.warning("[Agent 3] Failed to parse feature plan, using defaults")
            feature_plan = {
                "target_column": eda_report.get("target_column_suggestion"),
                "task_type": eda_report.get("task_type_suggestion", "classification"),
                "selected_features": list(df.columns),
                "encode_columns": [],
                "drop_columns": [],
            }
        
        logger.info(f"[Agent 3] Generated feature plan with {len(feature_plan.get('selected_features', []))} features")
        
        # Execute feature engineering
        target = feature_plan.get("target_column")
        selected_features = feature_plan.get("selected_features", list(df.columns))
        encode_columns = feature_plan.get("encode_columns", [])
        drop_columns = feature_plan.get("drop_columns", [])
        
        # Drop explicitly flagged columns
        cols_to_drop = [c for c in drop_columns if c in df.columns and c != target]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
        
        # One-hot encode categorical columns
        for col in encode_columns:
            if col in df.columns and col != target:
                dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
                df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
        
        # Keep only selected features + target
        if selected_features and target:
            valid_features = [c for c in selected_features if c in df.columns and c != target]
            if valid_features:
                keep_cols = valid_features + ([target] if target in df.columns else [])
                df = df[keep_cols]
        
        # Save engineered data
        os.makedirs("data/engineered", exist_ok=True)
        engineered_path = f"data/engineered/engineered_{project_id}.csv"
        from tools.data_loader import save_dataset
        save_dataset(df, engineered_path)
        
        logger.info(f"[Agent 3] Saved engineered data to {engineered_path}")
        
        return {
            "feature_engineering_plan": feature_plan,
            "selected_features": selected_features,
            "engineered_data_path": engineered_path,
            "feature_stats": feature_stats,  # Add stats for dashboard
        }
    
    except Exception as e:
        logger.error(f"[Agent 3] Failed: {e}", exc_info=True)
        return {"error": str(e)}


def execute_feature_engineering(state: Dict[str, Any], feature_plan: Dict) -> str:
    """Execute the feature engineering plan."""
    import os
    from tools.data_loader import load_dataset, save_dataset

    project_id = state.get("PROJECT_ID", "")
    # Use cleaned data if available, else raw
    data_path = state.get("cleaned_data_path") or state.get("DATASET_PATH", "")

    if not data_path or not os.path.exists(data_path):
        raise ValueError(f"No valid data path found: {data_path}")

    df = load_dataset(data_path)

    target = feature_plan.get("target_column")
    selected_features = feature_plan.get("selected_features", [])
    encode_columns = feature_plan.get("encode_columns", [])
    drop_columns = feature_plan.get("drop_columns", [])

    # Drop explicitly flagged columns
    cols_to_drop = [c for c in drop_columns if c in df.columns and c != target]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    # One-hot encode categorical columns
    for col in encode_columns:
        if col in df.columns and col != target:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
            df = pd.concat([df.drop(columns=[col]), dummies], axis=1)

    # Keep only selected features + target
    if selected_features and target:
        valid_features = [c for c in selected_features if c in df.columns and c != target]
        if valid_features:
            keep_cols = valid_features + ([target] if target in df.columns else [])
            df = df[keep_cols]

    # Save
    os.makedirs("data/engineered", exist_ok=True)
    engineered_path = f"data/engineered/engineered_{project_id}.csv"
    save_dataset(df, engineered_path)
    return engineered_path


if __name__ == "__main__":
    client = _get_module_client()
    test_state = {
        "project_id": "test-123",
        "cleaned_data_path": "data/cleaned/test.csv",
        "eda_report": {"overview": {"target_column": "target"}},
    }
    result = run_agent_3_with_review(test_state, client)
    print("Features:", result.get("selected_features"))
