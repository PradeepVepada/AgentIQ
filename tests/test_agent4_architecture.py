"""Tests for Agent 4 — Model Architecture."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.agent4_model_arch import (
    _detect_task_type,
    _make_pipeline,
    _get_classification_models,
    _get_regression_models,
    _stratified_split,
)


class TestDetectTaskType:
    def test_classification_goal(self):
        df = pd.DataFrame({"x": [1, 2], "y": [0, 1]})
        assert _detect_task_type("Predict churn", df, "y") == "classification"

    def test_regression_goal(self):
        df = pd.DataFrame({"x": [1, 2], "y": [1.5, 2.5]})
        assert _detect_task_type("Forecast sales", df, "y") == "regression"

    def test_clustering_goal(self):
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        assert _detect_task_type("Segment customers", df, "y") == "clustering"


class TestMakePipeline:
    def test_knn_gets_scaler(self):
        from sklearn.neighbors import KNeighborsClassifier
        pipe = _make_pipeline("KNeighborsClassifier", KNeighborsClassifier())
        assert pipe.steps[0][0] == "scaler"

    def test_random_forest_no_scaler(self):
        from sklearn.ensemble import RandomForestClassifier
        pipe = _make_pipeline("RandomForestClassifier", RandomForestClassifier())
        assert "scaler" not in [s[0] for s in pipe.steps]


class TestGetClassificationModels:
    def test_returns_dict(self):
        models = _get_classification_models()
        assert isinstance(models, dict)
        assert len(models) > 0

    def test_has_expected_models(self):
        models = _get_classification_models()
        assert "RandomForest" in models
        assert "LogisticRegression" in models
        assert "XGBoost" in models


class TestGetRegressionModels:
    def test_returns_dict(self):
        models = _get_regression_models()
        assert isinstance(models, dict)
        assert len(models) > 0

    def test_has_expected_models(self):
        models = _get_regression_models()
        assert "RandomForest" in models
        assert "Ridge" in models
        assert "XGBoost" in models


class TestStratifiedSplit:
    def test_split_ratio(self):
        df = pd.DataFrame({
            "target": [0] * 50 + [1] * 50,
            "feat": list(range(100)),
        })
        result = _stratified_split(df, "target", test_size=0.2)
        assert result["X_train_shape"][0] == 80
        assert result["X_test_shape"][0] == 20

    def test_stratify_preserved(self):
        df = pd.DataFrame({
            "target": [0] * 50 + [1] * 50,
            "feat": list(range(100)),
        })
        result = _stratified_split(df, "target", test_size=0.2)
        assert result["stratify"] is True
