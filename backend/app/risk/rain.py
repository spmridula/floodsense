"""Turn point rainfall (Open-Meteo sample points) into per-cell rainfall. Pure NumPy; no I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from app.risk.methodology import ACCUMULATION_WINDOW_HOURS


@dataclass
class PointSeries:
    point_id: str
    lat: float
    lon: float
    hourly: dict[datetime, float | None]  # valid_time (UTC, end of hour) -> mm in that hour


@dataclass
class RainField:
    intensity_mm: np.ndarray       # per cell, mm in the target hour (NaN = unknown)
    accumulation_mm: np.ndarray    # per cell, mm over the window ending at the target hour (NaN = unknown)
    target_time: datetime
    accumulation_hours_available: int   # fewest hours of data behind any point's accumulation
    points_used: int


def idw_matrix(cell_lat, cell_lon, pt_lat, pt_lon, k: int = 4, power: float = 2.0) -> np.ndarray:
    """(n_cells x n_points) inverse-distance weights over each cell's k nearest points; rows sum to 1."""
    cell_lat, cell_lon = np.asarray(cell_lat, float), np.asarray(cell_lon, float)
    pt_lat, pt_lon = np.asarray(pt_lat, float), np.asarray(pt_lon, float)
    if pt_lat.size == 0:
        raise ValueError("no weather points")
    kx = np.cos(np.radians(cell_lat))[:, None]
    d = 111.32 * np.hypot(cell_lat[:, None] - pt_lat[None, :], (cell_lon[:, None] - pt_lon[None, :]) * kx)  # km
    k = min(k, pt_lat.size)
    nearest = np.argpartition(d, k - 1, axis=1)[:, :k]
    W = np.zeros_like(d)
    rows = np.arange(d.shape[0])[:, None]
    dk = d[rows, nearest]
    with np.errstate(divide="ignore"):
        w = 1.0 / np.maximum(dk, 1e-6) ** power
    exact = dk < 1e-6
    w = np.where(exact.any(axis=1, keepdims=True), exact.astype(float), w)   # cell sits on a point: take that point only
    W[rows, nearest] = w
    return W / W.sum(axis=1, keepdims=True)


def apply_idw(W: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Weighted mean ignoring missing (NaN) point values. NaN where none of a cell's nearest points has data."""
    ok = np.isfinite(values)
    Wm = W * ok[None, :]
    denom = Wm.sum(axis=1)
    out = (Wm @ np.where(ok, values, 0.0)) / np.where(denom > 0, denom, 1.0)
    return np.where(denom > 0, out, np.nan)


def build_rain_field(cell_lat, cell_lon, series: list[PointSeries], base_time: datetime, horizon_hours: int,
                     window_hours: int = ACCUMULATION_WINDOW_HOURS) -> RainField:
    """Rainfall at `base_time + horizon_hours` and the accumulation over the `window_hours` ending then."""
    if horizon_hours < 0:
        raise ValueError("horizon_hours must be >= 0")
    target = base_time + timedelta(hours=horizon_hours)
    hours = [target - timedelta(hours=i) for i in range(window_hours)]
    v_int = np.full(len(series), np.nan)
    v_acc = np.full(len(series), np.nan)
    n_hours = []
    for i, s in enumerate(series):
        got = [s.hourly.get(h) for h in hours]
        present = [g for g in got if g is not None]
        if s.hourly.get(target) is not None:
            v_int[i] = s.hourly[target]
        if present and s.hourly.get(target) is not None:     # need the target hour itself, else the window is not "ending now"
            v_acc[i] = float(sum(present))
            n_hours.append(len(present))
    W = idw_matrix(cell_lat, cell_lon, [s.lat for s in series], [s.lon for s in series])
    return RainField(apply_idw(W, v_int), apply_idw(W, v_acc), target,
                     min(n_hours) if n_hours else 0, int(np.isfinite(v_int).sum()))
