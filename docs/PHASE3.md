# Phase 3 — prediction engine: status

## New
- `app/geo/hydro.py`: sink-filling, D8 flow directions, flow accumulation (pure NumPy; 1.5 M px in a few seconds).
- Cell table gains `depression_depth_m_max` and `flow_acc_log10_m2_max`; cells are now built from every pixel (was every 2nd).
- `app/risk/`: `methodology.py` (all constants + provenance), `rain.py` (IDW, 24 h accumulation), `engine.py` (S, H, R, categories, explanations),
  `evaluation.py` (sensitivity, presence-only back-test).
- API: `/api/risk/methodology`, `/api/risk/summary`, `/api/risk/cells`, `/api/risk/cells/{id}` (all take `?horizon=0..3`).
- CLI: `risk-now`, `risk-sensitivity`, `risk-backtest --hotspots file.csv`.
- UI: risk card on Overview (category bars, horizon selector, experimental/stale flags, error boundary per panel).
- Weather history default raised to 24 h so the IMD-style accumulation can be computed.

## Verified in the sandbox
147 automated checks: 132 backend + 14 frontend (+1 build). Hydrology against analytic cases (plane accumulation = column+1, basin outlet = all
cells, mass conservation, pit depth); risk arithmetic (S x H exact, anchors, monotonicity, boundaries); interpolation; API behaviour for no/short/stale/dry/
heavy rain, horizons, missing or outdated cell table; evaluation functions; full-size performance (build ~6 s, 0.5 GB; compute ~1 ms).
`pip-audit` and `npm audit`: nothing found.

## Bugs found by the tests while building this phase
- Engine produced a hazard from accumulation alone when intensity was unknown (contradicting the documented rule) — fixed.
- A malformed API response could blank the whole page — card validates responses and each panel sits in an error boundary.

## NOT verified
- Behaviour on your real elevation data (new hydrology features): see "what to run" in the README and send me the `cells-summary` output.
- Whether the risk categories look sensible against places you know. This is the main thing to check by eye.
- Any predictive skill. There are no flood labels; the engine is a transparent heuristic.
- Browser rendering; Windows behaviour of the new commands.

## Patch 4 (after first run on a real laptop)
- Observation from the user's screenshot: the risk card sat below the visible area, and with dry weather every cell is correctly "low", so the
  engine appeared to do nothing. Changes: compact status strip, rainfall and risk side by side, and the Demo tab now runs the invented storm through
  the REAL risk engine (`GET /api/demo/risk`), clearly labelled "synthetic rain, real engine". Nothing is stored.
- Timestamps now show local time plus explicit UTC (IST is UTC+5:30, so "hour ending 6:30 pm" was confusing).
- `risk-now` in dry weather lists the highest TERRAIN-susceptibility cells instead of arbitrary zero-score cells.
- Bug caught by a test: the new demo endpoint silently accepted a minute that is not a multiple of the step; now rejected with 422.
- User's real-data results (5,670 cells): sensitivity Spearman mean 0.988 / min 0.939, top-decile overlap mean 0.864 / min 0.727.
  Open concern: the median cell shows a 1.6 m "depression" (p95 5.1 m), probably building artefacts in the surface model; to be tested against a map in Phase 4.
- NOT visually verified by the author (no browser in the sandbox): the new layout.
