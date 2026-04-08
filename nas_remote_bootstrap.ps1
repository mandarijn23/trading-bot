param(
    [string]$NasHost = "nas@192.168.1.70",
    [string]$AppDir = "/home/nas/trading-bot",
    [string]$PrimaryModel = "qwen2.5:3b",
    [string]$FallbackModel = "phi3:mini"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting remote NAS AI bootstrap on $NasHost" -ForegroundColor Cyan
Write-Host "You may be prompted for the NAS password a few times (ssh/scp)." -ForegroundColor Yellow

$localRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$requiredFiles = @(
    "nas_copilot.sh",
    "nas_ai_bootstrap.sh",
    "nas_health_check.sh",
    "nas_repair.sh",
    "run_stock_session.sh"
)

foreach ($name in $requiredFiles) {
    $full = Join-Path $localRoot $name
    if (-not (Test-Path $full)) {
        throw "Required local file missing: $full"
    }
}

Write-Host "Ensuring remote app directory exists: $AppDir" -ForegroundColor Cyan
ssh $NasHost "mkdir -p '$AppDir'"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create remote app directory $AppDir"
}

Write-Host "Uploading required NAS helper scripts..." -ForegroundColor Cyan
$sources = $requiredFiles | ForEach-Object { Join-Path $localRoot $_ }
scp @sources "${NasHost}:$AppDir/"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upload required scripts to ${NasHost}:$AppDir"
}

$remoteScript = @"
set -euo pipefail
APP_DIR='$AppDir'
PRIMARY_MODEL='$PrimaryModel'
FALLBACK_MODEL='$FallbackModel'

cd "`$APP_DIR"
chmod +x ./nas_copilot.sh ./nas_ai_bootstrap.sh ./nas_health_check.sh ./nas_repair.sh ./run_stock_session.sh
COPILOT_ASSUME_YES=1 AI_MODEL="`$PRIMARY_MODEL" AI_FALLBACK_MODEL="`$FALLBACK_MODEL" ./nas_copilot.sh "`$APP_DIR" ai-bootstrap
COPILOT_ASSUME_YES=1 AI_MODEL="`$PRIMARY_MODEL" ./nas_copilot.sh "`$APP_DIR" ai-test
COPILOT_ASSUME_YES=1 ./nas_copilot.sh "`$APP_DIR" ai-status
"@

# Ensure the streamed script uses LF line endings so bash options parse correctly.
$remoteScript = $remoteScript -replace "`r", ""
Write-Host "Running remote bootstrap actions..." -ForegroundColor Cyan
$remoteScript | ssh $NasHost "bash -s"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Remote bootstrap failed with exit code $LASTEXITCODE"
}

Write-Host "Remote NAS AI bootstrap complete." -ForegroundColor Green