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
    info = build_cells(dem, geom, weather_grid(s.study_area_bbox, s.weather_grid_step_deg), resolution, out)
    print(f"Built {info['cells']} cells from {src} ({info['low_coverage_cells']} low-coverage).")
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
    c = sub.add_parser("build-cells"); c.add_argument("--resolution", type=int, default=9)
    cs = sub.add_parser("cells-summary", help="print distributions and the lowest cells of the built cell table")
    cs.add_argument("--resolution", type=int, default=9)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        if a.command == "init-db":
            init_db(); return 0
        if a.command == "weather-refresh": return cmd_weather_refresh()
        if a.command == "fetch-boundary": return cmd_fetch_boundary(a.query)
        if a.command == "fetch-dem": return cmd_fetch_dem(a.resolution)
        if a.command == "fetch-roads": return cmd_fetch_roads()
        if a.command == "build-cells": return cmd_build_cells(a.resolution)
        if a.command == "cells-summary": return cmd_cells_summary(a.resolution)
        if a.command == "status": return cmd_status()
    except ImportError as exc:
        print(f"{GEO_HINT}\n({exc})"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
