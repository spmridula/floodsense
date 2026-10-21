# Starts backend (8000) in a new window and frontend (5173) here.
$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","app.main:app","--reload","--port","8000" -WorkingDirectory (Join-Path $root "backend")
Set-Location (Join-Path $root "frontend")
npm run dev
