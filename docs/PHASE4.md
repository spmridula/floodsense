# Phase 4 — interactive map: status

## New
- `/map` page (MapLibre GL 6.15.0): hexagon cells coloured by risk category or any terrain layer (susceptibility, depression depth, relative height,
  upslope area, elevation); legend with danger end labelled; hover tooltips; click a cell for the full traceable explanation; selected-cell highlight;
  zoom/scale controls; data-freshness chip; stale/unreliable and EXPERIMENTAL-forecast flags; basemap attribution.
- Live / Demo toggle: Demo drives the real risk engine with an invented storm, per cell, under a "SYNTHETIC" banner (`/api/demo/risk/cells`).
- Water mask: `fetch-water` (OSM lake/reservoir/riverbank polygons) + `build-cells` adds `water_fraction`; cells >= 50% water are drawn as water, excluded
  from percentile ranks and never scored (previously a lake could have been coloured "critical").
- "Spots you know flood": click the map to save a spot to `data/hotspots.csv` (validated, deduplicated per cell, spreadsheet-injection-safe);
  `risk-backtest` uses this file by default.
- API: `/api/cells/geojson` (ETag + gzip), `/api/hotspots` (GET/POST/DELETE), `/api/demo/risk/cells`.
- Containment: map and each panel sit in error boundaries; WebGL failure shows a readable message instead of a blank page.

## Verified in the sandbox
- 156 backend tests, 44 frontend tests, typecheck, production build, `pip-audit`, `npm audit` (0 findings).
- Colour expressions are evaluated with MapLibre's own expression engine (`@maplibre/maplibre-gl-style-spec`): every category, water, unscored and
  malformed-feature case yields the intended colour, and the complete style (sources + layers) passes MapLibre's style validator.
- That check found a real defect: a feature missing the `is_water` property rendered BLACK (expression error). Now null-safe.
- Water-mask maths (half-covered cell = 50%), exclusion of lakes from percentile ranks, GeoJSON structure/ETag, hotspot CRUD and validation.
- Dependency choice: maplibre-gl 6.15.0 (20 days old) rather than the 6.17.0 published the same day. 6.x has no default export; code uses named imports (typechecked).

## NOT verified
- **Actual rendering in a browser.** The sandbox has no browser/WebGL; the map component is tested against a recording fake of MapLibre.
  Things only a real browser can confirm: tiles load, hexagons appear and align with streets, click/hover feel, mark-mode cursor, mobile layout.
- OpenStreetMap public tiles are used for development; their usage policy discourages heavy/production use. Choose a tile provider before deploying (Phase 8).
- The water layer on real Hyderabad data (polygon count, whether the big lakes are fully captured).
- Whether building clusters are what makes the "depression depth" feature unreliable (user confirmed building clusters, a road and a lake among the
  lowest cells). Building footprints are not yet used; planned next if the map confirms it.
