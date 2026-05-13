# ADR-002: Firebird Persistence Layer

**Status**: Accepted (Optional)  
**Date**: May 13, 2026  
**Deciders**: AgentIQ Development Team  
**Affects**: Storage layer, project state management, recovery mechanisms

---

## Context

AgentIQ needs to persist project state across sessions. The system must support:

1. **Project Recovery** — Resume interrupted pipelines
2. **Audit Trail** — Track all decisions and agent outputs
3. **Multi-Session Support** — Users can close and reopen projects
4. **Optional Persistence** — Should work without database for development

### Decision Options Considered

**Option 1: SQLite**
- Lightweight, file-based SQL database
- **Pros**: Simple, no server, widely supported
- **Cons**: Limited concurrency, not ideal for distributed systems, schema rigidity
- **Trade-off**: Simplicity vs. scalability

**Option 2: PostgreSQL**
- Full-featured relational database
- **Pros**: Scalable, robust, excellent for production
- **Cons**: Requires server setup, operational overhead, overkill for current scale
- **Trade-off**: Power vs. complexity

**Option 3: Firebird** ✅ **SELECTED**
- Embedded or client-server SQL database
- **Pros**: Embedded mode (no server), scalable to client-server, ACID compliant, good for ML workflows
- **Cons**: Less common than SQLite/PostgreSQL, smaller ecosystem
- **Trade-off**: Flexibility vs. ecosystem size

**Option 4: In-Memory Only**
- No persistence, state lost on restart
- **Pros**: Fastest, simplest
- **Cons**: No recovery, no audit trail, unsuitable for production
- **Trade-off**: Speed vs. reliability

---

## Decision

**We adopt Option 3: Firebird with Optional Persistence**

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│              (LangGraph State Machine)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│  Memory Storage  │    │ Firebird Storage │
│  (Default)       │    │  (Optional)      │
│  - Fast          │    │  - Persistent    │
│  - Dev-friendly  │    │  - Production    │
│  - No setup      │    │  - Recoverable   │
└──────────────────┘    └──────────────────┘
        │                         │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │   Storage Interface     │
        │  (Abstract base class)  │
        └────────────────────────┘
```

### Rationale

1. **Embedded Mode** — Firebird can run embedded (no server), perfect for development
2. **Scalability** — Can upgrade to client-server mode for production without code changes
3. **ACID Compliance** — Ensures data integrity for critical ML decisions
4. **Optional** — Default is in-memory; Firebird only activated via `STORAGE_MODE=firebird`
5. **Flexibility** — Supports both single-file and network deployments

---

## Implementation

### Storage Interface (Abstract)

```python
class StorageInterface(ABC):
    """Abstract storage interface."""
    
    @abstractmethod
    async def create_project(self, project_id: str, goal: str, dataset_path: str):
        """Create new project."""
        pass
    
    @abstractmethod
    async def get_state(self, project_id: str) -> Dict[str, Any]:
        """Get project state."""
        pass
    
    @abstractmethod
    async def update_state(self, project_id: str, **kwargs):
        """Update project state."""
        pass
    
    @abstractmethod
    async def record_decision(self, project_id: str, decision: Dict[str, Any]):
        """Record agent decision."""
        pass
```

### Memory Storage (Default)

```python
class MemoryStorage(StorageInterface):
    """In-memory storage (default)."""
    
    def __init__(self):
        self.projects = {}  # project_id -> state
        self.decisions = {}  # project_id -> [decisions]
    
    async def create_project(self, project_id: str, goal: str, dataset_path: str):
        self.projects[project_id] = {
            "PROJECT_ID": project_id,
            "PROJECT_GOAL": goal,
            "DATASET_PATH": dataset_path,
            "created_at": datetime.now().isoformat(),
        }
```

### Firebird Storage (Optional)

```python
class FirebirdStorage(StorageInterface):
    """Firebird database storage (optional)."""
    
    def __init__(self, dsn: str, user: str, password: str):
        self.dsn = dsn
        self.user = user
        self.password = password
        self.connection = None
    
    async def create_project(self, project_id: str, goal: str, dataset_path: str):
        # Insert into Firebird database
        query = """
            INSERT INTO PROJECTS (PROJECT_ID, PROJECT_GOAL, DATASET_PATH, CREATED_AT)
            VALUES (?, ?, ?, ?)
        """
        # Execute query...
```

### Configuration

```python
# From config/settings.py
storage_mode = os.getenv("STORAGE_MODE", "memory")  # Default: memory

if storage_mode == "firebird":
    storage = FirebirdStorage(
        dsn=os.getenv("FIREBIRD_DSN"),
        user=os.getenv("FIREBIRD_USER", "SYSDBA"),
        password=os.getenv("FIREBIRD_PASSWORD")
    )
else:
    storage = MemoryStorage()
```

### Environment Configuration

```env
# .env file

# Storage mode: "memory" (default) or "firebird"
STORAGE_MODE=memory

# Firebird configuration (only needed if STORAGE_MODE=firebird)
FIREBIRD_DSN=C:\path\to\database.fdb
FIREBIRD_USER=SYSDBA
FIREBIRD_PASSWORD=your_password
FIREBIRD_CHARSET=UTF8
```

---

## Consequences

### Positive

1. **Flexibility** — Choose storage based on deployment context
2. **Development-Friendly** — Default in-memory mode requires no setup
3. **Production-Ready** — Firebird mode provides persistence and recovery
4. **Scalability** — Can upgrade from embedded to client-server without code changes
5. **ACID Compliance** — Firebird ensures data integrity
6. **Audit Trail** — All decisions recorded in database
7. **Multi-Session Support** — Users can resume interrupted projects

### Negative

1. **Complexity** — Two storage implementations to maintain
2. **Firebird Overhead** — Embedded Firebird adds ~5-10MB to deployment
3. **Schema Management** — Database schema must be versioned and migrated
4. **Operational Burden** — Production deployments need database backups
5. **Ecosystem Size** — Firebird has smaller community than SQLite/PostgreSQL

### Mitigation

- **Complexity**: Abstract storage interface keeps implementations isolated
- **Overhead**: Firebird only loaded when `STORAGE_MODE=firebird`
- **Schema**: Use migration scripts in `db/migrations/`
- **Operations**: Provide backup/restore scripts
- **Ecosystem**: Firebird is mature and stable; documentation available

---

## Embedded vs. Client-Server Trade-offs

### Embedded Mode (Current)

```
Application → Firebird (embedded) → database.fdb
```

**Pros**:
- No server setup required
- Single-file deployment
- Perfect for development and small deployments
- Lower latency (local file access)

**Cons**:
- Single-process access only
- Not suitable for distributed systems
- Limited concurrent connections

### Client-Server Mode (Future)

```
Application → Firebird Client → Firebird Server → database.fdb
```

**Pros**:
- Multiple concurrent connections
- Suitable for distributed systems
- Better for production deployments
- Network-accessible

**Cons**:
- Requires server setup
- Network latency
- More operational complexity

### Migration Path

```
Development (Embedded)
    ↓
    └─→ Production (Client-Server)
        └─→ Distributed (Multiple Servers)
```

**Code remains the same** — only connection string changes:

```python
# Embedded (development)
dsn = "C:\\database.fdb"

# Client-Server (production)
dsn = "firebird://db-server.example.com:3050/database.fdb"
```

---

## Metrics

### Performance

| Metric | Embedded | Client-Server |
|--------|----------|----------------|
| Write latency | <10ms | 10-50ms |
| Read latency | <5ms | 5-20ms |
| Concurrent connections | 1-2 | 100+ |
| Deployment complexity | Low | Medium |

### Storage

| Metric | Value |
|--------|-------|
| Database file size | ~10-50MB (typical) |
| Project record size | ~5KB |
| Decision record size | ~2KB |
| Backup size | ~10-50MB |

### Scalability

| Scenario | Embedded | Client-Server |
|----------|----------|----------------|
| Single user | ✅ Excellent | ✅ Excellent |
| 10 concurrent users | ⚠️ Limited | ✅ Excellent |
| 100 concurrent users | ❌ Not suitable | ✅ Excellent |
| Distributed deployment | ❌ Not suitable | ✅ Excellent |

---

## Success Criteria

- ✅ In-memory storage works without Firebird
- ✅ Firebird storage works when enabled
- ✅ Project state persists across sessions
- ✅ Decisions are recorded in audit trail
- ✅ Recovery works after process crash
- ✅ Can upgrade from embedded to client-server
- ✅ Performance meets targets (<50ms latency)

---

## Future Enhancements

### ADR-004: Multi-Database Support
- Support PostgreSQL for large-scale deployments
- Support MongoDB for document-oriented storage
- Abstract storage interface enables easy addition

### ADR-005: Database Replication
- Master-slave replication for high availability
- Backup and disaster recovery procedures
- Data consistency guarantees

### ADR-006: Data Retention Policy
- Archive old projects to cold storage
- Implement data retention policies
- GDPR compliance for data deletion

---

## References

- `db/memory_storage.py` — In-memory storage implementation
- `db/firebird_storage.py` — Firebird storage implementation
- `db/firebird_client.py` — Firebird client wrapper
- `db/setup_db.py` — Database setup script
- `config/settings.py` — Configuration management
- `app/api.py` — Storage initialization

---

## Related Decisions

- **ADR-001**: Cross-agent memory (uses storage layer)
- **ADR-003**: LangGraph orchestration (state management)
- **ADR-004** (future): Multi-database support
- **ADR-005** (future): Database replication

---

## Approval

- **Proposed by**: AgentIQ Development Team
- **Reviewed by**: Architecture Review Board
- **Approved by**: Project Lead
- **Date**: May 13, 2026

---

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-05-13 | 1.0 | Initial decision record |

