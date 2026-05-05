"""Agent 3 — Feature Engineering.

Inputs: Cleaned data + EDA report
Outputs: Engineered features, selected feature set, scaling requirements
Human Gate: User reviews & approves feature importance before proceeding

Responsibilities:
- Load cleaned CSV
- Identify target column (from project_goal keywords or default to last column)
- Polynomial features (degree 2-3)
- Interaction features between top-correlated pairs
- Feature selection: correlation + mutual information + tree-based importance
- Determine scaling requirements per feature/method
- Save engineered data to /data/engineered/engineered_{project_id}.csv
- Document feature importance scores and scaling requirements
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from langsmith import traceable
from sklearn.preprocessing import LabelEncoder

from db import firebird_client as fb
from tools.data_loader import load_dataset, save_dataset
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

_NEEDS_SCALING_METHODS = {"pca", "rfe", "lasso", "ridge", "elasticnet", "svm", "knn"}


def _detect_task_type(project_goal: str) -> str:
    goal_lower = project_goal.lower()
    revenue_terms = ("revenue", "forecast", "estimate price", "predict sales", "regress")
    if any(k in goal_lower for k in revenue_terms):
        return "regression"
    if any(k in goal_lower for k in ("predict", "classify", "categor", "label", "churn", "fraud", "spam")):
        return "classification"
    if any(k in goal_lower for k in ("cluster", "segment", "group", "segmentation")):
        return "clustering"
    return "classification"


def _identify_target(df: pd.DataFrame, eda_report: Dict, project_goal: str) -> Optional[str]:
    goal_lower = project_goal.lower()
    for col in reversed(df.columns):
        col_lower = col.lower()
        if any(k in col_lower for k in ("target", "label", "class", "y", "outcome", "dependent", "response")):
            return col

    llm_analysis = eda_report.get("llm_eda_analysis", {})
    if llm_analysis and "dataset_assessment" in llm_analysis:
        da = llm_analysis["dataset_assessment"]
        if isinstance(da, dict) and "primary_target" in da:
            target = da["primary_target"]
            if target in df.columns:
                return target

    for col in reversed(df.columns):
        dtype = str(df[col].dtype)
        if dtype in ("object", "category", "int64") and df[col].nunique() <= 50:
            return col

    return df.columns[-1] if len(df.columns) > 1 else None


def _create_polynomial_features(df: pd.DataFrame, numeric_cols: List[str], degree: int = 2) -> pd.DataFrame:
    """Create polynomial features up to given degree for numeric columns."""
    result = df.copy()
    poly_cols_created = 0

    for col in numeric_cols:
        if result[col].dtype not in ("float64", "int64", "float32", "int32"):
            continue
        for d in range(2, degree + 1):
            new_col = f"{col}_poly{d}"
            result[new_col] = result[col] ** d
            poly_cols_created += 1

    logger.info("[Agent 3] Created %d polynomial features (degree 2-%d).", poly_cols_created, degree)
    return result


def _create_interaction_features(df: pd.DataFrame, top_pairs: List[tuple], max_pairs: int = 10) -> pd.DataFrame:
    """Create interaction (product) features for top correlated pairs."""
    result = df.copy()
    interaction_cols = 0

    for (col1, col2) in top_pairs[:max_pairs]:
        if col1 in result.columns and col2 in result.columns:
            result[f"{col1}_x_{col2}"] = result[col1] * result[col2]
            interaction_cols += 1

    logger.info("[Agent 3] Created %d interaction features.", interaction_cols)
    return result


def _select_by_correlation(df: pd.DataFrame, target: str, threshold: float = 0.7) -> List[str]:
    """Select features with correlation to target above threshold."""
    if target not in df.columns:
        return []
    numeric_df = df.select_dtypes(include=[np.number])
    if target not in numeric_df.columns:
        return []

    corrs = numeric_df.corr()[target].abs().sort_values(ascending=False)
    selected = corrs[corrs >= threshold].index.tolist()
    if target in selected:
        selected.remove(target)
    return selected


def _select_by_mutual_info(df: pd.DataFrame, target: str, top_k: int = 15) -> List[str]:
    """Select top-k features by mutual information score."""
    try:
        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
        task_type = _detect_task_type("")  # dummy to get right MI variant
        numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
        if target not in numeric_df.columns or len(numeric_df.columns) < 2:
            return []

        X = numeric_df.drop(columns=[target])
        y = numeric_df[target]
        X = X.apply(pd.to_numeric, errors="coerce").fillna(0)

        if task_type == "classification":
            scores = mutual_info_classif(X, y, random_state=42)
        else:
            scores = mutual_info_regression(X, y, random_state=42)

        mi_scores = pd.Series(scores, index=X.columns).sort_values(ascending=False)
        selected = mi_scores.head(top_k).index.tolist()
        logger.info("[Agent 3] MI selected: %s", selected[:10])
        return selected
    except Exception as e:
        logger.warning("[Agent 3] Mutual info selection failed: %s", e)
        return []


def _tree_importance(df: pd.DataFrame, target: str, top_k: int = 20) -> List[tuple]:
    """Get tree-based feature importance. Returns list of (feature, importance) tuples."""
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

        task_type = _detect_task_type("")
        numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
        if target not in numeric_df.columns or len(numeric_df.columns) < 2:
            return []

        X = numeric_df.drop(columns=[target])
        y = numeric_df[target]
        X = X.apply(pd.to_numeric, errors="coerce").fillna(0)

        if task_type == "classification":
            rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        else:
            rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)

        rf.fit(X, y)
        importances = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)
        result = list(zip(importances.index.tolist(), importances.values.tolist()))[:top_k]
        logger.info("[Agent 3] Tree importance top feature: %s (%.4f)", result[0][0] if result else "N/A", result[0][1] if result else 0)
        return result
    except Exception as e:
        logger.warning("[Agent 3] Tree importance failed: %s", e)
        return []


def _get_scaling_requirements(feature_names: List[str], method: str = "auto") -> Dict[str, bool]:
    """Determine which features need scaling based on method used."""
    scaling_reqs = {}
    for feat in feature_names:
        if method in _NEEDS_SCALING_METHODS or method == "auto":
            if any(k in feat.lower() for k in ("poly", "_x_", "_sq", "_cubed")):
                scaling_reqs[feat] = True
            else:
                scaling_reqs[feat] = False
        else:
            scaling_reqs[feat] = False
    return scaling_reqs


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 3, "agent_name": "Feature Engineering"})
def run_agent_3_features(state: PipelineState) -> PipelineState:
    """LangGraph node: Feature Engineering."""
    project_id = state["project_id"]
    cleaned_path = state.get("cleaned_data_path")
    eda_report = state.get("eda_report", {})
    project_goal = state.get("project_goal", "")
    human_feedback = state.get("human_feedback", {})

    logger.info("[Agent 3] Starting Feature Engineering — project %s", project_id)
    t0 = time.time()

    if not cleaned_path:
        state["error"] = "No cleaned data path found in state"
        return state

    try:
        df = load_dataset(cleaned_path)
        logger.info("[Agent 3] Loaded %d rows × %d cols.", *df.shape)
    except Exception as exc:
        logger.error("[Agent 3] Data load failed: %s", exc)
        state["error"] = str(exc)
        return state

    target = _identify_target(df, eda_report, project_goal)
    if not target:
        state["error"] = "Could not identify target column"
        return state

    categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
    for col in categorical_cols:
        if col != target:
            try:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                logger.info("[Agent 3] Encoded categorical: %s", col)
            except Exception as e:
                logger.warning("[Agent 3] Failed to encode %s: %s", col, e)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if target in numeric_cols:
        numeric_cols.remove(target)

    plan = {
        "target_column": target,
        "task_type": _detect_task_type(project_goal),
        "polynomial_degree": 2,
        "max_interaction_pairs": 10,
        "correlation_threshold": 0.7,
        "mutual_info_top_k": 15,
        "tree_importance_top_k": 20,
    }

    correlation_selected = []
    mi_selected = []
    tree_selected = []
    all_selected = set()

    corr_thresh = human_feedback.get("correlation_threshold", plan["correlation_threshold"])
    mi_k = human_feedback.get("mi_top_k", plan["mutual_info_top_k"])
    tree_k = human_feedback.get("tree_top_k", plan["tree_importance_top_k"])

    if len(numeric_cols) >= 2:
        try:
            correlation_selected = _select_by_correlation(df, target, threshold=corr_thresh)
            all_selected.update(correlation_selected)
        except Exception as e:
            logger.warning("[Agent 3] Correlation selection failed: %s", e)

    try:
        mi_selected = _select_by_mutual_info(df, target, top_k=mi_k)
        all_selected.update(mi_selected)
    except Exception as e:
        logger.warning("[Agent 3] MI selection failed: %s", e)

    try:
        tree_tuples = _tree_importance(df, target, top_k=tree_k)
        tree_selected = [t[0] for t in tree_tuples]
        all_selected.update(tree_selected)
    except Exception as e:
        logger.warning("[Agent 3] Tree importance failed: %s", e)

    selected_features = list(all_selected)

    df_engineered = df.copy()

    if len(numeric_cols) >= 2:
        corrs = df[numeric_cols].corr().abs()
        strong_pairs = []
        for i, c1 in enumerate(numeric_cols):
            for c2 in numeric_cols[i+1:]:
                if pd.notna(corrs.loc[c1, c2]) and corrs.loc[c1, c2] >= corr_thresh:
                    strong_pairs.append((c1, c2))
        strong_pairs.sort(key=lambda p: corrs.loc[p[0], p[1]], reverse=True)
        df_engineered = _create_interaction_features(df_engineered, strong_pairs, max_pairs=plan["max_interaction_pairs"])

    poly_degree = human_feedback.get("polynomial_degree", plan["polynomial_degree"])
    if 2 <= poly_degree <= 3 and len(numeric_cols) > 0:
        df_engineered = _create_polynomial_features(df_engineered, numeric_cols, degree=poly_degree)

    final_features = selected_features[:]
    new_cols = [c for c in df_engineered.columns if c not in df.columns and c != target]
    final_features.extend(new_cols)
    final_features = list(dict.fromkeys(final_features))  # preserve order, dedupe

    feature_scores = {
        "correlation": {f: 1.0 for f in correlation_selected},
        "mutual_info": {f: float(mi_selected.index(f) + 1) / len(mi_selected) if f in mi_selected else 0 for f in final_features},
        "tree_importance": dict(tree_tuples) if tree_tuples else {},
    }

    scaling_requirements = {}
    for col in final_features:
        if col in df_engineered.select_dtypes(include=[np.number]).columns:
            scaling_requirements[col] = False  # mutual info / tree methods don't need scaling
        else:
            scaling_requirements[col] = True

    engineered_path = os.path.join("data", "engineered", f"engineered_{project_id}.csv")
    try:
        os.makedirs(os.path.dirname(engineered_path), exist_ok=True)
        save_dataset(df_engineered, engineered_path)
        logger.info("[Agent 3] Saved engineered data to %s", engineered_path)
    except Exception as exc:
        logger.error("[Agent 3] Failed to save engineered data: %s", exc)
        state["error"] = str(exc)
        return state

    feature_plan = {
        "target_column": target,
        "task_type": plan["task_type"],
        "original_features": list(df.columns),
        "selected_features": final_features,
        "polynomial_degree": poly_degree,
        "correlation_threshold": corr_thresh,
        "mi_top_k": mi_k,
        "tree_top_k": tree_k,
        "feature_scores": feature_scores,
        "scaling_requirements": scaling_requirements,
        "engineerings_applied": ["correlation_filter", "mutual_info", "tree_importance", "polynomial", "interaction"],
    }

    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        fb.update_state(
            project_id,
            feature_engineering_plan=feature_plan,
            selected_features=final_features,
            scaling_requirements=scaling_requirements,
            engineered_data_path=engineered_path,
            current_agent_id=3,
            approval_status="pending_feature_review",
        )
        fb.log_agent_report(
            project_id=project_id,
            agent_id=3,
            agent_name="Feature Engineering",
            report={
                "target_column": target,
                "task_type": plan["task_type"],
                "features_selected": len(final_features),
                "original_columns": len(df.columns),
                "engineered_columns": len(df_engineered.columns),
                "feature_scores": feature_scores,
            },
            status="success",
            execution_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.error("[Agent 3] Firebird write failed: %s", exc)

    state["feature_engineering_plan"] = feature_plan
    state["selected_features"] = final_features
    state["scaling_requirements"] = scaling_requirements
    state["engineered_data_path"] = engineered_path
    state["current_agent_id"] = 3
    state["approval_status"] = "pending_feature_review"
    state["error"] = None

    logger.info("[Agent 3] ✅ Complete in %d ms. Selected %d features.", elapsed_ms, len(final_features))
    return state
