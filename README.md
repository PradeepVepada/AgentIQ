# AgentIQ — Autonomous Data Science Pipeline

An autonomous 6-agent ML pipeline that guides users through the complete data science workflow:
**EDA → Data Prep → Feature Engineering → Model Architecture → Training → Evaluation**. 
This system though sequential mimic's the job that of a data analyst, system's ability to dynamically change tracks and switch imeplementation plans based on the self-correction/review loop and that of user's feedback is its core advantage.

Each step includes human approval gates, LangSmith tracing, and Firebird persistence.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Streamlit UI (Dark Theme)                     │
│   Project Setup → Plan Review → EDA Review → Approval Gates    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│              LangGraph Orchestrator (State Machine)               │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  CROSS-AGENT MEMORY (Decision Journal)                  │  │
│  │  • Context sharing across all 6 agents                   │  │
│  │  • Dynamic suggestions per agent                        │  │
│  │  • Failure recovery hints                                │  │
│  │  • Firebird persistence                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┐                     │
│  │ Ag 1 │ Ag 2 │ Ag 3 │ Ag 4 │ Ag 5 │ Ag 6 │                     │
│  │ EDA  │ Prep │ Feat │ Arch │ Train│ Eval │                     │
│  └──┬───┘──┬───┘──┬───┘──┬───┘──┬───┘──┬───┘                     │
└─────┼──────┼──────┼──────┼──────┼──────┼────────────────────────┘
      │      │      │      │      │      │
┌─────▼──────▼──────▼──────▼──────▼──────▼────────────────────────┐
│                    Firebird Database                            │
│   • Project State (JSON blobs)                                   │
│   • Agent Reports                                                │
│   • Decision History                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd AgentIQ
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
# NVIDIA API (LLM)
NVIDIA_API_KEY=your_nvidia_api_key
NVIDIA_MODEL_ID=minimax/minimax-m2-text

# Firebird Database
FIREBIRD_DSN=C:\path\to\database.fdb
FIREBIRD_USER=SYSDBA
FIREBIRD_PASSWORD=your_password
```

### 3. Run the Application

```bash
# Terminal 1: Backend API
cd AgentIQ
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Streamlit UI
cd AgentIQ
streamlit run streamlit_app.py --server.port 8501
```

### 4. Open Browser

Navigate to **http://localhost:8501**

---

## Project Structure

```
AgentIQ/
├── agents/                    # 6 LangGraph nodes
│   ├── agent1_eda.py        # EDA + two-phase workflow
│   ├── agent2_data_prep.py  # Cleaning + imputation
│   ├── agent3_feature_eng.py # Feature engineering
│   ├── agent4_model_arch.py  # Model selection
│   ├── agent5_training.py   # Hyperparameter tuning
│   └── agent6_evaluation.py  # Model evaluation
│
├── memory/                   # Cross-Agent Memory (NEW!)
│   ├── agent_memory.py      # Decision Journal
│   └── __init__.py
│
├── tools/                    # Shared utilities
│   ├── data_loader.py       # CSV/Excel/Parquet loader
│   ├── eda_tools.py         # Statistical analysis
│   └── prep_tools.py        # Data cleaning
│
├── workflows/                # LangGraph orchestration
│   ├── graph.py            # Pipeline graph
│   └── state.py            # PipelineState TypedDict
│
├── db/                      # Firebird persistence
│   └── firebird_client.py  # State store
│
├── app/                     # FastAPI server
│   └── main.py             # REST endpoints
│
├── tests/                   # Test suite
│   ├── test_memory.py      # Memory integration tests
│   ├── test_eda_robust.py  # Edge case tests
│   ├── test_agent1_eda.py
│   └── conftest.py
│
└── streamlit_app.py        # UI with dark theme
```

---

## Cross-Agent Memory

A Decision Journal lets all six agents share context and decisions instead of working in isolation by having each agent write its findings into a shared memory structure in agent_memory.py, where Agent 1 (EDA) records outputs like {"quality_score": 8, "missing_pct": 5.2, "outliers": 3}, Agent 2 (Prep) retrieves that context and receives suggestions such as “Low missing rate → use mean imputation,” then records its own decisions like {"duplicates_removed": 3, "imputation_method": "mean"}, and Agent 3 (Features) pulls combined context from Agents 1 and 2 to make more informed choices, with this pattern continuing through all six agents to build a complete audit trail; 

The Decision Journal lives inside the LangGraph state and can persist to Firebird so the system can recover gracefully after crashes, resulting in better decisions, no redundant analysis, richer error‑recovery hints, and a fully traceable pipeline.

### Key Features

1. **Decision Journal** — Each agent records decisions with:
   - Summary (human-readable)
   - Details (structured data)
   - Confidence score
   - Reasoning
   - Impact on downstream agents

2. **Context Retrieval** — Before executing, each agent can:
   - See what previous agents decided
   - Get quality summary from EDA
   - View known issues
   - Receive dynamic suggestions

3. **Dynamic Suggestions** — Context-aware tips:
   - Agent 2: "High missing rate (25%) — consider MNAR-aware imputation"
   - Agent 3: "High multicollinearity — use PCA before interaction features"
   - Agent 4: "50+ features — recommend tree-based models"

4. **Failure Recovery** — When an agent fails:
   - Recovery hint is recorded
   - Next agent can access the hint
   - Manager Agent can retry with alternative strategy

### Usage in Agents

```python
from memory.agent_memory import AgentMemory, Decision, DecisionType
from datetime import datetime

def run_agent_1_eda(state):
    # Initialize memory
    if state.get("memory") is None:
        memory = AgentMemory(project_id=state["project_id"], db_client=fb)
        state["memory"] = memory

    # Get context (from previous agents)
    context = memory.get_agent_context(agent_id=1)
    state["dynamic_suggestions"] = context["dynamic_suggestions"]

    # ... do work ...

    # Record decision for next agents
    decision = Decision(
        agent_id=1,
        agent_name="EDA",
        decision_type=DecisionType.ANALYSIS,
        timestamp=datetime.now().isoformat(),
        summary=f"Quality score: {quality_score}/10",
        details={"quality_score": quality_score, "missing_pct": 15},
        confidence=0.95,
        reasoning="Comprehensive EDA analysis",
        impact="Informs imputation strategy in Agent 2"
    )
    memory.record_decision(decision)

    return state
```

---

## Robust EDA Features

The pipeline includes edge-case safe functions from the ML Pipeline docs:

| Function | Description |
|----------|-------------|
| `detect_missing_mechanism()` | MCAR/MAR/MNAR classification with confidence scores |
| `detect_outliers_robust()` | IQR, Z-score, MAD, Isolation Forest methods |
| `bivariate_analysis_safe()` | Handles empty, null, constant columns |
| `multivariate_analysis_safe()` | Condition index, multicollinearity detection |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /projects/create` | Create new project |
| `POST /projects/{pid}/upload` | Upload dataset |
| `GET /projects/{pid}/state` | Get project state |
| `POST /projects/{pid}/feedback` | Submit approval/revision |
| `POST /projects/{pid}/run` | Run full pipeline |
| `POST /projects/{pid}/resume` | Resume paused pipeline |
| `POST /projects/{pid}/run/agent1` | Run just Agent 1 |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run memory tests
pytest tests/test_memory.py -v

# Run robust EDA tests
pytest tests/test_eda_robust.py -v

# Run with coverage
pytest tests/ --cov=agents --cov=memory -v
```

---

## Dependencies

- **Orchestration**: langgraph, langsmith
- **LLM**: 4o-mini(openai)
- **Database**: fdb (Firebird)
- **Data Processing**: pandas, numpy, scikit-learn
- **Visualization**: plotly, matplotlib, seaborn
- **API**: fastapi, uvicorn
- **UI**: streamlit

---

## Credits

Built with contributions from:
- **User's original AgentIQ** — LangGraph orchestration, Firebird persistence
- **Friend's Data_Rad** — Two-phase EDA workflow, Streamlit UI
- **ML Pipeline docs** — Cross-agent memory implementation, robust EDA functions

For full documentation, see `docs/ML_Pipeline/`.

---

## License

MIT
