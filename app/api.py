"""FastAPI server - minimal, async, latency-optimized."""
import os
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from db.memory_storage import MemoryStorage
from db.firebird_storage import FirebirdStorage
from agents.self_review_loop import OpenAIClientWrapper
from agents.unified_agent import AgentRunner, extract_agent_outputs
from app.orchestrator import PipelineOrchestrator
from agents.agent1_eda_with_review import run_agent_1_with_review
from agents.agent2_data_prep_with_review import run_agent_2_with_review
from agents.agent3_feature_eng_with_review import run_agent_3_with_review
from agents.agent4_model_arch_with_review import run_agent_4_with_review
from agents.agent5_training_with_review import run_agent_5_with_review
from agents.agent6_evaluation_with_review import run_agent_6_with_review

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── Setup ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="AgentIQ Pipeline", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage and LLM
storage_mode = os.getenv("STORAGE_MODE", "memory").lower()

if storage_mode == "firebird":
    try:
        storage = FirebirdStorage(
            dsn=os.getenv("FIREBIRD_DSN"),
            user=os.getenv("FIREBIRD_USER", "SYSDBA"),
            password=os.getenv("FIREBIRD_PASSWORD")
        )
        logger.info("Using Firebird storage")
    except Exception as e:
        logger.warning(f"Firebird storage failed: {e}, falling back to memory storage")
        storage = MemoryStorage()
else:
    storage = MemoryStorage()
    logger.info("Using in-memory storage")

def _make_llm_client() -> OpenAIClientWrapper:
    """Create OpenAI client."""
    raw = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return OpenAIClientWrapper(raw)

# Orchestrator
orchestrator = PipelineOrchestrator(storage, _make_llm_client())

# Register agents
orchestrator.register_agent(1, AgentRunner(1, "EDA", run_agent_1_with_review))
orchestrator.register_agent(2, AgentRunner(2, "Data Prep", run_agent_2_with_review))
orchestrator.register_agent(3, AgentRunner(3, "Feature Eng", run_agent_3_with_review))
orchestrator.register_agent(4, AgentRunner(4, "Model Arch", run_agent_4_with_review))
orchestrator.register_agent(5, AgentRunner(5, "Training", run_agent_5_with_review))
orchestrator.register_agent(6, AgentRunner(6, "Evaluation", run_agent_6_with_review))

# Data directory
_RAW_DATA_DIR = Path(__file__).parents[1] / "data" / "raw"
_RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Models ────────────────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    project_goal: str

class ApprovalRequest(BaseModel):
    feedback: Optional[str] = None

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.0.0"}

@app.get("/projects")
async def list_projects():
    """List all projects."""
    projects = await storage.list_projects()
    return [
        {
            "project_id": p.get("PROJECT_ID"),
            "project_goal": p.get("PROJECT_GOAL"),
            "dataset_name": p.get("DATASET_NAME"),
            "current_step": p.get("CURRENT_STEP"),
            "status": p.get("APPROVAL_STATUS"),
            "created_at": p.get("created_at"),
        }
        for p in projects
    ]

@app.post("/projects")
async def create_project_with_upload(
    project_goal: str = Form(...),
    file: UploadFile = File(...)
):
    """Create project and upload dataset in one call."""
    project_id = str(uuid.uuid4())
    
    # Save file
    file_path = _RAW_DATA_DIR / f"{project_id}_{file.filename}"
    contents = await file.read()
    file_path.write_bytes(contents)
    
    # Create project
    await storage.create_project(project_id, project_goal, str(file_path))
    await storage.update_state(project_id, DATASET_NAME=file.filename)
    
    logger.info(f"[API] Project {project_id} created with dataset {file.filename}")
    
    return {
        "project_id": project_id,
        "dataset_path": str(file_path),
        "status": "created"
    }

@app.get("/projects/{project_id}/state")
async def get_state(project_id: str):
    """Get project state."""
    state = await storage.get_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")
    return state

@app.post("/projects/{project_id}/run")
async def run_pipeline(project_id: str, background_tasks: BackgroundTasks, mode: str = "human_in_loop", enable_revision_loop: bool = True):
    """Start pipeline in specified mode.
    
    Args:
        project_id: Project ID
        mode: "human_in_loop" or "auto"
        enable_revision_loop: Enable self-review loop for agents
    """
    state = await storage.get_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")
    
    # Store mode and revision settings
    await storage.update_state(
        project_id,
        APPROVAL_MODE=mode,
        ENABLE_REVISION_LOOP=enable_revision_loop
    )
    
    # Run in background
    if mode == "auto":
        background_tasks.add_task(orchestrator.run_auto, project_id)
    else:
        background_tasks.add_task(orchestrator.run_human_in_loop, project_id)
    
    return {
        "status": "pipeline_started",
        "project_id": project_id,
        "mode": mode,
        "enable_revision_loop": enable_revision_loop
    }

@app.post("/projects/{project_id}/approve/{agent_num}")
async def approve_agent(project_id: str, agent_num: int, req: ApprovalRequest, background_tasks: BackgroundTasks):
    """Approve agent and continue to next."""
    state = await storage.get_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")
    
    # Run next agent in background
    background_tasks.add_task(orchestrator.approve_and_continue, project_id, agent_num)
    
    return {
        "status": "approved",
        "agent": agent_num,
        "message": f"Agent {agent_num} approved. Running next agent..."
    }

@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete project."""
    state = await storage.get_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")
    
    await storage.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
