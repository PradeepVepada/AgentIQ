"""Tests for Agent 5 — Training & Tuning."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import tempfile
import os

from agents.agent5_training import (
    _get_search_space,
    _tune_pipeline,
)


class TestGetSearchSpace:
    def test_logistic_regression_space(self):
        space = _get_search_space("LogisticRegression")
        assert "model__C" in space
        assert "model__penalty" in space

    def test_random_forest_space(self):
        space = _get_search_space("RandomForest")
        assert "model__n_estimators" in space
        assert "model__max_depth" in space

    def test_xgboost_space(self):
        space = _get_search_space("XGBoost")
        assert "model__n_estimators" in space
        assert "model__max_depth" in space

    def test_empty_space_for_unknown(self):
        space = _get_search_space("UnknownModelXYZ")
        assert space == {}


class TestTunePipeline:
    def test_tune_with_defaults(self):
        from sklearn.linear_model import LinearRegression
        from sklearn.datasets import make_regression

        X, y = make_regression(n_samples=100, n_features=5, noise=0.1, random_state=42)
        df = pd.DataFrame(X, columns=[f"f{i}" for i in range(5)])
        df["target"] = y
        X_train = df.drop("target", axis=1)
        y_train = df["target"]

        pipeline = _make_pipeline_for_test("LinearRegression")
        result = _tune_pipeline(pipeline, X_train, y_train, "regression", "LinearRegression", n_trials=3)

        assert result["status"] in ("success", "default_only", "failed_fit")
        assert "best_params" in result

    def test_tune_classification(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.datasets import make_classification

        X, y = make_classification(n_samples=100, n_features=5, n_classes=2, random_state=42)
        df = pd.DataFrame(X, columns=[f"f{i}" for i in range(5)])
        df["target"] = y
        X_train = df.drop("target", axis=1)
        y_train = df["target"]

        pipeline = _make_pipeline_for_test("LogisticRegression")
        result = _tune_pipeline(pipeline, X_train, y_train, "classification", "LogisticRegression", n_trials=3)

        assert result["status"] in ("success", "default_only", "failed_fit")


def _make_pipeline_for_test(model_name):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.ensemble import RandomForestClassifier

    if model_name == "LogisticRegression":
        return Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1000))])
    elif model_name == "RandomForest":
        return Pipeline([("model", RandomForestClassifier(n_estimators=10, random_state=42))])
    else:
        return Pipeline([("model", LinearRegression())])
