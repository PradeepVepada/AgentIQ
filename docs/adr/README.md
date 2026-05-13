# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) documenting major architectural decisions for AgentIQ.

---

## Overview

ADRs are structured documents that capture:
- **Context**: Why the decision was needed
- **Options**: Alternatives considered
- **Decision**: What was chosen and why
- **Consequences**: Trade-offs and implications
- **Metrics**: How success is measured

---

## ADRs

### ADR-001: Cross-Agent Memory Implementation

**File**: `ADR-001-cross-agent-memory.md`  
**Status**: ✅ Accepted  
**Date**: May 13, 2026

**Question**: How should agents share context and decisions?

**Options Evaluated**:
1. Database polling (rejected)
2. Local memory + Firebird persistence (✅ SELECTED)
3. Shared LLM context (rejected)

**Decision**: Use a Decision Journal in LangGraph state with optional Firebird persistence

**Key Benefits**:
- Fast context retrieval (<50ms)
- Clean interface
- Optional persistence
- Flexible schema

**Trade-offs**:
- Memory growth vs. persistence
- Simplicity vs. queryability

**Implementation**:
- `memory/agent_memory.py` — Decision Journal
- `workflows/state.py` — PipelineState with memory fields
- `agents/agent1_eda_with_review.py` — Example usage

---

### ADR-002: Firebird Persistence Layer

**File**: `ADR-002-firebird-persistence.md`  
**Status**: ✅ Accepted (Optional)  
**Date**: May 13, 2026

**Question**: How should project state be persisted?

**Options Evaluated**:
1. SQLite (rejected)
2. PostgreSQL (rejected)
3. Firebird (✅ SELECTED)
4. In-memory only (rejected)

**Decision**: Use Firebird with optional persistence (default: in-memory)

**Key Benefits**:
- Embedded mode (no server setup)
- Scalable to client-server
- ACID compliance
- Optional (development-friendly)

**Trade-offs**:
- Embedded vs. client-server
- Simplicity vs. scalability
- Smaller ecosystem

**Implementation**:
- `db/memory_storage.py` — In-memory storage (default)
- `db/firebird_storage.py` — Firebird storage (optional)
- `config/settings.py` — Storage configuration
- `app/api.py` — Storage initialization

**Current Status**: ✅ Implemented but optional (default: memory mode)

---

### ADR-003: LangGraph State Machine Orchestration

**File**: `ADR-003-langgraph-orchestration.md`  
**Status**: ✅ Accepted  
**Date**: May 13, 2026

**Question**: How should the 6-agent pipeline be orchestrated?

**Options Evaluated**:
1. Luigi (rejected)
2. Apache Airflow (rejected)
3. Custom state machine (rejected)
4. LangGraph (✅ SELECTED)

**Decision**: Use LangGraph state machine for orchestration

**Key Benefits**:
- Agent-native design
- Built-in approval gates
- Self-review loop support
- Simple API
- LangSmith integration

**Trade-offs**:
- Newer framework
- Smaller ecosystem
- Limited scaling

**Implementation**:
- `workflows/graph.py` — Main pipeline graph
- `workflows/state.py` — PipelineState definition
- `agents/self_review_loop.py` — Self-review loops
- `app/orchestrator.py` — Pipeline orchestrator

**Current Status**: ✅ Fully implemented and active

---

## Implementation Status

### ADR-001: Cross-Agent Memory ✅ IMPLEMENTED

**Status**: Fully implemented

**Evidence**:
- ✅ `memory/agent_memory.py` exists with Decision class
- ✅ `workflows/state.py` has memory fields
- ✅ All agents can record decisions
- ✅ Tests in `tests/test_memory_persistence.py`

**Usage**:
```python
# Initialize memory
memory = AgentMemory(project_id=state["project_id"])

# Record decision
decision = Decision(
    agent_id=1,
    summary="Quality score: 8/10",
    details={"quality_score": 8},
    confidence=0.95,
)
memory.record_decision(decision)

# Retrieve context
context = memory.get_agent_context(agent_id=2)
```

---

### ADR-002: Firebird Persistence ✅ IMPLEMENTED (Optional)

**Status**: Implemented but optional (default: memory mode)

**Evidence**:
- ✅ `db/memory_storage.py` — In-memory storage (active)
- ✅ `db/firebird_storage.py` — Firebird storage (available)
- ✅ `config/settings.py` — Storage configuration
- ✅ `app/api.py` — Storage initialization with fallback

**Current Configuration**:
```env
STORAGE_MODE=memory  # Default: in-memory
# STORAGE_MODE=firebird  # Optional: Firebird persistence
```

**To Enable Firebird**:
```env
STORAGE_MODE=firebird
FIREBIRD_DSN=C:\path\to\database.fdb
FIREBIRD_USER=SYSDBA
FIREBIRD_PASSWORD=your_password
```

**Usage**:
```python
# Storage is abstracted
if storage_mode == "firebird":
    storage = FirebirdStorage(dsn, user, password)
else:
    storage = MemoryStorage()

# Same interface for both
await storage.create_project(project_id, goal, dataset_path)
await storage.get_state(project_id)
```

---

### ADR-003: LangGraph Orchestration ✅ FULLY IMPLEMENTED

**Status**: Fully implemented and active

**Evidence**:
- ✅ `workflows/graph.py` — Main pipeline graph
- ✅ `workflows/state.py` — PipelineState TypedDict
- ✅ All 6 agents use StateGraph
- ✅ Approval gates implemented with `interrupt()`
- ✅ Self-review loops in each agent
- ✅ Tests in `tests/test_pipeline_e2e.py`

**Usage**:
```python
# Build graph
graph = build_pipeline_graph()

# Run pipeline
result = graph.invoke(initial_state)

# With approval gates
result = graph.invoke(
    initial_state,
    config={"interrupt_before": ["approval_1", "approval_2"]}
)
```

---

## Decision Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentIQ Architecture                     │
└─────────────────────────────────────────────────────────────┘

ADR-003: LangGraph Orchestration
    ↓
    ├─→ Manages execution flow
    ├─→ Maintains PipelineState
    └─→ Enables approval gates

ADR-001: Cross-Agent Memory
    ↓
    ├─→ Stores decisions in PipelineState
    ├─→ Provides context to agents
    └─→ Enables error recovery

ADR-002: Firebird Persistence
    ↓
    ├─→ Persists PipelineState
    ├─→ Provides audit trail
    └─→ Enables project recovery
```

---

## Trade-offs Summary

### ADR-001: Memory vs. Persistence

| Aspect | Option 1 (DB Polling) | Option 2 (Local Memory) | Option 3 (LLM Context) |
|--------|----------------------|------------------------|----------------------|
| Latency | High (DB queries) | Low (<50ms) ✅ | Medium (token cost) |
| Coupling | High (DB dependency) | Low (in-process) ✅ | None (LLM only) |
| Flexibility | Medium (schema) | High (JSON) ✅ | Low (token limits) |
| Cost | Medium (DB ops) | Low ✅ | High (tokens) |
| **Selected** | ❌ | ✅ | ❌ |

### ADR-002: Storage Backend

| Aspect | SQLite | PostgreSQL | Firebird | In-Memory |
|--------|--------|-----------|----------|-----------|
| Setup | Simple | Complex | Medium ✅ | None |
| Scalability | Limited | Excellent | Good ✅ | None |
| Embedded | Yes | No | Yes ✅ | N/A |
| ACID | Yes | Yes | Yes ✅ | No |
| Ecosystem | Large | Largest | Small | N/A |
| **Selected** | ❌ | ❌ | ✅ | ✅ (default) |

### ADR-003: Orchestration Framework

| Aspect | Luigi | Airflow | Custom | LangGraph |
|--------|-------|---------|--------|-----------|
| Complexity | Medium | High | High | Low ✅ |
| Approval Gates | No | Awkward | Custom | Built-in ✅ |
| Self-Review | No | No | Custom | Natural ✅ |
| Learning Curve | Moderate | Steep | High | Gentle ✅ |
| LLM Integration | No | No | Custom | Native ✅ |
| **Selected** | ❌ | ❌ | ❌ | ✅ |

---

## Future ADRs

### ADR-004: Conditional Routing (Planned)
- Route to different agents based on data characteristics
- Skip agents if conditions not met
- Parallel agent execution

### ADR-005: Dynamic Agent Selection (Planned)
- Choose agents based on problem type
- Add/remove agents dynamically
- Custom agent chains

### ADR-006: Distributed Orchestration (Planned)
- Run agents on different machines
- Horizontal scaling
- Fault tolerance

### ADR-007: Multi-Database Support (Planned)
- Support PostgreSQL for large-scale deployments
- Support MongoDB for document storage
- Abstract storage interface

---

## How to Use ADRs

### For Development

1. **Understand Decisions**: Read ADRs to understand why choices were made
2. **Evaluate Changes**: Use ADR format to propose new decisions
3. **Maintain Consistency**: Follow established patterns

### For Interviews

1. **Show Thinking**: "I evaluated 3 options and chose X because..."
2. **Explain Trade-offs**: "The trade-off is Y vs. Z"
3. **Demonstrate Discipline**: "We document all major decisions"

### For Onboarding

1. **New Team Members**: Read ADRs to understand architecture
2. **Context**: Understand why things are the way they are
3. **Future Changes**: Know what decisions have been made

---

## ADR Template

```markdown
# ADR-NNN: [Title]

**Status**: Proposed/Accepted/Deprecated  
**Date**: [Date]  
**Deciders**: [Team]  
**Affects**: [Components]

---

## Context

[Problem statement and background]

### Decision Options Considered

**Option 1: [Name]**
- Pros: ...
- Cons: ...

**Option 2: [Name]** ✅ **SELECTED**
- Pros: ...
- Cons: ...

---

## Decision

[What was chosen and why]

### Rationale

1. [Reason 1]
2. [Reason 2]
3. [Reason 3]

---

## Consequences

### Positive
- [Benefit 1]
- [Benefit 2]

### Negative
- [Trade-off 1]
- [Trade-off 2]

---

## Metrics

[Success criteria and measurements]

---

## References

[Links to implementation]

---

## Related Decisions

[Links to related ADRs]
```

---

## References

- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **Firebird**: https://firebirdsql.org/
- **ADR Format**: https://adr.github.io/

---

## Summary

| ADR | Title | Status | Implementation |
|-----|-------|--------|-----------------|
| 001 | Cross-Agent Memory | ✅ Accepted | ✅ Fully Implemented |
| 002 | Firebird Persistence | ✅ Accepted | ✅ Implemented (Optional) |
| 003 | LangGraph Orchestration | ✅ Accepted | ✅ Fully Implemented |

**All three ADRs are implemented in the codebase.**

---

**Last Updated**: May 13, 2026  
**Version**: 1.0

