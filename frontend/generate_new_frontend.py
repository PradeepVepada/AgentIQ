#!/usr/bin/env python3
"""
Generate the new single-agent focus frontend for AgentIQ
"""

html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AgentIQ - Data Science Studio</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif; 
            background: #0D1117; 
            color: #F1F5F9; 
            overflow: hidden;
        }
        
        .app-container { display: flex; height: 100vh; }
        
        /* SIDEBAR */
        .sidebar { 
            width: 280px; background: #161B22; border-right: 1px solid #1E2D3D; 
            padding: 20px; display: flex; flex-direction: column; overflow-y: auto; 
        }
        .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
        .logo-icon { 
            width: 36px; height: 36px; background: linear-gradient(135deg, #3B82F6, #8B5CF6); 
            border-radius: 8px; display: flex; align-items: center; justify-content: center; 
            font-weight: 700; color: white; font-size: 14px; 
        }
        .logo-text { font-size: 18px; font-weight: 700; }
        .logo-text span { color: #3B82F6; }
        .new-btn { 
            background: #3B82F6; color: white; border: none; padding: 12px; 
            border-radius: 8px; cursor: pointer; font-weight: 600; width: 100%; 
            margin-bottom: 20px; transition: all 0.2s;
        }
        .new-btn:hover { background: #2563EB; transform: translateY(-1px); }
        .section-label { 
            font-size: 11px; text-transform: uppercase; color: #6E7681; 
            font-weight: 600; margin-bottom: 10px; letter-spacing: 0.5px; 
        }
        .project-item { 
            padding: 12px; border-radius: 6px; margin-bottom: 8px; cursor: pointer; 
            border: 1px solid transparent; transition: all 0.2s; 
        }
        .project-item:hover { background: #1E2D3D; }
        .project-item.active { background: #1E2D3D; border-color: #3B82F6; }
        .project-title { 
            font-weight: 500; font-size: 13px; margin-bottom: 6px; 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; 
        }
        .project-meta { font-size: 11px; color: #6E7681; }
        .status-pill { 
            display: inline-block; padding: 2px 8px; border-radius: 10px; 
            font-size: 10px; font-weight: 600; margin-top: 6px; 
        }
        
        /* MAIN */
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        
        /* HEADER */
        .header { 
            background: #161B22; border-bottom: 1px solid #1E2D3D; padding: 20px 30px; 
        }
        .header-top { 
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; 
        }
        .project-info h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
        .project-info p { color: #6E7681; font-size: 14px; }
        .header-actions { display: flex; gap: 10px; }
        .btn { 
            padding: 10px 16px; border-radius: 6px; border: none; 
            cursor: pointer; font-weight: 500; font-size: 13px; transition: all 0.2s;
        }
        .btn-primary { background: #3B82F6; color: white; }
        .btn-primary:hover { background: #2563EB; transform: translateY(-1px); }
        .btn-danger { background: transparent; color: #F85149; border: 1px solid #F85149; }
        .btn-danger:hover { background: #F85149; color: white; }
        
        /* PIPELINE PROGRESS */
        .pipeline-progress { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
        .agent-step { 
            background: #0D1117; border: 1px solid #1E2D3D; border-radius: 8px; 
            padding: 12px; text-align: center; cursor: pointer; transition: all 0.2s; 
        }
        .agent-step:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2); }
        .agent-step.done { border-color: #3FB950; background: rgba(63, 185, 80, 0.1); }
        .agent-step.active { 
            border-color: #3B82F6; background: rgba(59, 130, 246, 0.1); 
            box-shadow: 0 0 20px rgba(59, 130, 246, 0.3);
        }
        .agent-step.pending { opacity: 0.5; }
        .agent-num { 
            width: 32px; height: 32px; border-radius: 50%; background: #1E2D3D; 
            display: flex; align-items: center; justify-content: center; 
            font-weight: 600; margin: 0 auto 8px; font-size: 14px; 
        }
        .agent-step.done .agent-num { background: #3FB950; color: white; }
        .agent-step.active .agent-num { 
            background: #3B82F6; color: white; animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.7); }
            50% { box-shadow: 0 0 0 10px rgba(59, 130, 246, 0); }
        }
        .agent-name { font-size: 11px; font-weight: 600; margin-bottom: 4px; }
        .agent-status { font-size: 10px; color: #6E7681; }
        .agent-step.done .agent-status { color: #3FB950; }
        .agent-step.active .agent-status { color: #3B82F6; }
        
        /* CONTENT */
        .content { flex: 1; overflow-y: auto; padding: 30px; }
        .welcome { text-align: center; padding: 100px 40px; }
        .welcome-icon { font-size: 60px; margin-bottom: 20px; opacity: 0.3; }
        .welcome h1 { font-size: 28px; margin-bottom: 10px; }
        .welcome p { color: #6E7681; }
        
        /* AGENT VIEW */
        .agent-view { display: none; }
        .agent-view.active { display: block; animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .agent-header { margin-bottom: 30px; }
        .agent-title { 
            font-size: 11px; color: #3B82F6; font-weight: 700; 
            text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; 
        }
        .agent-heading { font-size: 32px; font-weight: 800; margin-bottom: 8px; }
        .agent-subtitle { color: #6E7681; font-size: 14px; }
        
        /* STATS GRID */
        .stats-grid { 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 16px; margin-bottom: 30px; 
        }
        .stat-card { 
            background: #161B22; border: 1px solid #1E2D3D; border-radius: 10px; 
            padding: 20px; transition: all 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3); }
        .stat-label { 
            font-size: 11px; text-transform: uppercase; color: #6E7681; 
            font-weight: 600; margin-bottom: 8px; 
        }
        .stat-value { font-size: 28px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
        .stat-value.blue { color: #3B82F6; }
        .stat-value.green { color: #3FB950; }
        .stat-value.orange { color: #F0883E; }
        .stat-value.purple { color: #A855F7; }
        .stat-value.red { color: #F85149; }
        
        /* SECTION */
        .section { 
            background: #161B22; border: 1px solid #1E2D3D; border-radius: 12px; 
            padding: 24px; margin-bottom: 24px; 
        }
        .section-title { 
            font-size: 11px; color: #6E7681; font-weight: 700; 
            text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 16px; 
            display: flex; align-items: center; gap: 8px;
        }
        .section-title::before {
            content: ''; width: 3px; height: 16px; 
            background: #3B82F6; border-radius: 2px;
        }
        
        /* DATA TABLE */
        .data-table { 
            width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; 
        }
        .data-table th, .data-table td { 
            padding: 12px; text-align: left; border-bottom: 1px solid #1E2D3D; 
        }
        .data-table th { 
            color: #6E7681; font-weight: 600; font-size: 11px;
            text-transform: uppercase; letter-spacing: 0.5px;
        }
        .data-table td { color: #8B949E; }
        .data-table tr:hover { background: rgba(59, 130, 246, 0.05); }
        
        /* FEATURE TAGS */
        .feature-list { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
        .feature-tag { 
            background: #1E2D3D; padding: 6px 12px; border-radius: 6px; 
            font-size: 12px; color: #8B949E; transition: all 0.2s;
        }
        .feature-tag:hover { background: #3B82F6; color: white; transform: translateY(-1px); }
        
        /* INSIGHTS */
        .insights-list { margin: 16px 0; }
        .insight-item { 
            background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); 
            border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; 
            font-size: 13px; line-height: 1.6; display: flex; align-items: start; gap: 10px;
        }
        .insight-item.success { 
            background: rgba(63, 185, 80, 0.1); border-color: rgba(63, 185, 80, 0.3); 
        }
        .insight-item.warning { 
            background: rgba(245, 158, 11, 0.1); border-color: rgba(245, 158, 11, 0.3); 
        }
        .insight-item.error { 
            background: rgba(248, 81, 73, 0.1); border-color: rgba(248, 81, 73, 0.3); 
        }
        .insight-icon { font-size: 16px; flex-shrink: 0; }
        
        /* CHARTS */
        .chart-container { 
            background: #0D1117; border: 1px solid #1E2D3D; border-radius: 8px; 
            padding: 16px; margin: 16px 0; 
        }
        .chart-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px; margin: 16px 0;
        }
        
        /* MODAL */
        .modal-overlay { 
            position: fixed; top: 0; left: 0; right: 0; bottom: 0; 
            background: rgba(0,0,0,0.7); display: none; align-items: center; 
            justify-content: center; z-index: 100; backdrop-filter: blur(4px);
        }
        .modal-overlay.active { display: flex; }
        .modal { 
            background: #161B22; border: 1px solid #1E2D3D; border-radius: 12px; 
            padding: 30px; width: 450px; animation: modalSlideIn 0.3s ease-out;
        }
        @keyframes modalSlideIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .modal h2 { margin-bottom: 20px; }
        .modal input { 
            width: 100%; padding: 12px; background: #0D1117; border: 1px solid #1E2D3D; 
            border-radius: 6px; color: white; font-size: 14px; margin-bottom: 16px; 
        }
        .modal input:focus {
            outline: none; border-color: #3B82F6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        .modal-btns { display: flex; gap: 10px; }
        .modal-btns .btn { flex: 1; }
        .file-drop { 
            border: 2px dashed #1E2D3D; border-radius: 8px; padding: 30px; 
            text-align: center; margin-bottom: 16px; cursor: pointer; transition: all 0.2s; 
        }
        .file-drop:hover { border-color: #3B82F6; background: rgba(59, 130, 246, 0.05); }
        .file-drop.has-file { border-color: #3FB950; background: rgba(63, 185, 80, 0.1); }
        .file-drop-icon { font-size: 24px; margin-bottom: 8px; }
        .file-drop-text { color: #6E7681; }
        .hidden { display: none !important; }
        
        /* SCROLLBAR */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #0D1117; }
        ::-webkit-scrollbar-thumb { background: #1E2D3D; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #3B82F6; }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="sidebar">
            <div class="logo">
                <div class="logo-icon">IQ</div>
                <div class="logo-text">Agent<span>IQ</span></div>
            </div>
            <button class="new-btn" onclick="showModal()">+ New Project</button>
            <div class="section-label">Your Projects</div>
            <div id="projectsList"></div>
        </div>
        
        <div class="main">
            <div class="header" id="header" style="display:none;">
                <div class="header-top">
                    <div class="project-info">
                        <h1 id="projectTitle">Project</h1>
                        <p id="projectGoal"></p>
                    </div>
                    <div class="header-actions">
                        <button class="btn btn-primary" onclick="runPipeline()">&#9654; Run Pipeline</button>
                        <button class="btn btn-danger" onclick="deleteProject()">Delete</button>
                    </div>
                </div>
                <div class="pipeline-progress" id="pipelineProgress"></div>
            </div>
            
            <div class="content">
                <div id="welcome" class="welcome">
                    <div class="welcome-icon">&#128640;</div>
                    <h1>Welcome to AgentIQ</h1>
                    <p>Select a project or create a new one to get started</p>
                </div>
                
                <div id="agent1View" class="agent-view"></div>
                <div id="agent2View" class="agent-view"></div>
                <div id="agent3View" class="agent-view"></div>
                <div id="agent4View" class="agent-view"></div>
                <div id="agent5View" class="agent-view"></div>
                <div id="agent6View" class="agent-view"></div>
            </div>
        </div>
    </div>
    
    <div class="modal-overlay" id="modalOverlay">
        <div class="modal">
            <h2>Create New Project</h2>
            <input type="text" id="goalInput" placeholder="Project goal (e.g., predict loan default)">
            <div class="file-drop" id="fileDrop" onclick="document.getElementById('fileInput').click()">
                <div class="file-drop-icon">&#128193;</div>
                <div class="file-drop-text" id="fileDropText">Click to upload CSV file</div>
            </div>
            <input type="file" id="fileInput" accept=".csv" style="display:none" onchange="handleFile(this)">
            <div class="modal-btns">
                <button class="btn btn-primary" onclick="createProject()">Create Project</button>
                <button class="btn" style="background:#1E2D3D;color:#8B949E;" onclick="hideModal()">Cancel</button>
            </div>
        </div>
    </div>

    <script src="app.js"></script>
</body>
</html>
"""

# Write the HTML file
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("✓ Generated index.html")
