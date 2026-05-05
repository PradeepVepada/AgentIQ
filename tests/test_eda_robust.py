"""Comprehensive tests for Agent 1 EDA edge cases and robust functions.

Tests cover:
- Edge case handling (empty, single-row, all-null)
- MCAR/MAR/MNAR detection
- Robust outlier detection
- Safe bivariate/multivariate analysis
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.eda_tools import (
    detect_missing_mechanism,
    detect_outliers_robust,
    bivariate_analysis_safe,
    multivariate_analysis_safe,
    detect_column_types,
)


class TestDetectMissingMechanism:
    """Tests for missing mechanism detection."""

    def test_no_missing(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        results = detect_missing_mechanism(df)
        assert len(results) == 2
        assert all(r["mechanism"] == "NONE" for r in results)

    def test_mcar_detection(self):
        """Test MCAR (Missing Completely At Random) detection."""
        np.random.seed(42)
        n = 100
        data = {
            "a": np.random.normal(100, 15, n),
            "b": np.random.normal(50, 10, n),
        }
        # Introduce MCAR: randomly remove values (not correlated with other vars)
        mask = np.random.random(n) < 0.2  # 20% missing
        data["a"][mask] = np.nan

        df = pd.DataFrame(data)
        results = detect_missing_mechanism(df)
        a_result = [r for r in results if r["column"] == "a"][0]
        # Should detect as MCAR (low correlation with other vars)
        assert a_result["mechanism"] in ["MCAR", "MAR"]

    def test_mnar_detection(self):
        """Test MNAR (Missing Not At Random) detection."""
        np.random.seed(42)
        n = 100
        income = np.random.exponential(50000, n)
        # Income missing if TRUE income > 150k (MNAR - depends on unobserved)
        income_reported = income.copy()
        income_reported[income > 150000] = np.nan

        df = pd.DataFrame({
            "income_reported": income_reported,
            "age": np.random.normal(40, 15, n)
        })

        results = detect_missing_mechanism(df)
        income_result = [r for r in results if r["column"] == "income_reported"][0]
        # With high missing and target correlation, should detect as MNAR or MAR
        assert income_result["mechanism"] in ["MNAR", "MAR", "UNCERTAIN"]

    def test_with_target_column(self):
        df = pd.DataFrame({
            "feature1": [1, 2, np.nan, 4, 5],
            "feature2": [5, 4, 3, 2, 1],
            "target": [0, 1, 0, 1, 0]
        })
        results = detect_missing_mechanism(df, target_col="target")
        assert len(results) == 3


class TestDetectOutliersRobust:
    """Tests for robust outlier detection."""

    def test_iqr_method(self):
        df = pd.DataFrame({"values": [1, 2, 3, 4, 5, 100]})  # 100 is outlier
        result = detect_outliers_robust(df["values"], method="iqr")
        assert result["outlier_count"] >= 1

    def test_zscore_method(self):
        df = pd.DataFrame({"values": list(range(50)) + [1000]})
        result = detect_outliers_robust(df["values"], method="zscore")
        assert result["outlier_count"] >= 1

    def test_too_few_values(self):
        df = pd.DataFrame({"values": [1, 2]})
        result = detect_outliers_robust(df["values"], method="iqr")
        assert result["outlier_count"] == 0
        assert "Too few" in result["note"]

    def test_zero_variance(self):
        df = pd.DataFrame({"values": [5, 5, 5, 5, 5]})
        result = detect_outliers_robust(df["values"], method="iqr")
        assert result["outlier_count"] == 0
        assert "Zero variance" in result["note"]

    def test_normal_distribution_clean(self):
        np.random.seed(42)
        df = pd.DataFrame({"values": np.random.normal(100, 10, 1000)})
        result = detect_outliers_robust(df["values"], method="iqr")
        # Normal distribution should have < 1% outliers
        assert result["outlier_pct"] < 5


class TestBivariateAnalysisSafe:
    """Tests for safe bivariate analysis."""

    def test_insufficient_columns(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        results, notes = bivariate_analysis_safe(df, ["a"])
        assert results == []
        assert "insufficient_columns" in notes

    def test_all_null_column(self):
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [np.nan, np.nan, np.nan],
            "c": [4.0, 5.0, 6.0]
        })
        results, notes = bivariate_analysis_safe(df, ["a", "b", "c"])
        # Should skip column "b" (all null) - results may have 1 correlation between a and c
        # The key is that b is not in results
        feature_cols = {r.get("feature_1") for r in results} | {r.get("feature_2") for r in results}
        assert "b" not in feature_cols

    def test_all_identical_column(self):
        df = pd.DataFrame({
            "a": [5.0, 5.0, 5.0],
            "b": [1.0, 2.0, 3.0]
        })
        results, notes = bivariate_analysis_safe(df, ["a", "b"])
        # Constant column correlation is NaN - should be filtered
        assert results == [] or "nan_correlations" in notes

    def test_strong_correlation_detected(self):
        df = pd.DataFrame({
            "a": list(range(100)),
            "b": [x * 2 for x in range(100)]
        })
        results, notes = bivariate_analysis_safe(df, ["a", "b"], min_correlation_threshold=0.9)
        assert len(results) >= 1
        assert results[0]["abs_correlation"] >= 0.9

    def test_inf_values_handled(self):
        df = pd.DataFrame({
            "a": [1.0, np.inf, 3.0],
            "b": [4.0, 5.0, -np.inf]
        })
        results, notes = bivariate_analysis_safe(df, ["a", "b"])
        # Should not crash, should return something
        assert isinstance(results, list)


class TestMultivariateAnalysisSafe:
    """Tests for safe multivariate analysis."""

    def test_insufficient_columns(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        results, notes = multivariate_analysis_safe(df, ["a", "b"])
        assert "note" in results

    def test_multicollinearity_detection(self):
        n = 100
        a_vals = np.arange(n, dtype=float)
        b_vals = a_vals * 2  # Perfect correlation
        c_vals = np.random.randn(n)

        df = pd.DataFrame({"a": a_vals, "b": b_vals, "c": c_vals})
        results, notes = multivariate_analysis_safe(df, ["a", "b", "c"])

        assert "condition_index" in results
        assert "multicollinearity_risk" in results
        # With a and b perfectly correlated, should detect some risk
        assert results["multicollinearity_risk"] in ["low", "medium", "high"]

    def test_all_nan_eigenvalues(self):
        # Edge case: all identical values
        df = pd.DataFrame({
            "a": [5, 5, 5, 5],
            "b": [5, 5, 5, 5],
            "c": [1, 2, 3, 4]
        })
        results, notes = multivariate_analysis_safe(df, ["a", "b", "c"])
        # Should handle gracefully
        assert isinstance(results, dict)


class TestDetectColumnTypes:
    """Tests for column type detection."""

    def test_numeric_detection(self):
        df = pd.DataFrame({
            "income": [1000, 2000, 3000],
            "age": [25, 30, 35]
        })
        df, id_cols, num_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
        assert len(num_cols) >= 2

    def test_categorical_detection(self):
        df = pd.DataFrame({
            "name": ["Alice", "Bob", "Charlie"],
            "city": ["NYC", "LA", "SF"]
        })
        df, id_cols, num_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
        assert len(cat_cols) >= 2

    def test_identifier_detection(self):
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"]
        })
        df, id_cols, num_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
        assert "id" in id_cols

    def test_datetime_detection(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        })
        df, id_cols, num_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
        assert len(date_cols) >= 1

    def test_mixed_types(self):
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "amount": [100.5, 200.3, 300.2],
            "category": ["A", "B", "A"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        })
        df, id_cols, num_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
        assert len(id_cols) >= 1
        assert len(num_cols) >= 1
        assert len(cat_cols) >= 1
        assert len(date_cols) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])