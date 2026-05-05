"""FastAPI server — AgentIQ Pipeline API with Human-in-the-Loop.

Endpoints:
  POST /projects/create
  POST /projects/{pid}/upload
  GET  /projects/{pid}/state
  POST /projects/{pid}/feedback
  GET  /projects/{pid}/agent_reports
  POST /projects/{pid}/run?mode=human_in_loop  # New: Human-in-loop mode
  POST /projects/{pid}/run?mode=auto           # Traditional auto-run
  POST /projects/{pid}/resume
  POST /projects/{pid}/run/agent{1-6}
  POST /projects/{pid}/run/full
  DELETE /projects/{pid}
  
  # Human-in-loop endpoints:
  POST /projects/{pid}/approve/{agent_num}      # Approve agent
  POST /projects/{pid}/reject/{agent_num}      # Reject with feedback
  POST /projects/{pid}/continue                # Continue to next agent
  GET  /projects/{pid}/approval_status         # Get approval status
  POST /projects/{pid}/remind/{agent_num}      # Send reminder
"""
from __future__ import annotations

import asyncio
import os
import threading
import uuid
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Query, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

from db import simple_storage as fb  # Use simple storage for thesis presentation
from agents.self_review_loop import OpenAIClientWrapper
from agents.agent1_eda_with_review import run_agent_1_with_review
from agents.agent2_data_prep_with_review import run_agent_2_with_review
from agents.agent3_feature_eng_with_review import run_agent_3_with_review
from agents.agent4_model_arch_with_review import run_agent_4_with_review
from agents.agent5_training_with_review import run_agent_5_with_review
from agents.agent6_evaluation_with_review import run_agent_6_with_review

logger = logging.getLogger(__name__)


# ── LLM client factory ────────────────────────────────────────────────────────

def _make_llm_client() -> OpenAIClientWrapper:
    """Create a wrapped OpenAI client compatible with .invoke() interface."""
    # Use OpenAI API instead of NVIDIA for faster response
    raw = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    return OpenAIClientWrapper(raw)


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="AgentIQ Pipeline API", version="3.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RAW_DATA_DIR = Path(__file__).parents[1] / "data" / "raw"
_RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    project_goal: str


class FeedbackRequest(BaseModel):
    agent_id: int
    decision: str
    feedback_text: Optional[str] = None
    feedback_metadata: Optional[dict] = None


class HumanApprovalRequest(BaseModel):
    """Request for human approval workflow"""
    mode: str = "human_in_loop"  # "human_in_loop" or "auto"


class ApprovalRequest(BaseModel):
    """Approve an agent"""
    feedback: Optional[str] = None
    highlighted_data: Optional[List[Dict[str, Any]]] = None
    structured_feedback: Optional[Dict[str, Any]] = None


class RejectionRequest(BaseModel):
    """Reject an agent with feedback"""
    feedback: str
    highlighted_data: Optional[List[Dict[str, Any]]] = None
    structured_feedback: Optional[Dict[str, Any]] = None
    revision_instructions: Optional[str] = None


class ContinueRequest(BaseModel):
    """Continue to next agent"""
    agent_num: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_state(db_state: dict) -> dict:
    """Normalize DB state to frontend-compatible format."""
    if not db_state:
        return {}

    normalized = {
        "PROJECT_GOAL": db_state.get("PROJECT_GOAL") or db_state.get("project_goal", ""),
        "DATASET_NAME": db_state.get("DATASET_NAME") or db_state.get("dataset_name", "None"),
        "DATASET_PATH": db_state.get("DATASET_PATH") or db_state.get("dataset_path", ""),
        "CURRENT_STEP": db_state.get("CURRENT_STEP") or db_state.get("current_step", ""),
        "STATUS": (
            db_state.get("STATUS")
            or db_state.get("approval_status")
            or db_state.get("APPROVAL_STATUS", "pending")
        ),
        "THREAD_ID": db_state.get("THREAD_ID") or db_state.get("thread_id", ""),
        "APPROVAL_MODE": db_state.get("APPROVAL_MODE") or db_state.get("approval_mode", "auto"),
    }

    # Optional report fields
    for field in (
        "EDA_REPORT", "CLEANING_REPORT", "FEATURE_ENGINEERING_PLAN",
        "SELECTED_FEATURES", "CANDIDATE_MODELS", "SPLIT_STRATEGY",
        "TRAINING_RESULTS", "TUNING_RESULTS", "EVALUATION_REPORT",
        "LLM_EDA_ANALYSIS", "TASK_TYPE",
    ):
        val = db_state.get(field) or db_state.get(field.lower())
        if val is not None:
            normalized[field] = val

    # Approval status fields
    if "agent_approvals" in db_state:
        normalized["AGENT_APPROVALS"] = db_state.get("agent_approvals")
    elif "AGENT_APPROVALS" in db_state:
        normalized["AGENT_APPROVALS"] = db_state["AGENT_APPROVALS"]

    # Preserve any remaining fields
    for key, value in db_state.items():
        if key not in normalized:
            normalized[key] = value

    return normalized


def _build_agent_state(db_state: dict, agent_id: int) -> dict:
    """Build a clean state dict for an agent from DB state."""
    return {
        "project_id": db_state.get("PROJECT_ID", ""),
        "project_goal": db_state.get("PROJECT_GOAL", ""),
        "dataset_path": db_state.get("DATASET_PATH", ""),
        "dataset_name": db_state.get("DATASET_NAME", ""),
        "current_agent_id": agent_id,
        "approval_status": "pending",
        # Pass through all prior agent outputs
        "eda_report": db_state.get("EDA_REPORT"),
        "llm_eda_analysis": db_state.get("LLM_EDA_ANALYSIS"),
        "cleaning_report": db_state.get("CLEANING_REPORT"),
        "cleaned_data_path": db_state.get("CLEANED_DATA_PATH"),
        "feature_engineering_plan": db_state.get("FEATURE_ENGINEERING_PLAN") or {},
        "selected_features": db_state.get("SELECTED_FEATURES"),
        "engineered_data_path": db_state.get("ENGINEERED_DATA_PATH"),
        "candidate_models": db_state.get("CANDIDATE_MODELS") or {},
        "split_strategy": db_state.get("SPLIT_STRATEGY") or {},
        "train_idx_path": db_state.get("TRAIN_IDX_PATH"),
        "test_idx_path": db_state.get("TEST_IDX_PATH"),
        "task_type": db_state.get("TASK_TYPE"),
        "training_results": db_state.get("TRAINING_RESULTS") or {},
        "tuning_results": db_state.get("TUNING_RESULTS") or {},
    }


def _get_agent_approval_status(db_state: dict, agent_num: int) -> Dict[str, Any]:
    """Get approval status for a specific agent."""
    approvals = db_state.get("agent_approvals") or db_state.get("AGENT_APPROVALS") or {}
    agent_status = approvals.get(str(agent_num), {})
    
    return {
        "status": agent_status.get("status", "pending"),
        "feedback": agent_status.get("feedback", ""),
        "highlighted_data": agent_status.get("highlighted_data", []),
        "structured_feedback": agent_status.get("structured_feedback", {}),
        "timestamp": agent_status.get("timestamp", ""),
        "reminders_sent": agent_status.get("reminders_sent", 0),
        "last_reminder": agent_status.get("last_reminder", ""),
        "elapsed_seconds": agent_status.get("elapsed_seconds", 0),
    }


def _update_agent_approval_status(project_id: str, agent_num: int, updates: Dict[str, Any]):
    """Update approval status for a specific agent."""
    db_state = fb.get_state(project_id)
    if not db_state:
        return
    
    approvals = db_state.get("agent_approvals") or db_state.get("AGENT_APPROVALS") or {}
    agent_status = approvals.get(str(agent_num), {})
    
    # Update status
    agent_status.update(updates)
    
    # Add timestamp if not present
    if "timestamp" not in agent_status:
        agent_status["timestamp"] = datetime.now().isoformat()
    
    # Calculate elapsed seconds
    if "timestamp" in agent_status:
        try:
            start_time = datetime.fromisoformat(agent_status["timestamp"])
            elapsed = (datetime.now() - start_time).total_seconds()
            agent_status["elapsed_seconds"] = int(elapsed)
        except:
            agent_status["elapsed_seconds"] = 0
    
    approvals[str(agent_num)] = agent_status
    
    # Update database
    fb.update_state(project_id, agent_approvals=approvals)


def _send_reminder(project_id: str, agent_num: int):
    """Send a reminder notification."""
    db_state = fb.get_state(project_id)
    if not db_state:
        return
    
    # Get current status
    status = _get_agent_approval_status(db_state, agent_num)
    
    # Update reminder count
    reminders_sent = status.get("reminders_sent", 0) + 1
    _update_agent_approval_status(project_id, agent_num, {
        "reminders_sent": reminders_sent,
        "last_reminder": datetime.now().isoformat()
    })
    
    # Log reminder (in production, this would send email/notification)
    logger.info(f"Reminder sent for project {project_id}, agent {agent_num}. Total reminders: {reminders_sent}")
    
    return {"reminder_sent": True, "reminder_count": reminders_sent}


def _start_reminder_system(project_id: str, agent_num: int):
    """Start reminder system for an agent."""
    # Send first reminder after 30 seconds
    def _send_first_reminder():
        time.sleep(30)
        _send_reminder(project_id, agent_num)
    
    # Send subsequent reminders every 2 minutes
    def _send_subsequent_reminders():
        while True:
            time.sleep(120)  # 2 minutes
            db_state = fb.get_state(project_id)
            if not db_state:
                break
                
            status = _get_agent_approval_status(db_state, agent_num)
            if status.get("status") != "pending":
                break  # Stop if agent is no longer pending
                
            _send_reminder(project_id, agent_num)
    
    # Start reminder threads
    threading.Thread(target=_send_first_reminder, daemon=True).start()
    threading.Thread(target=_send_subsequent_reminders, daemon=True).start()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.2.0"}


@app.get("/projects")
def list_all_projects():
    projects = fb.list_projects()
    return [
        {
            "project_id": p.get("project_id") or p.get("PROJECT_ID", ""),
            "project_goal": p.get("project_goal") or p.get("PROJECT_GOAL", ""),
            "dataset_name": p.get("dataset_name") or p.get("DATASET_NAME", ""),
            "current_step": p.get("current_step") or p.get("CURRENT_STEP", ""),
            "status": (
                p.get("approval_status")
                or p.get("APPROVAL_STATUS")
                or p.get("status")
                or "pending"
            ),
            "approval_mode": p.get("approval_mode") or p.get("APPROVAL_MODE", "auto"),
            "created_at": str(p.get("created_at", "")),
        }
        for p in projects
    ]


@app.post("/projects")
async def create_project_with_file(
    project_goal: str = Form(...),
    file: UploadFile = File(...)
):
    """Create a project and upload dataset in one call."""
    project_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    
    # Create project
    fb.create_project(project_id, project_goal, dataset_path="")
    fb.update_state(project_id, thread_id=thread_id, approval_mode="auto")
    
    # Upload file
    file_path = _RAW_DATA_DIR / f"{project_id}_{file.filename}"
    contents = await file.read()
    file_path.write_bytes(contents)
    fb.update_state(project_id, dataset_path=str(file_path), dataset_name=file.filename)
    
    return {
        "project_id": project_id,
        "thread_id": thread_id,
        "dataset_path": str(file_path),
        "status": "created"
    }


@app.post("/projects/create")
def create_project(req: ProjectCreateRequest):
    project_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    fb.create_project(project_id, req.project_goal, dataset_path="")
    fb.update_state(project_id, thread_id=thread_id, approval_mode="auto")
    return {"project_id": project_id, "thread_id": thread_id, "status": "created"}


@app.post("/projects/{project_id}/upload")
async def upload_dataset(project_id: str, file: UploadFile = File(...)):
    state = fb.get_state(project_id)
    if state is None:
        raise HTTPException(404, "Project not found")
    file_path = _RAW_DATA_DIR / f"{project_id}_{file.filename}"
    contents = await file.read()
    file_path.write_bytes(contents)
    fb.update_state(project_id, dataset_path=str(file_path), dataset_name=file.filename)
    return {"project_id": project_id, "dataset_path": str(file_path), "status": "uploaded"}


@app.get("/projects/{project_id}/state")
def get_project_state(project_id: str):
    state = fb.get_state(project_id)
    if state is None:
        raise HTTPException(404, "Project not found")
    return _normalize_state(state)


@app.post("/projects/{project_id}/feedback")
async def submit_feedback(
    project_id: str,
    feedback: FeedbackRequest,
    resume: bool = Query(True),
):
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    fb.update_state(
        project_id,
        approval_status=feedback.decision,
        human_feedback=feedback.dict(),
    )
    return {"status": "feedback_recorded", "project_id": project_id}


@app.post("/projects/{project_id}/resume")
async def resume_pipeline(project_id: str):
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    return {"status": "resumed", "project_id": project_id}


@app.get("/projects/{project_id}/agent_reports")
def get_agent_reports(project_id: str, agent_id: int):
    return fb.get_agent_reports(project_id, agent_id)


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    try:
        fb.delete_project(project_id)
        return {"status": "deleted", "project_id": project_id}
    except Exception as e:
        logger.error("Error deleting project %s: %s", project_id, e)
        raise HTTPException(500, f"Failed to delete project: {e}")


# ── Human-in-Loop Endpoints ────────────────────────────────────────────────

@app.get("/projects/{project_id}/approval_status")
def get_approval_status(project_id: str):
    """Get approval status for all agents."""
    import json
    state = fb.get_state(project_id)
    if state is None:
        raise HTTPException(404, "Project not found")
    
    approvals = state.get("agent_approvals") or state.get("AGENT_APPROVALS") or {}
    
    # Handle case where approvals is a JSON string
    if isinstance(approvals, str):
        try:
            approvals = json.loads(approvals)
        except:
            approvals = {}
    
    # Convert string keys to integers for consistency
    approvals_dict = {}
    for key, value in approvals.items():
        try:
            agent_num = int(key)
            approvals_dict[agent_num] = value
        except:
            pass
    
    # Calculate elapsed times
    for agent_num, agent_status in approvals_dict.items():
        if isinstance(agent_status, dict) and "timestamp" in agent_status:
            try:
                start_time = datetime.fromisoformat(agent_status["timestamp"])
                elapsed = (datetime.now() - start_time).total_seconds()
                agent_status["elapsed_seconds"] = int(elapsed)
            except:
                agent_status["elapsed_seconds"] = 0
    
    return {
        "project_id": project_id,
        "approval_mode": state.get("approval_mode") or state.get("APPROVAL_MODE", "auto"),
        "agent_approvals": approvals_dict,
        "current_step": state.get("current_step") or state.get("CURRENT_STEP", ""),
    }


@app.post("/projects/{project_id}/run")
async def run_pipeline(
    project_id: str,
    req: HumanApprovalRequest,
    background_tasks: BackgroundTasks
):
    """Start pipeline with human-in-the-loop or auto mode."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    
    # Update approval mode
    fb.update_state(project_id, approval_mode=req.mode)
    
    if req.mode == "auto":
        # Run traditional auto pipeline
        return await _run_auto_pipeline(project_id)
    else:
        # Start human-in-the-loop pipeline
        return await _run_human_in_loop_pipeline(project_id, background_tasks)


async def _run_auto_pipeline(project_id: str):
    """Run traditional auto pipeline."""
    def _run():
        client = _make_llm_client()
        logger.info("[Auto Pipeline] Starting full run for %s", project_id)

        steps = [
            (1, run_agent_1_with_review, "eda_review",       "eda_report",              "EDA"),
            (2, run_agent_2_with_review, "prep_review",      "cleaning_report",         "Data Prep"),
            (3, run_agent_3_with_review, "features_review",  "feature_engineering_plan","Feature Eng"),
            (4, run_agent_4_with_review, "model_review",     "candidate_models",        "Model Arch"),
            (5, run_agent_5_with_review, "training_review",  "training_results",        "Training"),
            (6, run_agent_6_with_review, "complete",         "evaluation_report",       "Evaluation"),
        ]

        for agent_id, run_fn, step_name, key_field, label in steps:
            try:
                current_db = fb.get_state(project_id)
                if current_db is None:
                    logger.error("[Auto Pipeline] Project %s disappeared", project_id)
                    return

                fb.update_state(project_id, current_step=f"{step_name.split('_')[0]}_running", approval_status="running")

                state = _build_agent_state(current_db, agent_id=agent_id)
                result = run_fn(state, client)

                updates = {
                    "current_step": result.get("current_step", step_name),
                    "approval_status": "pending" if agent_id < 6 else "complete",
                }

                # Persist all output fields
                for field in (
                    "eda_report", "llm_eda_analysis", "task_type",
                    "cleaning_report", "cleaned_data_path",
                    "feature_engineering_plan", "selected_features", "engineered_data_path",
                    "candidate_models", "split_strategy",
                    "training_results", "tuning_results",
                    "evaluation_report",
                ):
                    if result.get(field) is not None:
                        updates[field] = result[field]

                fb.update_state(project_id, **updates)
                logger.info("[Auto Pipeline] Agent %d (%s) complete", agent_id, label)

            except Exception as e:
                logger.error("[Auto Pipeline] Agent %d (%s) failed: %s", agent_id, label, e)
                fb.update_state(
                    project_id,
                    current_step=f"agent{agent_id}_error",
                    approval_status="error",
                )
                return  # Stop pipeline on failure

        logger.info("[Auto Pipeline] Full run complete for %s", project_id)

    threading.Thread(target=_run, daemon=True, name=f"auto-pipeline-{project_id[:8]}").start()
    return {"status": "auto_pipeline_started", "project_id": project_id, "mode": "auto"}


async def _run_human_in_loop_pipeline(project_id: str, background_tasks: BackgroundTasks):
    """Start human-in-the-loop pipeline (runs only agent 1 initially)."""
    def _run_agent_1():
        try:
            db_state = fb.get_state(project_id)
            if db_state is None:
                logger.error("[Human Pipeline] Project %s disappeared", project_id)
                return

            fb.update_state(project_id, current_step="eda_running", approval_status="running")

            state = _build_agent_state(db_state, agent_id=1)
            result = run_agent_1_with_review(state, _make_llm_client())

            updates = {
                "current_step": result.get("current_step", "eda_review"),
                "approval_status": "pending",
            }
            
            if result.get("eda_report"):
                updates["eda_report"] = result["eda_report"]
            if result.get("llm_eda_analysis"):
                updates["llm_eda_analysis"] = result["llm_eda_analysis"]
            if result.get("task_type"):
                updates["task_type"] = result["task_type"]
            
            fb.update_state(project_id, **updates)
            
            # Set up approval status for agent 1
            _update_agent_approval_status(project_id, 1, {
                "status": "pending",
                "timestamp": datetime.now().isoformat()
            })
            
            # Start reminder system
            _start_reminder_system(project_id, 1)
            
            logger.info("[Human Pipeline] Agent 1 complete, awaiting approval")
            
        except Exception as e:
            logger.error("[Human Pipeline] Agent 1 failed: %s", e)
            fb.update_state(project_id, current_step="eda_error", approval_status="error")
            _update_agent_approval_status(project_id, 1, {"status": "error"})

    threading.Thread(target=_run_agent_1, daemon=True, name=f"human-agent1-{project_id[:8]}").start()
    return {"status": "human_pipeline_started", "project_id": project_id, "mode": "human_in_loop", "current_agent": 1}


@app.post("/projects/{project_id}/approve/{agent_num}")
def approve_agent(project_id: str, agent_num: int, req: ApprovalRequest):
    """Approve an agent and continue to next agent."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    
    # Update approval status
    _update_agent_approval_status(project_id, agent_num, {
        "status": "approved",
        "feedback": req.feedback or "",
        "highlighted_data": req.highlighted_data or [],
        "structured_feedback": req.structured_feedback or {},
        "approved_at": datetime.now().isoformat()
    })
    
    # If this is the last agent, mark complete
    if agent_num == 6:
        fb.update_state(project_id, 
            current_step="complete",
            approval_status="complete"
        )
        return {"status": "approved", "agent": agent_num, "pipeline": "complete"}
    
    # Otherwise, run next agent
    next_agent = agent_num + 1
    
    def _run_next_agent():
        try:
            current_db = fb.get_state(project_id)
            if current_db is None:
                return
            
            # Map agent number to function
            agent_functions = {
                1: run_agent_1_with_review,
                2: run_agent_2_with_review,
                3: run_agent_3_with_review,
                4: run_agent_4_with_review,
                5: run_agent_5_with_review,
                6: run_agent_6_with_review,
            }
            
            step_names = {
                1: "eda_running",
                2: "prep_running",
                3: "features_running",
                4: "model_running",
                5: "training_running",
                6: "eval_running",
            }
            
            review_steps = {
                1: "eda_review",
                2: "prep_review",
                3: "features_review",
                4: "model_review",
                5: "training_review",
                6: "complete",
            }
            
            fb.update_state(project_id, 
                current_step=step_names[next_agent],
                approval_status="running"
            )
            
            state = _build_agent_state(current_db, agent_id=next_agent)
            result = agent_functions[next_agent](state, _make_llm_client())
            
            updates = {
                "current_step": result.get("current_step", review_steps[next_agent]),
                "approval_status": "pending",
            }
            
            # Persist agent outputs
            output_fields = {
                1: ["eda_report", "llm_eda_analysis", "task_type"],
                2: ["cleaning_report", "cleaned_data_path"],
                3: ["feature_engineering_plan", "selected_features", "engineered_data_path"],
                4: ["candidate_models", "split_strategy"],
                5: ["training_results", "tuning_results"],
                6: ["evaluation_report"],
            }
            
            for field in output_fields.get(next_agent, []):
                if result.get(field) is not None:
                    updates[field] = result[field]
            
            fb.update_state(project_id, **updates)
            
            # Set up approval status for next agent
            _update_agent_approval_status(project_id, next_agent, {
                "status": "pending",
                "timestamp": datetime.now().isoformat()
            })
            
            # Start reminder system for next agent
            _start_reminder_system(project_id, next_agent)
            
            logger.info(f"[Human Pipeline] Agent {next_agent} complete, awaiting approval")
            
        except Exception as e:
            logger.error(f"[Human Pipeline] Agent {next_agent} failed: {e}")
            fb.update_state(project_id, 
                current_step=f"agent{next_agent}_error",
                approval_status="error"
            )
            _update_agent_approval_status(project_id, next_agent, {"status": "error"})
    
    threading.Thread(target=_run_next_agent, daemon=True, 
                     name=f"human-agent{next_agent}-{project_id[:8]}").start()
    
    return {
        "status": "approved",
        "agent": agent_num,
        "next_agent": next_agent,
        "message": f"Agent {agent_num} approved. Running agent {next_agent}..."
    }


@app.post("/projects/{project_id}/reject/{agent_num}")
def reject_agent(project_id: str, agent_num: int, req: RejectionRequest):
    """Reject an agent with feedback."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    
    # Update approval status
    _update_agent_approval_status(project_id, agent_num, {
        "status": "rejected",
        "feedback": req.feedback,
        "highlighted_data": req.highlighted_data or [],
        "structured_feedback": req.structured_feedback or {},
        "revision_instructions": req.revision_instructions or "",
        "rejected_at": datetime.now().isoformat()
    })
    
    # Update project state to indicate revision needed
    fb.update_state(project_id,
        current_step=f"agent{agent_num}_revision_needed",
        approval_status="revision"
    )
    
    return {
        "status": "rejected",
        "agent": agent_num,
        "message": f"Agent {agent_num} rejected. Revision needed."
    }


@app.post("/projects/{project_id}/continue")
def continue_to_agent(project_id: str, req: ContinueRequest):
    """Manually continue to a specific agent (skip ahead)."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    
    agent_num = req.agent_num
    
    # Check if previous agents are approved
    for i in range(1, agent_num):
        status = _get_agent_approval_status(db_state, i)
        if status.get("status") != "approved":
            raise HTTPException(400, f"Cannot skip to agent {agent_num}. Agent {i} is not approved.")
    
    # Run the requested agent
    def _run_agent():
        try:
            current_db = fb.get_state(project_id)
            if current_db is None:
                return
            
            # Map agent number to function
            agent_functions = {
                1: run_agent_1_with_review,
                2: run_agent_2_with_review,
                3: run_agent_3_with_review,
                4: run_agent_4_with_review,
                5: run_agent_5_with_review,
                6: run_agent_6_with_review,
            }
            
            step_names = {
                1: "eda_running",
                2: "prep_running",
                3: "features_running",
                4: "model_running",
                5: "training_running",
                6: "eval_running",
            }
            
            review_steps = {
                1: "eda_review",
                2: "prep_review",
                3: "features_review",
                4: "model_review",
                5: "training_review",
                6: "complete",
            }
            
            fb.update_state(project_id, 
                current_step=step_names[agent_num],
                approval_status="running"
            )
            
            state = _build_agent_state(current_db, agent_id=agent_num)
            result = agent_functions[agent_num](state, _make_llm_client())
            
            updates = {
                "current_step": result.get("current_step", review_steps[agent_num]),
                "approval_status": "pending",
            }
            
            # Persist agent outputs
            output_fields = {
                1: ["eda_report", "llm_eda_analysis", "task_type"],
                2: ["cleaning_report", "cleaned_data_path"],
                3: ["feature_engineering_plan", "selected_features", "engineered_data_path"],
                4: ["candidate_models", "split_strategy"],
                5: ["training_results", "tuning_results"],
                6: ["evaluation_report"],
            }
            
            for field in output_fields.get(agent_num, []):
                if result.get(field) is not None:
                    updates[field] = result[field]
            
            fb.update_state(project_id, **updates)
            
            # Set up approval status
            _update_agent_approval_status(project_id, agent_num, {
                "status": "pending",
                "timestamp": datetime.now().isoformat()
            })
            
            # Start reminder system
            _start_reminder_system(project_id, agent_num)
            
            logger.info(f"[Human Pipeline] Agent {agent_num} complete via continue, awaiting approval")
            
        except Exception as e:
            logger.error(f"[Human Pipeline] Agent {agent_num} failed: {e}")
            fb.update_state(project_id, 
                current_step=f"agent{agent_num}_error",
                approval_status="error"
            )
            _update_agent_approval_status(project_id, agent_num, {"status": "error"})
    
    threading.Thread(target=_run_agent, daemon=True, 
                     name=f"human-continue-agent{agent_num}-{project_id[:8]}").start()
    
    return {
        "status": "continued",
        "agent": agent_num,
        "message": f"Running agent {agent_num}..."
    }


@app.post("/projects/{project_id}/remind/{agent_num}")
def send_reminder(project_id: str, agent_num: int):
    """Send a reminder for an agent awaiting approval."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")
    
    status = _get_agent_approval_status(db_state, agent_num)
    if status.get("status") != "pending":
        raise HTTPException(400, f"Agent {agent_num} is not pending approval")
    
    result = _send_reminder(project_id, agent_num)
    
    return {
        "status": "reminder_sent",
        "agent": agent_num,
        "reminder_count": result["reminder_count"]
    }


# ── Individual agent endpoints ────────────────────────────────────────────────

@app.post("/projects/{project_id}/run/agent1")
def run_agent1_only(project_id: str):
    """Run Agent 1 (EDA) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="eda_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=1)
        result = run_agent_1_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "eda_review"), "approval_status": "pending"}
        if result.get("eda_report"):
            updates["eda_report"] = result["eda_report"]
        if result.get("llm_eda_analysis"):
            updates["llm_eda_analysis"] = result["llm_eda_analysis"]
        if result.get("task_type"):
            updates["task_type"] = result["task_type"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 1] Failed: %s", e)
        fb.update_state(project_id, current_step="eda_error", approval_status="error")
        raise HTTPException(500, f"Agent 1 failed: {e}")

    return {"status": "agent1_completed", "project_id": project_id}


@app.post("/projects/{project_id}/run/agent2")
def run_agent2_only(project_id: str):
    """Run Agent 2 (Data Prep) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="prep_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=2)
        result = run_agent_2_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "prep_review"), "approval_status": "pending"}
        if result.get("cleaning_report"):
            updates["cleaning_report"] = result["cleaning_report"]
        if result.get("cleaned_data_path"):
            updates["cleaned_data_path"] = result["cleaned_data_path"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 2] Failed: %s", e)
        fb.update_state(project_id, current_step="prep_error", approval_status="error")
        raise HTTPException(500, f"Agent 2 failed: {e}")

    return {"status": "agent2_completed", "project_id": project_id}


@app.post("/projects/{project_id}/run/agent3")
def run_agent3_only(project_id: str):
    """Run Agent 3 (Feature Engineering) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="features_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=3)
        result = run_agent_3_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "features_review"), "approval_status": "pending"}
        if result.get("feature_engineering_plan"):
            updates["feature_engineering_plan"] = result["feature_engineering_plan"]
        if result.get("selected_features"):
            updates["selected_features"] = result["selected_features"]
        if result.get("engineered_data_path"):
            updates["engineered_data_path"] = result["engineered_data_path"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 3] Failed: %s", e)
        fb.update_state(project_id, current_step="features_error", approval_status="error")
        raise HTTPException(500, f"Agent 3 failed: {e}")

    return {"status": "agent3_completed", "project_id": project_id}


@app.post("/projects/{project_id}/run/agent4")
def run_agent4_only(project_id: str):
    """Run Agent 4 (Model Architecture) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="model_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=4)
        result = run_agent_4_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "model_review"), "approval_status": "pending"}
        if result.get("candidate_models"):
            updates["candidate_models"] = result["candidate_models"]
        if result.get("split_strategy"):
            updates["split_strategy"] = result["split_strategy"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 4] Failed: %s", e)
        fb.update_state(project_id, current_step="model_error", approval_status="error")
        raise HTTPException(500, f"Agent 4 failed: {e}")

    return {"status": "agent4_completed", "project_id": project_id}


@app.post("/projects/{project_id}/run/agent5")
def run_agent5_only(project_id: str):
    """Run Agent 5 (Training & Tuning) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="training_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=5)
        result = run_agent_5_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "training_review"), "approval_status": "pending"}
        if result.get("training_results"):
            updates["training_results"] = result["training_results"]
        if result.get("tuning_results"):
            updates["tuning_results"] = result["tuning_results"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 5] Failed: %s", e)
        fb.update_state(project_id, current_step="training_error", approval_status="error")
        raise HTTPException(500, f"Agent 5 failed: {e}")

    return {"status": "agent5_completed", "project_id": project_id}


@app.post("/projects/{project_id}/run/agent6")
def run_agent6_only(project_id: str):
    """Run Agent 6 (Evaluation & Reporting) with self-review."""
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    fb.update_state(project_id, current_step="eval_running", approval_status="running")

    try:
        state = _build_agent_state(db_state, agent_id=6)
        result = run_agent_6_with_review(state, _make_llm_client())

        updates = {"current_step": result.get("current_step", "complete"), "approval_status": "complete"}
        if result.get("evaluation_report"):
            updates["evaluation_report"] = result["evaluation_report"]
        fb.update_state(project_id, **updates)
    except Exception as e:
        logger.error("[Agent 6] Failed: %s", e)
        fb.update_state(project_id, current_step="eval_error", approval_status="error")
        raise HTTPException(500, f"Agent 6 failed: {e}")

    return {"status": "agent6_completed", "project_id": project_id}


# ── Full pipeline (background thread) ────────────────────────────────────────

@app.post("/projects/{project_id}/run/full")
async def run_full_pipeline(project_id: str):
    """Run full pipeline (agents 1-6) in a background thread (auto mode)."""
    
    # Set to auto mode
    fb.update_state(project_id, approval_mode="auto")
    
    db_state = fb.get_state(project_id)
    if db_state is None:
        raise HTTPException(404, "Project not found")

    def _run():
        client = _make_llm_client()
        logger.info("[Pipeline] Starting full run for %s", project_id)

        steps = [
            (1, run_agent_1_with_review, "eda_review",       "eda_report",              "EDA"),
            (2, run_agent_2_with_review, "prep_review",      "cleaning_report",         "Data Prep"),
            (3, run_agent_3_with_review, "features_review",  "feature_engineering_plan","Feature Eng"),
            (4, run_agent_4_with_review, "model_review",     "candidate_models",        "Model Arch"),
            (5, run_agent_5_with_review, "training_review",  "training_results",        "Training"),
            (6, run_agent_6_with_review, "complete",         "evaluation_report",       "Evaluation"),
        ]

        for agent_id, run_fn, step_name, key_field, label in steps:
            try:
                current_db = fb.get_state(project_id)
                if current_db is None:
                    logger.error("[Pipeline] Project %s disappeared", project_id)
                    return

                fb.update_state(project_id, current_step=f"{step_name.split('_')[0]}_running", approval_status="running")

                state = _build_agent_state(current_db, agent_id=agent_id)
                result = run_fn(state, client)

                updates = {
                    "current_step": result.get("current_step", step_name),
                    "approval_status": "pending" if agent_id < 6 else "complete",
                }

                # Persist all output fields
                for field in (
                    "eda_report", "llm_eda_analysis", "task_type",
                    "cleaning_report", "cleaned_data_path",
                    "feature_engineering_plan", "selected_features", "engineered_data_path",
                    "candidate_models", "split_strategy",
                    "training_results", "tuning_results",
                    "evaluation_report",
                ):
                    if result.get(field) is not None:
                        updates[field] = result[field]

                fb.update_state(project_id, **updates)
                logger.info("[Pipeline] Agent %d (%s) complete", agent_id, label)

            except Exception as e:
                logger.error("[Pipeline] Agent %d (%s) failed: %s", agent_id, label, e)
                fb.update_state(
                    project_id,
                    current_step=f"agent{agent_id}_error",
                    approval_status="error",
                )
                return  # Stop pipeline on failure

        logger.info("[Pipeline] Full run complete for %s", project_id)

    threading.Thread(target=_run, daemon=True, name=f"pipeline-{project_id[:8]}").start()
    return {"status": "pipeline_started", "project_id": project_id, "mode": "auto"}


# ── Legacy /run endpoint (updated for backward compatibility) ───────────────



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
