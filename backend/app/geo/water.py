"""Water-body mask from OpenStreetMap polygons (lakes, reservoirs, riverbanks)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.geo.fetch import FetchError, OSM_LICENCE  # noqa: F401  (OSM_LICENCE re-exported for the CLI)

WATER_TAGS = {"natural": "water", "waterway": "riverbank", "landuse": "reservoir"}


def fetch_water(geometry, out_path: Path) -> dict:
    import osmnx as ox

    try:
        gdf = ox.features_from_polygon(geometry, WATER_TAGS)
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"OSM water download failed: {type(exc).__name__}: {exc}. Overpass may be busy; retry later.") from exc
    gdf = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])][["geometry"]].reset_index(drop=True)
    if gdf.empty:
        raise FetchError("no water polygons found in the study area (unexpected for Hyderabad); check the boundary")
    area_km2 = float(gdf.to_crs(gdf.estimate_utm_crs()).area.sum() / 1e6)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG", layer="water")
    return {"polygons": int(len(gdf)), "water_area_km2": round(area_km2, 2)}


def load_water_union(path: Path):
    import geopandas as gpd
    import shapely

    gdf = gpd.read_file(path)
    geom = shapely.union_all(shapely.make_valid(gdf.geometry.to_numpy()))
    if geom.is_empty:
        raise ValueError("water layer is empty")
    return geom


def water_fraction(cell_polys, water_geom) -> np.ndarray:
    """Fraction (0..1) of each cell polygon covered by water. Degree-area ratios (fine at cell scale)."""
    import shapely

    geoms = np.asarray(list(cell_polys), dtype=object)
    frac = np.zeros(len(geoms))
    if len(geoms) == 0:
        return frac
    shapely.prepare(water_geom)
    hit = shapely.intersects(geoms, water_geom)
    if hit.any():
        inter = shapely.intersection(geoms[hit], water_geom)
        frac[hit] = shapely.area(inter) / shapely.area(geoms[hit])
    return np.clip(frac, 0.0, 1.0)
