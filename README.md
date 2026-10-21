# FloodSense — Urban Flood Early Warning & Safe Routing (Hyderabad)

> **Advisory student project. Not an official warning system.** Follow instructions from GHMC, HYDRAA, police and emergency services.

**Current status: Phase 1 (foundation) complete.** No weather, risk or routing features exist yet.
The app currently shows backend health/readiness and an honest data-source register.

## Quick start

Prerequisites: Python 3.11+ (tested 3.12), Node 20+ (tested 22).

| | Windows PowerShell | macOS / Linux |
|---|---|---|
| Setup (once) | `.\scripts\setup.ps1` | `./scripts/setup.sh` |
| Run | `.\scripts\dev.ps1` | `./scripts/dev.sh` |
| Test | `.\scripts\test.ps1` | `./scripts/test.sh` |

Then open http://localhost:5173 (API docs: http://localhost:8000/docs).
If PowerShell blocks scripts: `Set-ExecutionPolicy -Scope Process Bypass`.
The PowerShell scripts have **not** been executed by the author (Linux sandbox); the bash scripts were run from a clean copy.

## Layout
- `backend/` FastAPI app (`app/`), Alembic migrations (`alembic/`), tests (`tests/`)
- `frontend/` React + TypeScript + Vite, Vitest tests
- `scripts/` setup / dev / test for both platforms; `data/` local SQLite + future raw data (git-ignored)
- `docs/` decisions, hosting notes

## Troubleshooting
- **Port 8000/5173 in use:** stop the other process, or run uvicorn with `--port 8001` and set `FLOODSENSE_BACKEND_URL=http://127.0.0.1:8001` before `npm run dev`.
- **`/ready` returns 503 "expected revision":** run `python -m app.cli init-db` inside `backend/`.
- **Frontend says "Cannot reach backend":** backend isn't running or is on another port.
- **`npm install` crashes with `edgesOut`:** npm 10.9.x bug with vitest 5 peers; `frontend/.npmrc` already sets `legacy-peer-deps=true`, so use `npm ci`.
- **Python not found on Windows:** try `py -3.12 -m venv backend\.venv` in `setup.ps1`.
