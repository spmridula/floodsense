"""Command-line helpers (run from the backend/ folder):  python -m app.cli <command>"""
import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import get_engine, run_migrations, seed_data_sources

GEO_HINT = "Geospatial packages missing. Run: pip install -r requirements-geo.txt  (setup scripts do this)"


def _session():
    return sessionmaker(bind=get_engine(get_settings().database_url))()


def init_db() -> None:
    settings = get_settings()
    run_migrations(settings.database_url)
    with _session() as session:
        added = seed_data_sources(session)
    print(f"Database ready ({settings.database_url.split('///')[0]}). Seeded {added} new data source rows.")


def _paths():
    d = get_settings().data_dir
    return {"raw": d / "raw", "processed": d / "processed", "manifest": d / "manifest.json", "base": d}


def _record(name, path, url, licence, extra, source_key):
    from app.geo.provenance import mark_source_verified, record_artifact
    p = _paths()
    record_artifact(p["manifest"], name, path, url, licence, extra, base_dir=p["base"])
    with _session() as s:
        mark_source_verified(s, source_key)
    print(f"  recorded in {p['manifest'].name}; data-source '{source_key}' marked verified")


def cmd_weather_refresh() -> int:
    from app.ingest.weather import OpenMeteoClient
    from app.routers.weather import get_client
    from app.services.weather_service import refresh_weather, snapshot
    from app.geo.provenance import mark_source_verified
    s = get_settings()
    with _session() as session:
        out = refresh_weather(session, get_client(s), s)
        print(f"{out.status}: {out.message}")
        if out.status == "updated":
            mark_source_verified(session, "open_meteo")
        snap = snapshot(session, s)
        print(json.dumps({k: snap[k] for k in ("freshness", "fetched_at", "latest_valid_time", "summary")}, default=str, indent=2))
    return 0 if out.status != "failed" else 1


def cmd_fetch_boundary(query: str) -> int:
    from app.geo.fetch import OSM_LICENCE, FetchError, fetch_boundary
    p = _paths()
    out = p["raw"] / "boundary" / "boundary.geojson"
    try:
        info = fetch_boundary(query, out)
    except FetchError as exc:
        print(f"FAILED: {exc}"); return 1
    print(f"Boundary saved: area {info['area_km2']} km2, bounds {info['bounds']}")
    for w in info["warnings"]:
        print(f"  WARNING: {w}")
    minx, miny, maxx, maxy = info["bounds"]
    print(f"  To cover it with weather points set:  FLOODSENSE_STUDY_AREA_BBOX=[{minx},{miny},{maxx},{maxy}]  in .env")
    _record("boundary", out, "https://nominatim.openstreetmap.org/", OSM_LICENCE, info, "osm_boundary")
    return 0


def _geometry():
    """Boundary polygon if fetched, otherwise the approximate bbox (with a loud note)."""
    import geopandas as gpd
    from shapely.geometry import box
    f = _paths()["raw"] / "boundary" / "boundary.geojson"
    if f.exists():
        return gpd.read_file(f).geometry.iloc[0], "boundary.geojson"
    print("  NOTE: no boundary.geojson - using the APPROXIMATE bounding box. Run fetch-boundary for the real polygon.")
    return box(*get_settings().study_area_bbox), "approximate bbox"


def cmd_fetch_dem(resolution: int) -> int:
    from app.geo.fetch import DEM_LICENCE, FetchError, fetch_dem
    from app.geo.terrain import describe_dem, read_dem
    geom, _ = _geometry()
    out = _paths()["raw"] / "dem" / f"dem_cop{resolution}.tif"
    try:
        info = fetch_dem(geom.bounds, out, resolution)
    except FetchError as exc:
        print(f"FAILED: {exc}"); return 1
    dem, _t = read_dem(out)
    desc = describe_dem(dem)
    print(f"DEM saved: {desc}")
    _record(f"dem_cop{resolution}", out, "https://registry.opendata.aws/copernicus-dem/", DEM_LICENCE, info | {"stats": desc}, "copernicus_dem")
    return 0


def cmd_fetch_roads() -> int:
    from app.geo.fetch import OSM_LICENCE, FetchError, fetch_roads
    geom, src = _geometry()
    out = _paths()["raw"] / "roads" / "roads.gpkg"
    print(f"Downloading drivable roads for {src} (large areas can take many minutes)...")
    try:
        q = fetch_roads(geom, out)
    except FetchError as exc:
        print(f"FAILED: {exc}"); return 1
    print(f"Road graph: {q}")
    _record("roads", out, "https://www.openstreetmap.org/", OSM_LICENCE, q, "osm_roads")
    return 0


def cmd_fetch_water() -> int:
    from app.geo.water import OSM_LICENCE, FetchError, fetch_water
    geom, src = _geometry()
    out = _paths()["raw"] / "water" / "water.gpkg"
    print(f"Downloading water polygons for {src}...")
    try:
        info = fetch_water(geom, out)
    except FetchError as exc:
        print(f"FAILED: {exc}"); return 1
    print(f"Water layer: {info}")
    from app.geo.provenance import record_artifact
    p = _paths()
    record_artifact(p["manifest"], "water", out, "https://www.openstreetmap.org/", OSM_LICENCE, info, base_dir=p["base"])
    return 0


def cmd_build_cells(resolution: int) -> int:
    from app.geo.cells import build_cells
    from app.geo.grid import weather_grid
    from app.geo.provenance import record_artifact
    s, p = get_settings(), _paths()
    dem = next(iter(sorted((p["raw"] / "dem").glob("dem_cop*.tif"))), None) if (p["raw"] / "dem").exists() else None
    if dem is None:
        print("FAILED: no DEM found. Run fetch-dem first."); return 1
    geom, src = _geometry()
    out = p["processed"] / f"cells_res{resolution}.gpkg"
    wfile = p["raw"] / "water" / "water.gpkg"
    water = None
    if wfile.exists():
        from app.geo.water import load_water_union
        water = load_water_union(wfile)
    else:
        print("  NOTE: no water layer - lakes/reservoirs will NOT be masked. Run fetch-water, then build-cells again.")
    info = build_cells(dem, geom, weather_grid(s.study_area_bbox, s.weather_grid_step_deg), resolution, out, water)
    print(f"Built {info['cells']} cells from {src} ({info['low_coverage_cells']} low-coverage)"
          + (f"; {info['water_cells']} water-body cells excluded from scoring." if info["water_masked"] else "."))
    if info["max_weather_point_dist_km"] > 111 * s.weather_grid_step_deg:
        print(f"  WARNING: some cells are {info['max_weather_point_dist_km']} km from the nearest weather point - "
              "the weather grid does not cover the study geometry. Update FLOODSENSE_STUDY_AREA_BBOX.")
    record_artifact(p["manifest"], f"cells_res{resolution}", out, "derived: DEM + boundary", "derived from Copernicus DEM and OSM (see their licences)", info, base_dir=p["base"])
    return 0


def cmd_cells_summary(resolution: int) -> int:
    import geopandas as gpd
    from app.geo.cells import summarize_cells
    f = _paths()["processed"] / f"cells_res{resolution}.gpkg"
    if not f.exists():
        print(f"FAILED: {f} not found. Run build-cells first."); return 1
    info = summarize_cells(gpd.read_file(f))
    print(f"Cells: {info['cells']}  (low coverage: {info['low_coverage']})")
    print("\nFeature distributions (cell means):")
    for k, d in info["features"].items():
        print(f"  {k:18s} min {d['min']:8.2f} | p1 {d['p1']:8.2f} | p5 {d['p5']:8.2f} | median {d['median']:8.2f} | p95 {d['p95']:8.2f} | p99 {d['p99']:8.2f} | max {d['max']:8.2f}")
    w = info["weather_point_dist_km"]
    print(f"\nDistance to nearest weather point: median {w['median']:.1f} km, max {w['max']:.1f} km")
    print("Cells per weather point:", info["cells_per_weather_point"])
    print("\n10 cells lowest relative to their ~1 km surroundings (check these on a map against places you know):")
    for r in info["lowest_relative_elevation"]:
        print(f"  {r['rel_elev_m']:7.2f} m rel | {r['elevation_m']:6.1f} m abs | lat {r['lat']}, lon {r['lon']}  https://www.google.com/maps?q={r['lat']},{r['lon']}")
    return 0


def cmd_risk_now(horizon: int) -> int:
    from app.risk.engine import CellTableError
    from app.services import risk_service as rs
    s = get_settings()
    try:
        with _session() as session:
            r = rs.run(session, s, horizon)
    except (CellTableError, ValueError) as exc:
        print(f"FAILED: {exc}"); return 1
    m = r.meta
    print(f"Model {m['model_version']} | horizon +{horizon}h ({m['horizon_status']}) | data {m['data_freshness']} | reliable={m.get('reliable')}")
    print(f"Observation hour: {m['observation_time']} | target: {m.get('target_time')}")
    for w in m.get("warnings", []):
        print(f"  WARNING: {w}")
    if r.result is None:
        print("No scores (rainfall unavailable)."); return 0
    print("Category counts:", r.result["category"].value_counts(dropna=False).to_dict())
    print("Rain mm/h over cells: min %.2f  max %.2f" % (r.result["rain_mm_per_h"].min(), r.result["rain_mm_per_h"].max()))
    dry = float(r.result["score"].max()) == 0.0
    top = r.result.nlargest(10, "susceptibility" if dry else "score")
    if dry:
        print("No rain: every score is 0 (the index is rain-triggered). Showing the 10 cells with the highest TERRAIN susceptibility instead:")
    else:
        print("Top 10 cells by index (score is NOT a probability):")
    for t in top.itertuples():
        print(f"  {t.score:.3f} {t.category:9s} S={t.susceptibility:.2f} H={t.hazard:.2f}  {t.lat:.5f},{t.lon:.5f}")
    return 0


def cmd_risk_sensitivity(n: int, perturb: float) -> int:
    from app.risk.engine import CellTableError, load_cell_table
    from app.risk.evaluation import sensitivity
    try:
        table = load_cell_table(get_settings().cells_path)
    except CellTableError as exc:
        print(f"FAILED: {exc}"); return 1
    r = sensitivity(table, n=n, perturb=perturb)
    print(json.dumps(r, indent=2))
    print("Reading: Spearman near 1 and a high top-decile overlap mean the ranking does not hinge on the exact weights.")
    return 0


def cmd_risk_backtest(path: str | None) -> int:
    from app.risk.engine import CellTableError, load_cell_table
    from app.risk.evaluation import backtest, load_hotspots_csv
    path = path or str(get_settings().data_dir / "hotspots.csv")
    try:
        table = load_cell_table(get_settings().cells_path)
        res = backtest(table, load_hotspots_csv(Path(path)), get_settings().cells_resolution)
    except (CellTableError, ValueError, OSError) as exc:
        print(f"FAILED: {exc}"); return 1
    print(json.dumps(res, indent=2))
    return 0


def cmd_status() -> int:
    p = _paths()
    for label, path in [("boundary", p["raw"] / "boundary" / "boundary.geojson"), ("dem", p["raw"] / "dem"),
                        ("roads", p["raw"] / "roads" / "roads.gpkg"), ("cells", p["processed"]), ("manifest", p["manifest"])]:
        print(f"{label:9s} {'present' if path.exists() else 'MISSING'}  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="floodsense")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("weather-refresh", help="fetch Open-Meteo now (also a connectivity check)")
    b = sub.add_parser("fetch-boundary"); b.add_argument("--query", default="Hyderabad, Telangana, India")
    d = sub.add_parser("fetch-dem"); d.add_argument("--resolution", type=int, choices=[30, 90], default=30)
    sub.add_parser("fetch-roads")
    sub.add_parser("fetch-water", help="OSM lake/reservoir/riverbank polygons (used to mask water cells)")
    c = sub.add_parser("build-cells"); c.add_argument("--resolution", type=int, default=9)
    cs = sub.add_parser("cells-summary", help="print distributions and the lowest cells of the built cell table")
    cs.add_argument("--resolution", type=int, default=9)
    rn = sub.add_parser("risk-now", help="compute current risk from stored weather and the cell table")
    rn.add_argument("--horizon", type=int, default=0)
    rs_ = sub.add_parser("risk-sensitivity", help="how stable is the ranking if the weights change?")
    rs_.add_argument("--trials", type=int, default=200); rs_.add_argument("--perturb", type=float, default=0.5)
    rb = sub.add_parser("risk-backtest", help="compare terrain susceptibility with a CSV of known waterlogging points (lat,lon)")
    rb.add_argument("--hotspots", default=None, help="CSV with lat,lon (default: the spots you marked on the map, data/hotspots.csv)")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        if a.command == "init-db":
            init_db(); return 0
        if a.command == "weather-refresh": return cmd_weather_refresh()
        if a.command == "fetch-boundary": return cmd_fetch_boundary(a.query)
        if a.command == "fetch-dem": return cmd_fetch_dem(a.resolution)
        if a.command == "fetch-roads": return cmd_fetch_roads()
        if a.command == "fetch-water": return cmd_fetch_water()
        if a.command == "build-cells": return cmd_build_cells(a.resolution)
        if a.command == "cells-summary": return cmd_cells_summary(a.resolution)
        if a.command == "risk-now": return cmd_risk_now(a.horizon)
        if a.command == "risk-sensitivity": return cmd_risk_sensitivity(a.trials, a.perturb)
        if a.command == "risk-backtest": return cmd_risk_backtest(a.hotspots)
        if a.command == "status": return cmd_status()
    except ImportError as exc:
        print(f"{GEO_HINT}\n({exc})"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
