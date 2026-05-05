"""Tests for Agent 6 — Evaluation & Reporting."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.agent6_evaluation import (
    _compute_classification_metrics,
    _compute_regression_metrics,
    _build_error_analysis,
)


class TestComputeClassificationMetrics:
    def test_accuracy_one(self):
        y_true = np.array([1, 1, 1])
        y_pred = np.array([1, 1, 1])
        metrics = _compute_classification_metrics(y_true, y_pred)
        assert metrics["accuracy"] == 1.0

    def test_accuracy_zero(self):
        y_true = np.array([0, 1, 1])
        y_pred = np.array([1, 0, 1])
        metrics = _compute_classification_metrics(y_true, y_pred)
        assert metrics["accuracy"] == pytest.approx(1/3)

    def test_precision_recall_f1(self):
        y_true = np.array([0, 1, 1, 1])
        y_pred = np.array([0, 1, 0, 1])
        metrics = _compute_classification_metrics(y_true, y_pred)
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics

    def test_confusion_matrix_shape(self):
        y_true = np.array([0, 1, 1, 1])
        y_pred = np.array([0, 1, 0, 1])
        metrics = _compute_classification_metrics(y_true, y_pred)
        assert len(metrics["confusion_matrix"]) == 2


class TestComputeRegressionMetrics:
    def test_perfect_prediction(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.0, 2.0, 3.0])
        metrics = _compute_regression_metrics(y_true, y_pred)
        assert metrics["mae"] == 0.0
        assert metrics["rmse"] == 0.0
        assert metrics["r2"] == 1.0

    def test_r2_score(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.1, 2.1, 2.9])
        metrics = _compute_regression_metrics(y_true, y_pred)
        assert 0.9 < metrics["r2"] <= 1.0
        assert metrics["mae"] > 0


class TestBuildErrorAnalysis:
    def test_classification_misclassifications(self):
        y_true = pd.Series([0, 1, 1, 1, 0])
        y_pred = np.array([0, 1, 0, 1, 1])
        errors = _build_error_analysis(y_true, y_pred, "classification")
        assert "top_misclassifications" in errors

    def test_regression_residuals(self):
        y_true = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        y_pred = np.array([1.5, 2.5, 2.5, 4.5, 4.5])
        errors = _build_error_analysis(y_true, y_pred, "regression")
        assert "residual_mean" in errors or "residual_patterns" in errors
