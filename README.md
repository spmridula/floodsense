# FloodSense — Urban Flood Early Warning & Safe Routing (Hyderabad)

> **Advisory student project. Not an official warning system.** Follow instructions from GHMC, HYDRAA, police and emergency services.

**Current status: Phase 4 (interactive map) complete.** Live modelled rainfall, synthetic demo mode, terrain/hydrology features, and a transparent
risk index (uncalibrated, relative; **not** a probability), and an interactive map at `/map`. **No routing yet** (Phase 5).
See `docs/RISK_METHODOLOGY.md`, `docs/PHASE3.md`, `docs/PHASE4.md` (verified vs not).

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

## Phase 2: loading real data (run once, on your laptop)
Run from the `backend` folder with the venv Python (`.venv\Scripts\python.exe` on Windows, `.venv/bin/python` elsewhere):
```
python -m app.cli weather-refresh   # live Open-Meteo fetch; also tests your connection
python -m app.cli fetch-boundary    # OSM polygon for Hyderabad; prints area + a suggested FLOODSENSE_STUDY_AREA_BBOX
python -m app.cli fetch-dem         # Copernicus GLO-30 elevation tile(s) from AWS (tens of MB)
python -m app.cli fetch-roads       # OSM drivable network (can take many minutes for the whole city)
python -m app.cli build-cells       # H3 cell table: elevation, slope, low-lying proxy (GeoPackage for QGIS)
python -m app.cli cells-summary     # distributions + the 10 lowest cells (sanity-check against places you know)
python -m app.cli status            # what exists
```
Inspect `fetch-boundary` output first: if the area looks wrong, tell me before downloading roads. Each step records a SHA-256,
source URL, licence and time in `data/manifest.json` and marks the source "verified" on the Data sources page.
While the backend runs with `FLOODSENSE_WEATHER_AUTOREFRESH=true` it refreshes weather every 15 min (never faster than 5 min).

## Phase 3: computing risk (after the Phase 2 downloads)
Re-run these two once after updating (they pick up the new terrain features and 24 h of rainfall history):
```
python -m app.cli build-cells        # now also computes depression depth + flow accumulation (about a minute)
python -m app.cli weather-refresh    # wait 5 min after a previous refresh
python -m app.cli risk-now           # category counts + top cells (works offline from stored data)
python -m app.cli cells-summary      # includes the new features
python -m app.cli risk-sensitivity   # how much the ranking depends on the weights
python -m app.cli risk-backtest --hotspots my_points.csv    # optional: CSV with lat,lon of known waterlogging spots
```
API docs for the new endpoints: http://localhost:8000/docs (section "risk").

## Phase 4: the map
After updating (frontend gets a new dependency, so run `npm ci` in `frontend`):
```
python -m app.cli fetch-water      # lake/reservoir polygons from OpenStreetMap (small download)
python -m app.cli build-cells      # re-run: adds water_fraction; water cells are no longer scored
```
Restart the backend, then open http://localhost:5173/map. Use "Mark a spot on the map" to record places you know flood, then run
`python -m app.cli risk-backtest` (no file needed) to compare them with the terrain ranking.

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
- **`fetch-*` says geospatial packages are missing:** `pip install -r backend/requirements-geo.txt` (rasterio/geopandas wheels need a 64-bit Python 3.11-3.12).
- **DEM download 403/404:** the tile may not be publicly released; try `fetch-dem --resolution 90` and tell me what happens.
- **Python not found on Windows:** try `py -3.12 -m venv backend\.venv` in `setup.ps1`.
