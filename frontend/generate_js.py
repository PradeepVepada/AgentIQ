#!/usr/bin/env python3
"""Generate the JavaScript for single-agent focus frontend"""

js_content = """// ═══════════════════════════════════════════════════════════
// AgentIQ - Single-Agent Focus Frontend
// ═══════════════════════════════════════════════════════════

var API = 'http://localhost:8000';
var currentPid = null;
var selectedFile = null;
var currentAgentNum = 1;
var pollInterval = null;

var AGENTS = [
    {id:1, name:'Data Intake & EDA'},
    {id:2, name:'Data Preparation'},
    {id:3, name:'Feature Engineering'},
    {id:4, name:'Model Architecture'},
    {id:5, name:'Training & Tuning'},
    {id:6, name:'Evaluation & Report'}
];

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════
loadProjects();

// ═══════════════════════════════════════════════════════════
// PROJECT MANAGEMENT
// ═══════════════════════════════════════════════════════════
function loadProjects() {
    fetch(API + '/projects')
        .then(r => r.json())
        .then(list => {
            var html = '';
            for (var i = 0; i < list.length; i++) {
                var p = list[i];
                var step = p.current_step || '';
                var title = (p.project_goal || 'Untitled').substring(0, 25);
                var active = p.project_id === currentPid ? 'active' : '';
                html += `<div class="project-item ${active}" onclick="selectProject('${p.project_id}')">
                    <div class="project-title">${title}</div>
                    <div class="project-meta">${(p.created_at || '').substring(0, 10)}</div>
                    <div class="status-pill">${step || 'pending'}</div>
                </div>`;
            }
            document.getElementById('projectsList').innerHTML = html;
        });
}

function selectProject(pid) {
    currentPid = pid;
    document.getElementById('welcome').style.display = 'none';
    document.getElementById('header').style.display = 'block';
    loadProjects();
    
    fetch(API + '/projects/' + pid + '/state')
        .then(r => r.json())
        .then(s => renderDashboard(s));
    
    // Start polling for updates
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => {
        fetch(API + '/projects/' + pid + '/state')
            .then(r => r.json())
            .then(s => renderDashboard(s));
    }, 3000);
}

function renderDashboard(s) {
    document.getElementById('projectTitle').textContent = s.PROJECT_GOAL || 'Project';
    document.getElementById('projectGoal').textContent = s.PROJECT_GOAL || '';
    
    // Determine current agent
    currentAgentNum = getCurrentAgent(s.CURRENT_STEP);
    
    // Render pipeline progress
    renderPipeline(s.CURRENT_STEP);
    
    // Show only the current agent's view
    showAgentView(currentAgentNum, s);
}

function getCurrentAgent(step) {
    if (!step) return 1;
    if (step === 'complete') return 6;
    var map = {
        'eda': 1, 'prep': 2, 'features': 3,
        'model': 4, 'training': 5, 'eval': 6,
        'agent1': 1, 'agent2': 2, 'agent3': 3,
        'agent4': 4, 'agent5': 5, 'agent6': 6
    };
    for (var k in map) { if (step.includes(k)) return map[k]; }
    return 1;
}

function renderPipeline(step) {
    var current = getCurrentAgent(step);
    var html = '';
    
    for (var i = 0; i < AGENTS.length; i++) {
        var a = AGENTS[i];
        var agentNum = i + 1;
        var status = getAgentStatus(agentNum, current, step);
        var label = getAgentLabel(status, step);
        var cssClass = status;
        
        html += `<div class="agent-step ${cssClass}" onclick="switchToAgent(${agentNum})">
            <div class="agent-num">${a.id}</div>
            <div class="agent-name">${a.name}</div>
            <div class="agent-status">${label}</div>
        </div>`;
    }
    
    document.getElementById('pipelineProgress').innerHTML = html;
}

function getAgentStatus(agentNum, currentAgentNum, step) {
    if (step === 'complete') return 'done';
    if (agentNum < currentAgentNum) return 'done';
    if (agentNum === currentAgentNum) {
        if (step && step.includes('_running')) return 'active';
        if (step && step.includes('_error')) return 'error';
        return 'active';
    }
    return 'pending';
}

function getAgentLabel(status, step) {
    if (status === 'done') return 'Done ✓';
    if (status === 'error') return 'Error ✗';
    if (status === 'active') {
        if (step && step.includes('_running')) return 'Running...';
        return 'Active';
    }
    return 'Pending';
}

function switchToAgent(agentNum) {
    currentAgentNum = agentNum;
    fetch(API + '/projects/' + currentPid + '/state')
        .then(r => r.json())
        .then(s => showAgentView(agentNum, s));
}

// ═══════════════════════════════════════════════════════════
// SINGLE-AGENT VIEW RENDERING
// ═══════════════════════════════════════════════════════════
function showAgentView(agentNum, state) {
    // Hide all agent views
    for (var i = 1; i <= 6; i++) {
        document.getElementById('agent' + i + 'View').classList.remove('active');
    }
    
    // Show the selected agent view
    var viewId = 'agent' + agentNum + 'View';
    var viewEl = document.getElementById(viewId);
    
    // Render the agent's content
    switch(agentNum) {
        case 1: renderAgent1(viewEl, state); break;
        case 2: renderAgent2(viewEl, state); break;
        case 3: renderAgent3(viewEl, state); break;
        case 4: renderAgent4(viewEl, state); break;
        case 5: renderAgent5(viewEl, state); break;
        case 6: renderAgent6(viewEl, state); break;
    }
    
    viewEl.classList.add('active');
}

// ═══════════════════════════════════════════════════════════
// AGENT 1: EDA
// ═══════════════════════════════════════════════════════════
function renderAgent1(el, s) {
    if (!s.EDA_REPORT) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 1</div>
                <h1 class="agent-heading">Data Intake & EDA</h1>
                <p class="agent-subtitle">Exploratory Data Analysis in progress...</p>
            </div>
        `;
        return;
    }
    
    var eda = s.EDA_REPORT;
    var ov = eda.overview || {};
    var cols = eda.column_types || {};
    var missing = Array.isArray(eda.missing_analysis) ? eda.missing_analysis : [];
    var outliers = Array.isArray(eda.outlier_analysis) ? eda.outlier_analysis : [];
    var corr = Array.isArray(eda.correlation_analysis) ? eda.correlation_analysis : [];
    var stats = Array.isArray(eda.statistical_analysis) ? eda.statistical_analysis : [];
    var univariate = Array.isArray(eda.univariate_analysis) ? eda.univariate_analysis : [];
    var catSummary = Array.isArray(eda.categorical_summary) ? eda.categorical_summary : [];
    var llm = eda.llm_analysis || {};
    var dq = eda.data_quality || llm.data_quality || {};
    var findings = eda.key_findings || llm.key_findings || [];
    var recs = eda.recommendations || llm.recommendations || [];
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 1 COMPLETE</div>
            <h1 class="agent-heading">Data Intake & EDA</h1>
            <p class="agent-subtitle">Comprehensive exploratory data analysis</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Rows</div>
                <div class="stat-value blue">${(ov.rows||0).toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Columns</div>
                <div class="stat-value purple">${ov.columns||0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Missing Values</div>
                <div class="stat-value orange">${(ov.total_missing||0).toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Duplicates</div>
                <div class="stat-value red">${(ov.duplicate_rows||0).toLocaleString()}</div>
            </div>
        </div>
    `;
    
    // Data Quality Score
    if (dq.score !== undefined) {
        var score = parseFloat(dq.score) || 0;
        var scoreColor = score >= 7 ? 'green' : score >= 4 ? 'orange' : 'red';
        html += `
            <div class="section">
                <div class="section-title">Data Quality Score</div>
                <div class="stat-value ${scoreColor}" style="font-size:48px;">${score.toFixed(1)}/10</div>
            </div>
        `;
    }
    
    // Column Types
    html += '<div class="section"><div class="section-title">Column Types</div>';
    if (cols.numeric && cols.numeric.length) {
        html += `<p style="color:#6E7681;font-size:12px;margin-bottom:8px;">NUMERIC (${cols.numeric.length})</p>`;
        html += '<div class="feature-list">' + cols.numeric.map(x => `<span class="feature-tag">${x}</span>`).join('') + '</div>';
    }
    if (cols.categorical && cols.categorical.length) {
        html += `<p style="color:#6E7681;font-size:12px;margin:16px 0 8px 0;">CATEGORICAL (${cols.categorical.length})</p>`;
        html += '<div class="feature-list">' + cols.categorical.map(x => `<span class="feature-tag">${x}</span>`).join('') + '</div>';
    }
    html += '</div>';
    
    // Missing Values
    var missingCols = missing.filter(m => m.missing_pct > 0);
    if (missingCols.length) {
        html += `
            <div class="section">
                <div class="section-title">Missing Values (${missingCols.length} columns)</div>
                <table class="data-table">
                    <tr><th>Column</th><th>Missing</th><th>%</th><th>Status</th></tr>
        `;
        missingCols.slice(0,10).forEach(m => {
            var color = m.missing_pct > 30 ? '#F85149' : m.missing_pct > 5 ? '#F0883E' : '#8B949E';
            html += `<tr>
                <td>${m.column}</td>
                <td>${m.missing_count}</td>
                <td style="color:${color};">${m.missing_pct.toFixed(1)}%</td>
                <td>${m.status||''}</td>
            </tr>`;
        });
        html += '</table></div>';
    }
    
    // Statistical Summary
    if (stats.length) {
        html += `
            <div class="section">
                <div class="section-title">Statistical Summary</div>
                <table class="data-table">
                    <tr><th>Column</th><th>Mean</th><th>Median</th><th>Std</th><th>Min</th><th>Max</th></tr>
        `;
        stats.slice(0,8).forEach(s => {
            html += `<tr>
                <td>${s.column}</td>
                <td>${s.mean}</td>
                <td>${s.median}</td>
                <td>${s.std}</td>
                <td>${s.min}</td>
                <td>${s.max}</td>
            </tr>`;
        });
        html += '</table></div>';
    }
    
    // Outliers
    var outlierCols = outliers.filter(o => parseFloat(o.outlier_pct||0) > 0);
    if (outlierCols.length) {
        html += `
            <div class="section">
                <div class="section-title">Outlier Analysis</div>
                <table class="data-table">
                    <tr><th>Column</th><th>Outliers</th><th>%</th><th>Lower Bound</th><th>Upper Bound</th></tr>
        `;
        outlierCols.slice(0,8).forEach(o => {
            var color = parseFloat(o.outlier_pct||0) > 10 ? '#F85149' : parseFloat(o.outlier_pct||0) > 5 ? '#F0883E' : '#8B949E';
            html += `<tr>
                <td>${o.column}</td>
                <td>${o.outlier_count}</td>
                <td style="color:${color};">${o.outlier_pct}%</td>
                <td>${o.lower_bound||''}</td>
                <td>${o.upper_bound||''}</td>
            </tr>`;
        });
        html += '</table></div>';
    }
    
    // Correlations
    if (corr.length) {
        html += `
            <div class="section">
                <div class="section-title">Strong Correlations (|r| ≥ 0.7)</div>
                <table class="data-table">
                    <tr><th>Feature 1</th><th>Feature 2</th><th>Correlation</th><th>Strength</th></tr>
        `;
        corr.slice(0,8).forEach(c => {
            var val = parseFloat(c.correlation||0);
            var color = Math.abs(val) >= 0.9 ? '#F85149' : '#F0883E';
            html += `<tr>
                <td>${c.feature_1}</td>
                <td>${c.feature_2}</td>
                <td style="color:${color};">${c.correlation}</td>
                <td>${c.strength||''}</td>
            </tr>`;
        });
        html += '</table></div>';
    }
    
    // Key Findings
    if (findings.length) {
        html += '<div class="section"><div class="section-title">Key Findings</div><div class="insights-list">';
        findings.forEach(f => {
            html += `<div class="insight-item"><span class="insight-icon">💡</span><span>${f}</span></div>`;
        });
        html += '</div></div>';
    }
    
    // Recommendations
    if (recs.length) {
        html += '<div class="section"><div class="section-title">Recommendations</div><div class="insights-list">';
        recs.forEach(r => {
            html += `<div class="insight-item success"><span class="insight-icon">✓</span><span>${r}</span></div>`;
        });
        html += '</div></div>';
    }
    
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// AGENT 2: DATA PREPARATION
// ═══════════════════════════════════════════════════════════
function renderAgent2(el, s) {
    if (!s.CLEANING_REPORT) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 2</div>
                <h1 class="agent-heading">Data Preparation</h1>
                <p class="agent-subtitle">Cleaning and preparing data...</p>
            </div>
        `;
        return;
    }
    
    var cl = s.CLEANING_REPORT;
    var before = cl.shape_before || [0,0];
    var after = cl.shape_after || [0,0];
    var log = cl.execution_log || [];
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 2 COMPLETE</div>
            <h1 class="agent-heading">Data Preparation</h1>
            <p class="agent-subtitle">Data cleaning and preprocessing complete</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Rows Before</div>
                <div class="stat-value purple">${before[0].toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Rows After</div>
                <div class="stat-value green">${after[0].toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Rows Removed</div>
                <div class="stat-value orange">${Math.max(0, before[0]-after[0]).toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Steps Applied</div>
                <div class="stat-value blue">${log.length}</div>
            </div>
        </div>
    `;
    
    if (log.length) {
        html += `
            <div class="section">
                <div class="section-title">Cleaning Steps Applied</div>
                <table class="data-table">
                    <tr><th>Action</th><th>Column</th><th>Method</th><th>Status</th></tr>
        `;
        log.slice(0,10).forEach(e => {
            var step = e.step || {};
            var color = e.status === 'success' ? '#3FB950' : '#F85149';
            html += `<tr>
                <td>${step.action||''}</td>
                <td>${step.column||'global'}</td>
                <td>${step.method||''}</td>
                <td style="color:${color};">${e.status}</td>
            </tr>`;
        });
        html += '</table></div>';
    }
    
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// AGENT 3: FEATURE ENGINEERING
// ═══════════════════════════════════════════════════════════
function renderAgent3(el, s) {
    if (!s.FEATURE_ENGINEERING_PLAN && (!s.SELECTED_FEATURES || !s.SELECTED_FEATURES.length)) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 3</div>
                <h1 class="agent-heading">Feature Engineering</h1>
                <p class="agent-subtitle">Engineering features...</p>
            </div>
        `;
        return;
    }
    
    var fe = s.FEATURE_ENGINEERING_PLAN || {};
    var feats = s.SELECTED_FEATURES || fe.selected_features || [];
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 3 COMPLETE</div>
            <h1 class="agent-heading">Feature Engineering</h1>
            <p class="agent-subtitle">Feature selection and transformation complete</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Features Selected</div>
                <div class="stat-value blue">${feats.length}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Target Column</div>
                <div class="stat-value purple">${fe.target_column||'-'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Task Type</div>
                <div class="stat-value green">${fe.task_type||'-'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Encoded Columns</div>
                <div class="stat-value orange">${(fe.encode_columns||[]).length}</div>
            </div>
        </div>
    `;
    
    if (feats.length) {
        html += `
            <div class="section">
                <div class="section-title">Selected Features (${feats.length})</div>
                <div class="feature-list">
        `;
        feats.slice(0,30).forEach(f => {
            html += `<span class="feature-tag">${f}</span>`;
        });
        if (feats.length > 30) {
            html += `<span class="feature-tag">+${feats.length-30} more</span>`;
        }
        html += '</div></div>';
    }
    
    if (fe.notes) {
        html += `
            <div class="section">
                <div class="section-title">Notes</div>
                <p style="color:#8B949E;line-height:1.6;">${fe.notes}</p>
            </div>
        `;
    }
    
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// AGENT 4: MODEL ARCHITECTURE
// ═══════════════════════════════════════════════════════════
function renderAgent4(el, s) {
    if (!s.CANDIDATE_MODELS) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 4</div>
                <h1 class="agent-heading">Model Architecture</h1>
                <p class="agent-subtitle">Selecting models...</p>
            </div>
        `;
        return;
    }
    
    var models = Object.keys(s.CANDIDATE_MODELS);
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 4 COMPLETE</div>
            <h1 class="agent-heading">Model Architecture</h1>
            <p class="agent-subtitle">Model selection and configuration complete</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Candidate Models</div>
                <div class="stat-value blue">${models.length}</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">Selected Models</div>
            <div class="insights-list">
    `;
    
    models.forEach(m => {
        var cfg = s.CANDIDATE_MODELS[m];
        var scaling = cfg.needs_scaling ? 'Scaling required' : 'No scaling needed';
        html += `<div class="insight-item"><span class="insight-icon">🤖</span><span><strong>${m}</strong> — ${scaling}</span></div>`;
    });
    
    html += '</div></div>';
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// AGENT 5: TRAINING
// ═══════════════════════════════════════════════════════════
function renderAgent5(el, s) {
    if (!s.TRAINING_RESULTS) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 5</div>
                <h1 class="agent-heading">Training & Tuning</h1>
                <p class="agent-subtitle">Training models...</p>
            </div>
        `;
        return;
    }
    
    var results = s.TRAINING_RESULTS;
    var models = Object.keys(results);
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 5 COMPLETE</div>
            <h1 class="agent-heading">Training & Tuning</h1>
            <p class="agent-subtitle">Model training complete</p>
        </div>
        
        <div class="section">
            <div class="section-title">Training Results</div>
            <table class="data-table">
                <tr><th>Model</th><th>Train Score</th><th>Val Score</th><th>Status</th></tr>
    `;
    
    models.forEach(m => {
        var r = results[m];
        var trainScore = (r.train_score || 0).toFixed(4);
        var valScore = (r.val_score || 0).toFixed(4);
        html += `<tr>
            <td>${m}</td>
            <td>${trainScore}</td>
            <td>${valScore}</td>
            <td style="color:#3FB950;">✓ Complete</td>
        </tr>`;
    });
    
    html += '</table></div>';
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// AGENT 6: EVALUATION
// ═══════════════════════════════════════════════════════════
function renderAgent6(el, s) {
    if (!s.EVALUATION_REPORT) {
        el.innerHTML = `
            <div class="agent-header">
                <div class="agent-title">AGENT 6</div>
                <h1 class="agent-heading">Evaluation & Report</h1>
                <p class="agent-subtitle">Evaluating models...</p>
            </div>
        `;
        return;
    }
    
    var eval = s.EVALUATION_REPORT;
    var best = eval.best_model || {};
    
    var html = `
        <div class="agent-header">
            <div class="agent-title">AGENT 6 COMPLETE</div>
            <h1 class="agent-heading">Evaluation & Report</h1>
            <p class="agent-subtitle">Final evaluation complete</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Best Model</div>
                <div class="stat-value blue">${best.name||'-'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Test Score</div>
                <div class="stat-value green">${(best.test_score||0).toFixed(4)}</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">Final Report</div>
            <p style="color:#8B949E;line-height:1.6;">${eval.summary||'Evaluation complete.'}</p>
        </div>
    `;
    
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════
// PIPELINE ACTIONS
// ═══════════════════════════════════════════════════════════
function runPipeline() {
    if (!currentPid) return;
    fetch(API + '/projects/' + currentPid + '/run', {method: 'POST'})
        .then(r => r.json())
        .then(data => {
            console.log('Pipeline started:', data);
        });
}

function deleteProject() {
    if (!currentPid) return;
    if (!confirm('Delete this project?')) return;
    fetch(API + '/projects/' + currentPid, {method: 'DELETE'})
        .then(() => {
            currentPid = null;
            document.getElementById('welcome').style.display = 'block';
            document.getElementById('header').style.display = 'none';
            for (var i = 1; i <= 6; i++) {
                document.getElementById('agent' + i + 'View').classList.remove('active');
            }
            loadProjects();
        });
}

// ═══════════════════════════════════════════════════════════
// MODAL
// ═══════════════════════════════════════════════════════════
function showModal() {
    document.getElementById('modalOverlay').classList.add('active');
}

function hideModal() {
    document.getElementById('modalOverlay').classList.remove('active');
    document.getElementById('goalInput').value = '';
    document.getElementById('fileDrop').classList.remove('has-file');
    document.getElementById('fileDropText').textContent = 'Click to upload CSV file';
    selectedFile = null;
}

function handleFile(input) {
    if (input.files && input.files[0]) {
        selectedFile = input.files[0];
        document.getElementById('fileDrop').classList.add('has-file');
        document.getElementById('fileDropText').textContent = selectedFile.name;
    }
}

function createProject() {
    var goal = document.getElementById('goalInput').value;
    if (!goal || !selectedFile) {
        alert('Please provide a goal and upload a CSV file');
        return;
    }
    
    var formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('project_goal', goal);
    
    fetch(API + '/projects', {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        hideModal();
        selectProject(data.project_id);
    })
    .catch(err => {
        alert('Error creating project: ' + err);
    });
}
"""

with open('app.js', 'w', encoding='utf-8') as f:
    f.write(js_content)

print("✓ Generated app.js")
