"""DEM-derived terrain features.

IMPORTANT: Copernicus GLO-30 is a DIGITAL SURFACE model (includes buildings and trees). Every feature here is
derived from that surface, and is a susceptibility PROXY, not a measurement of where water will flow.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

FEATURE_DEFS = {
    "elevation_m_mean": {"kind": "derived_from_dem", "unit": "m", "limitation": "Surface elevation (buildings/trees included), ~30 m grid"},
    "elevation_m_min": {"kind": "derived_from_dem", "unit": "m", "limitation": "Lowest sampled pixel in the cell; noise-sensitive"},
    "slope_deg_mean": {"kind": "derived_from_dem", "unit": "deg", "limitation": "Slope of the surface model; building edges inflate it"},
    "rel_elev_m_mean": {"kind": "proxy", "unit": "m", "limitation": "Cell elevation minus ~1 km neighbourhood mean; negative = lower than surroundings. A low-lying proxy, not drainage."},
    "depression_depth_m_max": {"kind": "proxy", "unit": "m", "limitation": "Depth of the deepest closed depression in the cell after filling a SURFACE model; buildings create spurious pits and real drains/culverts are invisible"},
    "flow_acc_log10_m2_max": {"kind": "proxy", "unit": "log10(m2)", "limitation": "Largest D8 upslope area in the cell on a surface model; shows where surface water would concentrate, ignores storm drains"},
    "n_samples": {"kind": "quality", "unit": "count", "limitation": "DEM pixels sampled in the cell"},
}
MIN_SAMPLES = 5  # cells with fewer samples are flagged low_coverage


def pixel_size_m(transform, center_lat: float) -> tuple[float, float]:
    """Approximate pixel width/height in metres for a geographic (EPSG:4326) raster."""
    dx = abs(transform.a) * 111_320.0 * math.cos(math.radians(center_lat))
    dy = abs(transform.e) * 110_540.0
    return dx, dy


def read_dem(path: Path):
    """Return (array float32 with NaN for nodata, affine transform). Rejects non-geographic or rotated rasters."""
    import rasterio

    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"DEM must be EPSG:4326, got {src.crs}")
        arr = src.read(1).astype("float32")
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        t = src.transform
    if t.b != 0 or t.d != 0:
        raise ValueError("rotated rasters are not supported")
    arr[~np.isfinite(arr)] = np.nan
    return arr, t


def describe_dem(dem: np.ndarray, expected_range_m: tuple[float, float] = (100.0, 1200.0)) -> dict:
    valid = dem[np.isfinite(dem)]
    if valid.size == 0:
        raise ValueError("DEM contains no valid pixels")
    stats = {"pixels": int(dem.size), "valid_fraction": round(valid.size / dem.size, 4),
             "min_m": float(valid.min()), "median_m": float(np.median(valid)), "max_m": float(valid.max()), "warnings": []}
    lo, hi = expected_range_m
    if not (lo <= stats["median_m"] <= hi):
        stats["warnings"].append(f"median elevation {stats['median_m']:.0f} m outside expected {lo:.0f}-{hi:.0f} m for this study area")
    if stats["valid_fraction"] < 0.95:
        stats["warnings"].append(f"{(1 - stats['valid_fraction']) * 100:.1f}% of pixels are nodata")
    return stats


def slope_degrees(dem: np.ndarray, dx_m: float, dy_m: float) -> np.ndarray:
    if dem.ndim != 2 or min(dem.shape) < 2:
        raise ValueError("DEM must be 2-D with at least 2x2 pixels")
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("pixel size must be positive")
    dz_dy, dz_dx = np.gradient(dem, dy_m, dx_m)  # NaN neighbours propagate -> NaN slope (never invented)
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    slope[~np.isfinite(dem)] = np.nan  # central differences skip the centre pixel, so blank nodata explicitly
    return slope


def relative_elevation(dem: np.ndarray, window_px: int = 33) -> np.ndarray:
    """Elevation minus the NaN-aware local mean. Negative values = lower than the surroundings."""
    from scipy import ndimage

    valid = np.isfinite(dem)
    num = ndimage.uniform_filter(np.where(valid, dem, 0.0), size=window_px, mode="nearest")
    den = ndimage.uniform_filter(valid.astype("float64"), size=window_px, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, num / den, np.nan)
    rel = dem - mean
    rel[~valid] = np.nan
    return rel.astype("float32")


def cell_stats(dem, slope, rel, transform, resolution: int, step: int = 1, extra: dict | None = None):
    """Aggregate pixel features into H3 cells. `extra` maps output-name -> (2-D array, 'max'|'mean') for additional layers."""
    import h3
    import pandas as pd

    rows = np.arange(0, dem.shape[0], step)
    cols = np.arange(0, dem.shape[1], step)
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    lon = transform.c + (cc.ravel() + 0.5) * transform.a
    lat = transform.f + (rr.ravel() + 0.5) * transform.e
    elev, slp, rl = dem[rr, cc].ravel(), slope[rr, cc].ravel(), rel[rr, cc].ravel()
    ok = np.isfinite(elev)
    cells = [h3.latlng_to_cell(float(a), float(b), resolution) for a, b in zip(lat[ok], lon[ok])]
    data = {"cell": cells, "elev": elev[ok], "slope": slp[ok], "rel": rl[ok]}
    aggs = dict(elevation_m_mean=("elev", "mean"), elevation_m_min=("elev", "min"),
                slope_deg_mean=("slope", "mean"), rel_elev_m_mean=("rel", "mean"), n_samples=("elev", "size"))
    for name, (arr, how) in (extra or {}).items():
        data[name] = arr[rr, cc].ravel()[ok]
        aggs[name] = (name, how)
    return pd.DataFrame(data).groupby("cell").agg(**aggs)
