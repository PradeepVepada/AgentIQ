"""Agent 1 — Data Intake & EDA (Simplified Working Version)."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from langsmith import traceable

from db import firebird_client as fb
from memory.agent_memory import AgentMemory, Decision, DecisionType
from tools.data_loader import load_dataset
from tools.eda_tools import (
    compile_full_eda,
    classify_missing_mechanism,
    detect_outliers_robust,
    bivariate_analysis_safe,
    multivariate_analysis_safe,
)
from workflows.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Fast model

_FAILURE_CONTEXT = {}


def _call_llm(prompt: str, max_tokens: int = 2000) -> str:
    """Call LLM with error handling."""
    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("[Agent 1] LLM call failed: %s", e)
        return ""


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 1, "agent_name": "EDA"})
def run_agent_1_eda(state: PipelineState) -> Dict[str, Any]:
    """Run Agent 1: Generate EDA plan."""
    project_id = state["project_id"]
    dataset_path = state["dataset_path"]
    
    logger.info("[Agent 1] Generating EDA plan...")
    t0 = time.time()
    
    try:
        df = load_dataset(dataset_path)
        overview = {
            "rows": len(df),
            "columns": len(df.columns),
            "task_type": "classification",  # Default
            "target_column": None,
        }
        
        # Detect task type and target
        from tools.eda_tools import detect_column_types
        col_types = detect_column_types(df)
        
        # Call LLM to suggest target and task
        llm_analysis = {
            "task_type": "classification",
            "target_column": df.columns[-1],  # Default to last column
            "cleaning_plan": [],
        }
        
        # Generate structured EDA plan
        plan = {
            "overview": overview,
            "column_types": col_types,
            "task_type": llm_analysis.get("task_type", "classification"),
            "target_column": llm_analysis.get("target_column"),
            "cleaning_plan": llm_analysis.get("cleaning_plan", []),
        }
        
        state["eda_plan"] = plan
        state["current_step"] = "eda_plan_review"
        
        logger.info("[Agent 1] Plan generated in %.1fms", (time.time() - t0) * 1000)
        
    except Exception as e:
        logger.error("[Agent 1] Failed: %s", e)
        state["error"] = str(e)
    
    return state


@traceable(run_type="chain", project_name="agentiq-pipeline", metadata={"agent_id": 1, "agent_name": "EDA-Execute"})
def execute_eda_plan(state: PipelineState) -> Dict[str, Any]:
    """Execute approved EDA plan and generate full report."""
    project_id = state["project_id"]
    dataset_path = state["dataset_path"]
    
    logger.info("[Agent 1] Executing EDA plan...")
    t0 = time.time()
    
    try:
        df = load_dataset(dataset_path)
        plan = state.get("eda_plan", {})
        
        # Compile full EDA report
        eda_report = compile_full_eda(df, plan.get("target_column"))
        
        # Generate LLM-enhanced analysis
        llm_prompt = f"""Analyze this EDA summary and provide insights:

Dataset: {plan.get('overview', {}).get('rows', 0)} rows × {plan.get('overview', {}).get('columns', 0)} columns
Target: {plan.get('target_column', 'Unknown')}

Key findings from analysis:
- Missing values: {eda_report.get('missing_analysis', {}).get('total_missing_pct', 0):.1f}%
- Data quality score: {eda_report.get('data_quality', {}).get('score', 0):.1f}/10

Provide 3-5 key insights and recommendations."""

        llm_analysis = _call_llm(llm_prompt)
        
        state["eda_report"] = eda_report
        state["llm_eda_analysis"] = {"analysis": llm_analysis}
        state["current_step"] = "eda_review"
        
        logger.info("[Agent 1] EDA complete in %.1fms", (time.time() - t0) * 1000)
        
    except Exception as e:
        logger.error("[Agent 1] Execution failed: %s", e)
        state["error"] = str(e)
    
    return state


if __name__ == "__main__":
    # Test
    test_state = {
        "project_id": "test-123",
        "dataset_path": "data/raw/credit_risk.csv",
        "project_goal": "predict loan default",
    }
    result = run_agent_1_eda(test_state)
    print("Plan:", bool(result.get("eda_plan")))
