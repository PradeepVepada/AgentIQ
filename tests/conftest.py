"""Shared pytest fixtures for AgentIQ tests."""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

DATA_DIR = Path(__file__).parent / "fixtures"
DATA_DIR.mkdir(exist_ok=True)


# ── Mock LLM Client ──────────────────────────────────────────────────────

class MockLLMClient:
    """Mock LLM client for testing without API calls."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.call_count = 0
        self.last_prompt = None
    
    def invoke(self, prompt: str):
        """Mock LLM invocation."""
        self.call_count += 1
        self.last_prompt = prompt
        
        # Return mock response based on prompt content
        if "EDA" in prompt or "analysis" in prompt.lower():
            content = "APPROVED: The EDA analysis is comprehensive and well-structured."
        elif "review" in prompt.lower():
            content = "APPROVED: The output meets quality standards."
        else:
            content = "APPROVED: The analysis is complete."
        
        # Return object with .content attribute
        response = Mock()
        response.content = content
        return response


@pytest.fixture
def mock_llm_client():
    """Provide a mock LLM client for testing."""
    return MockLLMClient()


# ── Firebird Database Fixtures ──────────────────────────────────────────

@pytest.fixture
def temp_firebird_db():
    """Create a temporary Firebird database for testing."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.fdb")
        
        # Try to create a Firebird database
        try:
            import fdb
            # Create empty database
            con = fdb.create_database(
                f"localhost:{db_path}",
                user="SYSDBA",
                password="masterkey"
            )
            con.close()
            yield db_path
        except ImportError:
            # Firebird not installed, skip
            pytest.skip("Firebird not installed")
        except Exception as e:
            # Firebird not available, skip
            pytest.skip(f"Firebird not available: {e}")


# ── Memory Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def mock_decision():
    """Create a mock Decision object for testing."""
    from datetime import datetime
    
    decision_dict = {
        "agent_id": 1,
        "agent_name": "EDA",
        "decision_type": "ANALYSIS",
        "timestamp": datetime.now().isoformat(),
        "summary": "Quality score: 8/10",
        "details": {
            "quality_score": 8,
            "missing_pct": 5.2,
            "outlier_count": 3,
        },
        "confidence": 0.95,
        "reasoning": "Comprehensive statistical analysis",
        "impact": "Informs imputation strategy",
    }
    return decision_dict


@pytest.fixture
def mock_memory_context():
    """Create mock memory context for agents."""
    return {
        "previous_decisions": [
            {
                "agent_id": 1,
                "agent_name": "EDA",
                "summary": "Quality score: 8/10",
                "details": {"quality_score": 8, "missing_pct": 5.2},
            }
        ],
        "dynamic_suggestions": [
            "High missing rate (5.2%) — consider mean imputation",
            "3 outliers detected — use robust scaling",
        ],
        "known_issues": ["Column 'X' has constant values"],
        "recovery_hints": [],
    }


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


# ── Integration Test Fixtures ───────────────────────────────────────────

@pytest.fixture
def mock_state_with_memory(mock_pipeline_state, mock_memory_context):
    """Pipeline state with memory context initialized."""
    state = mock_pipeline_state.copy()
    state["memory"] = Mock()
    state["memory"].get_agent_context = Mock(return_value=mock_memory_context)
    state["memory"].record_decision = Mock()
    state["dynamic_suggestions"] = mock_memory_context["dynamic_suggestions"]
    return state


@pytest.fixture
def mock_state_with_revision_loop(mock_pipeline_state):
    """Pipeline state with revision loop enabled."""
    state = mock_pipeline_state.copy()
    state["enable_revision_loop"] = True
    state["max_iterations"] = 3
    state["iterations"] = 0
    state["generation_history"] = []
    state["feedback_history"] = []
    state["approved"] = False
    state["status"] = "generating"
    return state


@pytest.fixture
def mock_state_timeout_test(mock_pipeline_state):
    """Pipeline state for testing timeout behavior."""
    state = mock_pipeline_state.copy()
    state["enable_revision_loop"] = True
    state["max_iterations"] = 1  # Force timeout after 1 iteration
    state["iterations"] = 0
    state["approved"] = False
    state["status"] = "generating"
    return state


# ── Data Quality Fixtures ───────────────────────────────────────────────

@pytest.fixture
def df_with_missing_values():
    """DataFrame with various missing value patterns."""
    df = pd.DataFrame({
        "col_mcar": [1, 2, np.nan, 4, 5, np.nan, 7, 8, 9, 10],  # MCAR
        "col_mar": [1, 2, 3, np.nan, 5, np.nan, 7, 8, 9, 10],   # MAR
        "col_complete": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],        # No missing
        "col_mostly_missing": [1, np.nan, np.nan, np.nan, 5, np.nan, np.nan, 8, np.nan, 10],
    })
    return df


@pytest.fixture
def df_with_outliers():
    """DataFrame with outliers."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "normal": rng.normal(0, 1, 100),
        "with_outliers": np.concatenate([rng.normal(0, 1, 95), [100, 101, 102, 103, 104]]),
    })
    return df


@pytest.fixture
def df_with_multicollinearity():
    """DataFrame with highly correlated features."""
    rng = np.random.default_rng(42)
    x = rng.normal(0, 1, 100)
    df = pd.DataFrame({
        "feat_1": x,
        "feat_2": x + rng.normal(0, 0.1, 100),  # Highly correlated with feat_1
        "feat_3": x * 2 + rng.normal(0, 0.1, 100),  # Highly correlated with feat_1
        "feat_4": rng.normal(0, 1, 100),  # Independent
    })
    return df


@pytest.fixture
def df_with_duplicates():
    """DataFrame with duplicate rows."""
    df = pd.DataFrame({
        "col_a": [1, 2, 3, 1, 2, 3, 4, 5],
        "col_b": [10, 20, 30, 10, 20, 30, 40, 50],
    })
    return df


# ── Configuration Fixtures ──────────────────────────────────────────────

@pytest.fixture
def mock_settings():
    """Mock settings object."""
    from config.settings import PipelineConfig, StorageMode, LLMProvider
    
    settings = Mock(spec=PipelineConfig)
    settings.storage_mode = StorageMode.MEMORY
    settings.llm_provider = LLMProvider.OPENAI
    settings.openai_api_key = "sk-test-key"
    settings.openai_model = "gpt-4o-mini"
    settings.llm_temperature = 0.3
    settings.llm_max_tokens = 4096
    settings.enable_revision_loop = True
    settings.max_iterations_per_agent = 1
    settings.enable_human_in_loop = False
    settings.log_level = "INFO"
    return settings


# ── End-to-End Pipeline Fixtures ────────────────────────────────────────

@pytest.fixture
def full_pipeline_state(sample_classification_csv, project_id, mock_llm_client):
    """Complete pipeline state for end-to-end testing."""
    return {
        "project_id": project_id,
        "project_goal": "Binary classification",
        "dataset_path": sample_classification_csv,
        "dataset_name": "sample_classification.csv",
        "target_column": "target",
        "problem_type": "classification",
        
        # Memory
        "memory": Mock(),
        "dynamic_suggestions": [],
        "previous_decisions": [],
        
        # Agent outputs
        "eda_report": None,
        "llm_eda_analysis": None,
        "eda_approved": False,
        "cleaning_report": None,
        "cleaned_data_path": None,
        "selected_features": None,
        "engineered_data_path": None,
        "candidate_models": None,
        "training_results": None,
        "evaluation_report": None,
        
        # State machine
        "current_agent_id": 1,
        "current_step": "agent_1_eda",
        "approval_status": "pending",
        "thread_id": "test-thread-full",
        
        # Control
        "enable_revision_loop": False,  # Disable for speed
        "max_iterations": 1,
        "iterations": 0,
        "human_feedback": None,
        "error": None,
        "errors": [],
        "retry_count": 0,
    }

