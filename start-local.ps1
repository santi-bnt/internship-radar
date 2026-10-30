$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv312\Scripts\python.exe"
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$logs = Join-Path $root ".local-logs"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found at $python"
}

New-Item -ItemType Directory -Path $logs -Force | Out-Null

$env:ENVIRONMENT = "development"
$env:LOCAL_DEVELOPMENT_MODE = "true"
$env:APP_ACCESS_ENABLED = "true"
$env:DATABASE_URL = "sqlite:///$($root.Replace('\', '/'))/backend/internship_radar.db"
$env:INTERNAL_API_URL = "http://127.0.0.1:8000"
$env:SCHEDULER_ENABLED = "false"

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if (-not (Test-Endpoint "http://127.0.0.1:8000/health")) {
    Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "backend.out.log") `
        -RedirectStandardError (Join-Path $logs "backend.err.log") | Out-Null
}

if (-not (Test-Endpoint "http://127.0.0.1:3000")) {
    Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000" `
        -WorkingDirectory $frontend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "frontend.out.log") `
        -RedirectStandardError (Join-Path $logs "frontend.err.log") | Out-Null
}

$watch = [Diagnostics.Stopwatch]::StartNew()
$ready = $false
while ($watch.Elapsed.TotalSeconds -lt 60) {
    $elapsed = $watch.Elapsed.TotalSeconds.ToString("0.0")
    Write-Host "`rStarting Internship Radar... ${elapsed}s" -NoNewline
    if (
        (Test-Endpoint "http://127.0.0.1:8000/health") -and
        (Test-Endpoint "http://127.0.0.1:3000")
    ) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 300
}
$watch.Stop()
Write-Host ""

if (-not $ready) {
    throw "Startup exceeded 60 seconds. Check .local-logs for details."
}

Write-Host "Internship Radar ready in $($watch.Elapsed.TotalSeconds.ToString('0.0'))s"
Write-Host "Open: http://localhost:3000"
