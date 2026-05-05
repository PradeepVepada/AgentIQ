"""Agent 6 — Evaluation & Reporting.

Inputs: Tuned models, test set, training results
Outputs: Evaluation metrics, final structured report, recommendations
Human Gate: User reviews report and decides next steps (deploy, iterate, stop)

Responsibilities:
- Load each tuned model from disk
- Load test set using saved split indices
- Compute metrics:
    * Classification: Accuracy, Precision, Recall, F1, AUC-ROC, Confusion Matrix
    * Regression: MAE, RMSE, R2, MAPE, Residual analysis
    * Clustering: Silhouette, Calinski-Harabasz, Davies-Bouldin
- Error analysis: top misclassifications / residual patterns
- Side-by-side model comparison
- Feature importance from tree-based or linear models
- Generate structured evaluation_report dict
- Save evaluation_report to Firebird evaluation_report field
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


def _compute_classification_metrics(y_true, y_pred, y_proba=None) -> Dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        confusion_matrix, classification_report, roc_auc_score
    )

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }

    if y_proba is not None and len(np.unique(y_true)) == 2:
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
        except Exception:
            pass

    try:
        report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
        metrics["classification_report"] = report
    except Exception:
        pass

    return metrics


def _compute_regression_metrics(y_true, y_pred) -> Dict[str, Any]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_true, y_pred)),
        "mse": mse,
    }


def _compute_clustering_metrics(X, labels) -> Dict[str, Any]:
    from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score

    metrics = {}
    n_clusters = len(set(labels) - {-1})
    if n_clusters >= 2:
        try:
            metrics["silhouette"] = float(silhouette_score(X, labels))
            metrics["calinski_harabasz"] = float(calinski_harabasz_score(X, labels))
            metrics["davies_bouldin"] = float(davies_bouldin_score(X, labels))
        except Exception as e:
            logger.warning("[Agent 6] Clustering metrics failed: %s", e)
    return metrics


def _get_feature_importance(pipeline, feature_names: List[str]) -> Dict[str, float]:
    try:
        model = pipeline.steps[-1][1]
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            return dict(zip(feature_names, [float(x) for x in importances]))
        elif hasattr(model, "coef_"):
            coefs = np.abs(model.coef_).flatten()
            return dict(zip(feature_names[:len(coefs)], [float(x) for x in coefs]))
    except Exception as e:
        logger.warning("[Agent 6] Feature importance extraction failed: %s", e)
    return {}


def _build_error_analysis(y_true, y_pred, task_type: str, feature_names: List[str] = None) -> Dict[str, Any]:
    errors = {"top_misclassifications": [], "residual_patterns": ""}

    if task_type == "classification":
        try:
            misclassified = np.where(y_true.values != y_pred)[0]
            if len(misclassified) > 0:
                true_vals = y_true.values[misclassified]
                pred_vals = y_pred[misclassified]
                pairs = list(zip(true_vals, pred_vals))
                from collections import Counter
                pair_counts = Counter(pairs).most_common(5)
                errors["top_misclassifications"] = [
                    {"true": str(t), "predicted": str(p), "count": c}
                    for (t, p), c in pair_counts
                ]
        except Exception as e:
            logger.warning("[Agent 6] Misclassification analysis failed: %s", e)

    elif task_type == "regression":
        try:
            residuals = y_true.values - y_pred
            if len(residuals) > 0:
                errors["residual_mean"] = float(np.mean(residuals))
                errors["residual_std"] = float(np.std(residuals))
                errors["residual_patterns"] = (
                    "heteroscedastic" if np.abs(np.corrcoef(np.abs(residuals), y_pred)[0, 1]) > 0.5
                    else "homoscedastic"
                )
        except Exception as e:
            logger.warning("[Agent 6] Residual analysis failed: %s", e)

    return errors


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 6, "agent_name": "Evaluation & Reporting"})
def run_agent_6_evaluation(state: PipelineState) -> PipelineState:
    """LangGraph node: Evaluation & Reporting."""
    project_id = state["project_id"]
    engineered_path = state.get("engineered_data_path")
    split_strategy = state.get("split_strategy", {})
    tuning_results = state.get("tuning_results", {})
    training_results = state.get("training_results", {})
    task_type = state.get("task_type", "classification")

    logger.info("[Agent 6] Starting Evaluation — project %s", project_id)
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
    except Exception as exc:
        logger.error("[Agent 6] Load failed: %s", exc)
        state["error"] = str(exc)
        return state

    target_col = state.get("feature_engineering_plan", {}).get("target_column") or split_strategy.get("target_column")
    if not target_col:
        state["error"] = "No target column specified"
        return state

    X = df.drop(columns=[target_col])
    y = df[target_col]
    X_test = X.iloc[test_idx]
    y_test = y.iloc[test_idx]
    feature_names = X.columns.tolist()

    model_dir = os.path.join("models", project_id)

    evaluation_results = {}
    feature_importances = {}
    all_metrics = {}

    for model_name in tuning_results:
        model_path = os.path.join(model_dir, f"tuned_{model_name}_{project_id}.pkl")
        if not os.path.exists(model_path):
            logger.warning("[Agent 6] Model not found: %s", model_path)
            continue

        try:
            with open(model_path, "rb") as f:
                pipeline = pickle.load(f)
        except Exception as exc:
            logger.warning("[Agent 6] Could not load %s: %s", model_name, exc)
            continue

        try:
            y_pred = pipeline.predict(X_test)
        except Exception as exc:
            logger.warning("[Agent 6] Prediction failed for %s: %s", model_name, exc)
            continue

        if task_type == "classification":
            metrics = _compute_classification_metrics(y_test, y_pred)
            try:
                if hasattr(pipeline, "predict_proba"):
                    y_proba = pipeline.predict_proba(X_test)[:, 1]
                    metrics.update(_compute_classification_metrics(y_test, y_pred, y_proba))
            except Exception:
                pass
        elif task_type == "regression":
            metrics = _compute_regression_metrics(y_test, y_pred)
        else:
            metrics = _compute_clustering_metrics(X_test.values, y_pred)

        fi = _get_feature_importance(pipeline, feature_names)
        if fi:
            feature_importances[model_name] = fi

        error_analysis = _build_error_analysis(y_test, y_pred, task_type, feature_names)

        evaluation_results[model_name] = {
            "metrics": metrics,
            "error_analysis": error_analysis,
            "training_cv": training_results.get(model_name, {}),
        }
        all_metrics[model_name] = metrics

    if not evaluation_results:
        state["error"] = "No models could be evaluated"
        return state

    best_model = max(all_metrics, key=lambda m: all_metrics[m].get(
        "f1" if task_type == "classification" else "r2" if task_type == "regression" else "silhouette", 0
    ))

    best_metrics = all_metrics[best_model]
    best_cv = training_results.get(best_model, {}).get("cv_mean", 0)
    best_test = best_metrics.get(
        "f1" if task_type == "classification" else "r2" if task_type == "regression" else "silhouette", 0
    )

    recommendations = []
    risks = []

    if task_type == "classification":
        if best_metrics.get("f1", 0) >= 0.9:
            recommendations.append(f"Deploy {best_model} — excellent F1 of {best_metrics['f1']:.3f}")
        elif best_metrics.get("f1", 0) >= 0.7:
            recommendations.append(f"Deploy {best_model} — acceptable F1 of {best_metrics['f1']:.3f}")
        else:
            recommendations.append(f"Model performance is below threshold — consider more features or data")

    elif task_type == "regression":
        if best_metrics.get("r2", 0) >= 0.85:
            recommendations.append(f"Deploy {best_model} — strong R2 of {best_metrics['r2']:.3f}")
        elif best_metrics.get("r2", 0) >= 0.6:
            recommendations.append(f"Deploy {best_model} — moderate R2 of {best_metrics['r2']:.3f}, monitor for drift")
        else:
            recommendations.append("Low R2 — model may underfit, consider additional features")

    if best_cv - best_test > 0.1:
        risks.append(f"Potential overfitting: train={best_cv:.3f}, test={best_test:.3f}")
    if task_type == "classification":
        if best_metrics.get("precision", 0) < 0.6 or best_metrics.get("recall", 0) < 0.6:
            risks.append("Class imbalance may be affecting performance")

    best_fi = feature_importances.get(best_model, {})
    if best_fi:
        top_features = sorted(best_fi.items(), key=lambda x: x[1], reverse=True)[:5]
        recommendations.append(f"Key predictors: {', '.join([f[0] for f in top_features])}")

    evaluation_report = {
        "best_model": best_model,
        "task_type": task_type,
        "best_model_metrics": best_metrics,
        "model_comparison": all_metrics,
        "feature_importance": feature_importances,
        "error_analysis": evaluation_results.get(best_model, {}).get("error_analysis", {}),
        "recommendations": recommendations,
        "risks": risks,
    }

    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        fb.update_state(
            project_id,
            evaluation_report=evaluation_report,
            current_agent_id=6,
            approval_status="pending_eval_review",
        )
        fb.log_agent_report(
            project_id=project_id,
            agent_id=6,
            agent_name="Evaluation & Reporting",
            report={
                "best_model": best_model,
                "best_metrics": best_metrics,
                "models_evaluated": list(evaluation_results.keys()),
                "recommendations": recommendations,
                "risks": risks,
            },
            status="success",
            execution_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.error("[Agent 6] Firebird write failed: %s", exc)

    state["evaluation_report"] = evaluation_report
    state["current_agent_id"] = 6
    state["approval_status"] = "pending_eval_review"
    state["error"] = None

    logger.info("[Agent 6] ✅ Complete in %d ms. Best: %s (F1=%.3f).",
                elapsed_ms, best_model, best_metrics.get("f1", best_metrics.get("r2", 0)))
    return state
