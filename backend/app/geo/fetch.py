"""Downloaders for static layers. Network calls are isolated in small functions; logic around them is pure/testable.

These hit external hosts (AWS S3, Nominatim, Overpass) and are meant to be run once on the developer's machine.
"""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import httpx

DEM_LICENCE = "Copernicus DEM licence (free for general public; attribute ESA/Copernicus) - see registry.opendata.aws/copernicus-dem"
OSM_LICENCE = "ODbL 1.0 - (c) OpenStreetMap contributors"


class FetchError(Exception):
    """User-facing failure message."""


# ---------- Copernicus DEM ----------
def dem_tile_names(bbox: tuple[float, float, float, float], resolution_m: int = 30) -> list[str]:
    """Tile ids covering bbox. Tiles are named by their lower-left integer corner, e.g. ..._N17_00_E078_00_DEM.
    Naming for 30 m verified from provider forum; the '_30_' prefix for the 90 m product is inferred, NOT verified."""
    if resolution_m not in (30, 90):
        raise ValueError("resolution_m must be 30 or 90")
    min_lon, min_lat, max_lon, max_lat = bbox
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ValueError("invalid bbox")
    prefix = "10" if resolution_m == 30 else "30"
    eps = 1e-9
    names = []
    for lat in range(math.floor(min_lat), math.floor(max_lat - eps) + 1):
        for lon in range(math.floor(min_lon), math.floor(max_lon - eps) + 1):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            names.append(f"Copernicus_DSM_COG_{prefix}_{ns}_00_{ew}_00_DEM")
    return names


def dem_tile_url(name: str, resolution_m: int = 30) -> str:
    bucket = "copernicus-dem-30m" if resolution_m == 30 else "copernicus-dem-90m"
    return f"https://{bucket}.s3.amazonaws.com/{name}/{name}.tif"


def download_file(url: str, dest: Path, transport: httpx.BaseTransport | None = None, timeout: float = 120.0) -> Path:
    """Stream to a temp file then rename, so an interrupted download never leaves a half file at `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True) as http:
            with http.stream("GET", url) as r:
                if r.status_code in (403, 404):
                    raise FetchError(f"{url} -> HTTP {r.status_code}. The tile may not exist or may not be publicly released "
                                     "(some countries' tiles are withheld from the public GLO-30 set).")
                if r.status_code != 200:
                    raise FetchError(f"{url} -> HTTP {r.status_code}")
                fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
                try:
                    with os.fdopen(fd, "wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
    except httpx.HTTPError as exc:
        raise FetchError(f"network error downloading {url}: {type(exc).__name__}. Check your internet connection.") from exc
    if dest.stat().st_size == 0:
        dest.unlink()
        raise FetchError(f"{url} returned an empty file")
    return dest


def fetch_dem(bbox, out_path: Path, resolution_m: int = 30, tiles_dir: Path | None = None,
              transport: httpx.BaseTransport | None = None) -> dict:
    """Download tile(s), mosaic, clip to bbox (+small margin), write one GeoTIFF."""
    import rasterio
    from rasterio.merge import merge

    tiles_dir = tiles_dir or out_path.parent / "tiles"
    paths = []
    for name in dem_tile_names(bbox, resolution_m):
        paths.append(download_file(dem_tile_url(name, resolution_m), tiles_dir / f"{name}.tif", transport))
    margin = 0.01
    bounds = (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)
    srcs = [rasterio.open(p) for p in paths]
    try:
        mosaic, transform = merge(srcs, bounds=bounds)
        profile = srcs[0].profile.copy()
        profile.update(driver="GTiff", height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
                       count=1, compress="deflate", tiled=False, blockxsize=None, blockysize=None)
        profile.pop("blockxsize", None); profile.pop("blockysize", None)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(mosaic[0], 1)
    finally:
        for s in srcs:
            s.close()
    return {"tiles": [p.name for p in paths], "resolution_m": resolution_m, "bounds": bounds}


# ---------- Boundary and roads (OpenStreetMap) ----------
def check_boundary(gdf, min_km2: float = 100.0, max_km2: float = 5000.0) -> dict:
    """Validate a boundary GeoDataFrame. Returns area/bounds and warnings; raises FetchError if unusable."""
    if gdf is None or len(gdf) == 0:
        raise FetchError("boundary query returned nothing")
    geom = gdf.geometry.iloc[0]
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise FetchError(f"boundary is a {geom.geom_type}, expected Polygon/MultiPolygon")
    if not geom.is_valid:
        geom = geom.buffer(0)
        if not geom.is_valid or geom.is_empty:
            raise FetchError("boundary geometry is invalid and could not be repaired")
    area_km2 = float(gdf.iloc[[0]].set_geometry([geom], crs=gdf.crs).to_crs(gdf.estimate_utm_crs()).area.iloc[0] / 1e6)
    warnings = []
    if not (min_km2 <= area_km2 <= max_km2):
        warnings.append(f"area {area_km2:.0f} km2 is outside the plausible {min_km2:.0f}-{max_km2:.0f} km2 range - inspect it in QGIS")
    return {"area_km2": round(area_km2, 1), "bounds": tuple(round(b, 4) for b in geom.bounds), "warnings": warnings, "geometry": geom}


def fetch_boundary(query: str, out_path: Path) -> dict:
    import osmnx as ox

    try:
        gdf = ox.geocode_to_gdf(query)
    except Exception as exc:  # noqa: BLE001 - osmnx raises several types; surface one clear message
        raise FetchError(f"could not geocode {query!r}: {type(exc).__name__}: {exc}") from exc
    info = check_boundary(gdf)
    out = gdf.iloc[[0]].set_geometry([info["geometry"]], crs=gdf.crs)[["geometry"]]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(out_path, driver="GeoJSON")
    return {k: v for k, v in info.items() if k != "geometry"} | {"query": query}


def graph_quality(n_nodes: int, n_edges: int, largest_component_nodes: int) -> dict:
    if n_nodes == 0 or n_edges == 0:
        raise FetchError("road graph is empty")
    frac = largest_component_nodes / n_nodes
    warnings = [] if frac >= 0.9 else [f"only {frac:.0%} of nodes are in the largest connected component; routing may hit unreachable pockets"]
    return {"nodes": n_nodes, "edges": n_edges, "largest_component_fraction": round(frac, 4), "warnings": warnings}


def fetch_roads(geometry, out_path: Path) -> dict:
    import networkx as nx
    import osmnx as ox

    try:
        G = ox.graph_from_polygon(geometry, network_type="drive", simplify=True)
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"OSM road download failed: {type(exc).__name__}: {exc}. Overpass can time out on big areas; retry later.") from exc
    largest = max((len(c) for c in nx.weakly_connected_components(G)), default=0)
    q = graph_quality(G.number_of_nodes(), G.number_of_edges(), largest)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ox.io.save_graph_geopackage(G, filepath=out_path)
    return q
