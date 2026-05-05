# AgentIQ Pipeline - Presentation Guide

## Architecture Overview

**AgentIQ** is a 6-agent ML pipeline orchestrator with human-in-the-loop approval gates. Each agent specializes in a stage of the ML workflow.

### Key Features

✅ **Async-First Architecture** - Zero blocking I/O, minimal latency  
✅ **Human-in-Loop Approval** - Pause after each agent for human feedback  
✅ **Real-Time Dashboard** - Live analysis display with clean UI  
✅ **Minimal State Transfer** - Only required fields passed between agents  
✅ **Production-Ready Error Handling** - Structured errors with root cause  
✅ **Firebird-Ready** - Abstract storage layer for easy DB migration  

---

## Quick Start

### 1. Start Backend
```bash
cd AgentIQ
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
```

### 2. Start Frontend
```bash
cd AgentIQ/frontend
python -m http.server 8080
```

### 3. Open Browser
```
http://localhost:8080
```

---

## Pipeline Flow

```
User Upload Dataset
    ↓
Create Project
    ↓
Agent 1: EDA Analysis
    ↓ (Human Approval)
Agent 2: Data Preparation
    ↓ (Human Approval)
Agent 3: Feature Engineering
    ↓ (Human Approval)
Agent 4: Model Architecture
    ↓ (Human Approval)
Agent 5: Training & Tuning
    ↓ (Auto - no approval)
Agent 6: Evaluation & Report
    ↓
Pipeline Complete
```

---

## Agent Responsibilities

### Agent 1: Data Intake & EDA
- Loads dataset
- Runs statistical analysis (missing values, outliers, correlations)
- LLM generates structured EDA report
- **Output**: eda_report, task_type, llm_eda_analysis

### Agent 2: Data Preparation
- Executes cleaning plan
- Handles missing values, duplicates, outliers
- **Output**: cleaning_report, cleaned_data_path

### Agent 3: Feature Engineering
- Detects task type (classification/regression/clustering)
- Creates polynomial and interaction features
- Selects top features by correlation
- **Output**: feature_engineering_plan, selected_features, engineered_data_path

### Agent 4: Model Architecture
- Selects candidate models based on task type
- Creates sklearn pipeline with preprocessing
- Defines hyperparameter search space
- **Output**: candidate_models, split_strategy, train_idx_path, test_idx_path

### Agent 5: Training & Tuning
- Trains all candidate models
- Hyperparameter tuning with Optuna
- Tracks training metrics
- **Output**: training_results, tuning_results

### Agent 6: Evaluation & Report
- Evaluates best model on test set
- Generates comprehensive evaluation report
- **Output**: evaluation_report

---

## Dashboard Features

### Pipeline Progress
- Visual representation of all 6 agents
- Status indicators: ○ (pending), ⟳ (running), ✓ (done), ✗ (error)
- Real-time updates every 2 seconds

### Analysis Display
- **Stats Grid**: Rows, columns, missing values, duplicates
- **Key Findings**: Automatically extracted from EDA
- **Approval Section**: Human approval button to continue

### Error Handling
- Structured error messages with root cause
- Automatic error display on dashboard
- Pipeline halts gracefully on failure

---

## Technical Highlights

### Async Architecture
- All I/O operations are non-blocking
- Agents run in thread pool to avoid blocking FastAPI
- Background tasks for long-running operations

### Minimal State Transfer
- Only required fields passed to each agent
- Reduces serialization overhead
- Faster state updates

### Storage Abstraction
- `Storage` interface for in-memory and Firebird
- Easy migration: just swap storage implementation
- No code changes needed in orchestrator or agents

### Error Handling
- Try-catch at orchestrator level
- Structured error responses
- Graceful degradation

---

## Performance Metrics

| Agent | Typical Time | Bottleneck |
|-------|-------------|-----------|
| Agent 1 (EDA) | 30-60s | LLM API latency |
| Agent 2 (Prep) | 20-40s | Data processing |
| Agent 3 (Features) | 20-40s | Feature generation |
| Agent 4 (Architecture) | 10-20s | Model selection |
| Agent 5 (Training) | 2-5 min | Model training |
| Agent 6 (Evaluation) | 10-20s | Evaluation metrics |

**Total Pipeline**: ~5-7 minutes (with human approval delays)

---

## Presentation Demo Script

### Step 1: Create Project
1. Click "+ New Project"
2. Enter goal: "Predict loan default"
3. Upload dataset (CSV)
4. Click "Create Project"

### Step 2: Run Pipeline
1. Click "▶ Run Pipeline"
2. Watch Agent 1 execute (30-60s)
3. Dashboard shows EDA analysis
4. Review findings

### Step 3: Approve & Continue
1. Click "✓ Approve & Continue"
2. Agent 2 starts automatically
3. Repeat for Agents 3-4
4. Agents 5-6 run automatically

### Step 4: View Results
1. Pipeline completes
2. Show final evaluation report
3. Highlight key metrics

---

## Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID <PID> /F
```

### Frontend not connecting
- Ensure backend is running on port 8000
- Check CORS is enabled (it is by default)
- Open browser console for errors

### Agent fails
- Check backend logs for error message
- Verify dataset is valid CSV
- Ensure OPENAI_API_KEY is set in .env

### Slow performance
- Check network latency to OpenAI API
- Verify dataset size (< 100MB recommended)
- Monitor CPU/memory usage

---

## Architecture Decisions

### Why Async?
- FastAPI is async-native
- Agents run in thread pool to avoid blocking
- Minimal latency for API responses

### Why Minimal State Transfer?
- Reduces serialization overhead
- Faster state updates
- Cleaner agent interfaces

### Why Storage Abstraction?
- Easy migration from in-memory to Firebird
- No code changes needed in orchestrator
- Testable with mock storage

### Why Human-in-Loop?
- Allows human oversight of AI decisions
- Enables course correction mid-pipeline
- Builds trust in automated system

---

## Future Enhancements

- [ ] WebSocket support for real-time updates
- [ ] Caching for expensive operations
- [ ] Parallel agent execution where possible
- [ ] Advanced error recovery strategies
- [ ] Multi-user support with authentication
- [ ] Firebird persistence layer
- [ ] Model versioning and comparison
- [ ] Automated hyperparameter tuning

---

## Contact & Support

For questions or issues, check the backend logs:
```bash
tail -f AgentIQ/backend.log
```

Good luck with your presentation! 🚀
