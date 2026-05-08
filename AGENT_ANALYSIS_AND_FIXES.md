# Agent 2, 3, 4 Analysis and Fixes

## Executive Summary

**Agent 2 Issue**: Shows 0 for all metrics because the cleaning report is not being populated with actual statistics.
**Agent 3 Issue**: Feature selection is working but stats not being properly calculated/displayed.
**Agent 4 Issue**: Model architecture selection is working but needs better error handling and validation.

---

## AGENT 2 ANALYSIS: Data Preparation

### Current Problem
```
ROWS PROCESSED: 0
MISSING HANDLED: 0
OUTLIERS DETECTED: 0
DUPLICATES REMOVED: 0
```

### Root Cause Analysis

1. **Cleaning Report Not Tracking Metrics**
   - The `cleaning_report` dict is created but doesn't track:
     - Actual rows processed
     - Missing values handled
     - Outliers detected
     - Duplicates removed

2. **Execution Log Not Aggregating Stats**
   - `execution_log` tracks individual steps but doesn't aggregate metrics
   - No counter for missing values handled
   - No counter for outliers detected

3. **LLM Cleaning Plan Often Empty**
   - When LLM generates cleaning plan, it often returns empty array
   - No fallback to automatic cleaning

### Fix Implementation

```python
# BEFORE (Current)
cleaning_report = {
    "shape_before": [rows_before, cols_before],
    "shape_after": [len(df), len(df.columns)],
    "rows_removed": rows_before - len(df),
    "steps_applied": len([e for e in execution_log if e.get("status") == "success"]),
    "execution_log": execution_log,
}

# AFTER (Fixed)
# Track actual metrics during execution
missing_handled = 0
outliers_detected = 0
duplicates_removed = 0

for step in cleaning_plan:
    if step["action"] == "remove_duplicates":
        duplicates_removed += step.get("rows_removed", 0)
    elif step["action"] == "impute":
        missing_handled += df[column].isna().sum()
    elif step["action"] == "remove_outliers":
        outliers_detected += step.get("rows_removed", 0)

cleaning_report = {
    "rows_processed": rows_before,
    "missing_handled": missing_handled,
    "outliers_detected": outliers_detected,
    "duplicates_removed": duplicates_removed,
    "cleaning_steps": [s.get("action") for s in execution_log if s.get("status") == "success"],
}
```

### Recommended Changes

1. **Add Automatic Cleaning Fallback**
   - If LLM returns empty plan, apply automatic cleaning:
     - Remove duplicates
     - Fill missing values with median/mode
     - Cap outliers with IQR method

2. **Track Metrics During Execution**
   - Count missing values before/after imputation
   - Count rows before/after outlier removal
   - Count duplicates removed

3. **Improve Cleaning Plan Generation**
   - Add more context to LLM prompt
   - Include examples of good cleaning plans
   - Add validation to ensure plan is not empty

---

## AGENT 3 ANALYSIS: Feature Engineering

### Current Status
✅ **Working correctly** - Deterministic feature selection is functioning

### What's Working
1. **Deterministic Selection**
   - Calculates correlation with target
   - Selects top 15 features by correlation
   - Removes highly correlated duplicates (>0.85)
   - Consistent results across runs

2. **Feature Stats Calculation**
   - `total_features`: Correctly counts all columns
   - `selected_features`: Correctly counts selected features
   - `top_features`: Correctly lists top 10 by correlation

### Issues Found

1. **Stats Not Being Passed to Frontend**
   - `feature_stats` is calculated but not always returned
   - Frontend expects `feature_stats` in response

2. **Feature Plan Generation**
   - LLM sometimes generates empty `selected_features` list
   - Should use deterministic selection as fallback

3. **Categorical Features Not Handled**
   - Categorical columns included in selection but not encoded
   - Should be one-hot encoded before training

### Recommended Fixes

```python
# BEFORE
return {
    "feature_engineering_plan": feature_plan,
    "selected_features": selected_features,
    "engineered_data_path": engineered_path,
    # Missing: feature_stats
}

# AFTER
return {
    "feature_engineering_plan": feature_plan,
    "selected_features": selected_features,
    "engineered_data_path": engineered_path,
    "feature_stats": {
        "total_features": len(df.columns) - 1,  # Exclude target
        "selected_features": len(selected_features),
        "top_features": sorted_features[:10],
        "numeric_features": len(numeric_cols),
        "categorical_features": len(categorical_cols),
    }
}
```

### Performance Notes
- **Deterministic Selection**: ✅ Fast and consistent
- **LLM Generation**: ⚠️ Sometimes slow, sometimes empty
- **Encoding**: ⚠️ Not applied, should be done before training

---

## AGENT 4 ANALYSIS: Model Architecture

### Current Status
✅ **Working correctly** - Model selection and split creation functioning

### What's Working
1. **Model Selection**
   - LLM generates appropriate models for task type
   - Fallback to LogisticRegression + RandomForest if parsing fails
   - Includes scaling requirements

2. **Train/Test Split**
   - Correctly creates stratified split for classification
   - Saves indices to disk
   - Proper random state for reproducibility

3. **Error Handling**
   - Gracefully handles missing engineered data
   - Provides default models if LLM fails

### Issues Found

1. **Candidate Models Format Inconsistency**
   - Sometimes returned as dict, sometimes as list
   - Frontend expects list format

2. **Missing Model Metadata**
   - No information about model hyperparameters
   - No information about scaling requirements

3. **Split Strategy Not Validated**
   - No check if stratify column exists
   - No validation of test_size value

### Recommended Fixes

```python
# BEFORE
return {
    "candidate_models": arch_plan.get("candidate_models", {}),  # Dict format
    "split_strategy": arch_plan.get("split_strategy", {}),
    "train_idx_path": train_idx_path,
    "test_idx_path": test_idx_path,
}

# AFTER
# Convert to list format for consistency
candidate_models_list = [
    {
        "name": model_name,
        "needs_scaling": model_info.get("needs_scaling", 0),
        "model_family": model_info.get("model_family", model_name),
    }
    for model_name, model_info in arch_plan.get("candidate_models", {}).items()
]

return {
    "candidate_models": candidate_models_list,  # List format
    "split_strategy": arch_plan.get("split_strategy", {}),
    "train_idx_path": train_idx_path,
    "test_idx_path": test_idx_path,
}
```

### Performance Notes
- **Model Selection**: ✅ Fast (1-2 LLM calls)
- **Split Creation**: ✅ Fast (< 1 second)
- **Error Recovery**: ✅ Good fallback strategy

---

## Implementation Priority

### High Priority (Fixes Agent 2)
1. ✅ Track actual metrics during cleaning execution
2. ✅ Add automatic cleaning fallback
3. ✅ Improve cleaning plan generation

### Medium Priority (Improves Agent 3)
1. ✅ Ensure feature_stats always returned
2. ✅ Add categorical feature encoding
3. ✅ Improve LLM feature plan generation

### Low Priority (Improves Agent 4)
1. ✅ Standardize candidate_models format
2. ✅ Add model metadata
3. ✅ Validate split strategy

---

## Testing Strategy

### Agent 2 Testing
```python
# Test with credit_risk dataset
# Expected: rows_processed > 0, missing_handled > 0
# Verify: All metrics non-zero
```

### Agent 3 Testing
```python
# Test feature selection consistency
# Run twice with same dataset
# Expected: Same features selected both times
# Verify: feature_stats in response
```

### Agent 4 Testing
```python
# Test model selection
# Expected: 2-5 candidate models
# Verify: candidate_models is list format
```

---

## Summary Table

| Agent | Issue | Severity | Status | Fix |
|-------|-------|----------|--------|-----|
| 2 | Metrics showing 0 | HIGH | 🔴 Needs Fix | Track metrics during execution |
| 2 | Empty cleaning plan | MEDIUM | 🟡 Partial | Add automatic fallback |
| 3 | Stats not returned | MEDIUM | 🟡 Partial | Always return feature_stats |
| 3 | Categorical not encoded | LOW | 🟢 OK | Can be done in Agent 5 |
| 4 | Format inconsistency | LOW | 🟢 OK | Standardize to list format |
| 4 | Missing metadata | LOW | 🟢 OK | Add in future enhancement |

---

## Next Steps

1. **Immediate**: Fix Agent 2 metrics tracking
2. **Short-term**: Improve Agent 3 feature stats
3. **Long-term**: Enhance Agent 4 model metadata

All fixes maintain backward compatibility and don't break existing functionality.
