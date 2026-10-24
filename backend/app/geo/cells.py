"""Build the per-cell static feature table for the study area (GeoPackage, QGIS-compatible)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.geo.grid import GridPoint, nearest_point
from app.geo.terrain import (FEATURE_DEFS, MIN_SAMPLES, cell_stats, describe_dem, pixel_size_m, read_dem,
                             relative_elevation, slope_degrees)


def cells_for_geometry(geom, resolution: int) -> list[str]:
    """H3 cells whose centres lie inside a shapely Polygon/MultiPolygon (lon/lat order, as in GeoJSON)."""
    import h3
    from shapely.geometry import MultiPolygon, Polygon

    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    out: set[str] = set()
    for p in polys:
        if not isinstance(p, Polygon) or p.is_empty:
            raise ValueError("geometry must be a non-empty Polygon/MultiPolygon")
        ext = [(y, x) for x, y in p.exterior.coords]
        holes = [[(y, x) for x, y in r.coords] for r in p.interiors]
        out.update(h3.polygon_to_cells(h3.LatLngPoly(ext, *holes), resolution))
    return sorted(out)


def build_cells(dem_path: Path, geometry, weather_points: list[GridPoint], resolution: int, out_path: Path) -> dict:
    """Join DEM-derived features to every H3 cell inside `geometry`; write a GeoPackage + feature definitions."""
    import geopandas as gpd
    import h3
    from shapely.geometry import Polygon

    dem, transform = read_dem(dem_path)
    dem_info = describe_dem(dem)
    dx, dy = pixel_size_m(transform, center_lat=transform.f + transform.e * dem.shape[0] / 2)
    stats = cell_stats(dem, slope_degrees(dem, dx, dy), relative_elevation(dem), transform, resolution)

    ids = cells_for_geometry(geometry, resolution)
    if not ids:
        raise ValueError("no H3 cells inside the study geometry")
    df = stats.reindex(ids)
    df["n_samples"] = df["n_samples"].fillna(0).astype(int)
    df["low_coverage"] = df["n_samples"] < MIN_SAMPLES
    # Too few DEM pixels to trust: blank the features (NaN) so downstream code can never silently use them.
    feature_cols = ["elevation_m_mean", "elevation_m_min", "slope_deg_mean", "rel_elev_m_mean"]
    df.loc[df["low_coverage"], feature_cols] = np.nan

    lat_lon = [h3.cell_to_latlng(c) for c in ids]
    near = [nearest_point(la, lo, weather_points) for la, lo in lat_lon]
    df["lat"], df["lon"] = [a for a, _ in lat_lon], [b for _, b in lat_lon]
    df["weather_point_id"] = [p.point_id for p in near]
    k = np.cos(np.radians(df["lat"].to_numpy()))
    df["weather_point_dist_km"] = np.round(111.32 * np.hypot(
        df["lat"].to_numpy() - np.array([p.lat for p in near]),
        (df["lon"].to_numpy() - np.array([p.lon for p in near])) * k), 2)
    df.index.name = "cell_id"
    df = df.reset_index()
    polys = [Polygon([(lo, la) for la, lo in h3.cell_to_boundary(c)]) for c in ids]
    gdf = gpd.GeoDataFrame(df, geometry=polys, crs="EPSG:4326")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG", layer=f"cells_res{resolution}")
    out_path.with_suffix(".features.json").write_text(json.dumps(FEATURE_DEFS, indent=2), encoding="utf-8")
    return {"cells": len(gdf), "low_coverage_cells": int(gdf["low_coverage"].sum()), "dem": dem_info,
            "max_weather_point_dist_km": float(gdf["weather_point_dist_km"].max())}


def summarize_cells(gdf, n_lowest: int = 10) -> dict:
    """Distribution summary of the cell table, for sanity-checking real data before it feeds a risk model."""
    import numpy as np

    out: dict = {"cells": int(len(gdf)), "low_coverage": int(gdf["low_coverage"].sum()), "features": {}}
    for col in ("elevation_m_mean", "slope_deg_mean", "rel_elev_m_mean"):
        v = gdf[col].dropna().to_numpy()
        if v.size:
            p = np.percentile(v, [1, 5, 50, 95, 99])
            out["features"][col] = {"min": float(v.min()), "p1": float(p[0]), "p5": float(p[1]), "median": float(p[2]),
                                    "p95": float(p[3]), "p99": float(p[4]), "max": float(v.max())}
    out["weather_point_dist_km"] = {"median": float(gdf["weather_point_dist_km"].median()), "max": float(gdf["weather_point_dist_km"].max())}
    out["cells_per_weather_point"] = gdf["weather_point_id"].value_counts().sort_index().to_dict()
    low = gdf.dropna(subset=["rel_elev_m_mean"]).nsmallest(n_lowest, "rel_elev_m_mean")
    out["lowest_relative_elevation"] = [
        {"cell_id": r.cell_id, "lat": round(r.lat, 5), "lon": round(r.lon, 5), "rel_elev_m": round(float(r.rel_elev_m_mean), 2),
         "elevation_m": round(float(r.elevation_m_mean), 1)} for r in low.itertuples()]
    return out
