# AgentIQ - Quick Reference Guide

## 🚀 Quick Start (5 minutes)

### 1. Install
```bash
cd AgentIQ
pip install -r requirements.txt
```

### 2. Configure
```bash
# Edit .env with your OpenAI API key
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
```

### 3. Run Backend
```bash
py -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run Frontend (new terminal)
```bash
cd AgentIQ/frontend
py -m http.server 8080
```

### 5. Open Browser
```
http://localhost:8080
```

---

## 📋 System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10/11, Linux, macOS |
| **Python** | 3.10+ (tested on 3.12, 3.14) |
| **RAM** | 8GB minimum, 16GB recommended |
| **Disk** | 5GB+ for dependencies |
| **API Key** | OpenAI API key required |

---

## 🔧 Environment Variables

```env
# Required
OPENAI_API_KEY=sk-proj-...

# Optional (for observability)
LANGSMITH_API_KEY=lsv2_pt_...
LANGCHAIN_TRACING_V2=true
LANGSMITH_PROJECT=agentiq-pipeline

# Storage (default: memory)
STORAGE_MODE=memory
# or: firebird (requires Firebird database)
```

---

## 📦 Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ≥1.1.0 | Orchestration |
| openai | ≥1.0.0 | LLM API |
| fastapi | ≥0.104.0 | Web API |
| pandas | ≥2.0.0 | Data processing |
| scikit-learn | ≥1.3.0 | ML algorithms |

---

## 🌐 Services

| Service | Port | URL | Command |
|---------|------|-----|---------|
| Backend | 8000 | http://localhost:8000 | `uvicorn app.api:app --port 8000` |
| Frontend | 8080 | http://localhost:8080 | `python -m http.server 8080` |

---

## 📁 Project Structure

```
AgentIQ/
├── agents/              # 6 agent implementations
├── app/                 # FastAPI server
├── frontend/            # Web UI (HTML/JS)
├── tools/               # Shared utilities
├── db/                  # Database layer
├── workflows/           # LangGraph config
├── tests/               # Test suite
├── data/                # Data storage
└── requirements.txt     # Dependencies
```

---

## 🤖 The 6 Agents

| Agent | Purpose | Input | Output |
|-------|---------|-------|--------|
| 1 | EDA | Raw dataset | Statistics, findings |
| 2 | Data Prep | Raw data | Cleaned data |
| 3 | Features | Cleaned data | Selected features |
| 4 | Models | Features | 10 candidate models |
| 5 | Training | Model + data | Trained model |
| 6 | Evaluation | Model + test | Metrics, report |

---

## 📊 Data Formats

**Supported Input**:
- CSV (.csv)
- Excel (.xlsx)
- Parquet (.parquet)

**Output**:
- CSV (.csv)
- Stored in `data/` directories

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_agent1_eda.py -v

# With coverage
pytest tests/ --cov=agents -v
```

---

## 🔌 API Endpoints

```
POST   /projects                    # Create project
GET    /projects                    # List projects
GET    /projects/{id}/state         # Get state
POST   /projects/{id}/run           # Run pipeline
POST   /projects/{id}/approve/{n}   # Approve agent
GET    /health                      # Health check
```

---

## 🎨 Frontend Features

✅ Project creation
✅ Dataset upload
✅ Pipeline execution
✅ Agent result display
✅ Human feedback dialog
✅ Auto/Human-in-Loop toggle
✅ Self-Review toggle
✅ All features display (Agent 1)
✅ Finalized features display (Agent 3)

---

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check port 8000 is free
netstat -ano | findstr :8000

# Check Python version
python --version  # Should be 3.10+

# Check dependencies
pip list | grep langgraph
```

### Frontend won't load
```bash
# Check port 8080 is free
netstat -ano | findstr :8080

# Check browser console (F12)
# Look for CORS or network errors
```

### API calls failing
```bash
# Check API key
echo %OPENAI_API_KEY%

# Test API
curl http://localhost:8000/health
```

---

## 📝 Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start backend
py -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload

# Start frontend
cd frontend && py -m http.server 8080

# Run tests
pytest tests/ -v

# Check git status
git status

# Push to GitHub
git add -A
git commit -m "message"
git push -u origin main
```

---

## 🔐 Security Notes

- ✅ Never commit .env file
- ✅ Use environment variables for secrets
- ✅ Keep API keys private
- ✅ Use HTTPS in production
- ✅ Validate all inputs
- ✅ Sanitize error messages

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| README.md | Project overview |
| FINAL_REQUIREMENTS.md | Complete requirements |
| UI_REDESIGN_SUMMARY.md | UI changes |
| IMPLEMENTATION_VERIFICATION.md | Implementation details |
| DEPLOYMENT_READY.md | Deployment guide |
| QUICK_REFERENCE.md | This file |

---

## 🚀 Deployment Checklist

- [ ] Python 3.10+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] .env configured with API keys
- [ ] Backend starts without errors
- [ ] Frontend loads in browser
- [ ] Can create project
- [ ] Can upload dataset
- [ ] Can run pipeline
- [ ] All agents complete successfully
- [ ] Results display correctly

---

## 📞 Support

- **GitHub**: https://github.com/PradeepVepada/AgentIQ
- **OpenAI API**: https://platform.openai.com
- **LangGraph**: https://langchain-ai.github.io/langgraph
- **FastAPI**: https://fastapi.tiangolo.com

---

## 📊 Performance Targets

| Agent | Target Time |
|-------|------------|
| Agent 1 (EDA) | < 30s |
| Agent 2 (Prep) | < 20s |
| Agent 3 (Features) | < 15s |
| Agent 4 (Models) | < 10s |
| Agent 5 (Training) | < 60s |
| Agent 6 (Evaluation) | < 20s |

---

## 🎯 Version Info

- **AgentIQ**: 5.4.0
- **Python**: 3.10+
- **LangGraph**: 1.1.0+
- **FastAPI**: 0.104.0+

---

**Last Updated**: May 9, 2026
**Status**: ✅ Production Ready
