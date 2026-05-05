"""Tests for Agent 3 — Feature Engineering."""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from agents.agent3_feature_eng import (
    _detect_task_type,
    _identify_target,
    _select_by_correlation,
    _create_polynomial_features,
)


class TestDetectTaskType:
    def test_classification_keywords(self):
        assert _detect_task_type("Predict churn") == "classification"
        assert _detect_task_type("Classify spam") == "classification"
        assert _detect_task_type("customer churn prediction") == "classification"

    def test_regression_keywords(self):
        assert _detect_task_type("Forecast sales") == "regression"
        assert _detect_task_type("Estimate price") == "regression"
        assert _detect_task_type("predict revenue") == "regression"

    def test_clustering_keywords(self):
        assert _detect_task_type("Segment customers") == "clustering"
        assert _detect_task_type("Cluster groups") == "clustering"

    def test_default_classification(self):
        assert _detect_task_type("do something with data") == "classification"


class TestIdentifyTarget:
    def test_explicit_target_column(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "target": [0, 1, 0]})
        target = _identify_target(df, {}, "predict something")
        assert target == "target"

    def test_last_column_fallback(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        target = _identify_target(df, {}, "general analysis")
        assert target == "b"

    def test_categorical_fallback(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3], "outcome": ["a", "b", "a"]})
        target = _identify_target(df, {}, "predict outcome")
        assert target == "outcome"


class TestSelectByCorrelation:
    def test_high_correlation_selected(self):
        df = pd.DataFrame({
            "target": [1, 2, 3, 4, 5],
            "feat1": [1, 2, 3, 4, 5],
            "feat2": [1, 2, 200, 4, 5],
        })
        selected = _select_by_correlation(df, "target", threshold=0.9)
        assert "feat1" in selected

    def test_low_correlation_excluded(self):
        df = pd.DataFrame({
            "target": [1, 2, 3, 4, 5],
            "feat1": [1, 200, 3, 400, 5],
        })
        selected = _select_by_correlation(df, "target", threshold=0.9)
        assert "feat1" not in selected or "feat2" in selected


class TestPolynomialFeatures:
    def test_creates_poly_features(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        result = _create_polynomial_features(df, ["a"], degree=2)
        assert "a_poly2" in result.columns

    def test_degree_3(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        result = _create_polynomial_features(df, ["a"], degree=3)
        assert "a_poly2" in result.columns
        assert "a_poly3" in result.columns
