"""Agent 4 — Model Architecture with Self-Reviewing."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

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

# ══════════════════════════════════════════════════════════════════
# PROMPT FUNCTIONS (Agent-specific)
# ══════════════════════════════════════════════════════════════════

def build_model_arch_generation_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 4 to select models."""
    
    feature_plan = state.get("feature_engineering_plan", {})
    eda_report = state.get("eda_report", {})
    previous_feedback = state.get("feedback", "")
    
    # On revision, include previous feedback
    revision_note = ""
    if state.get("revision_count", 0) > 0:
        revision_note = f"\n\nPrevious feedback to address:\n{previous_feedback}"
    
    task_type = feature_plan.get("task_type", "classification")
    target = feature_plan.get("target_column", "target")
    features = feature_plan.get("selected_features", [])[:20]
    
    prompt = f"""You are a machine learning architect.

Task: {task_type}
Target Column: {target}
Available Features: {features}

Based on the feature engineering plan and EDA report, select the best candidate models.

Return a JSON object with:
1. "candidate_models": dict where keys are model names and values are dict with "needs_scaling" (0 or 1) and "model_family"
2. "split_strategy": dict with "task_type", "test_size" (0.2), "stratify" (target column if classification)

For {task_type}, recommend these model types:
- Classification: LogisticRegression, SVM_RBF, SVM_Linear, KNN, RandomForest, XGBoost, LightGBM, GradientBoosting, ExtraTrees, GaussianNB
- Regression: LinearRegression, Ridge, Lasso, ElasticNet, SVR, KNN, RandomForestRegressor, XGBRegressor, LGBMRegressor, GradientBoostingRegressor, ExtraTreesRegressor
- Clustering: KMeans, GaussianMixture

Be thorough but practical.{revision_note}"""
    
    return prompt


def build_model_arch_review_prompt(state: Dict[str, Any]) -> str:
    """Build prompt for Agent 4 to review its own model selection."""
    
    output = state.get("output", "")
    
    prompt = f"""Review this model architecture plan for quality, completeness, and correctness:

PLAN:
{output}

Evaluate:
1. Are candidate models appropriate for the task type?
2. Is the split strategy reasonable?
3. Are scaling requirements correct?
4. Are there enough diverse model types?
5. Is the output valid JSON?

Reply EXACTLY with one of:
APPROVED: [brief explanation of why it's good]
NEEDS_REVISION: [specific improvements needed]

Do NOT include any other text."""
    
    return prompt


# ══════════════════════════════════════════════════════════════════
# BUILD THE SELF-REVIEWING GRAPH
# ══════════════════════════════════════════════════════════════════

def build_model_arch_graph_with_review(llm_client):
    """Build Agent 4 graph with self-review loop."""
    from agents.self_review_loop import (
        create_generate_node,
        create_review_node,
        create_conditional_edge,
    )
    from langgraph.graph import StateGraph, START, END
    
    # Create nodes
    generate = create_generate_node(
        agent_id=4,
        agent_name="Model Architecture",
        generate_prompt_fn=build_model_arch_generation_prompt,
        llm_client=llm_client,
    )
    
    review = create_review_node(
        agent_id=4,
        agent_name="Model Architecture",
        review_prompt_fn=build_model_arch_review_prompt,
        llm_client=llm_client,
    )
    
    # Create conditional edge
    should_revise = create_conditional_edge(agent_id=4)
    
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


# ══════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTION
# ══════════════════════════════════════════════════════════════════

@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 4, "agent_name": "Model Architecture"})
def run_agent_4_with_review(state: Dict[str, Any], llm_client) -> Dict[str, Any]:
    """
    Run Agent 4 with self-reviewing loop.
    """
    logger.info("[Agent 4] Starting Model Architecture with self-review loop")
    
    try:
        # Get feature engineering plan
        feature_plan = state.get("feature_engineering_plan", {})
        task_type = feature_plan.get("task_type", "classification")
        target_column = feature_plan.get("target_column")
        selected_features = feature_plan.get("selected_features", [])
        
        # Build model architecture prompt
        prompt = build_model_arch_generation_prompt({
            "feature_engineering_plan": feature_plan,
            "eda_report": state.get("EDA_REPORT", {}),
        })
        
        # Generate model architecture
        logger.info("[Agent 4] Generating model architecture...")
        response = llm_client.invoke(prompt)
        output = response.content if hasattr(response, 'content') else str(response)
        
        # Parse architecture plan
        try:
            arch_plan = json.loads(output)
            if not isinstance(arch_plan, dict):
                arch_plan = {}
        except:
            logger.warning("[Agent 4] Failed to parse architecture plan, using defaults")
            arch_plan = {}
        
        # Set defaults if not provided
        if "candidate_models" not in arch_plan:
            # Provide comprehensive model list based on task type
            if task_type == "classification":
                arch_plan["candidate_models"] = {
                    "LogisticRegression": {"needs_scaling": 1, "model_family": "LogisticRegression"},
                    "RandomForest": {"needs_scaling": 0, "model_family": "RandomForestClassifier"},
                    "GradientBoosting": {"needs_scaling": 0, "model_family": "GradientBoostingClassifier"},
                    "SVM_RBF": {"needs_scaling": 1, "model_family": "SVC"},
                    "KNN": {"needs_scaling": 1, "model_family": "KNeighborsClassifier"},
                    "DecisionTree": {"needs_scaling": 0, "model_family": "DecisionTreeClassifier"},
                    "XGBoost": {"needs_scaling": 0, "model_family": "XGBClassifier"},
                    "LightGBM": {"needs_scaling": 0, "model_family": "LGBMClassifier"},
                    "ExtraTrees": {"needs_scaling": 0, "model_family": "ExtraTreesClassifier"},
                    "GaussianNB": {"needs_scaling": 0, "model_family": "GaussianNB"},
                }
            else:  # regression
                arch_plan["candidate_models"] = {
                    "Ridge": {"needs_scaling": 1, "model_family": "Ridge"},
                    "RandomForestRegressor": {"needs_scaling": 0, "model_family": "RandomForestRegressor"},
                    "GradientBoostingRegressor": {"needs_scaling": 0, "model_family": "GradientBoostingRegressor"},
                    "SVR": {"needs_scaling": 1, "model_family": "SVR"},
                    "KNNRegressor": {"needs_scaling": 1, "model_family": "KNeighborsRegressor"},
                    "DecisionTreeRegressor": {"needs_scaling": 0, "model_family": "DecisionTreeRegressor"},
                    "XGBRegressor": {"needs_scaling": 0, "model_family": "XGBRegressor"},
                    "LGBMRegressor": {"needs_scaling": 0, "model_family": "LGBMRegressor"},
                    "ExtraTreesRegressor": {"needs_scaling": 0, "model_family": "ExtraTreesRegressor"},
                    "Lasso": {"needs_scaling": 1, "model_family": "Lasso"},
                }
        
        if "split_strategy" not in arch_plan:
            arch_plan["split_strategy"] = {
                "task_type": task_type,
                "test_size": 0.2,
                "stratify": target_column if task_type == "classification" else None,
            }
        
        logger.info(f"[Agent 4] Generated {len(arch_plan.get('candidate_models', {}))} candidate models")
        
        # Convert candidate_models dict to list format for frontend with detailed reasoning
        candidate_models_dict = arch_plan.get("candidate_models", {})
        
        # Model reasoning based on characteristics
        model_reasoning = {
            "LogisticRegression": "Fast, interpretable baseline for binary/multiclass classification with linear decision boundaries",
            "RandomForest": "Robust ensemble method that handles non-linear relationships and feature interactions well",
            "GradientBoosting": "Powerful boosting algorithm that builds trees sequentially to correct errors",
            "SVM_RBF": "Effective for non-linear patterns using kernel trick, good for medium-sized datasets",
            "KNN": "Simple instance-based learner, effective when similar instances have similar labels",
            "DecisionTree": "Interpretable model that captures non-linear patterns through recursive splitting",
            "XGBoost": "State-of-the-art gradient boosting with regularization, often wins competitions",
            "LightGBM": "Fast gradient boosting optimized for large datasets with leaf-wise tree growth",
            "ExtraTrees": "Ensemble of randomized trees with extra randomization for better generalization",
            "GaussianNB": "Probabilistic classifier based on Bayes theorem, fast and works well with small data",
            "Ridge": "Linear regression with L2 regularization to prevent overfitting",
            "RandomForestRegressor": "Ensemble of decision trees for robust regression with feature importance",
            "GradientBoostingRegressor": "Sequential boosting for regression tasks with strong predictive power",
            "SVR": "Support Vector Regression for non-linear patterns using kernel methods",
            "KNNRegressor": "Instance-based regression, predicts based on nearest neighbors",
            "DecisionTreeRegressor": "Tree-based regression capturing non-linear relationships",
            "XGBRegressor": "Gradient boosting for regression with advanced regularization",
            "LGBMRegressor": "Fast gradient boosting regressor optimized for efficiency",
            "ExtraTreesRegressor": "Randomized ensemble regressor for better generalization",
            "Lasso": "Linear regression with L1 regularization for feature selection",
        }
        
        candidate_models_list = [
            {
                "name": model_name,
                "needs_scaling": model_info.get("needs_scaling", 0),
                "model_family": model_info.get("model_family", model_name),
                "reason": model_reasoning.get(model_name, f"Selected for {task_type} task"),
                "scaling_required": "Yes" if model_info.get("needs_scaling", 0) else "No"
            }
            for model_name, model_info in candidate_models_dict.items()
        ]
        
        logger.info(f"[Agent 4] Converted to list format: {len(candidate_models_list)} models")
        
        # Create train/test split indices
        project_id = state.get("PROJECT_ID", "")
        engineered_path = state.get("engineered_data_path")
        
        if engineered_path:
            from tools.data_loader import load_dataset
            df = load_dataset(engineered_path)
            
            from sklearn.model_selection import train_test_split
            
            test_size = arch_plan["split_strategy"].get("test_size", 0.2)
            stratify_col = arch_plan["split_strategy"].get("stratify")
            stratify = df[stratify_col] if stratify_col and stratify_col in df.columns else None
            
            train_idx, test_idx = train_test_split(
                range(len(df)),
                test_size=test_size,
                stratify=stratify,
                random_state=42
            )
            
            # Save indices
            import numpy as np
            os.makedirs("data/splits", exist_ok=True)
            train_idx_path = f"data/splits/train_idx_{project_id}.npy"
            test_idx_path = f"data/splits/test_idx_{project_id}.npy"
            
            np.save(train_idx_path, train_idx)
            np.save(test_idx_path, test_idx)
            
            logger.info(f"[Agent 4] Created train/test split: {len(train_idx)} train, {len(test_idx)} test")
            
            return {
                "candidate_models": candidate_models_list,  # Return as list
                "split_strategy": arch_plan.get("split_strategy", {}),
                "train_idx_path": train_idx_path,
                "test_idx_path": test_idx_path,
            }
        else:
            logger.warning("[Agent 4] No engineered data path provided")
            return {
                "candidate_models": candidate_models_list,  # Return as list
                "split_strategy": arch_plan.get("split_strategy", {}),
            }
    
    except Exception as e:
        logger.error(f"[Agent 4] Failed: {e}", exc_info=True)
        return {"error": str(e)}


if __name__ == "__main__":
    client = _get_module_client()
    test_state = {
        "feature_engineering_plan": {
            "task_type": "classification",
            "target_column": "target",
            "selected_features": ["f1", "f2", "f3"],
        },
        "eda_report": {"overview": {"target_column": "target"}},
    }
    result = run_agent_4_with_review(test_state, client)
    print("Models:", list(result.get("candidate_models", {}).keys())[:3])
