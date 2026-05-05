"""Agent 4 — Model Architecture.

Inputs: Engineered features + feature selection plan + project goal
Outputs: Train/test splits, candidate model pipelines with proper scaling
Human Gate: User approves chosen model set & split strategy before Agent 5

Responsibilities:
- Detect task type (classification/regression/clustering) from project goal
- Stratified train/test split (default 80/20) preserving class distribution
- Save train/test row indices as numpy files for reproducibility
- Initialize candidate model pipelines with proper scaling per the pipeline doc:
    * StandardScaler required: KNN, KMeans, GMM, LogisticRegression, LinearRegression,
      Lasso, Ridge, ElasticNet, SVM (all kernels), Neural networks
    * No scaling: RandomForest, XGBoost, LightGBM, CatBoost, DecisionTree, ExtraTrees
- Build pipelines: scaler (if needed) + model
- Save candidate_pipelines dict as pickle
"""
from __future__ import annotations

import logging
import os
import pickle
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from langsmith import traceable

from db import firebird_client as fb
from tools.data_loader import load_dataset
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)


_SCALING_MODELS = (
    # Distance-based
    "KNeighborsClassifier", "KNeighborsRegressor", "KMeans", "GaussianMixture",
    # Gradient/linear
    "LogisticRegression", "LinearRegression", "Ridge", "Lasso", "ElasticNet",
    "SVC", "SVR", "LinearSVC", "LinearRegression",
    # Variance-sensitive
    "PCA", "RidgeClassifier",
)

_NO_SCALING_MODELS = (
    "RandomForestClassifier", "RandomForestRegressor",
    "XGBClassifier", "XGBRegressor",
    "LGBMClassifier", "LGBMRegressor",
    "CatBoostClassifier", "CatBoostRegressor",
    "DecisionTreeClassifier", "DecisionTreeRegressor",
    "ExtraTreesClassifier", "ExtraTreesRegressor",
    "GradientBoostingClassifier", "GradientBoostingRegressor",
    "AdaBoostClassifier", "AdaBoostRegressor",
)


def _detect_task_type(project_goal: str, df: pd.DataFrame, target_col: str) -> str:
    goal_lower = project_goal.lower()
    if any(k in goal_lower for k in ("predict", "classify", "categor", "label", "churn", "fraud", "spam", "attrition")):
        return "classification"
    if any(k in goal_lower for k in ("forecast", "regress", "estimate", "price", "demand", "sales", "score", "yield")):
        return "regression"
    if any(k in goal_lower for k in ("cluster", "segment", "group", "segmentation")):
        return "clustering"

    if target_col and target_col in df.columns:
        dtype = str(df[target_col].dtype)
        n_unique = df[target_col].nunique()
        if dtype in ("object", "category") or (dtype in ("int64", "int32") and n_unique <= 20):
            return "classification"

    return "classification"


def _make_pipeline(model_name: str, model_instance) -> Any:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if model_name in _SCALING_MODELS:
        return Pipeline([("scaler", StandardScaler()), ("model", model_instance)])
    return Pipeline([("model", model_instance)])


def _get_classification_models() -> Dict[str, Any]:
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.svm import SVC, LinearSVC
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.ensemble import (
        RandomForestClassifier, GradientBoostingClassifier, AdaBoostClassifier, ExtraTreesClassifier
    )
    from sklearn.naive_bayes import GaussianNB

    return {
        "LogisticRegression": _make_pipeline("LogisticRegression", LogisticRegression(max_iter=1000)),
        "SVM_RBF": _make_pipeline("SVC", SVC(kernel="rbf", probability=True)),
        "SVM_Linear": _make_pipeline("SVC", LinearSVC(max_iter=2000)),
        "KNN": _make_pipeline("KNeighborsClassifier", KNeighborsClassifier()),
        "RandomForest": _make_pipeline("RandomForestClassifier", RandomForestClassifier(n_estimators=100, random_state=42)),
        "XGBoost": _make_pipeline("XGBClassifier", __import__("xgboost", fromlist=["XGBClassifier"]).XGBClassifier(eval_metric="logloss", use_label_encoder=False)),
        "LightGBM": _make_pipeline("LGBMClassifier", __import__("lightgbm", fromlist=["LGBMClassifier"]).LGBMClassifier(verbosity=-1)),
        "GradientBoosting": _make_pipeline("GradientBoostingClassifier", GradientBoostingClassifier()),
        "ExtraTrees": _make_pipeline("ExtraTreesClassifier", ExtraTreesClassifier(n_estimators=100, random_state=42)),
        "GaussianNB": _make_pipeline("GaussianNB", GaussianNB()),
    }


def _get_regression_models() -> Dict[str, Any]:
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.svm import SVR, LinearSVR
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.ensemble import (
        RandomForestRegressor, GradientBoostingRegressor, ExtraTreesRegressor
    )

    return {
        "LinearRegression": _make_pipeline("LinearRegression", LinearRegression()),
        "Ridge": _make_pipeline("Ridge", Ridge()),
        "Lasso": _make_pipeline("Lasso", Lasso(max_iter=2000)),
        "ElasticNet": _make_pipeline("ElasticNet", ElasticNet(max_iter=2000)),
        "SVR_RBF": _make_pipeline("SVR", SVR(kernel="rbf")),
        "SVR_Linear": _make_pipeline("SVR", LinearSVR(max_iter=2000)),
        "KNN": _make_pipeline("KNeighborsRegressor", KNeighborsRegressor()),
        "RandomForest": _make_pipeline("RandomForestRegressor", RandomForestRegressor(n_estimators=100, random_state=42)),
        "XGBoost": _make_pipeline("XGBRegressor", __import__("xgboost", fromlist=["XGBRegressor"]).XGBRegressor()),
        "LightGBM": _make_pipeline("LGBMRegressor", __import__("lightgbm", fromlist=["LGBMRegressor"]).LGBMRegressor(verbosity=-1)),
        "GradientBoosting": _make_pipeline("GradientBoostingRegressor", GradientBoostingRegressor()),
        "ExtraTrees": _make_pipeline("ExtraTreesRegressor", ExtraTreesRegressor(n_estimators=100, random_state=42)),
    }


def _get_clustering_models() -> Dict[str, Any]:
    from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    return {
        "KMeans": Pipeline([("scaler", StandardScaler()), ("model", KMeans(n_init=10, random_state=42))]),
        "GaussianMixture": Pipeline([("scaler", StandardScaler()), ("model", GaussianMixture(n_components=3, random_state=42))]),
        "DBSCAN": Pipeline([("scaler", StandardScaler()), ("model", DBSCAN(eps=0.5, min_samples=5))]),
        "Hierarchical": Pipeline([("scaler", StandardScaler()), ("model", AgglomerativeClustering())]),
    }


def _stratified_split(
    df: pd.DataFrame,
    target_col: str,
    test_size: float = 0.2,
    min_samples_per_class: int = 2,
    random_state: int = 42
) -> Dict[str, Any]:
    from sklearn.model_selection import train_test_split

    X = df.drop(columns=[target_col])
    y = df[target_col]

    stratify = y if y.nunique() >= 2 and y.value_counts().min() >= min_samples_per_class else None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        stratify=stratify,
        random_state=random_state,
    )

    train_idx = X_train.index.values
    test_idx = X_test.index.values

    return {
        "X_train_shape": list(X_train.shape),
        "X_test_shape": list(X_test.shape),
        "y_train_shape": list(y_train.shape),
        "y_test_shape": list(y_test.shape),
        "test_size": test_size,
        "stratify": stratify is not None,
        "class_distribution_train": y_train.value_counts().to_dict(),
        "class_distribution_test": y_test.value_counts().to_dict() if stratify is not None else {},
        "train_idx_path": None,
        "test_idx_path": None,
    }


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 4, "agent_name": "Model Architecture"})
def run_agent_4_architecture(state: PipelineState) -> PipelineState:
    """LangGraph node: Model Architecture."""
    project_id = state["project_id"]
    engineered_path = state.get("engineered_data_path")
    feature_plan = state.get("feature_engineering_plan", {})
    selected_features = state.get("selected_features", [])
    scaling_requirements = state.get("scaling_requirements", {})
    project_goal = state.get("project_goal", "")
    human_feedback = state.get("human_feedback", {})

    logger.info("[Agent 4] Starting Model Architecture — project %s", project_id)
    t0 = time.time()

    if not engineered_path:
        state["error"] = "No engineered data path found in state"
        return state

    try:
        df = load_dataset(engineered_path)
        logger.info("[Agent 4] Loaded %d rows × %d cols.", *df.shape)
    except Exception as exc:
        logger.error("[Agent 4] Data load failed: %s", exc)
        state["error"] = str(exc)
        return state

    target_col = feature_plan.get("target_column")
    if not target_col or target_col not in df.columns:
        state["error"] = f"Target column '{target_col}' not found in engineered data"
        return state

    task_type = _detect_task_type(project_goal, df, target_col)
    logger.info("[Agent 4] Detected task type: %s", task_type)

    test_size = human_feedback.get("test_size", 0.2)
    min_samples = human_feedback.get("min_samples_per_class", 2)

    split_result = _stratified_split(df, target_col, test_size=test_size, min_samples_per_class=min_samples)

    train_idx_path = os.path.join("data", "splits", f"train_idx_{project_id}.npy")
    test_idx_path = os.path.join("data", "splits", f"test_idx_{project_id}.npy")
    try:
        os.makedirs(os.path.dirname(train_idx_path), exist_ok=True)
        X = df.drop(columns=[target_col])
        y = df[target_col]
        X_train = X.iloc[split_result.get("train_idx", [])] if "train_idx" not in split_result else None

        train_idx = split_result.get("train_idx", np.arange(len(df) - int(len(df) * test_size)))
        test_idx = split_result.get("test_idx", np.arange(int(len(df) * test_size)))

        np.save(train_idx_path, train_idx)
        np.save(test_idx_path, test_idx)
        split_result["train_idx_path"] = train_idx_path
        split_result["test_idx_path"] = test_idx_path
        logger.info("[Agent 4] Saved split indices: train=%s, test=%s", train_idx_path, test_idx_path)
    except Exception as exc:
        logger.error("[Agent 4] Failed to save split indices: %s", exc)

    if task_type == "classification":
        candidate_models = _get_classification_models()
    elif task_type == "regression":
        candidate_models = _get_regression_models()
    else:
        candidate_models = _get_clustering_models()

    model_dir = os.path.join("models", project_id)
    try:
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "candidate_models.pkl")
        with open(model_path, "wb") as f:
            pickle.dump(candidate_models, f)
        logger.info("[Agent 4] Saved %d candidate pipelines to %s", len(candidate_models), model_path)
    except Exception as exc:
        logger.error("[Agent 4] Failed to save candidate models: %s", exc)
        state["error"] = str(exc)
        return state

    model_info = {}
    for name, pipeline in candidate_models.items():
        needs_scaling = isinstance(pipeline.steps[0][1], type(pipeline.named_steps.get("scaler"))) if "scaler" in pipeline.named_steps else False
        model_info[name] = {
            "needs_scaling": needs_scaling,
            "model_family": type(pipeline.steps[-1][1]).__name__,
        }

    split_strategy = {
        "task_type": task_type,
        "test_size": test_size,
        "min_samples_per_class": min_samples,
        "stratify": split_result["stratify"],
        "class_distribution_train": split_result["class_distribution_train"],
        "class_distribution_test": split_result.get("class_distribution_test", {}),
        "train_idx_path": train_idx_path,
        "test_idx_path": test_idx_path,
    }

    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        fb.update_state(
            project_id,
            split_strategy=split_strategy,
            candidate_models=model_info,
            train_idx_path=train_idx_path,
            test_idx_path=test_idx_path,
            task_type=task_type,
            current_agent_id=4,
            approval_status="pending_model_review",
        )
        fb.log_agent_report(
            project_id=project_id,
            agent_id=4,
            agent_name="Model Architecture",
            report={
                "task_type": task_type,
                "candidate_models": list(candidate_models.keys()),
                "split_strategy": split_strategy,
            },
            status="success",
            execution_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.error("[Agent 4] Firebird write failed: %s", exc)

    state["split_strategy"] = split_strategy
    state["candidate_models"] = model_info
    state["train_idx_path"] = train_idx_path
    state["test_idx_path"] = test_idx_path
    state["task_type"] = task_type
    state["current_agent_id"] = 4
    state["approval_status"] = "pending_model_review"
    state["error"] = None

    logger.info("[Agent 4] ✅ Complete in %d ms. %d candidates for %s.",
                elapsed_ms, len(candidate_models), task_type)
    return state
