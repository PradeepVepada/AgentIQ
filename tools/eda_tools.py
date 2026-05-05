"""Pure analytical utility functions used by Agent 1 (EDA).

All functions are stateless — they accept a DataFrame and return
serialisable Python dicts/lists so results can be stored as JSON
in Firebird and passed to the LLM as context.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import json
import numpy as np
import pandas as pd

# ── Column-type detection ──────────────────────────────────────────────────

_TRUE_ID_NAMES = {"id", "uuid", "key", "adsh", "accession", "identifier"}
_NUMERIC_HINTS = {
    "value", "amount", "price", "revenue", "sales",
    "cost", "profit", "income", "expense", "total",
    "balance", "quantity", "qty", "count",
    "score", "rate", "ratio", "percent", "percentage",
}

def _clean_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    cleaned = (
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")

def _is_numeric_like(s: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(s):
        return True
    non_null = s.dropna()
    if non_null.empty:
        return False
    return _clean_numeric(non_null).notna().mean() >= 0.8

def _is_datetime_like(s: pd.Series) -> bool:
    try:
        non_null = s.dropna()
        if non_null.empty:
            return False
        return pd.to_datetime(non_null, errors="coerce").notna().mean() >= 0.8
    except Exception:
        return False

def _has_time_component(s: pd.Series) -> bool:
    try:
        converted = pd.to_datetime(s.dropna(), errors="coerce").dropna()
        if converted.empty:
            return False
        return bool(
            ((converted.dt.hour != 0) |
             (converted.dt.minute != 0) |
             (converted.dt.second != 0)).any()
        )
    except Exception:
        return False

def _is_identifier(column_name: str) -> bool:
    name = column_name.lower().strip()
    return (name in _TRUE_ID_NAMES or 
            name.endswith("_id") or 
            name.endswith("_key") or 
            name.endswith("_uuid"))

def detect_column_types(df: pd.DataFrame):
    """Detect column types for a dataframe.
    Returns: (df, id_cols, numeric_cols, categorical_cols, date_cols, time_cols)
    """
    id_cols, numeric_cols, cat_cols, date_cols, time_cols = [], [], [], [], []
    
    for col in df.columns:
        name = col.lower().strip()
        if _is_identifier(col):
            id_cols.append(col)
        elif name in _NUMERIC_HINTS or _is_numeric_like(df[col]):
            df[col] = _clean_numeric(df[col])
            numeric_cols.append(col)
        elif _is_datetime_like(df[col]):
            df[col] = pd.to_datetime(df[col], errors="coerce")
            if _has_time_component(df[col]):
                time_cols.append(col)
            else:
                date_cols.append(col)
        else:
            cat_cols.append(col)
    
    return df, id_cols, numeric_cols, cat_cols, date_cols, time_cols

# ── Individual analysis builders ───────────────────────────────────────────────

def _fmt(x, digits: int = 3):
    if pd.isna(x):
        return None
    try:
        x = float(x)
    except Exception:
        return x
    return f"{x:.{digits}e}" if abs(x) >= 1_000_000 else round(x, digits)

def build_dataset_overview(df: pd.DataFrame, col_types: Dict) -> Dict:
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing": int(df.isnull().sum().sum()),
        "numeric_count": len(col_types[2]),  # numeric_cols is 2nd element
        "categorical_count": len(col_types[3]),  # cat_cols is 3rd element
        "id_count": len(col_types[1]),  # id_cols is 1st element
        "date_count": len(col_types[4]) + len(col_types[5]),  # date + time cols
    }

def build_missing_table(df: pd.DataFrame) -> List[Dict]:
    rows = []
    for col in df.columns:
        mc = int(df[col].isnull().sum())
        pct = round(mc / len(df) * 100, 2) if len(df) > 0 else 0
        if pct == 0:
            status = "Good"
        elif pct <= 5:
            status = "Low Missing"
        elif pct <= 30:
            status = "Needs Strategy"
        elif pct <= 60:
            status = "High Risk"
        else:
            status = "Consider Dropping"
        rows.append({"column": col, "missing_count": mc, "missing_pct": pct, "status": status})
    return rows

def build_statistical_analysis(df: pd.DataFrame, numeric_cols: List[str]) -> List[Dict]:
    rows = []
    for col in numeric_cols:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        mode_v = s.mode()
        rows.append({
            "column": col,
            "count": int(s.count()),
            "mean": _fmt(s.mean()),
            "median": _fmt(s.median()),
            "mode": _fmt(mode_v.iloc[0]) if not mode_v.empty else None,
            "std": _fmt(s.std()),
            "variance": _fmt(s.var()),
            "min": _fmt(s.min()),
            "p25": _fmt(s.quantile(0.25)),
            "p50": _fmt(s.quantile(0.50)),
            "p75": _fmt(s.quantile(0.75)),
            "max": _fmt(s.max()),
        })
    return rows

def build_univariate_analysis(df: pd.DataFrame, numeric_cols: List[str]) -> List[Dict]:
    rows = []
    for col in numeric_cols:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        skew = s.skew()
        kurt = s.kurtosis()
        rng = s.max() - s.min()
        rows.append({
            "column": col,
            "skewness": _fmt(skew),
            "kurtosis": _fmt(kurt),
            "distribution": "Right-skewed" if skew > 0.5 else ("Left-skewed" if skew < -0.5 else "Approx. symmetric"),
            "tail_behaviour": "Heavy-tailed" if kurt > 3 else ("Light-tailed" if kurt < -1 else "Normal"),
            "normalization_recommended": bool(rng > 1000 or s.std() > abs(s.mean()) or abs(skew) > 1),
            "suggested_transform": "log or robust scaling" if abs(skew) > 1 else "standard or min-max",
        })
    return rows

def build_outlier_analysis(df: pd.DataFrame, numeric_cols: List[str]) -> List[Dict]:
    rows = []
    for col in numeric_cols:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = s[(s < lo) | (s > hi)]
        rows.append({
            "column": col,
            "outlier_count": int(outliers.count()),
            "outlier_pct": _fmt(outliers.count() / len(s) * 100),
            "lower_bound": _fmt(lo),
            "upper_bound": _fmt(hi),
        })
    return rows

def build_correlation_analysis(df: pd.DataFrame, numeric_cols: List[str]) -> List[Dict]:
    if len(numeric_cols) < 2:
        return []
    corr = df[numeric_cols].apply(pd.to_numeric, errors="coerce").corr()
    rows = []
    for i, c1 in enumerate(corr.columns):
        for c2 in corr.columns[i + 1:]:
            val = corr.loc[c1, c2]
            if pd.notna(val) and abs(val) >= 0.7:
                rows.append({
                    "feature_1": c1,
                    "feature_2": c2,
                    "correlation": _fmt(val),
                    "strength": "strong positive" if val > 0 else "strong negative",
                })
    return rows

def build_categorical_summary(df: pd.DataFrame, cat_cols: List[str]) -> List[Dict]:
    rows = []
    for col in cat_cols:
        vc = df[col].value_counts(dropna=False)
        rows.append({
            "column": col,
            "unique_values": int(df[col].nunique(dropna=True)),
            "top_value": str(vc.index[0]) if not vc.empty else None,
            "top_freq": int(vc.iloc[0]) if not vc.empty else 0,
            "high_cardinality": bool(df[col].nunique(dropna=True) > 30),
        })
    return rows

def compile_full_eda(df: pd.DataFrame) -> Dict:
    """Run all analyses and return a single serialisable EDA dict."""
    col_types = detect_column_types(df)
    missing_mechanisms = classify_missing_mechanism(df)
    return {
        "overview": build_dataset_overview(df, col_types),
        "column_types": {
            "id": col_types[1],
            "numeric": col_types[2],
            "categorical": col_types[3],
            "date": col_types[4],
            "time": col_types[5],
        },
        "missing_analysis": build_missing_table(df),
        "statistical_analysis": build_statistical_analysis(df, col_types[2]),
        "univariate_analysis": build_univariate_analysis(df, col_types[2]),
        "outlier_analysis": build_outlier_analysis(df, col_types[2]),
        "correlation_analysis": build_correlation_analysis(df, col_types[2]),
        "categorical_summary": build_categorical_summary(df, col_types[3]),
        "missing_mechanisms": missing_mechanisms,
    }

def classify_missing_mechanism(df: pd.DataFrame) -> Dict[str, str]:
    """Classify each column's missing values as MCAR, MAR, or MNAR."""
    mechanisms = {}
    
    for col in df.columns:
        if df[col].isnull().sum() == 0:
            mechanisms[col] = "none"
            continue
        
        mechanisms[col] = detect_mcar_mar_mnar(df, col)
    
    return mechanisms

def detect_mcar_mar_mnar(df: pd.DataFrame, column: str) -> str:
    """Detect missing mechanism: MCAR, MAR, or MNAR."""
    if df[column].isnull().sum() == 0:
        return "none"
    
    missing_indicator = df[column].isnull().astype(int)
    df_test = df.drop(columns=[column])
    
    numeric_cols = df_test.select_dtypes(include=[np.number]).columns
    
    if len(numeric_cols) == 0:
        return _heuristic_mcar_mnar(df, column)
    
    correlations = []
    for col in numeric_cols:
        corr = df_test[col].corr(missing_indicator)
        if pd.notna(corr) and not np.isnan(corr):
            correlations.append(abs(corr))
    
    mean_corr = np.mean(correlations) if correlations else 0
    
    if mean_corr < 0.05:
        return "MCAR"
    
    if mean_corr >= 0.05 and mean_corr < 0.2:
        return "MAR"
    
    return "MNAR"

def _heuristic_mcar_mnar(df: pd.DataFrame, column: str) -> str:
    """Fallback heuristic for non-numeric columns."""
    missing_count = df[column].isnull().sum()
    missing_pct = missing_count / len(df) * 100
    
    if missing_pct > 50:
        return "MNAR"
    elif missing_pct > 20:
        return "MAR"
    else:
        return "MCAR"

# ── Project Goal Suggestions (from friend's code) ─────────────────────────

def suggest_project_goals(dataset_path: str, dataset_name: str) -> list:
    """
    Quick LLM call to suggest project goals based on column names.
    Returns list of suggestion dicts.
    """
    import os
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()
    
    # Use OpenAI API for faster response
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Quick scan - just column names
    from tools.data_loader import load_dataset
    df = load_dataset(dataset_path)
    columns = df.columns.tolist()
    
    # Detect likely target columns
    numeric_cols = [c for c in columns 
                    if pd.api.types.is_numeric_dtype(df[c]) or 
                    _is_numeric_like(df[c])]
    
    prompt = f"""
Dataset name: {dataset_name}
Columns: {', '.join(columns)}
Numeric columns: {', '.join(numeric_cols)}

Suggest exactly 3 specific, business-friendly project goals
for this dataset. Write them for a non-technical user.
Do NOT use words like regression, classification, clustering.
Instead say "predict", "identify", "analyze", "find", "compare".

Return ONLY this JSON:
{{
    "suggestions": [
        {{
            "goal": "one sentence goal written for business user",
            "target_column": "most relevant column name from the list",
            "icon": "single emoji that fits the goal"
        }}
    ]
}}
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        raw_json = response.choices[0].message.content.strip()
        
        # Parse JSON from response
        if "```json" in raw_json:
            json_str = raw_json.split("```json")[1].split("```")[0].strip()
        elif "{" in raw_json:
            start = raw_json.find("{")
            end = raw_json.rfind("}") + 1
            json_str = raw_json[start:end]
        else:
            json_str = raw_json
        
        result = json.loads(json_str)
        return result.get("suggestions", [])
    except Exception as e:
        print(f"Error generating suggestions: {e}")
        # Fallback suggestions
        return [
            {"goal": f"Analyze patterns in {dataset_name}", "target_column": numeric_cols[0] if numeric_cols else "", "icon": "📊"},
            {"goal": f"Find insights from the data", "target_column": numeric_cols[0] if numeric_cols else "", "icon": "💡"},
            {"goal": f"Understand relationships between columns", "target_column": numeric_cols[0] if numeric_cols else "", "icon": "🔍"},
        ]

# ── quick_scan_dataset (from friend's code) ─────────────────────────────────────

def quick_scan_dataset(dataset_path: str) -> str:
    """
    Fast lightweight scan of the dataset.
    Returns shape, column names, basic type hints,
    missing value counts and duplicate count.
    Used for plan generation only - not full analysis.
    """
    from tools.data_loader import load_dataset
    
    df = load_dataset(dataset_path)
    df, id_cols, numeric_cols, cat_cols, date_cols, time_cols = detect_column_types(df)
    
    column_hints = []
    for col in df.columns:
        if col in id_cols:
            dtype = "Identifier"
            confidence = 90
        elif col in numeric_cols:
            dtype = "Numeric"
            confidence = 85
        elif col in cat_cols:
            dtype = "Categorical"
            confidence = 80
        elif col in date_cols:
            dtype = "Date"
            confidence = 90
        elif col in time_cols:
            dtype = "Time"
            confidence = 88
        else:
            dtype = "Unknown"
            confidence = 40
        
        # Lower confidence for ambiguous names
        name_lower = col.lower()
        if any(w in name_lower for w in 
               ["id","code","key","num","no"]):
            if dtype == "Numeric":
                confidence = 55  # might be identifier
        
        column_hints.append({
            "column": col,
            "detected_type": dtype,
            "confidence": confidence,
            "unique_values": int(df[col].nunique()),
            "missing": int(df[col].isnull().sum()),
            "needs_confirmation": confidence < 75,
        })
    
    result = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_hints": column_hints,
        "missing_values_total": int(df.isnull().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_columns": numeric_cols,
        "categorical_columns": cat_cols,
        "date_columns": date_cols,
        "identifier_columns": id_cols,
    }
    return json.dumps(result)


# ═══════════════════════════════════════════════════════════════════════════
# ROBUST EDA FUNCTIONS (from ML_Pipeline docs)
# ═══════════════════════════════════════════════════════════════════════════

def detect_missing_mechanism(df: pd.DataFrame, target_col: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Classify missing mechanism for each column: MCAR, MAR, or MNAR.

    MCAR (Missing Completely At Random):
    - Missingness independent of all variables
    - Safe to: Listwise deletion, mean imputation

    MAR (Missing At Random):
    - Missingness depends on observed variables
    - Safe to: Multiple imputation, KNN imputation

    MNAR (Missing Not At Random):
    - Missingness depends on unobserved values
    - Dangerous: Biased analysis, requires domain knowledge
    """
    results = []

    for col in df.columns:
        missing_mask = df[col].isna()
        missing_count = missing_mask.sum()
        missing_pct = (missing_count / len(df) * 100) if len(df) > 0 else 0

        if missing_pct == 0:
            results.append({
                "column": col,
                "missing_pct": 0,
                "mechanism": "NONE",
                "confidence": 1.0,
                "recommendation": "No action needed"
            })
            continue

        # Heuristic 1: Test correlation between missingness & other vars
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if col in numeric_cols:
            numeric_cols.remove(col)

        max_corr = 0.0
        correlated_vars = []

        for other_col in numeric_cols[:10]:
            try:
                other_vals = pd.to_numeric(df[other_col], errors="coerce")
                corr = missing_mask.astype(int).corr(other_vals)
                if abs(corr) > 0.1:
                    max_corr = max(max_corr, abs(corr))
                    correlated_vars.append((other_col, round(corr, 3)))
            except Exception:
                pass

        # Heuristic 2: Check for target-dependent missingness (MNAR signal)
        mnar_signal = False
        target_corr = 0.0

        if target_col and target_col in df.columns and target_col != col:
            try:
                target_vals = pd.to_numeric(df[target_col], errors="coerce")
                target_corr = missing_mask.astype(int).corr(target_vals)
                if abs(target_corr) > 0.15:
                    mnar_signal = True
            except Exception:
                pass

        # Classify mechanism
        if max_corr < 0.05 and not mnar_signal:
            mechanism = "MCAR"
            confidence = 0.8
            recommendation = (
                "Likely MCAR. Safe to use: mean/median imputation, listwise deletion (if <10% missing)."
            )
        elif max_corr >= 0.05 and max_corr < 0.2 and not mnar_signal:
            mechanism = "MAR"
            confidence = 0.7
            recommendation = f"Likely MAR (correlates with {correlated_vars[:2]}). Use: KNN, MICE imputation."
        elif max_corr >= 0.2 or mnar_signal:
            mechanism = "MNAR"
            confidence = 0.6
            recommendation = (
                "Possible MNAR. WARNING: Imputation may introduce bias. "
                "Consider: sensitivity analysis, domain-expert review, explicit missing indicator."
            )
        else:
            mechanism = "UNCERTAIN"
            confidence = 0.5
            recommendation = "Unusual missing pattern. Inspect manually."

        results.append({
            "column": col,
            "missing_pct": round(missing_pct, 2),
            "mechanism": mechanism,
            "confidence": round(confidence, 2),
            "correlated_with": correlated_vars[:3],
            "target_correlation": round(target_corr, 3) if target_col else None,
            "recommendation": recommendation,
        })

    return results


def detect_outliers_robust(series: pd.Series, method: str = "iqr") -> Dict[str, Any]:
    """
    Detect outliers using multiple strategies.

    Methods:
    - iqr: Tukey IQR (good for normal-ish distributions)
    - zscore: Standard deviations (good for symmetric distributions)
    - mad: Median Absolute Deviation (robust to extreme outliers)
    - isolation_forest: Anomaly detection (good for multimodal)
    """
    series_clean = pd.to_numeric(series, errors="coerce").dropna()

    # Edge cases
    if len(series_clean) < 5:
        return {
            "method": method,
            "outlier_count": 0,
            "outlier_pct": 0.0,
            "note": "Too few values (<5) for outlier detection",
        }

    if series_clean.std() == 0:
        return {
            "method": method,
            "outlier_count": 0,
            "outlier_pct": 0.0,
            "note": "Zero variance (all identical values)",
        }

    outlier_mask = pd.Series(False, index=series_clean.index)

    # IQR Method (Tukey's fences)
    if method == "iqr":
        Q1, Q3 = series_clean.quantile([0.25, 0.75])
        IQR = Q3 - Q1

        if IQR > 0:
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            outlier_mask = (series_clean < lower) | (series_clean > upper)
        else:
            method = "zscore"

    # Z-Score Method
    if method == "zscore":
        mean = series_clean.mean()
        std = series_clean.std()

        if std > 0:
            z_scores = np.abs((series_clean - mean) / std)
            outlier_mask = z_scores > 3
        else:
            return {"method": method, "outlier_count": 0, "outlier_pct": 0.0, "note": "Standard deviation is zero"}

    # MAD Method
    elif method == "mad":
        median = series_clean.median()
        mad = np.median(np.abs(series_clean - median))

        if mad > 0:
            modified_z = 0.6745 * (series_clean - median) / mad
            outlier_mask = np.abs(modified_z) > 3.5
        else:
            return {"method": method, "outlier_count": 0, "outlier_pct": 0.0, "note": "Median absolute deviation is zero"}

    # Isolation Forest
    elif method == "isolation_forest":
        try:
            from sklearn.ensemble import IsolationForest
            iso_forest = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
            predictions = iso_forest.fit_predict(series_clean.values.reshape(-1, 1))
            outlier_mask = predictions == -1
        except Exception:
            return detect_outliers_robust(series, method="iqr")

    outlier_count = int(outlier_mask.sum())
    outlier_pct = (outlier_count / len(series_clean) * 100) if len(series_clean) > 0 else 0

    return {
        "method": method,
        "outlier_count": outlier_count,
        "outlier_pct": round(outlier_pct, 2),
        "threshold_description": f"Detected using {method} method",
        "sample_outlier_indices": list(series_clean[outlier_mask].index[:5]),
    }


def bivariate_analysis_safe(df: pd.DataFrame, numeric_cols: List[str],
                            min_correlation_threshold: float = 0.5) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Perform bivariate analysis with comprehensive edge-case handling.

    Returns:
        Tuple of:
        - List of strong correlations (if any)
        - Dict of warnings/notes
    """
    results = []
    notes = {}

    # Edge case: insufficient columns
    if not numeric_cols or len(numeric_cols) < 2:
        notes["insufficient_columns"] = f"Only {len(numeric_cols) or 0} numeric columns; need >=2"
        return results, notes

    # Edge case: filter out all-NULL columns
    valid_cols = [
        col for col in numeric_cols
        if col in df.columns and df[col].notna().sum() > 0
    ]

    if len(valid_cols) < 2:
        notes["insufficient_valid_columns"] = f"Only {len(valid_cols)} columns with non-null values"
        return results, notes

    # Try to compute correlation
    try:
        corr_matrix = df[valid_cols].corr()
    except Exception as e:
        notes["correlation_error"] = str(e)
        return results, notes

    # Edge case: correlation matrix is all NaN
    if corr_matrix.isna().all().all():
        notes["all_nan_correlations"] = "All correlations are NaN (insufficient variance?)"
        return results, notes

    # Extract strong correlations
    for i, col1 in enumerate(valid_cols):
        for col2 in valid_cols[i + 1:]:
            if col1 in corr_matrix.index and col2 in corr_matrix.columns:
                corr_val = corr_matrix.loc[col1, col2]

                if pd.isna(corr_val):
                    continue

                if abs(corr_val) >= min_correlation_threshold:
                    co_non_null = int(df[[col1, col2]].notna().all(axis=1).sum())

                    results.append({
                        "feature_1": col1,
                        "feature_2": col2,
                        "correlation": _fmt(corr_val),
                        "abs_correlation": float(abs(corr_val)),
                        "strength": "strong" if abs(corr_val) >= 0.7 else "moderate",
                        "direction": "positive" if corr_val > 0 else "negative",
                        "samples": co_non_null,
                    })

    results = sorted(results, key=lambda x: x['abs_correlation'], reverse=True)

    return results, notes


def multivariate_analysis_safe(df: pd.DataFrame, numeric_cols: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Perform multivariate analysis with edge-case handling."""
    notes = {}

    if len(numeric_cols) < 3:
        return {"note": "Need >=3 numeric columns for multivariate analysis"}, notes

    valid_cols = [
        col for col in numeric_cols
        if col in df.columns and df[col].notna().sum() > 0
    ]

    if len(valid_cols) < 3:
        return {"note": f"Only {len(valid_cols)} columns with non-null values"}, notes

    try:
        corr = df[valid_cols].corr()

        eigenvalues = np.linalg.eigvals(corr.values)
        eigenvalues = eigenvalues[eigenvalues > 1e-10]

        if len(eigenvalues) == 0:
            return {"note": "Eigenvalues all near-zero (degenerate case)"}, notes

        condition_index = np.sqrt(max(eigenvalues) / min(eigenvalues)) if len(eigenvalues) > 0 and min(eigenvalues) > 0 else float('inf')

        multicollinearity_cols = []
        for i, col1 in enumerate(valid_cols):
            for col2 in valid_cols[i + 1:]:
                if abs(corr.loc[col1, col2]) >= 0.9:
                    multicollinearity_cols.append(f"{col1} <-> {col2} ({corr.loc[col1, col2]:.3f})")

        return {
            "condition_index": round(condition_index, 3) if condition_index != float('inf') else "inf",
            "multicollinearity_risk": (
                "high" if condition_index > 30
                else "medium" if condition_index > 10
                else "low"
            ),
            "highly_correlated_pairs": multicollinearity_cols,
            "eigenvalue_ratio": round(max(eigenvalues) / min(eigenvalues), 3) if len(eigenvalues) > 0 and min(eigenvalues) > 0 else None,
            "sample_size": len(df),
            "columns_analyzed": len(valid_cols),
        }, notes

    except Exception as e:
        notes["error"] = str(e)
        return {}, notes
