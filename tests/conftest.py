"""Shared pytest fixtures for AgentIQ tests."""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

DATA_DIR = Path(__file__).parent / "fixtures"
DATA_DIR.mkdir(exist_ok=True)


@pytest.fixture
def sample_classification_df():
    """Binary classification dataset: 200 rows, 5 numeric features, 1 target."""
    rng = np.random.default_rng(42)
    n = 200
    X = rng.normal(size=(n, 5))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    df = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(5)])
    df["target"] = y
    return df


@pytest.fixture
def sample_regression_df():
    """Regression dataset: 200 rows, 5 numeric features, 1 continuous target."""
    rng = np.random.default_rng(42)
    n = 200
    X = rng.normal(size=(n, 5))
    y = X[:, 0] * 2 + X[:, 1] + rng.normal(size=n) * 0.5
    df = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(5)])
    df["target"] = y
    return df


@pytest.fixture
def sample_csv_path(sample_classification_df, tmp_path):
    """Save classification df to a temp CSV and return its path."""
    p = tmp_path / "sample_classification.csv"
    sample_classification_df.to_csv(p, index=False)
    return str(p)


@pytest.fixture
def sample_classification_csv(sample_classification_df, tmp_path):
    """Save and return path to classification CSV."""
    p = tmp_path / "sample_classification.csv"
    sample_classification_df.to_csv(p, index=False)
    return str(p)


@pytest.fixture
def sample_regression_csv(sample_regression_df, tmp_path):
    """Save and return path to regression CSV."""
    p = tmp_path / "sample_regression.csv"
    sample_regression_df.to_csv(p, index=False)
    return str(p)


@pytest.fixture
def project_id():
    return "test-project-0000"


@pytest.fixture
def mock_pipeline_state(sample_classification_csv, project_id):
    """Minimal pipeline state for testing agents in isolation."""
    return {
        "project_id": project_id,
        "project_goal": "Test classification project",
        "dataset_path": sample_classification_csv,
        "current_agent_id": 1,
        "approval_status": "pending",
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }


@pytest.fixture
def mock_state_agent2(sample_classification_csv, project_id):
    """Pipeline state ready for Agent 2."""
    return {
        "project_id": project_id,
        "project_goal": "Test classification",
        "dataset_path": sample_classification_csv,
        "current_agent_id": 2,
        "approval_status": "pending",
        "eda_report": {
            "overview": {"rows": 200, "columns": 6, "numeric_count": 5, "categorical_count": 0, "total_missing": 10, "duplicate_rows": 0},
            "missing_analysis": [{"column": "feat_0", "missing_pct": 5, "status": "moderate"}],
            "column_types": {"numeric": ["feat_0", "feat_1"], "categorical": [], "id": [], "datetime": []},
        },
        "cleaning_plan": [
            {"action": "impute", "column": "feat_0", "strategy": "mean", "priority": 1, "reason": "Test"},
        ],
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }


@pytest.fixture
def mock_state_agent3(sample_classification_csv, project_id):
    """Pipeline state ready for Agent 3."""
    return {
        "project_id": project_id,
        "project_goal": "Classify the target",
        "dataset_path": sample_classification_csv,
        "cleaned_data_path": sample_classification_csv,
        "eda_report": {
            "target_column": "target",
            "llm_eda_analysis": {"dataset_assessment": {"primary_target": "target"}},
        },
        "current_agent_id": 3,
        "approval_status": "pending",
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }


@pytest.fixture
def engineered_csv_path(sample_classification_csv, tmp_path):
    """Load classification CSV (simulating engineered data) and return path."""
    df = pd.read_csv(sample_classification_csv)
    p = tmp_path / "engineered_test.csv"
    df.to_csv(p, index=False)
    return str(p)


@pytest.fixture
def mock_state_agent4(engineered_csv_path, project_id):
    """Pipeline state ready for Agent 4."""
    train_idx = np.arange(160)
    test_idx = np.arange(160, 200)
    train_path = tmp_path / "train_idx.npy"
    test_path = tmp_path / "test_idx.npy"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        np.save(os.path.join(tmp_dir, "train_idx.npy"), train_idx)
        np.save(os.path.join(tmp_dir, "test_idx.npy"), test_idx)
    return {
        "project_id": project_id,
        "project_goal": "Classify the target",
        "dataset_path": "",
        "engineered_data_path": engineered_csv_path,
        "feature_engineering_plan": {"target_column": "target"},
        "selected_features": [c for c in ["feat_0", "feat_1", "feat_2"] if c in pd.read_csv(engineered_csv_path).columns],
        "scaling_requirements": {"feat_0": False, "feat_1": False, "feat_2": False},
        "current_agent_id": 4,
        "approval_status": "pending",
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }


@pytest.fixture
def mock_state_agent5(project_id):
    """Pipeline state ready for Agent 5."""
    return {
        "project_id": project_id,
        "project_goal": "Classify the target",
        "dataset_path": "",
        "engineered_data_path": "",
        "feature_engineering_plan": {"target_column": "target"},
        "split_strategy": {},
        "candidate_models": {
            "RandomForest": {"needs_scaling": False},
            "LogisticRegression": {"needs_scaling": True},
        },
        "task_type": "classification",
        "current_agent_id": 5,
        "approval_status": "pending",
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }


@pytest.fixture
def mock_state_agent6(project_id):
    """Pipeline state ready for Agent 6."""
    return {
        "project_id": project_id,
        "project_goal": "Classify the target",
        "dataset_path": "",
        "engineered_data_path": "",
        "feature_engineering_plan": {"target_column": "target"},
        "split_strategy": {},
        "tuning_results": {
            "RandomForest": {"best_score": 0.85, "best_params": {"n_estimators": 100}},
            "LogisticRegression": {"best_score": 0.80, "best_params": {"C": 1.0}},
        },
        "training_results": {
            "RandomForest": {"cv_mean": 0.85, "cv_std": 0.05, "cv_scores": [0.8, 0.85, 0.9, 0.82, 0.88]},
            "LogisticRegression": {"cv_mean": 0.80, "cv_std": 0.04, "cv_scores": [0.78, 0.82, 0.79, 0.81, 0.80]},
        },
        "task_type": "classification",
        "current_agent_id": 6,
        "approval_status": "pending",
        "retry_count": 0,
        "error": None,
        "thread_id": "test-thread-0000",
    }
