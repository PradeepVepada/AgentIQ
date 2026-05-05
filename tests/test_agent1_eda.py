"""Tests for Agent 1 — Data Intake & EDA."""
from __future__ import annotations

import pandas as pd
import pytest

from agents.agent1_eda import (
    validate_data_types,
    bivariate_analysis,
    multivariate_analysis,
    generate_correlation_heatmap_data,
    compute_data_quality_score,
)


class TestValidateDataTypes:
    def test_detects_text_as_numeric(self):
        df = pd.DataFrame({"col": ["1", "2", "3"]})
        issues = validate_data_types(df)
        assert any(i["column"] == "col" and i["suggested_type"] == "numeric" for i in issues)

    def test_empty_df(self):
        df = pd.DataFrame()
        issues = validate_data_types(df)
        assert issues == []

    def test_numeric_column_clean(self):
        df = pd.DataFrame({"col": [1.0, 2.0, 3.0]})
        issues = validate_data_types(df)
        assert issues == []


class TestBivariateAnalysis:
    def test_no_numeric_cols(self):
        df = pd.DataFrame({"a": ["x", "y", "z"]})
        assert bivariate_analysis(df, []) == []

    def test_single_numeric_col(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        assert bivariate_analysis(df, ["a"]) == []

    def test_strong_correlation_detected(self):
        import numpy as np
        df = pd.DataFrame({"a": list(range(100)), "b": [x * 2 for x in range(100)]})
        df["a"] = df["a"].astype(float)
        result = bivariate_analysis(df, ["a", "b"])
        assert len(result) >= 1
        assert result[0]["abs_correlation"] >= 0.9

    def test_weak_correlation_filtered(self):
        import numpy as np
        rng = np.random.default_rng(42)
        df = pd.DataFrame({"a": rng.normal(size=50), "b": rng.normal(size=50)})
        result = bivariate_analysis(df, ["a", "b"])
        for r in result:
            assert r["abs_correlation"] >= 0.5


class TestMultivariateAnalysis:
    def test_insufficient_columns(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = multivariate_analysis(df, ["a"])
        assert "note" in result

    def test_multicollinearity_detection(self):
        import numpy as np
        n = 100
        a_vals = np.arange(n, dtype=float)
        b_vals = a_vals * 2
        df = pd.DataFrame({"a": a_vals, "b": b_vals, "c": np.random.randn(n)})
        result = multivariate_analysis(df, ["a", "b", "c"])
        assert "condition_index" in result or "multicollinearity_risk" in result


class TestComputeDataQualityScore:
    def test_perfect_score(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        eda = {"overview": {"rows": 2, "columns": 2, "total_missing": 0, "duplicate_rows": 0}}
        score, issues = compute_data_quality_score(df, eda)
        assert score == 10.0
        assert issues == []

    def test_missing_penalty(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        eda = {"overview": {"rows": 3, "columns": 2, "total_missing": 1, "duplicate_rows": 0}, "missing_analysis": []}
        score, issues = compute_data_quality_score(df, eda)
        assert score < 10.0

    def test_high_missing_col_penalty(self):
        df = pd.DataFrame({"a": [None] * 60 + [1] * 40, "b": [1] * 100})
        eda = {
            "overview": {"rows": 100, "columns": 2, "total_missing": 60, "duplicate_rows": 0},
            "missing_analysis": [{"column": "a", "missing_pct": 60}],
            "outlier_analysis": [],
        }
        score, issues = compute_data_quality_score(df, eda)
        assert any(">50% missing" in i for i in issues)
