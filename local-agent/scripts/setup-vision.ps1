param([switch]$UseGpu, [string]$Model = "gemma3:4b")
$ErrorActionPreference = "Stop"
if ($Model -notmatch '^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,100}$' -or $Model -match 'cloud|https?|@|\.com|\.net|\.io') {
    throw "Choose a downloaded local vision model; cloud models are disabled."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Install Docker Desktop or run Ollama natively before starting local vision." }
& docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $desktopPath = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktopPath)) { throw "Open Docker Desktop first." }
    Start-Process -FilePath $desktopPath -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 2
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker did not start. Open Docker Desktop, check WSL2 and retry." }
}
$composePath = Join-Path $PSScriptRoot "..\compose.vision.yml"
$composeOptions = @("compose", "--project-name", "radar-local-ai", "-f", $composePath)
if ($UseGpu -or (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
    $composeOptions += @("-f", (Join-Path $PSScriptRoot "..\compose.vision.gpu.yml"))
    Write-Host "Starting local vision with NVIDIA GPU support."
} else { Write-Host "Starting local vision on CPU; inference may be slower." }
& docker @composeOptions up -d --wait
if ($LASTEXITCODE -ne 0) { throw "Could not start the local model container. Check Docker/GPU support and that port 11434 is free." }
$ready = $false
try {
    $info = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/show' -Method Post -ContentType 'application/json' -Body (@{ model = $Model } | ConvertTo-Json) -TimeoutSec 5
    $ready = $info.capabilities -contains 'vision' -and -not $info.remote_model -and -not $info.remote_host
} catch { $ready = $false }
if (-not $ready) {
    Write-Host "Downloading $Model from the official Ollama registry. This first download needs several GB; subsequent starts reuse it."
    & docker @composeOptions exec -T vision ollama pull $Model
    if ($LASTEXITCODE -ne 0) { throw "Could not download the local vision model. No cloud fallback will be used." }
}
$info = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/show' -Method Post -ContentType 'application/json' -Body (@{ model = $Model } | ConvertTo-Json) -TimeoutSec 10
if ($info.capabilities -notcontains 'vision' -or $info.remote_model -or $info.remote_host) { throw "The selected model is not a local vision model." }
Write-Host "Local HTML + image analysis ready: $Model. Cloud inference disabled."
