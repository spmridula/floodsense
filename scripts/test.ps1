$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."
Push-Location (Join-Path $root "backend"); .\.venv\Scripts\python.exe -m pytest -q; Pop-Location
Push-Location (Join-Path $root "frontend"); npm test; npm run build; Pop-Location
