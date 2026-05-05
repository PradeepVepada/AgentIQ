"""Tests for data preparation tools (tools/prep_tools.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.prep_tools import (
    impute_column,
    remove_duplicates,
    cap_outliers,
    flag_outliers,
    correct_dtype,
    standardize_categorical,
    drop_column,
    execute_cleaning_plan,
)


class TestImputeColumn:
    def test_mean_imputation(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        result = impute_column(df, "a", "mean")
        assert result["a"].isna().sum() == 0
        assert result["a"].iloc[1] == 2.0

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = impute_column(df, "nonexistent", "mean")
        assert result.equals(df)


class TestRemoveDuplicates:
    def test_removes_duplicates(self):
        df = pd.DataFrame({"a": [1, 2, 1], "b": [3, 4, 3]})
        result = remove_duplicates(df)
        assert len(result) == 2


class TestCapOutliers:
    def test_caps_outliers(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 100]})
        result = cap_outliers(df, "a", method="iqr")
        assert result["a"].max() < 100

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = cap_outliers(df, "nonexistent", method="iqr")
        assert result.equals(df)


class TestFlagOutliers:
    def test_adds_flag_column(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 100]})
        result = flag_outliers(df, "a")
        assert f"{'a'}_outlier_flag" in result.columns


class TestCorrectDtype:
    def test_numeric_conversion(self):
        df = pd.DataFrame({"a": ["1", "2", "3"]})
        result = correct_dtype(df, "a", "numeric")
        assert result["a"].dtype in (np.float64, np.int64)

    def test_unknown_type_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = correct_dtype(df, "a", "unknown_type_xyz")
        assert result.equals(df)


class TestStandardizeCategorical:
    def test_lowercase_strip(self):
        df = pd.DataFrame({"a": ["  Hello  ", "WORLD", "  test"]})
        result = standardize_categorical(df, "a")
        assert result["a"].tolist() == ["hello", "world", "test"]


class TestDropColumn:
    def test_drops_column(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = drop_column(df, "a")
        assert "a" not in result.columns
        assert "b" in result.columns


class TestExecuteCleaningPlan:
    def test_executes_plan(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0, 100.0]})
        plan = [
            {"action": "impute", "column": "a", "strategy": "mean"},
            {"action": "cap_outliers", "column": "a"},
        ]
        result, log = execute_cleaning_plan(df, plan)
        assert result["a"].isna().sum() == 0

    def test_unknown_action_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        plan = [{"action": "unknown_xyz", "column": "a"}]
        result, log = execute_cleaning_plan(df, plan)
        assert log[0]["status"] == "skipped"
