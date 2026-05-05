# AgentIQ Startup Script
Write-Host 'Cleaning up old processes...' -ForegroundColor Yellow

# Port 8000 (Backend)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($port8000) {
    Write-Host 'Killing process on port 8000...' -ForegroundColor Red
    Stop-Process -Id $port8000.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Port 8080 (Frontend)
$port8080 = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
if ($port8080) {
    Write-Host 'Killing process on port 8080...' -ForegroundColor Red
    Stop-Process -Id $port8080.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host 'Ports cleaned up.' -ForegroundColor Green

# Start Backend
Write-Host 'Starting Backend on port 8000...' -ForegroundColor Cyan
$backendPath = 'C:\Users\santosh Arsid\Desktop\Man Cave\DataAgents\AgentIQ'
$backendScript = {
    Set-Location $args[0]
    python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
}
Start-Job -ScriptBlock $backendScript -ArgumentList $backendPath -Name 'backend'
Write-Host 'Backend started' -ForegroundColor Green

Start-Sleep -Seconds 5

# Start Frontend
Write-Host 'Starting Frontend on port 8080...' -ForegroundColor Cyan
$frontendPath = 'C:\Users\santosh Arsid\Desktop\Man Cave\DataAgents\AgentIQ\frontend'
$frontendScript = {
    Set-Location $args[0]
    python -m http.server 8080
}
Start-Job -ScriptBlock $frontendScript -ArgumentList $frontendPath -Name 'frontend'
Write-Host 'Frontend started' -ForegroundColor Green

Write-Host ''
Write-Host 'Backend:  http://localhost:8000' -ForegroundColor Cyan
Write-Host 'Frontend: http://localhost:8080' -ForegroundColor Cyan
Get-Job | Format-Table Name, State