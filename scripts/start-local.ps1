param([switch]$Development, [int]$FrontendPort = 3000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendPath = Join-Path $projectRoot 'frontend'
$logsPath = Join-Path $projectRoot 'data\logs'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install backend/runtime/requirements.txt first. See README.md.' }
if (!(Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules\next'))) { throw 'Run npm ci in frontend first.' }
foreach ($port in @(8000,$FrontendPort)) {
  if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Check the existing service before starting another instance." }
}
New-Item -ItemType Directory -Path $logsPath -Force | Out-Null
if (!$env:RAG_ALLOWED_ORIGINS) { $env:RAG_ALLOWED_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort,http://localhost:8000,http://127.0.0.1:8000" }
if ($Development) {
  $webArguments = @('node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port',"$FrontendPort")
} else {
  $standalonePath = Join-Path $frontendPath '.next\standalone'
  if (!(Test-Path -LiteralPath (Join-Path $standalonePath 'server.js'))) { throw 'Run npm run build in frontend before starting production mode.' }
  Copy-Item -LiteralPath (Join-Path $frontendPath '.next\static') -Destination (Join-Path $standalonePath '.next\static') -Recurse -Force
  $env:PORT = "$FrontendPort"
  $env:HOSTNAME = '127.0.0.1'
  $webArguments = @('.next/standalone/server.js')
}
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','backend.runtime.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logsPath 'api.log') -RedirectStandardError (Join-Path $logsPath 'api-error.log') -PassThru
$webProcess = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList $webArguments -WorkingDirectory $frontendPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logsPath 'web.log') -RedirectStandardError (Join-Path $logsPath 'web-error.log') -PassThru
@{ api = $apiProcess.Id; frontend = $webProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logsPath 'processes.json')
Write-Output "Started API PID $($apiProcess.Id) and frontend PID $($webProcess.Id)."
Write-Output "Frontend: http://localhost:$FrontendPort | API docs: http://localhost:8000/docs"
Write-Output "Logs: $logsPath"
