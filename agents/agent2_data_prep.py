"""Agent 2 — Data Preparation.

Inputs: Raw data + EDA report + human feedback
Outputs: Cleaned data, cleaning plan
Human Gate: User reviews & approves cleaning decisions

Responsibilities:
- Handle missing values (imputation strategy based on MCAR/MAR/MNAR)
- Remove exact duplicates (preserve business-valid duplicates)
- Outlier treatment (cap, remove, or flag)
- Data type corrections
- Categorical standardization
- Normalization/scaling decisions (deferred to Agent 4)
- Save cleaned data to /data/cleaned_{project_id}.csv
- Document all cleaning decisions in cleaning_plan

Failure Recovery:
- If imputation fails -> LangSmith identifies failed column
- Manager Agent re-runs imputation with alternative strategy
- Updated cleaning_plan stored in Firebird
- Human re-approves before Agent 3

Cross-agent memory integration per AGENT_LIGHTNING_INTEGRATION Option 2.
For memory module, see memory/agent_memory.py
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
import numpy as np
import pandas as pd
from langsmith import traceable, trace

from db import firebird_client as fb
from memory.agent_memory import AgentMemory, Decision, DecisionType
from tools.data_loader import load_dataset, save_dataset
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

_IMPUTATION_STRATEGIES = ["mean", "median", "mode", "constant", "ffill", "bfill", "drop_rows", "drop_column"]

_OUTLIER_STRATEGIES = ["cap", "remove", "flag", "none"]

_FAILURE_CONTEXT = {}


def _fmt(x, digits: int = 3):
    if pd.isna(x):
        return None
    try:
        x = float(x)
    except Exception:
        return x
    return f"{x:.{digits}f}" if abs(x) < 1_000_000 else f"{x:.3e}"


def impute_missing_values(
    df: pd.DataFrame,
    column: str,
    strategy: str,
    constant_value: Any = None,
    eda_missing_type: str = "MCAR"
) -> Tuple[pd.Series, Dict]:
    """Impute missing values for a column using the specified strategy."""
    result = {"column": column, "strategy": strategy, "values_imputed": 0, "status": "success"}
    
    if df[column].isnull().sum() == 0:
        result["status"] = "skipped"
        result["note"] = "No missing values"
        return df[column], result
    
    missing_count = df[column].isnull().sum()
    result["values_imputed"] = int(missing_count)
    
    try:
        if strategy == "mean":
            fill_value = df[column].mean()
            df[column] = df[column].fillna(fill_value)
            result["fill_value"] = _fmt(fill_value)
            
        elif strategy == "median":
            fill_value = df[column].median()
            df[column] = df[column].fillna(fill_value)
            result["fill_value"] = _fmt(fill_value)
            
        elif strategy == "mode":
            mode_vals = df[column].mode()
            fill_value = mode_vals.iloc[0] if not mode_vals.empty else None
            df[column] = df[column].fillna(fill_value)
            result["fill_value"] = str(fill_value)
            
        elif strategy == "constant":
            df[column] = df[column].fillna(constant_value)
            result["fill_value"] = str(constant_value)
            
        elif strategy == "ffill":
            df[column] = df[column].fillna(method="ffill")
            
        elif strategy == "bfill":
            df[column] = df[column].fillna(method="bfill")
            
        elif strategy == "drop_rows":
            df.dropna(subset=[column], inplace=True)
            result["rows_dropped"] = missing_count
            result["note"] = "Dropped rows with missing values"
            
        elif strategy == "drop_column":
            if column in df.columns:
                df.drop(columns=[column], inplace=True)
            result["column_dropped"] = True
            result["note"] = "Column dropped entirely"
        else:
            df[column] = df[column].fillna(df[column].mode().iloc[0] if not df[column].mode().empty else 0)
            
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error("[Agent 2] Imputation failed for %s: %s", column, e)
    
    return df[column], result


def handle_duplicates(df: pd.DataFrame, preserve_business_valid: bool = True) -> Tuple[pd.DataFrame, Dict]:
    """Remove exact duplicates, preserving business-valid ones if specified."""
    result = {
        "duplicates_found": 0,
        "duplicates_removed": 0,
        "status": "success"
    }
    
    dup_count = df.duplicated().sum()
    result["duplicates_found"] = int(dup_count)
    
    if dup_count > 0:
        original_shape = df.shape
        if preserve_business_valid:
            df_clean = df.drop_duplicates(keep="first")
        else:
            df_clean = df.drop_duplicates()
        
        result["duplicates_removed"] = int(original_shape[0] - df_clean.shape[0])
        result["rows_before"] = original_shape[0]
        result["rows_after"] = df_clean.shape[0]
        df = df_clean
    
    return df, result


def treat_outliers(
    df: pd.DataFrame,
    column: str,
    strategy: str = "cap",
    method: str = "iqr",
    lower_quantile: float = 0.25,
    upper_quantile: float = 0.75,
    iqr_multiplier: float = 1.5,
    cap_value: float = None
) -> Tuple[pd.DataFrame, Dict]:
    """Treat outliers using specified strategy."""
    result = {
        "column": column,
        "strategy": strategy,
        "outliers_identified": 0,
        "outliers_treated": 0,
        "status": "success"
    }
    
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    if s.empty:
        return df, result
    
    if method == "iqr":
        q1 = s.quantile(lower_quantile)
        q3 = s.quantile(upper_quantile)
        iqr = q3 - q1
        lower_bound = q1 - iqr_multiplier * iqr
        upper_bound = q3 + iqr_multiplier * iqr
    elif method == "percentile":
        lower_bound = s.quantile(0.05)
        upper_bound = s.quantile(0.95)
    else:
        lower_bound = s.mean() - 3 * s.std()
        upper_bound = s.mean() + 3 * s.std()
    
    outlier_mask = (df[column] < lower_bound) | (df[column] > upper_bound)
    outlier_count = outlier_mask.sum()
    result["outliers_identified"] = int(outlier_count)
    result["lower_bound"] = _fmt(lower_bound)
    result["upper_bound"] = _fmt(upper_bound)
    
    if strategy == "none":
        return df, result
    
    if strategy == "flag":
        flag_col = f"{column}_outlier"
        df[flag_col] = outlier_mask.astype(int)
        result["flag_column"] = flag_col
        result["outliers_treated"] = 0
        
    elif strategy == "cap":
        if cap_value is not None:
            df.loc[df[column] < lower_bound, column] = cap_value
            df.loc[df[column] > upper_bound, column] = cap_value
        else:
            df.loc[df[column] < lower_bound, column] = lower_bound
            df.loc[df[column] > upper_bound, column] = upper_bound
        result["outliers_treated"] = outlier_count
        
    elif strategy == "remove":
        df = df[~outlier_mask]
        result["outliers_treated"] = outlier_count
        result["rows_after_removal"] = len(df)
    
    return df, result


def correct_data_types(df: pd.DataFrame, dtype_corrections: List[Dict]) -> Tuple[pd.DataFrame, Dict]:
    """Correct data types based on EDA findings."""
    result = {"corrections_applied": [], "status": "success"}
    
    for correction in dtype_corrections:
        col = correction.get("column")
        target_type = correction.get("target_type")
        
        if col not in df.columns:
            continue
            
        try:
            if target_type == "numeric":
                df[col] = pd.to_numeric(df[col], errors="coerce")
                result["corrections_applied"].append({
                    "column": col,
                    "from": str(df[col].dtype),
                    "to": "numeric",
                    "status": "success"
                })
            elif target_type == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")
                result["corrections_applied"].append({
                    "column": col,
                    "from": str(df[col].dtype),
                    "to": "datetime",
                    "status": "success"
                })
            elif target_type == "category":
                df[col] = df[col].astype("category")
                result["corrections_applied"].append({
                    "column": col,
                    "from": str(df[col].dtype),
                    "to": "category",
                    "status": "success"
                })
            elif target_type == "string":
                df[col] = df[col].astype(str)
                result["corrections_applied"].append({
                    "column": col,
                    "from": str(df[col].dtype),
                    "to": "string",
                    "status": "success"
                })
        except Exception as e:
            result["corrections_applied"].append({
                "column": col,
                "target_type": target_type,
                "status": "failed",
                "error": str(e)
            })
    
    return df, result


def standardize_categoricals(
    df: pd.DataFrame,
    columns: List[str],
    method: str = "label"
) -> Tuple[pd.DataFrame, Dict]:
    """Standardize categorical columns."""
    result = {"columns_standardized": [], "status": "success"}
    
    for col in columns:
        if col not in df.columns:
            continue
            
        try:
            if method == "label":
                df[col] = df[col].astype(str).str.strip().str.lower()
            elif method == "onehot":
                pass
            elif method == "ordinal":
                unique_vals = df[col].dropna().unique()
                mapping = {v: i for i, v in enumerate(unique_vals)}
                df[f"{col}_encoded"] = df[col].map(mapping)
                result["encoding_mapping"] = mapping
            
            result["columns_standardized"].append({
                "column": col,
                "method": method,
                "status": "success"
            })
        except Exception as e:
            result["columns_standardized"].append({
                "column": col,
                "status": "failed",
                "error": str(e)
            })
    
    return df, result


def apply_cleaning_plan(
    df: pd.DataFrame,
    cleaning_plan: List[Dict],
    eda_report: Dict,
    failure_context: Optional[Dict] = None
) -> Tuple[pd.DataFrame, Dict]:
    """Apply the full cleaning plan generated by Agent 1."""
    execution_log = []
    shape_before = list(df.shape)

    missing_mechanisms = eda_report.get("missing_mechanisms", {})
    missing_analysis = {m["column"]: m for m in eda_report.get("missing_analysis", [])}

    for step in cleaning_plan:
        action = step.get("action")
        column = step.get("column")
        strategy = step.get("strategy")
        priority = step.get("priority", 99)

        try:
            if action == "impute":
                col_missing_type = missing_mechanisms.get(column, "MCAR")
                actual_strategy = strategy or ("mean" if col_missing_type == "MCAR" else "mode")

                df[column], imp_result = impute_missing_values(
                    df, column, actual_strategy,
                    eda_missing_type=col_missing_type
                )
                execution_log.append({
                    "step": step,
                    "status": imp_result["status"],
                    "result": imp_result
                })

            elif action == "remove_duplicates":
                df, dup_result = handle_duplicates(df)
                execution_log.append({
                    "step": step,
                    "status": "success",
                    "result": dup_result
                })

            elif action == "cap_outliers" or action == "flag_outliers":
                method = step.get("method", "iqr")
                strat = "cap" if action == "cap_outliers" else "flag"
                df, outlier_result = treat_outliers(
                    df, column, strategy=strat, method=method
                )
                execution_log.append({
                    "step": step,
                    "status": outlier_result["status"],
                    "result": outlier_result
                })

            elif action == "correct_dtype":
                df, dtype_result = correct_data_types(
                    df, [{"column": column, "target_type": step.get("target_type")}]
                )
                execution_log.append({
                    "step": step,
                    "status": dtype_result["status"],
                    "result": dtype_result
                })

            elif action == "standardize_categorical":
                df, cat_result = standardize_categoricals(df, [column])
                execution_log.append({
                    "step": step,
                    "status": cat_result["status"],
                    "result": cat_result
                })

        except Exception as e:
            logger.error("[Agent 2] Failed to apply step %s: %s", step, e)
            if failure_context is not None:
                failure_context["step"] = "apply_cleaning_plan"
                failure_context["action"] = action
                failure_context["column"] = column
                failure_context["error"] = str(e)
            execution_log.append({
                "step": step,
                "status": "failed",
                "error": str(e)
            })

    shape_after = list(df.shape)

    report = {
        "shape_before": shape_before,
        "shape_after": shape_after,
        "steps_applied": len([e for e in execution_log if e["status"] == "success"]),
        "steps_failed": len([e for e in execution_log if e["status"] == "failed"]),
        "execution_log": execution_log
    }

    return df, report


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 2, "agent_name": "Data Prep"})
def run_agent_2_prep(state: PipelineState) -> PipelineState:
    """LangGraph node: Data Preparation with memory integration."""
    project_id = state["project_id"]
    dataset_path = state["dataset_path"]
    eda_report = state.get("eda_report", {})
    cleaning_plan = state.get("cleaning_plan", [])
    human_feedback = state.get("human_feedback", {})

    logger.info("[Agent 2] Starting Data Prep — project %s", project_id)
    t0 = time.time()

    # ── Initialize Memory ─────────────────────────────────────────────────
    memory: Optional[AgentMemory] = state.get("memory")
    if memory is None:
        memory = AgentMemory(project_id=project_id, db_client=fb)
        state["memory"] = memory

    # Get context from Agent 1 findings
    context = memory.get_agent_context(agent_id=2)
    state["dynamic_suggestions"] = context.get("dynamic_suggestions", [])
    state["previous_decisions"] = context.get("previous_decisions", [])
    state["known_issues"] = context.get("known_issues", [])

    global _FAILURE_CONTEXT
    _FAILURE_CONTEXT = {"project_id": project_id, "step": None, "action": None, "column": None, "error": None}

    if not cleaning_plan:
        logger.warning("[Agent 2] No cleaning plan found, using defaults")
        cleaning_plan = _generate_default_cleaning_plan(eda_report)

    if human_feedback:
        feedback_plan = _parse_human_feedback(human_feedback, cleaning_plan)
        cleaning_plan = _merge_feedback_plan(cleaning_plan, feedback_plan)

    try:
        df = load_dataset(dataset_path)
        original_rows = len(df)
        logger.info("[Agent 2] Loaded %d rows × %d cols.", *df.shape)
    except Exception as exc:
        logger.error("[Agent 2] Data load failed: %s", exc)
        state["error"] = str(exc)
        memory.record_failure(agent_id=2, step="load_data", error=str(exc), recovery_hint="Check file path and format")
        return state

    df_cleaned, cleaning_report = apply_cleaning_plan(df, cleaning_plan, eda_report, _FAILURE_CONTEXT)

    cleaned_path = os.path.join("data", "cleaned", f"cleaned_{project_id}.csv")
    try:
        save_dataset(df_cleaned, cleaned_path)
        logger.info("[Agent 2] Saved cleaned data to %s", cleaned_path)
        cleaning_report["cleaned_data_path"] = cleaned_path
    except Exception as exc:
        logger.error("[Agent 2] Failed to save cleaned data: %s", exc)
        cleaning_report["save_error"] = str(exc)

    elapsed_ms = int((time.time() - t0) * 1000)

    # ── Record Decision in Memory ─────────────────────────────────────────
    rows_after = len(df_cleaned)
    rows_removed = original_rows - rows_after

    decision = Decision(
        agent_id=2,
        agent_name="Data Prep",
        decision_type=DecisionType.IMPUTATION,
        timestamp=datetime.now().isoformat(),
        summary=f"Cleaned {rows_after:,} rows (removed {rows_removed})",
        details={
            "rows_before": original_rows,
            "rows_after": rows_after,
            "rows_removed": rows_removed,
            "cleaning_decisions": cleaning_report.get("execution_log", []),
            "cleaning_plan": cleaning_plan,
        },
        confidence=0.9,
        reasoning="Applied data quality fixes based on Agent 1 EDA findings",
        impact="Cleaned data ready for feature engineering in Agent 3"
    )
    memory.record_decision(decision)

    try:
        fb.update_state(
            project_id,
            cleaning_report=cleaning_report,
            cleaned_data_path=cleaned_path,
            current_agent_id=2,
            approval_status="pending_prep_review",
        )
        fb.log_agent_report(
            project_id=project_id,
            agent_id=2,
            agent_name="Data Prep",
            report={
                "cleaning_plan": cleaning_plan,
                "cleaning_report": cleaning_report,
                "human_feedback_applied": bool(human_feedback)
            },
            status="success",
            execution_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.error("[Agent 2] Firebird write failed: %s", exc)

    state["cleaned_data_path"] = cleaned_path
    state["cleaning_report"] = cleaning_report
    state["current_agent_id"] = 2
    state["approval_status"] = "pending_prep_review"
    state["error"] = None
    state["memory"] = memory

    logger.info("[Agent 2] ✅ Complete in %d ms.", elapsed_ms)
    return state


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 2, "agent_name": "Data Prep", "retry": True})
def retry_failed_cleaning_step(
    state: PipelineState,
    failed_step: Optional[Dict] = None,
    alternative_strategy: Optional[str] = None
) -> PipelineState:
    """Retry any failed cleaning step with alternative strategy.

    Args:
        state: Pipeline state containing cleaned_data and cleaning_report
        failed_step: The step that failed (from execution_log). If None, uses _FAILURE_CONTEXT.
        alternative_strategy: New strategy to use. If None, derives from step type.
    """
    logger.info("[Agent 2] Retrying failed cleaning step")

    if failed_step is None:
        failed_step = {
            "action": _FAILURE_CONTEXT.get("action"),
            "column": _FAILURE_CONTEXT.get("column"),
            "strategy": alternative_strategy
        }

    cleaned_path = state.get("cleaned_data_path")
    if cleaned_path:
        df = load_dataset(cleaned_path)
    else:
        df = load_dataset(state["dataset_path"])

    action = failed_step.get("action")
    column = failed_step.get("column")
    result = {"status": "success"}

    try:
        if action == "impute":
            df[column], result = impute_missing_values(df, column, alternative_strategy or "median")

        elif action == "cap_outliers":
            df, result = treat_outliers(df, column, strategy="cap", method=alternative_strategy or "iqr")

        elif action == "flag_outliers":
            df, result = treat_outliers(df, column, strategy="flag", method=alternative_strategy or "iqr")

        elif action == "remove_outliers":
            df, result = treat_outliers(df, column, strategy="remove", method=alternative_strategy or "iqr")

        elif action == "correct_dtype":
            df, result = correct_data_types(df, [{"column": column, "target_type": alternative_strategy}])

        elif action == "standardize_categorical":
            df, result = standardize_categoricals(df, [column])

        elif action == "remove_duplicates":
            df, result = handle_duplicates(df)

        else:
            logger.warning("[Agent 2] Unknown action to retry: %s", action)
            result = {"status": "unknown_action", "action": action}

    except Exception as e:
        logger.error("[Agent 2] Retry failed for %s/%s: %s", action, column, e)
        result = {"status": "retry_failed", "error": str(e)}

    cleaning_report = state.get("cleaning_report", {})
    cleaning_report["retry_log"] = cleaning_report.get("retry_log", [])
    cleaning_report["retry_log"].append({
        "action": action,
        "column": column,
        "alternative_strategy": alternative_strategy,
        "result": result,
    })
    state["cleaning_report"] = cleaning_report

    fb.update_state(state["project_id"], cleaning_report=cleaning_report)
    fb.log_agent_report(
        project_id=state["project_id"],
        agent_id=2,
        agent_name="Data Prep",
        report={"retry": failed_step, "result": result},
        status="retry",
    )

    return state


def retry_failed_imputation(
    state: PipelineState,
    column: str,
    alternative_strategy: str
) -> PipelineState:
    """Re-run imputation with alternative strategy for a failed column."""
    logger.info("[Agent 2] Retrying imputation for %s with %s", column, alternative_strategy)

    cleaned_path = state.get("cleaned_data_path")
    if cleaned_path:
        df = load_dataset(cleaned_path)
    else:
        df = load_dataset(state["dataset_path"])

    df[column], result = impute_missing_values(df, column, alternative_strategy)

    cleaning_report = state.get("cleaning_report", {})
    cleaning_report["retry_log"] = cleaning_report.get("retry_log", [])
    cleaning_report["retry_log"].append({
        "column": column,
        "strategy": alternative_strategy,
        "result": result
    })
    state["cleaning_report"] = cleaning_report

    fb.update_state(state["project_id"], cleaning_report=cleaning_report)

    return state


def _generate_default_cleaning_plan(eda_report: Dict) -> List[Dict]:
    """Generate a default cleaning plan based on EDA findings."""
    plan = []
    priority = 1
    
    missing = eda_report.get("missing_analysis", [])
    for m in missing:
        if m.get("missing_pct", 0) > 0:
            col = m["column"]
            mechanism = eda_report.get("missing_mechanisms", {}).get(col, "MCAR")
            
            if m["missing_pct"] > 80:
                action = "drop_column"
                strategy = None
            elif m["missing_pct"] > 30:
                action = "impute"
                strategy = "median" if mechanism == "MCAR" else "mode"
            else:
                action = "impute"
                strategy = "mean" if mechanism == "MCAR" else "ffill"

            plan.append({
                "action": action,
                "column": col,
                "strategy": strategy,
                "priority": priority,
                "reason": f"Missing {m['missing_pct']}% ({mechanism})"
            })
            priority += 1
    
    duplicates = eda_report.get("overview", {}).get("duplicate_rows", 0)
    if duplicates > 0:
        plan.append({
            "action": "remove_duplicates",
            "column": None,
            "priority": priority,
            "reason": f"Found {duplicates} duplicate rows"
        })
        priority += 1
    
    return plan


def _parse_human_feedback(feedback: Dict, current_plan: List[Dict]) -> List[Dict]:
    """Parse human feedback into modified cleaning plan."""
    feedback_text = feedback.get("feedback_text", "")
    
    modifications = []
    
    if "drop column" in feedback_text.lower():
        import re
        matches = re.findall(r'drop\s+(\w+)', feedback_text, re.IGNORECASE)
        for col in matches:
            modifications.append({
                "action": "drop_column",
                "column": col,
                "priority": 1,
                "reason": "Requested by human"
            })
    
    if "impute" in feedback_text.lower():
        import re
        matches = re.findall(r'impute\s+(\w+)\s+(mean|median|mode|constant)', feedback_text, re.IGNORECASE)
        for col, strategy in matches:
            modifications.append({
                "action": "impute",
                "column": col,
                "strategy": strategy,
                "priority": 1,
                "reason": "Requested by human"
            })
    
    if "keep" in feedback_text.lower() and "outlier" in feedback_text.lower():
        modifications.append({
            "action": "no_outlier_treatment",
            "column": None,
            "priority": 99,
            "reason": "Human requested to keep outliers"
        })
    
    return modifications


def _merge_feedback_plan(current_plan: List[Dict], feedback_mods: List[Dict]) -> List[Dict]:
    """Merge human feedback modifications with current plan."""
    modified_plan = [p for p in current_plan]

    for mod in feedback_mods:
        if mod.get("action") == "drop_column":
            modified_plan = [p for p in modified_plan if not (p.get("column") == mod.get("column"))]
            modified_plan.insert(0, mod)
        elif mod.get("action") == "impute":
            for i, p in enumerate(modified_plan):
                if p.get("column") == mod.get("column") and p.get("action") == "impute":
                    modified_plan[i]["strategy"] = mod.get("strategy")
                    modified_plan[i]["reason"] = mod.get("reason")
                    break
        elif mod.get("action") == "no_outlier_treatment":
            modified_plan = [p for p in modified_plan if p.get("action") not in ["cap_outliers", "flag_outliers"]]

    return modified_plan


def get_failure_context() -> Dict:
    """Get the current failure context for Manager Agent."""
    return _FAILURE_CONTEXT.copy()