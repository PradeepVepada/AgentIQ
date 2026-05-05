"""LangGraph orchestration graph for the AgentIQ pipeline.

Full 6-agent pipeline:
  Agent 1 (EDA) → Human Gate 1 → Agent 2 (Data Prep) → Human Gate 2
  → Agent 3 (Feature Eng) → Human Gate 3 → Agent 4 (Model Arch) → Human Gate 4
  → Agent 5 (Training) → Agent 6 (Evaluation) → Human Gate 6

Human gates use LangGraph's interrupt() — the graph pauses and waits
for external input (from Streamlit or FastAPI /feedback endpoint).

Cross-agent memory integration per AGENT_LIGHTNING_INTEGRATION Option 2:
- Each agent can access context from previous agents via memory
- Decisions are recorded and shared across agents
- Dynamic suggestions inform each agent's approach
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from agents.agent1_eda import run_agent_1_eda
from agents.agent2_data_prep import run_agent_2_prep
from agents.agent3_feature_eng import run_agent_3_features
from agents.agent4_model_arch import run_agent_4_architecture
from agents.agent5_training import run_agent_5_training
from agents.agent6_evaluation import run_agent_6_evaluation
from memory.agent_memory import AgentMemory
from workflows.state import PipelineState


# ── Human approval gate ────────────────────────────────────────────────────────

def human_approval_gate(state: PipelineState) -> PipelineState:
    """Pause the graph and wait for human feedback.

    The interrupt payload is surfaced in LangGraph Studio as a form.
    Resume by calling graph.invoke() with updated state or via the
    FastAPI /feedback endpoint.
    """
    agent_id = state.get("current_agent_id", "?")
    feedback = interrupt({
        "message": f"Please review Agent {agent_id} output and provide feedback.",
        "current_agent_id": agent_id,
        "approval_status": state.get("approval_status"),
    })
    state["approval_status"] = feedback.get("decision", "approved")
    state["human_feedback"] = feedback
    return state


# ── Routing functions ──────────────────────────────────────────────────────────

def route_eda_approval(state: PipelineState) -> str:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return "agent_2_prep"
    if status == "revision_requested":
        return "agent_1_eda"
    return END


def route_prep_approval(state: PipelineState) -> str:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return "agent_3_features"
    if status == "revision_requested":
        return "agent_2_prep"
    return END


def route_feature_approval(state: PipelineState) -> str:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return "agent_4_architecture"
    if status == "revision_requested":
        return "agent_3_features"
    return END


def route_model_approval(state: PipelineState) -> str:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return "agent_5_training"
    if status == "revision_requested":
        return "agent_4_architecture"
    return END


def route_training_status(state: PipelineState) -> str:
    error = state.get("error")
    if error and state.get("retry_count", 0) >= 3:
        return END
    if error:
        return "agent_5_training"
    return "agent_6_evaluation"


def route_eval_approval(state: PipelineState) -> str:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return END
    if status == "revision_requested":
        return "agent_3_features"
    return END


# ── Build graph ────────────────────────────────────────────────────────────────

def build_pipeline_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    # Agent nodes
    g.add_node("agent_1_eda", run_agent_1_eda)
    g.add_node("agent_2_prep", run_agent_2_prep)
    g.add_node("agent_3_features", run_agent_3_features)
    g.add_node("agent_4_architecture", run_agent_4_architecture)
    g.add_node("agent_5_training", run_agent_5_training)
    g.add_node("agent_6_evaluation", run_agent_6_evaluation)

    # Human gate nodes
    g.add_node("human_gate_1", human_approval_gate)
    g.add_node("human_gate_2", human_approval_gate)
    g.add_node("human_gate_3", human_approval_gate)
    g.add_node("human_gate_4", human_approval_gate)
    g.add_node("human_gate_6", human_approval_gate)

    # Entry point
    g.set_entry_point("agent_1_eda")

    # Agent 1 → Human Gate 1
    g.add_edge("agent_1_eda", "human_gate_1")
    g.add_conditional_edges(
        "human_gate_1",
        route_eda_approval,
        {
            "agent_2_prep": "agent_2_prep",
            "agent_1_eda": "agent_1_eda",
            END: END,
        },
    )

    # Agent 2 → Human Gate 2
    g.add_edge("agent_2_prep", "human_gate_2")
    g.add_conditional_edges(
        "human_gate_2",
        route_prep_approval,
        {
            "agent_3_features": "agent_3_features",
            "agent_2_prep": "agent_2_prep",
            END: END,
        },
    )

    # Agent 3 → Human Gate 3
    g.add_edge("agent_3_features", "human_gate_3")
    g.add_conditional_edges(
        "human_gate_3",
        route_feature_approval,
        {
            "agent_4_architecture": "agent_4_architecture",
            "agent_3_features": "agent_3_features",
            END: END,
        },
    )

    # Agent 4 → Human Gate 4
    g.add_edge("agent_4_architecture", "human_gate_4")
    g.add_conditional_edges(
        "human_gate_4",
        route_model_approval,
        {
            "agent_5_training": "agent_5_training",
            "agent_4_architecture": "agent_4_architecture",
            END: END,
        },
    )

    # Agent 5 → Agent 6 (no human gate, auto-retry on failure)
    g.add_conditional_edges(
        "agent_5_training",
        route_training_status,
        {
            "agent_6_evaluation": "agent_6_evaluation",
            "agent_5_training": "agent_5_training",
            END: END,
        },
    )

    # Agent 6 → Human Gate 6 (final gate)
    g.add_edge("agent_6_evaluation", "human_gate_6")
    g.add_conditional_edges(
        "human_gate_6",
        route_eval_approval,
        {
            END: END,
            "agent_3_features": "agent_3_features",
        },
    )

    return g


# ── Compile ─────────────────────────────────────────────────────────────────────

graph = build_pipeline_graph().compile(
    interrupt_before=["human_gate_1", "human_gate_2", "human_gate_3", "human_gate_4", "human_gate_6"]
)
