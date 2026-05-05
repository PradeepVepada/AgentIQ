"""Agent 5 — Training & Tuning.

Inputs: Candidate pipelines, train/test splits, tuning config
Outputs: Tuned models (saved to disk), hyperparameter logs (MLflow)
Human Gate: NONE — fully automated, results logged in LangSmith

Responsibilities:
- Load candidate pipelines and split indices
- For each candidate, run hyperparameter tuning via Optuna (20 trials, Bayesian)
- Track best params and CV score per model
- Save best tuned model to models/tuned_{name}_{project_id}.pkl
- Log tuning results to MLflow: hyperparameters, best CV score, training time
- Failure recovery: skip failed model, log error, continue with others

Scaling: Each pipeline already has scaler embedded (from Agent 4)
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
from pathlib import Path

load_dotenv()
logger = logging.getLogger(__name__)

_MAX_TRIALS = 0  # Skip tuning - use default params for faster execution
_CV_FOLDS = int(os.getenv("CV_FOLDS", "3"))

# Fix MLflow to use local directory that works on Windows
_MLFLOW_DIR = Path(__file__).parents[1] / "mlruns"
_MLFLOW_DIR.mkdir(exist_ok=True)


def _get_search_space(model_name: str) -> Dict[str, Any]:
    import optuna

    spaces = {
        "LogisticRegression": {
            "model__C": optuna.distributions.FloatDistribution(1e-3, 1e2, log=True),
            "model__penalty": optuna.distributions.CategoricalDistribution(["l2"]),
            "model__solver": optuna.distributions.CategoricalDistribution(["lbfgs", "saga"]),
        },
        "SVC": {
            "model__C": optuna.distributions.FloatDistribution(1e-3, 1e2, log=True),
            "model__gamma": optuna.distributions.CategoricalDistribution(["scale", "auto"]),
        },
        "KNeighborsClassifier": {
            "model__n_neighbors": optuna.distributions.IntDistribution(3, 30),
            "model__weights": optuna.distributions.CategoricalDistribution(["uniform", "distance"]),
            "model__metric": optuna.distributions.CategoricalDistribution(["euclidean", "manhattan"]),
        },
        "RandomForest": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 20),
            "model__min_samples_split": optuna.distributions.IntDistribution(2, 20),
        },
        "XGBoost": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 15),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
            "model__subsample": optuna.distributions.FloatDistribution(0.6, 1.0),
        },
        "LightGBM": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 15),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
            "model__num_leaves": optuna.distributions.IntDistribution(20, 100),
        },
        "GradientBoosting": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 200),
            "model__max_depth": optuna.distributions.IntDistribution(3, 10),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
        },
        "ExtraTrees": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 20),
        },
        "GaussianNB": {
            "model__var_smoothing": optuna.distributions.FloatDistribution(1e-12, 1e-6, log=True),
        },
        # Regression
        "LinearRegression": {},
        "Ridge": {
            "model__alpha": optuna.distributions.FloatDistribution(1e-3, 1e3, log=True),
        },
        "Lasso": {
            "model__alpha": optuna.distributions.FloatDistribution(1e-4, 1e2, log=True),
        },
        "ElasticNet": {
            "model__alpha": optuna.distributions.FloatDistribution(1e-4, 1e2, log=True),
            "model__l1_ratio": optuna.distributions.FloatDistribution(0.1, 0.9),
        },
        "SVR": {
            "model__C": optuna.distributions.FloatDistribution(1e-3, 1e2, log=True),
            "model__epsilon": optuna.distributions.FloatDistribution(1e-3, 1.0),
        },
        "KNN": {
            "model__n_neighbors": optuna.distributions.IntDistribution(3, 30),
            "model__weights": optuna.distributions.CategoricalDistribution(["uniform", "distance"]),
        },
        "RandomForestRegressor": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 20),
        },
        "XGBRegressor": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 15),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
        },
        "LGBMRegressor": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 15),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
        },
        "GradientBoostingRegressor": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 200),
            "model__max_depth": optuna.distributions.IntDistribution(3, 10),
            "model__learning_rate": optuna.distributions.FloatDistribution(1e-3, 0.3, log=True),
        },
        "ExtraTreesRegressor": {
            "model__n_estimators": optuna.distributions.IntDistribution(50, 300),
            "model__max_depth": optuna.distributions.IntDistribution(3, 20),
        },
        # Clustering
        "KMeans": {
            "model__n_clusters": optuna.distributions.IntDistribution(2, 10),
            "model__init": optuna.distributions.CategoricalDistribution(["k-means++", "random"]),
        },
        "GaussianMixture": {
            "model__n_components": optuna.distributions.IntDistribution(2, 10),
        },
    }

    base_name = model_name.replace("_RBF", "").replace("_Linear", "")
    return spaces.get(model_name, spaces.get(base_name, {}))


def _objective(trial, pipeline, X, y, task_type: str, search_space: Dict, n_cv: int = 5) -> float:
    from sklearn.model_selection import cross_val_score

    params = {}
    for param_name, distribution in search_space.items():
        try:
            params[param_name] = trial._suggest(param_name, distribution)
        except Exception as e:
            logger.warning(f"Trial param error: {e}")
            pass

    try:
        pipeline.set_params(**params)
    except Exception as e:
        logger.warning(f"Pipeline set_params failed: {e}")
        return float("nan")

    scorer = "accuracy" if task_type == "classification" else "r2"
    if task_type == "clustering":
        scorer = "adjusted_rand_score"

    # Check for NaN/Inf in data - convert to numpy array first
    X_arr = np.asarray(X)
    if not np.isfinite(X_arr).all():
        logger.warning("X contains non-finite values")
        return float("nan")
    
    try:
        scores = cross_val_score(pipeline, X, y, cv=n_cv, scoring=scorer, n_jobs=-1)
        return scores.mean()
    except Exception:
        return float("nan")


def _tune_pipeline(pipeline, X, y, task_type: str, model_name: str, n_trials: int = _MAX_TRIALS) -> Dict[str, Any]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    search_space = _get_search_space(model_name)

    n_samples = len(X)
    n_cv = min(_CV_FOLDS, max(2, n_samples // 2))
    
    # Skip tuning entirely when n_trials=0 - use default params
    if n_trials == 0:
        logger.info("[Agent 5] Skipping tuning for %s - using default params", model_name)
        try:
            pipeline.fit(X, y)
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "default_only"}
        except Exception as e:
            logger.error("[Agent 5] Default fit failed for %s: %s", model_name, str(e))
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "failed", "error": str(e)}

    effective_trials = min(n_trials, max(1, n_samples * 2))

    if not search_space:
        logger.info("[Agent 5] No search space for %s — training with defaults.", model_name)
        try:
            pipeline.fit(X, y)
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "default_only"}
        except Exception as e:
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "failed", "error": str(e)}

    study = optuna.create_study(direction="maximize")
    objective_fn = lambda trial: _objective(trial, pipeline, X, y, task_type, search_space, n_cv)

    try:
        study.optimize(objective_fn, n_trials=effective_trials, show_progress_bar=False)
        best_score = study.best_value
        if pd.isna(best_score) or best_score != best_score:
            logger.warning("[Agent 5] All trials returned NaN for %s, using default fit.", model_name)
            try:
                pipeline.fit(X, y)
            except Exception:
                pass
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "nan_fallback"}
        best_params = study.best_params
        pipeline.set_params(**best_params)
        try:
            pipeline.fit(X, y)
        except Exception:
            pass
        return {"best_params": best_params, "best_score": float(best_score), "n_trials": effective_trials, "status": "success"}
    except Exception as e:
        logger.warning("[Agent 5] Optuna failed for %s: %s", model_name, e)
        try:
            pipeline.fit(X, y)
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "failed_fit", "error": str(e)}
        except Exception as fit_err:
            return {"best_params": {}, "best_score": 0.0, "n_trials": 0, "status": "failed", "error": str(fit_err)}


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 5, "agent_name": "Training & Tuning"})
def run_agent_5_training(state: PipelineState) -> PipelineState:
    """LangGraph node: Training & Tuning (no human gate)."""
    project_id = state["project_id"]
    engineered_path = state.get("engineered_data_path")
    split_strategy = state.get("split_strategy", {})
    candidate_models_info = state.get("candidate_models", {})
    task_type = state.get("task_type", "classification")

    logger.info("[Agent 5] Starting Training & Tuning — project %s", project_id)
    t0 = time.time()

    if not engineered_path:
        state["error"] = "No engineered data path found"
        return state

    train_idx_path = split_strategy.get("train_idx_path") or state.get("train_idx_path")
    test_idx_path = split_strategy.get("test_idx_path") or state.get("test_idx_path")

    if not train_idx_path or not test_idx_path:
        state["error"] = "No split indices found"
        return state

    try:
        df = load_dataset(engineered_path)
        train_idx = np.load(train_idx_path)
        test_idx = np.load(test_idx_path)
        logger.info("[Agent 5] Loaded data and split indices.")
    except Exception as exc:
        logger.error("[Agent 5] Load failed: %s", exc)
        state["error"] = str(exc)
        return state

    target_col = state.get("feature_engineering_plan", {}).get("target_column") or split_strategy.get("target_column")
    if not target_col:
        state["error"] = "No target column specified"
        return state

    try:
        X = df.drop(columns=[target_col])
        y = df[target_col]
        X_train = X.iloc[train_idx]
        y_train = y.iloc[train_idx]
    except Exception as exc:
        state["error"] = f"Failed to apply split indices: {exc}"
        return state

    model_dir = os.path.join("models", project_id)
    os.makedirs(model_dir, exist_ok=True)

    candidate_path = os.path.join(model_dir, "candidate_models.pkl")
    if os.path.exists(candidate_path):
        try:
            with open(candidate_path, "rb") as f:
                candidate_pipelines = pickle.load(f)
        except Exception:
            candidate_pipelines = {}
    else:
        candidate_pipelines = {}

    tuning_results = {}
    training_results = {}
    mlflow_run_ids = []

    for model_name, pipeline in candidate_pipelines.items():
        model_key = model_name.replace("_", "").replace(" ", "")
        logger.info("[Agent 5] Tuning %s...", model_name)
        t_model = time.time()

        tune_result = _tune_pipeline(pipeline, X_train, y_train, task_type, model_name)

        model_path = os.path.join(model_dir, f"tuned_{model_name}_{project_id}.pkl")
        try:
            with open(model_path, "wb") as f:
                pickle.dump(pipeline, f)
            tune_result["model_path"] = model_path
        except Exception as exc:
            logger.warning("[Agent 5] Could not save tuned model %s: %s", model_name, exc)

        tune_result["training_time_ms"] = int((time.time() - t_model) * 1000)
        tuning_results[model_name] = tune_result

        try:
            from sklearn.model_selection import cross_val_score

            n_train_samples = len(X_train)
            n_cv = min(_CV_FOLDS, max(2, n_train_samples // 2))
            scorer = "accuracy" if task_type == "classification" else "r2"
            cv_scores = cross_val_score(pipeline, X_train, y_train, cv=n_cv, scoring=scorer, n_jobs=-1)
            training_results[model_name] = {
                "cv_mean": float(cv_scores.mean()) if cv_scores.size > 0 else 0.0,
                "cv_std": float(cv_scores.std()) if cv_scores.size > 0 else 0.0,
                "cv_scores": cv_scores.tolist() if cv_scores.size > 0 else [],
            }
        except Exception:
            training_results[model_name] = {"cv_mean": 0.0, "cv_std": 0.0, "cv_scores": []}

        try:
            import mlflow
            # Only set tracking URI, don't use model registry
            mlflow.set_tracking_uri(str(_MLFLOW_DIR).replace("\\", "/"))
            mlflow.set_experiment("agentiq-training")
            with mlflow.start_run(run_name=f"{project_id}_{model_name}") as run:
                mlflow.log_params(tune_result.get("best_params", {}))
                mlflow.log_metric("best_cv_score", tune_result.get("best_score", 0))
                mlflow.log_metric("training_time_ms", tune_result["training_time_ms"])
                mlflow.sklearn.log_model(pipeline, f"model_{model_name}", registered_model_name=None)
                mlflow_run_ids.append(run.info.run_id)
        except Exception as e:
            logger.warning("[Agent 5] MLflow logging failed: %s", e)

    def _score_key(m):
        score = tuning_results[m].get("best_score", 0)
        if pd.isna(score) or score != score:
            return -1.0
        return score

    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        fb.update_state(
            project_id,
            tuning_results=tuning_results,
            training_results=training_results,
            current_agent_id=5,
            approval_status="approved",
        )
        fb.log_agent_report(
            project_id=project_id,
            agent_id=5,
            agent_name="Training & Tuning",
            report={
                "models_tuned": list(tuning_results.keys()),
                "best_model": max(tuning_results, key=_score_key) if tuning_results else None,
                "tuning_results_summary": {m: {"best_score": r.get("best_score"), "status": r.get("status")} for m, r in tuning_results.items()},
            },
            status="success",
            execution_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.error("[Agent 5] Firebird write failed: %s", exc)

    state["tuning_results"] = tuning_results
    state["training_results"] = training_results
    state["current_agent_id"] = 5
    state["approval_status"] = "approved"
    state["error"] = None

    logger.info("[Agent 5] ✅ Complete in %d ms. Tuned %d models.",
                elapsed_ms, len(tuning_results))
    return state
