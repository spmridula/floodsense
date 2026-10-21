# Decisions and honest limitations (as of Phase 1)

1. **No ML flood classifier.** No geocoded, timestamped flood-event labels were found for Hyderabad (only news-reported hotspot counts). Core engine will be a transparent rule-based risk index; its score is never a calibrated probability.
2. **Whole-Hyderabad scope** (user choice). Study-area bbox is an approximate rectangle until the official GHMC boundary is ingested (Phase 2). Spatial unit: H3 cells; whole-city OSM graph is large, so it is precomputed offline and loaded read-only.
3. **Data register** lives in `backend/app/data_sources.py` and the `data_sources` table. Nothing is marked `verified` until code has actually downloaded/queried it.
4. **Frontend dev toolchain** uses vite 7 / vitest 5 (older lines had advisories). Requires `legacy-peer-deps` due to an npm 10.9 resolver crash. `npm audit`: 0 vulnerabilities; `pip-audit`: none found (both run 2026-10-21).
5. **Database:** SQLite + Alembic locally. PostgreSQL/PostGIS only if Phase 4-5 spatial queries need it.

# Hosting recommendation (to re-verify in Phase 8)
Whole-city road graph + DEM-derived layers need more memory than typical free tiers (often ~512 MB, with sleeping and no persistent disk — verify current terms). Recommended: a small VPS (about 2 vCPU / 2-4 GB RAM, a few USD/month) running Docker Compose behind Caddy (automatic HTTPS), with precomputed data baked into the image or a mounted volume. Free-tier PaaS (e.g. Render) is a fallback for a reduced demo. Prices and limits change — check provider pages before choosing. Nothing is deployed yet.
