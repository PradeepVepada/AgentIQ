"""Tests for Agent 2 — Data Preparation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.agent2_data_prep import (
    impute_missing_values,
    handle_duplicates,
    treat_outliers,
    correct_data_types,
    apply_cleaning_plan,
    _generate_default_cleaning_plan,
)


class TestImputeMissingValues:
    def test_impute_mean(self):
        df = pd.DataFrame({"a": [1.0, 2.0, None, 4.0]})
        result, report = impute_missing_values(df, "a", "mean")
        assert report["status"] == "success"
        assert result.isna().sum() == 0

    def test_impute_median(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0, None]})
        result, report = impute_missing_values(df, "a", "median")
        assert report["status"] == "success"
        assert result.isna().sum() == 0
        assert report["fill_value"] == "2.000"

    def test_impute_constant(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        result, report = impute_missing_values(df, "a", "constant", constant_value=99.0)
        assert result.iloc[1] == 99.0

    def test_impute_drop_rows(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0, None]})
        result, report = impute_missing_values(df, "a", "drop_rows")
        assert len(result) == 2

    def test_impute_no_missing(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        result, report = impute_missing_values(df, "a", "mean")
        assert report["status"] == "skipped"


class TestHandleDuplicates:
    def test_removes_duplicates(self):
        df = pd.DataFrame({"a": [1, 2, 1], "b": [3, 4, 3]})
        result, report = handle_duplicates(df)
        assert len(result) == 2
        assert report["duplicates_removed"] == 1

    def test_preserve_business_valid(self):
        df = pd.DataFrame({"a": [1, 2, 1], "b": [3, 4, 3]})
        result, report = handle_duplicates(df, preserve_business_valid=True)
        assert len(result) == 2

    def test_no_duplicates(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result, report = handle_duplicates(df)
        assert report["duplicates_found"] == 0


class TestTreatOutliers:
    def test_cap_iqr(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 100]})
        result, report = treat_outliers(df, "a", strategy="cap", method="iqr")
        assert report["outliers_identified"] >= 1
        assert report["outliers_treated"] >= 1

    def test_flag_outliers(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 100]})
        result, report = treat_outliers(df, "a", strategy="flag")
        assert "a_outlier" in result.columns

    def test_remove_outliers(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 100]})
        result, report = treat_outliers(df, "a", strategy="remove")
        assert len(result) < len(df)


class TestCorrectDataTypes:
    def test_text_to_numeric(self):
        df = pd.DataFrame({"a": ["1", "2", "three"]})
        result, report = correct_data_types(df, [{"column": "a", "target_type": "numeric"}])
        assert report["corrections_applied"][0]["status"] == "success"

    def test_mixed_to_string(self):
        df = pd.DataFrame({"a": [1, "two", 3.0]})
        result, report = correct_data_types(df, [{"column": "a", "target_type": "string"}])
        assert report["corrections_applied"][0]["status"] == "success"


class TestApplyCleaningPlan:
    def test_empty_plan(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result, report = apply_cleaning_plan(df, [], {})
        assert result.equals(df)

    def test_impute_step(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        plan = [{"action": "impute", "column": "a", "strategy": "mean", "priority": 1, "reason": "test"}]
        result, report = apply_cleaning_plan(df, plan, {})
        assert result["a"].isna().sum() == 0

    def test_remove_duplicates_step(self):
        df = pd.DataFrame({"a": [1, 2, 1]})
        plan = [{"action": "remove_duplicates", "priority": 1}]
        result, report = apply_cleaning_plan(df, plan, {})
        assert len(result) == 2

    def test_unknown_action_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        plan = [{"action": "unknown_action", "column": "a", "priority": 1}]
        result, report = apply_cleaning_plan(df, plan, {})
        assert report["steps_failed"] == 0


class TestGenerateDefaultCleaningPlan:
    def test_high_missing_drop_column(self):
        eda = {
            "missing_analysis": [
                {"column": "a", "missing_pct": 85},
            ],
            "overview": {"duplicate_rows": 0},
        }
        plan = _generate_default_cleaning_plan(eda)
        assert any(p["action"] == "drop_column" and p["column"] == "a" for p in plan)

    def test_moderate_missing_impute(self):
        eda = {
            "missing_analysis": [
                {"column": "b", "missing_pct": 40},
            ],
            "overview": {"duplicate_rows": 0},
            "missing_mechanisms": {},
        }
        plan = _generate_default_cleaning_plan(eda)
        assert any(p["action"] == "impute" and p["column"] == "b" for p in plan)

    def test_duplicates_added(self):
        eda = {
            "missing_analysis": [],
            "overview": {"duplicate_rows": 5},
        }
        plan = _generate_default_cleaning_plan(eda)
        assert any(p["action"] == "remove_duplicates" for p in plan)
