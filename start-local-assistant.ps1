param([switch]$WithDockerVision, [switch]$UseGpu, [string]$VisionModel = "gemma3:4b")
$ErrorActionPreference = "Stop"
$agentDirectory = Join-Path $PSScriptRoot "local-agent"
Push-Location $agentDirectory
try {
    if ($WithDockerVision) {
        & (Join-Path $agentDirectory "scripts\setup-vision.ps1") -UseGpu:$UseGpu -Model $VisionModel
        $env:RADAR_LOCAL_VISION_MODEL = $VisionModel
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Install Node.js 22 or later first." }
    $nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
    if ($nodeMajor -lt 22) { throw "The local assistant requires Node.js 22 or later." }
    if (-not (Test-Path -LiteralPath (Join-Path $agentDirectory "node_modules"))) {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "Could not install the local assistant dependencies." }
    }
    & npm.cmd run install-browser
    if ($LASTEXITCODE -ne 0) { throw "Could not install the assistant's Chromium browser." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Could not build the local assistant." }
    & npm.cmd start
} finally { Pop-Location }
