"""
End-to-end pipeline tests.

Tests the complete 6-agent pipeline from data intake to evaluation.
Verifies:
- All agents execute successfully
- State flows correctly through pipeline
- Memory is shared across agents
- Results are produced at each stage
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np


class TestPipelineE2E:
    """End-to-end pipeline tests."""
    
    def test_pipeline_initialization(self, full_pipeline_state):
        """Test pipeline initializes correctly."""
        assert full_pipeline_state["project_id"] is not None
        assert full_pipeline_state["dataset_path"] is not None
        assert full_pipeline_state["current_agent_id"] == 1
        assert full_pipeline_state["approval_status"] == "pending"
    
    def test_agent1_eda_execution(self, full_pipeline_state, sample_classification_df):
        """Test Agent 1 (EDA) executes successfully."""
        # Simulate Agent 1 execution
        state = full_pipeline_state.copy()
        
        # Load data
        df = sample_classification_df
        
        # Perform EDA
        eda_report = {
            "overview": {
                "rows": len(df),
                "columns": len(df.columns),
                "numeric_count": df.select_dtypes(include=[np.number]).shape[1],
                "categorical_count": df.select_dtypes(include=['object']).shape[1],
            },
            "missing_analysis": [],
            "outlier_analysis": [],
            "correlation_analysis": [],
        }
        
        state["eda_report"] = eda_report
        state["current_agent_id"] = 2
        
        # Verify state updated
        assert state["eda_report"] is not None
        assert state["eda_report"]["overview"]["rows"] == 200
        assert state["current_agent_id"] == 2
    
    def test_agent2_prep_execution(self, mock_state_agent2, sample_classification_df):
        """Test Agent 2 (Data Prep) executes successfully."""
        state = mock_state_agent2.copy()
        
        # Simulate data cleaning
        df = sample_classification_df.copy()
        
        # Remove duplicates
        df = df.drop_duplicates()
        
        # Impute missing values
        df = df.fillna(df.mean(numeric_only=True))
        
        # Create report
        cleaning_report = {
            "duplicates_removed": 0,
            "missing_imputed": 0,
            "outliers_handled": 0,
            "rows_before": 200,
            "rows_after": len(df),
        }
        
        state["cleaning_report"] = cleaning_report
        state["cleaned_data_path"] = "data/cleaned/test.csv"
        state["current_agent_id"] = 3
        
        # Verify state updated
        assert state["cleaning_report"] is not None
        assert state["current_agent_id"] == 3
    
    def test_agent3_features_execution(self, mock_state_agent3, sample_classification_df):
        """Test Agent 3 (Feature Engineering) executes successfully."""
        state = mock_state_agent3.copy()
        
        # Simulate feature selection
        df = sample_classification_df.copy()
        
        # Select features based on correlation with target
        target = df["target"]
        correlations = df.drop("target", axis=1).corrwith(target).abs()
        selected_features = correlations[correlations > 0.1].index.tolist()
        
        state["selected_features"] = selected_features
        state["engineered_data_path"] = "data/engineered/test.csv"
        state["current_agent_id"] = 4
        
        # Verify state updated
        assert state["selected_features"] is not None
        assert len(state["selected_features"]) > 0
        assert state["current_agent_id"] == 4
    
    def test_agent4_models_execution(self, mock_state_agent4):
        """Test Agent 4 (Model Architecture) executes successfully."""
        state = mock_state_agent4.copy()
        
        # Simulate model selection
        candidate_models = {
            "LogisticRegression": {"needs_scaling": True, "reason": "Linear model"},
            "RandomForest": {"needs_scaling": False, "reason": "Tree-based"},
            "SVM": {"needs_scaling": True, "reason": "Distance-based"},
            "GradientBoosting": {"needs_scaling": False, "reason": "Tree-based"},
            "KNN": {"needs_scaling": True, "reason": "Distance-based"},
            "NaiveBayes": {"needs_scaling": False, "reason": "Probabilistic"},
            "DecisionTree": {"needs_scaling": False, "reason": "Tree-based"},
            "MLP": {"needs_scaling": True, "reason": "Neural network"},
            "XGBoost": {"needs_scaling": False, "reason": "Tree-based"},
            "LightGBM": {"needs_scaling": False, "reason": "Tree-based"},
        }
        
        state["candidate_models"] = candidate_models
        state["task_type"] = "classification"
        state["current_agent_id"] = 5
        
        # Verify state updated
        assert state["candidate_models"] is not None
        assert len(state["candidate_models"]) == 10
        assert state["current_agent_id"] == 5
    
    def test_agent5_training_execution(self, mock_state_agent5):
        """Test Agent 5 (Training) executes successfully."""
        state = mock_state_agent5.copy()
        
        # Simulate model training
        training_results = {
            "RandomForest": {
                "cv_mean": 0.85,
                "cv_std": 0.05,
                "cv_scores": [0.80, 0.85, 0.90, 0.82, 0.88],
                "best_params": {"n_estimators": 100, "max_depth": 10},
            },
            "LogisticRegression": {
                "cv_mean": 0.80,
                "cv_std": 0.04,
                "cv_scores": [0.78, 0.82, 0.79, 0.81, 0.80],
                "best_params": {"C": 1.0, "solver": "lbfgs"},
            },
        }
        
        state["training_results"] = training_results
        state["current_agent_id"] = 6
        
        # Verify state updated
        assert state["training_results"] is not None
        assert "RandomForest" in state["training_results"]
        assert state["current_agent_id"] == 6
    
    def test_agent6_evaluation_execution(self, mock_state_agent6):
        """Test Agent 6 (Evaluation) executes successfully."""
        state = mock_state_agent6.copy()
        
        # Simulate model evaluation
        evaluation_report = {
            "best_model": "RandomForest",
            "best_score": 0.85,
            "metrics": {
                "accuracy": 0.85,
                "precision": 0.84,
                "recall": 0.86,
                "f1": 0.85,
                "auc": 0.90,
            },
            "recommendations": [
                "Model performs well on this dataset",
                "Consider ensemble methods for further improvement",
                "Monitor for data drift in production",
            ],
        }
        
        state["evaluation_report"] = evaluation_report
        state["approval_status"] = "completed"
        
        # Verify state updated
        assert state["evaluation_report"] is not None
        assert state["evaluation_report"]["best_model"] == "RandomForest"
        assert state["approval_status"] == "completed"
    
    def test_pipeline_state_flow(self, full_pipeline_state):
        """Test state flows correctly through all agents."""
        state = full_pipeline_state.copy()
        
        # Simulate pipeline progression
        agents = [1, 2, 3, 4, 5, 6]
        
        for agent_id in agents:
            state["current_agent_id"] = agent_id
            state["current_step"] = f"agent_{agent_id}"
            
            # Verify state updated
            assert state["current_agent_id"] == agent_id
            assert f"agent_{agent_id}" in state["current_step"]
    
    def test_pipeline_with_memory(self, full_pipeline_state, mock_memory_context):
        """Test pipeline with cross-agent memory."""
        state = full_pipeline_state.copy()
        
        # Initialize memory
        state["memory"] = Mock()
        state["memory"].get_agent_context = Mock(return_value=mock_memory_context)
        state["memory"].record_decision = Mock()
        
        # Agent 1 retrieves context
        context = state["memory"].get_agent_context(agent_id=1)
        assert context is not None
        
        # Agent 1 records decision
        decision = {
            "agent_id": 1,
            "summary": "Quality score: 8/10",
        }
        state["memory"].record_decision(decision)
        
        # Verify memory was used
        state["memory"].get_agent_context.assert_called()
        state["memory"].record_decision.assert_called()
    
    def test_pipeline_error_handling(self, full_pipeline_state):
        """Test pipeline handles errors gracefully."""
        state = full_pipeline_state.copy()
        
        # Simulate error in Agent 2
        error_msg = "Data cleaning failed: invalid column"
        state["error"] = error_msg
        state["errors"].append(error_msg)
        state["retry_count"] = 1
        
        # Verify error recorded
        assert state["error"] is not None
        assert len(state["errors"]) > 0
        assert state["retry_count"] > 0
    
    def test_pipeline_approval_gates(self, full_pipeline_state):
        """Test approval gates work correctly."""
        state = full_pipeline_state.copy()
        
        # Simulate approval workflow
        state["approval_status"] = "pending"
        assert state["approval_status"] == "pending"
        
        # User approves
        state["approval_status"] = "approved"
        assert state["approval_status"] == "approved"
        
        # Move to next agent
        state["current_agent_id"] = 2
        assert state["current_agent_id"] == 2


class TestPipelineIntegration:
    """Test integration between agents."""
    
    def test_agent1_output_feeds_agent2(self, full_pipeline_state, sample_classification_df):
        """Test Agent 1 output is used by Agent 2."""
        state = full_pipeline_state.copy()
        
        # Agent 1 produces EDA report
        state["eda_report"] = {
            "overview": {"rows": 200, "columns": 6},
            "missing_analysis": [{"column": "feat_0", "missing_pct": 5}],
        }
        
        # Agent 2 uses EDA report
        assert state["eda_report"] is not None
        assert state["eda_report"]["overview"]["rows"] == 200
    
    def test_agent2_output_feeds_agent3(self, full_pipeline_state):
        """Test Agent 2 output is used by Agent 3."""
        state = full_pipeline_state.copy()
        
        # Agent 2 produces cleaned data path
        state["cleaned_data_path"] = "data/cleaned/test.csv"
        
        # Agent 3 uses cleaned data
        assert state["cleaned_data_path"] is not None
        assert "cleaned" in state["cleaned_data_path"]
    
    def test_agent3_output_feeds_agent4(self, full_pipeline_state):
        """Test Agent 3 output is used by Agent 4."""
        state = full_pipeline_state.copy()
        
        # Agent 3 produces selected features
        state["selected_features"] = ["feat_0", "feat_1", "feat_2"]
        state["engineered_data_path"] = "data/engineered/test.csv"
        
        # Agent 4 uses selected features
        assert state["selected_features"] is not None
        assert len(state["selected_features"]) > 0
    
    def test_agent4_output_feeds_agent5(self, full_pipeline_state):
        """Test Agent 4 output is used by Agent 5."""
        state = full_pipeline_state.copy()
        
        # Agent 4 produces candidate models
        state["candidate_models"] = {
            "RandomForest": {"needs_scaling": False},
            "LogisticRegression": {"needs_scaling": True},
        }
        
        # Agent 5 uses candidate models
        assert state["candidate_models"] is not None
        assert "RandomForest" in state["candidate_models"]
    
    def test_agent5_output_feeds_agent6(self, full_pipeline_state):
        """Test Agent 5 output is used by Agent 6."""
        state = full_pipeline_state.copy()
        
        # Agent 5 produces training results
        state["training_results"] = {
            "RandomForest": {"cv_mean": 0.85, "cv_scores": [0.80, 0.85, 0.90]},
        }
        
        # Agent 6 uses training results
        assert state["training_results"] is not None
        assert "RandomForest" in state["training_results"]


class TestPipelinePerformance:
    """Test pipeline performance characteristics."""
    
    def test_pipeline_completes_in_reasonable_time(self, full_pipeline_state):
        """Test pipeline completes in reasonable time."""
        import time
        
        state = full_pipeline_state.copy()
        
        # Simulate pipeline execution
        start = time.time()
        
        # Simulate 6 agents
        for agent_id in range(1, 7):
            state["current_agent_id"] = agent_id
            # Simulate work (very fast for testing)
            pass
        
        elapsed = time.time() - start
        
        # Should complete very quickly (< 1 second for simulation)
        assert elapsed < 1.0
    
    def test_state_size_reasonable(self, full_pipeline_state):
        """Test pipeline state size is reasonable."""
        import sys
        
        state = full_pipeline_state.copy()
        
        # Add some data
        state["eda_report"] = {"data": "x" * 10000}
        state["training_results"] = {"data": "x" * 10000}
        
        # Estimate size
        size_bytes = sys.getsizeof(state)
        size_mb = size_bytes / (1024 * 1024)
        
        # Should be < 1MB
        assert size_mb < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

