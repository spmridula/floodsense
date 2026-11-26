"""Spatial grids: weather sample points (coarse) and H3 cells (fine). Pure functions, no I/O."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GridPoint:
    point_id: str
    lat: float
    lon: float


def validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    min_lon, min_lat, max_lon, max_lat = bbox
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError(f"invalid bbox {bbox}: expected (min_lon, min_lat, max_lon, max_lat)")


def make_point_id(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def _axis(lo: float, hi: float, step: float) -> list[float]:
    """Evenly spaced values from lo to hi inclusive with spacing <= step. A span no wider than one step gets a
    single value at the centre (every point of the span is then within step/2 of it)."""
    span = hi - lo
    if span <= step + 1e-9:
        return [round((lo + hi) / 2, 4)]
    n = math.ceil(span / step - 1e-9)  # number of intervals
    return [round(lo + i * span / n, 4) for i in range(n + 1)]


def weather_grid(bbox: tuple[float, float, float, float], step_deg: float) -> list[GridPoint]:
    """Sample points covering the bbox: both edges included, all points inside the box, spacing <= step_deg."""
    validate_bbox(bbox)
    if step_deg <= 0:
        raise ValueError("step_deg must be positive")
    min_lon, min_lat, max_lon, max_lat = bbox
    return [GridPoint(make_point_id(la, lo), la, lo)
            for la in _axis(min_lat, max_lat, step_deg) for lo in _axis(min_lon, max_lon, step_deg)]


def nearest_point(lat: float, lon: float, points: list[GridPoint]) -> GridPoint:
    """Nearest sample point (equirectangular distance; adequate at city scale)."""
    if not points:
        raise ValueError("no grid points")
    k = np.cos(np.radians(lat))
    d2 = [((p.lat - lat) ** 2 + ((p.lon - lon) * k) ** 2) for p in points]
    return points[int(np.argmin(d2))]


def h3_cells_for_polygon(exterior_latlon: list[tuple[float, float]], resolution: int,
                         holes: list[list[tuple[float, float]]] | None = None) -> list[str]:
    """H3 cells whose centres fall inside the polygon. Coordinates are (lat, lon)."""
    import h3  # local import: geo extras are optional for the base API

    if len(exterior_latlon) < 3:
        raise ValueError("polygon needs at least 3 vertices")
    poly = h3.LatLngPoly(exterior_latlon, *(holes or []))
    return sorted(h3.polygon_to_cells(poly, resolution))


def cell_centroid(cell: str) -> tuple[float, float]:
    import h3
    return h3.cell_to_latlng(cell)
