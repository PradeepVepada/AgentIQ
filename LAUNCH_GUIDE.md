# AgentIQ Pipeline - Launch Guide

## ✅ Application Status: RUNNING

### Services
- **Backend**: http://localhost:8000 ✅ Running
- **Frontend**: http://localhost:8080 ✅ Running

### Health Check
```
Backend Health: {"status":"ok","version":"5.0.0"}
Frontend Status: 200 OK
```

---

## 🚀 Quick Start

### Step 1: Open Application
Open your browser and navigate to:
```
http://localhost:8080
```

### Step 2: Create New Project
1. Click **"+ New Project"** button in sidebar
2. Enter project goal (e.g., "Predict loan default")
3. Upload a CSV dataset
4. Click **"Create Project"**

### Step 3: Configure Pipeline
1. **Auto Mode Toggle**: 
   - OFF (left) = Human-in-Loop mode (pause after each agent)
   - ON (right) = Auto mode (all agents run sequentially)

2. **Self-Review Toggle**:
   - ON (left) = LLM reviews its own output (2 LLM calls per agent)
   - OFF (right) = No self-review (1 LLM call per agent)

### Step 4: Run Pipeline
1. Click **"▶ Run Pipeline"** button
2. Watch agents execute in real-time
3. View results as each agent completes

### Step 5: Approve & Continue (Human-in-Loop Mode)
1. Review agent output
2. Click **"✓ Approve & Continue"** to proceed to next agent
3. Repeat for each agent

---

## 📊 Dashboard Features

### Pipeline Progress
- Visual representation of all 6 agents
- Status indicators:
  - ○ Pending
  - ⟳ Running
  - ✓ Complete
  - ✗ Error

### Agent Results Display

#### Agent 1: Data Intake & EDA
- Rows, Columns, Missing Values, Duplicates
- Key Findings from analysis

#### Agent 2: Data Preparation
- Rows Processed ✅ (Now fixed)
- Missing Handled ✅ (Now fixed)
- Outliers Detected ✅ (Now fixed)
- Duplicates Removed ✅ (Now fixed)

#### Agent 3: Feature Engineering
- Total Features
- Selected Features
- Top Features by Importance

#### Agent 4: Model Architecture
- Candidate Models ✅ (Now fixed)
- Primary Model ✅ (Now fixed)
- Candidate Models List

#### Agent 5: Training & Tuning
- Models Trained
- CV Scores for each model

---

## 🔧 Configuration

### Environment Variables
Located in `AgentIQ/.env`:
```
OPENAI_API_KEY=your_api_key_here
STORAGE_MODE=memory  # or "firebird" for production
```

### Backend Endpoints

#### Projects
- `GET /projects` - List all projects
- `POST /projects` - Create new project with dataset
- `GET /projects/{id}/state` - Get project state
- `DELETE /projects/{id}` - Delete project

#### Pipeline
- `POST /projects/{id}/run` - Run pipeline
  - Query params: `mode` (auto/human_in_loop), `enable_revision_loop` (true/false)
- `POST /projects/{id}/approve/{agent}` - Approve agent and continue

#### Health
- `GET /health` - Health check

---

## 🎯 Usage Scenarios

### Scenario 1: Quick Auto Pipeline
1. Create project
2. Toggle Auto Mode ON
3. Toggle Self-Review OFF (for speed)
4. Click Run Pipeline
5. Wait for completion (~3-5 minutes)

### Scenario 2: Human-in-Loop Review
1. Create project
2. Toggle Auto Mode OFF
3. Toggle Self-Review ON (for quality)
4. Click Run Pipeline
5. Review each agent output
6. Click Approve & Continue for each agent

### Scenario 3: Production Deployment
1. Set `STORAGE_MODE=firebird` in .env
2. Configure Firebird database connection
3. Run pipeline with error recovery active
4. Monitor error logs for issues

---

## 📈 Pipeline Architecture

### Agent Flow
```
User Upload Dataset
    ↓
Create Project
    ↓
Agent 1: EDA Analysis
    ↓ (Human Approval or Auto)
Agent 2: Data Preparation
    ↓ (Human Approval or Auto)
Agent 3: Feature Engineering
    ↓ (Human Approval or Auto)
Agent 4: Model Architecture
    ↓ (Human Approval or Auto)
Agent 5: Training & Tuning
    ↓ (Auto - no approval)
Pipeline Complete
```

### Error Recovery
- **Automatic Retry**: 3 attempts with exponential backoff
- **Circuit Breaker**: Stops retrying if >5 errors in 5 minutes
- **Fallback Strategies**: Minimal valid outputs when recovery fails
- **Error Logging**: All errors tracked in persistent storage

---

## 🐛 Troubleshooting

### Backend Won't Start
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID <PID> /F

# Restart backend
cd AgentIQ
py -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Won't Load
```bash
# Check if port 8080 is in use
netstat -ano | findstr :8080

# Restart frontend
cd AgentIQ/frontend
py -m http.server 8080
```

### Agent Fails
1. Check backend logs for error message
2. Verify dataset is valid CSV
3. Ensure OPENAI_API_KEY is set
4. Check error recovery logs in project state

### Slow Performance
1. Check network latency to OpenAI API
2. Verify dataset size (< 100MB recommended)
3. Monitor CPU/memory usage
4. Toggle Self-Review OFF for speed

---

## 📊 Performance Metrics

| Agent | Typical Time | Bottleneck |
|-------|-------------|-----------|
| Agent 1 (EDA) | 30-60s | LLM API latency |
| Agent 2 (Prep) | 20-40s | Data processing |
| Agent 3 (Features) | 20-40s | Feature generation |
| Agent 4 (Architecture) | 10-20s | Model selection |
| Agent 5 (Training) | 2-5 min | Model training |
| **Total** | **~5-7 min** | LLM + Training |

---

## ✅ Recent Fixes

### Agent 2: Metrics Tracking
- ✅ Now tracks actual metrics (missing_handled, outliers_detected, duplicates_removed)
- ✅ Added automatic cleaning fallback
- ✅ Proper metric aggregation during execution

### Agent 4: Model Display
- ✅ Fixed data format mismatch (dict → array)
- ✅ Now displays candidate models count correctly
- ✅ Shows primary model name correctly

---

## 🚀 Ready for Production

All agents 1-5 are:
- ✅ Fully functional
- ✅ Properly tracking metrics
- ✅ Have error recovery
- ✅ Have fallback strategies
- ✅ Display correctly on frontend

---

## 📝 Next Steps

1. **Open Application**: http://localhost:8080
2. **Create Project**: Upload your dataset
3. **Run Pipeline**: Choose Auto or Human-in-Loop mode
4. **View Results**: See agent outputs in real-time
5. **Iterate**: Adjust toggles and re-run as needed

---

## 📞 Support

For issues or questions:
1. Check backend logs: `AgentIQ/backend.log`
2. Check error summary in project state
3. Review agent-specific logs in console output
4. Check GitHub issues: https://github.com/PradeepVepada/AgentIQ

---

**Status**: ✅ Application Ready
**Version**: 5.1.0
**Date**: May 8, 2026
**Last Updated**: Agent 4 Fix Applied
