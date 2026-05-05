"""Agent 5 — Training & Tuning with Self-Reviewing."""

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


def _build_model_instances(task_type: str) -> dict:
    """Build sklearn model instances for the given task type."""
    from sklearn.linear_model import LogisticRegression, Ridge, Lasso
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

    if task_type == "classification":
        models = {
            "LogisticRegression": LogisticRegression(max_iter=500, random_state=42),
            "RandomForest": RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
            "GradientBoosting": GradientBoostingClassifier(n_estimators=100, random_state=42),
            "DecisionTree": DecisionTreeClassifier(max_depth=8, random_state=42),
            "KNN": KNeighborsClassifier(n_neighbors=5),
        }
        try:
            from xgboost import XGBClassifier
            models["XGBoost"] = XGBClassifier(n_estimators=100, random_state=42, verbosity=0, eval_metric="logloss")
        except ImportError:
            pass
        try:
            from lightgbm import LGBMClassifier
            models["LightGBM"] = LGBMClassifier(n_estimators=100, random_state=42, verbose=-1)
        except ImportError:
            pass
    else:
        models = {
            "Ridge": Ridge(alpha=1.0),
            "RandomForestRegressor": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
            "GradientBoostingRegressor": GradientBoostingRegressor(n_estimators=100, random_state=42),
            "DecisionTreeRegressor": DecisionTreeRegressor(max_depth=8, random_state=42),
            "KNNRegressor": KNeighborsRegressor(n_neighbors=5),
        }
        try:
            from xgboost import XGBRegressor
            models["XGBRegressor"] = XGBRegressor(n_estimators=100, random_state=42, verbosity=0)
        except ImportError:
            pass

    return models

# ════════════════════════════════════════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS (Agent-specific)
# ════════════════════════════════════════════════════════════════════════════════════════════════

def build_training_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 5 to generate training plan."""
    candidate_models = state.get("candidate_models", {})
    split_strategy = state.get("split_strategy", {})
    previous_feedback = state.get("feedback", "")
    
    # On revision, include previous feedback
    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"
    
    prompt = f"""You are a machine learning engineer.
    
Candidate Models: {json.dumps(list(candidate_models.keys())[:5], indent=2)}
Split Strategy: {json.dumps(split_strategy, indent=2)[:300]}

Generate a training configuration.

Return a JSON object with:
1. "training_config": dict with model-specific hyperparameters
2. "tuning_config": dict with Optuna search spaces
3. "cv_folds": number (3-5)
4. "metrics_to_track": list of metrics

Be comprehensive but practical.{revision_note}"""
    
    return prompt


def build_training_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 5 to review its own training plan."""
    output = state.get("output", "")
    
    prompt = f"""Review this training configuration for quality, completeness, and correctness:

CONFIGURATION:
{output}

Evaluate:
1. Are hyperparameters appropriate for each model?
2. Is the tuning configuration reasonable?
3. Are CV folds appropriate?
4. Are metrics relevant for the task?
5. Is the output valid JSON?

Reply EXACTLY with one of:
APPROVED: [brief explanation of why it's good]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""
    
    return prompt


# ════════════════════════════════════════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ════════════════════════════════════════════════════════════════════════════════════════════════

def build_training_graph_with_review(llm_client):
    """Build Agent 5 graph with self-review loop."""
    from agents.self_review_loop import (
        create_generate_node,
        create_review_node,
        create_conditional_edge,
    )
    from langgraph.graph import StateGraph, START, END
    
    # Create nodes
    generate = create_generate_node(
        agent_id=5,
        agent_name="Training",
        generate_prompt_fn=build_training_generation_prompt,
        llm_client=llm_client,
    )
    
    review = create_review_node(
        agent_id=5,
        agent_name="Training",
        review_prompt_fn=build_training_review_prompt,
        llm_client=llm_client,
    )
    
    # Create conditional edge
    should_revise = create_conditional_edge(agent_id=5)
    
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


# ════════════════════════════════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTION
# ════════════════════════════════════════════════════════════════════════════════════════════════

@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 5, "agent_name": "Training"})
def run_agent_5_with_review(state: Dict[str, Any], llm_client) -> Dict[str, Any]:
    """
    Run Agent 5 with self-reviewing loop.
    """
    from workflows.agent_state import AgentState, ReviewStatus
    from agents.review_safety import check_loop_safety, log_revision_summary
    
    logger.info("[Agent 5] Starting Training with self-review loop")
    
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
    graph = build_training_graph_with_review(llm_client)
    
    # Execute graph
    final_state = graph.invoke(agent_state)
    
    # Log results
    logger.info(
        f"[Agent 5] Complete: "
        f"{final_state['iterations']} iterations, "
        f"{final_state['revision_count']} revisions, "
        f"Status: {final_state['status'].value if hasattr(final_state['status'], 'value') else final_state['status']}"
    )
    
    # Parse training config from output
    try:
        training_config = json.loads(final_state.get("output", "{}"))
    except:
        training_config = {
            "training_config": {},
            "tuning_config": {},
            "cv_folds": 3,
            "metrics_to_track": ["accuracy" if state.get("task_type") == "classification" else "r2"],
        }
    
    # Execute real training
    logger.info("[Agent 5] Executing real model training...")
    training_results = {}
    tuning_results = {}

    try:
        import numpy as np
        from tools.data_loader import load_dataset

        # Load engineered data
        data_path = state.get("engineered_data_path") or state.get("cleaned_data_path") or state.get("DATASET_PATH", "")
        feature_plan = state.get("feature_engineering_plan") or {}
        target_col = feature_plan.get("target_column")
        task_type = state.get("task_type", "classification")
        candidate_models = state.get("candidate_models", {})

        if data_path and os.path.exists(data_path) and target_col:
            df = load_dataset(data_path)

            if target_col not in df.columns:
                # Try last column as target
                target_col = df.columns[-1]

            # Drop rows with missing target
            df = df.dropna(subset=[target_col])

            # Separate features and target
            feature_cols = [c for c in df.columns if c != target_col]
            X = df[feature_cols].copy()
            y = df[target_col].copy()

            # Handle remaining missing values
            for col in X.select_dtypes(include=[np.number]).columns:
                X[col] = X[col].fillna(X[col].median())

            # Drop non-numeric columns
            X = X.select_dtypes(include=[np.number])

            if len(X) > 10 and len(X.columns) > 0:
                from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold
                from sklearn.preprocessing import LabelEncoder, StandardScaler
                from sklearn.pipeline import Pipeline

                # Encode target if classification
                if task_type == "classification":
                    le = LabelEncoder()
                    y_enc = le.fit_transform(y.astype(str))
                    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
                    scoring = "f1_weighted"
                else:
                    y_enc = y.values
                    cv = KFold(n_splits=3, shuffle=True, random_state=42)
                    scoring = "r2"

                # Build model instances
                model_map = _build_model_instances(task_type)

                models_to_train = list(candidate_models.keys())[:4] if candidate_models else list(model_map.keys())[:4]

                for model_name in models_to_train:
                    if model_name not in model_map:
                        continue
                    try:
                        needs_scaling = candidate_models.get(model_name, {}).get("needs_scaling", 0)
                        if needs_scaling:
                            pipe = Pipeline([("scaler", StandardScaler()), ("model", model_map[model_name])])
                        else:
                            pipe = model_map[model_name]

                        scores = cross_val_score(pipe, X, y_enc, cv=cv, scoring=scoring, n_jobs=-1)
                        training_results[model_name] = {
                            "cv_mean": round(float(scores.mean()), 4),
                            "cv_std": round(float(scores.std()), 4),
                            "cv_scores": [round(float(s), 4) for s in scores],
                            "scoring": scoring,
                            "n_samples": len(X),
                            "n_features": len(X.columns),
                        }
                        tuning_results[model_name] = {
                            "best_params": {},
                            "best_score": round(float(scores.mean()), 4),
                            "status": "cv_complete",
                        }
                        logger.info("[Agent 5] %s: %.4f ± %.4f", model_name, scores.mean(), scores.std())
                    except Exception as e:
                        logger.warning("[Agent 5] %s failed: %s", model_name, e)
                        training_results[model_name] = {"cv_mean": 0.0, "cv_std": 0.0, "error": str(e)}
            else:
                logger.warning("[Agent 5] Not enough data to train: %d rows, %d features", len(X), len(X.columns))
        else:
            logger.warning("[Agent 5] No valid data path or target column")

    except Exception as e:
        logger.error("[Agent 5] Training execution failed: %s", e)

    # Fallback if nothing trained
    if not training_results:
        for model_name in list(state.get("candidate_models", {}).keys())[:3]:
            training_results[model_name] = {"cv_mean": 0.0, "cv_std": 0.0, "status": "failed"}
            tuning_results[model_name] = {"best_score": 0.0, "status": "failed"}
    
    # Record in memory
    if "memory" in state:
        memory: AgentMemory = state["memory"]
        decision = Decision(
            agent_id=5,
            agent_name="Training",
            decision_type=DecisionType.TRAINING,
            timestamp=datetime.now().isoformat(),
            summary=f"Training complete ({final_state['iterations']} iterations)",
            details={
                "iterations": final_state["iterations"],
                "revision_count": final_state["revision_count"],
                "status": final_state["status"].value if hasattr(final_state["status"], 'value') else str(final_state["status"]),
                "models_trained": len(training_results),
            },
            confidence=0.9,
            reasoning="Self-reviewed training configuration",
            impact="Provides trained models for Agent 6 evaluation"
        )
        memory.record_decision(decision)
    
    # Return merged state
    return {
        **state,
        **final_state,
        "training_results": training_results,
        "tuning_results": tuning_results,
        "current_step": "training_review",
    }


if __name__ == "__main__":
    client = _get_module_client()
    test_state = {
        "candidate_models": {
            "LogisticRegression": {"needs_scaling": 1, "model_family": "LogisticRegression"},
            "RandomForest": {"needs_scaling": 0, "model_family": "RandomForestClassifier"},
        },
        "split_strategy": {"task_type": "classification", "test_size": 0.2},
        "task_type": "classification",
    }
    result = run_agent_5_with_review(test_state, client)
    print("Training results:", bool(result.get("training_results")))
