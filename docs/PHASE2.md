# Phase 2 — data pipeline: what is verified and what is not

## Verified in the development sandbox (Linux, Python 3.12)
- 86 backend tests pass; 9 frontend tests pass; production build succeeds.
- Weather client: success, single/multi-location payloads, timeout + backoff, 429/5xx retry, 4xx no-retry, invalid JSON, wrong units,
  negative/NaN/absurd/duplicate/missing values, location-count mismatch — all against **mocked HTTP** (no real Open-Meteo traffic).
- Service: storage, idempotent upsert (no duplicate hours), 5-minute upstream cooldown, failed refresh keeps old data and records the error,
  freshness classification, separation of valid_time / fetched_at, forecast-vs-past flag.
- Real failure path: with the network blocked, the CLI and API report failure and show `unavailable` — no fabricated values.
- Terrain math checked against analytic answers (plane slope = atan(1/30) = 1.909 deg; pit depth hand-calculated); nodata → NaN; thin-coverage cells blanked.
- H3 cell generation, DEM → cell aggregation, GeoPackage output, provenance hashing, DEM tile naming, download atomicity — on synthetic data.

## Verified by the user on Windows (2026-10-21)
- `weather-refresh`: live Open-Meteo call succeeded; 225 readings = 25 points x 9 hours (6 past + 3 forecast), values plausible (mean 0.14, max 1.0 mm/h).
  This confirms the request parameters, the multi-location response shape and the mm unit.
- `fetch-boundary`: OSM returned a 609.6 km2 polygon, bounds (78.2387, 17.2916, 78.6224, 17.5608). Shape not yet inspected visually; official extent not verified.

## Patch 1 (found while reviewing the user's output)
- Weather grid now spans the box edge-to-edge with spacing <= step (previously the far edge was missed for boxes not divisible by the step).
- Changing the study area/grid no longer mixes in old points and no longer hits the 5-minute cooldown; the UI explains when stored data belongs to another grid.

## NOT verified (needs your laptop)
- ~~Any live call to Open-Meteo~~ (now verified, see above). Still unconfirmed: hourly `precipitation` = sum of the preceding hour in mm (documented); `past_hours`/`forecast_hours` accepted (documented);
  each location in a multi-location call counts as one API call (assumed). Budget: 25 points x 96 refreshes = 2,400 calls/day at the default; the
  documented free limit is under 10,000/day. A bigger box raises this (72 points = 6,912/day).
- **DEM and road downloads** (AWS S3, Overpass); the boundary download is now verified. Code and error handling are tested with mocks only.
- **DEM tile availability for India.** The public GLO-30 set withholds some countries' tiles; whether the N17/E078 tile is present is untested.
  90 m fallback naming is inferred, not verified.
- **Windows/macOS installs** of the geospatial wheels at the pinned versions, and the PowerShell scripts.
- Browser rendering of the new UI (tested with jsdom only).

## Data-honesty rules enforced in code
- Open-Meteo values are labelled `live_forecast` ("modelled, not a rain-gauge observation"). Nothing is labelled `live_observation`.
- Demo scenarios live in a separate module/endpoint, never touch the weather table, and every response carries `synthetic_demo` + a disclaimer.
- Missing/failed data is `unavailable`/NaN, never zero-filled or interpolated silently.
- DEM is a surface model (buildings/trees included); every terrain feature is documented as derived/proxy in `FEATURE_DEFS`.

## Known limitations carried forward
- Hourly 3-hour forecast resolution is coarse for a 30-60 min horizon; a 15-minute product exists in the API but its quality for India is unchecked.
- No historical-event replay yet (needs the Open-Meteo archive API; synthetic scenarios only for now).
- Flow accumulation is deferred to Phase 3 (needs depression filling on the full DEM).
- Study box is still an approximate rectangle until you run `fetch-boundary`.
