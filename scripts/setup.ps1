# One-time setup (Windows PowerShell). Requires Python 3.11+ and Node 20+.
# If scripts are blocked:  Set-ExecutionPolicy -Scope Process Bypass
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location backend; ..\backend\.venv\Scripts\python.exe -m app.cli init-db; Pop-Location
Push-Location frontend; npm ci; Pop-Location
Write-Host "Setup complete. Run scripts\dev.ps1"
