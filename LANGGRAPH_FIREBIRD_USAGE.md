# LangGraph & Firebird Usage Analysis

## Short Answer

**LangGraph**: ✅ **YES, actively used**
**Firebird**: ❌ **NO, not actively used** (optional fallback only)

---

## LangGraph Usage - ✅ ACTIVE

### Where It's Used

1. **Agent Self-Review Loops** (All 6 agents)
   - `agents/agent1_eda_with_review.py` - Uses `StateGraph`
   - `agents/agent2_data_prep_with_review.py` - Uses `StateGraph`
   - `agents/agent3_feature_eng_with_review.py` - Uses `StateGraph`
   - `agents/agent4_model_arch_with_review.py` - Uses `StateGraph`
   - `agents/agent5_training_with_review.py` - Uses `StateGraph`
   - `agents/agent6_evaluation_with_review.py` - Uses `StateGraph`

2. **Main Pipeline Orchestration**
   - `workflows/graph.py` - Main `StateGraph` for 6-agent pipeline
   - Uses `interrupt()` for human approval gates
   - Connects all agents in sequence

3. **State Management**
   - `workflows/state.py` - Defines `PipelineState` TypedDict
   - All agents read/write to shared state
   - State travels through LangGraph

### Code Evidence

```python
# From agents/agent1_eda_with_review.py
from langgraph.graph import StateGraph, START, END

def build_eda_graph_with_review(llm_client) -> StateGraph:
    """Build Agent 1 graph with self-review loop."""
    graph = StateGraph(dict)
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    # ... add edges and compile
```

```python
# From workflows/graph.py
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

def build_pipeline_graph() -> StateGraph:
    g = StateGraph(PipelineState)
    # Add all 6 agent nodes
    # Add human approval gates with interrupt()
```

---

## Firebird Usage - ❌ NOT ACTIVE

### Current Status

**Default**: `STORAGE_MODE=memory` (in-memory storage)
**Firebird**: Optional fallback only

### Code Evidence

```python
# From app/api.py
storage_mode = os.getenv("STORAGE_MODE", "memory").lower()

if storage_mode == "firebird":
    try:
        storage = FirebirdStorage(...)
        logger.info("Using Firebird storage")
    except Exception as e:
        logger.warning(f"Firebird storage failed: {e}, falling back to memory storage")
        storage = MemoryStorage()
else:
    storage = MemoryStorage()
    logger.info("Using in-memory storage")  # ← THIS IS WHAT'S RUNNING
```

### Why Not Active

1. **Default is Memory Storage**
   - Faster for development
   - No database setup required
   - Sufficient for current use case

2. **Firebird Files Exist But Unused**
   - `db/firebird_storage.py` - Implemented but not used
   - `db/firebird_client.py` - Implemented but not used
   - `db/setup_db.py` - Setup script but not executed
   - `db/add_*.py` - Migration scripts but not used

3. **Environment Variable Not Set**
   - `.env` has `STORAGE_MODE=memory`
   - Would need `STORAGE_MODE=firebird` to activate

---

## Summary Table

| Technology | Status | Usage | Evidence |
|-----------|--------|-------|----------|
| **LangGraph** | ✅ Active | Core orchestration | 6 agents use StateGraph, main pipeline uses StateGraph |
| **Firebird** | ❌ Inactive | Optional fallback | Code exists but STORAGE_MODE=memory by default |

---

## What's Actually Running

### ✅ Active Technologies
- **LangGraph**: State machine orchestration for all agents
- **OpenAI API**: LLM calls for agent reasoning
- **FastAPI**: Web API server
- **In-Memory Storage**: Project state stored in RAM

### ❌ Inactive Technologies
- **Firebird**: Database code exists but not used
- **Persistent Storage**: No data persisted between sessions

---

## To Activate Firebird

If you want to use Firebird:

1. **Set environment variable**
   ```env
   STORAGE_MODE=firebird
   FIREBIRD_DSN=C:\path\to\database.fdb
   FIREBIRD_USER=SYSDBA
   FIREBIRD_PASSWORD=your_password
   ```

2. **Run setup script**
   ```bash
   python db/setup_db.py
   ```

3. **Restart backend**
   ```bash
   py -m uvicorn app.api:app --port 8000 --reload
   ```

---

## Conclusion

**LangGraph**: Core technology, actively used for orchestration
**Firebird**: Optional technology, not currently used (memory storage instead)

Your project is **LangGraph-first** with **optional Firebird persistence**.

---

**Status**: Analysis Complete
**Date**: May 9, 2026
