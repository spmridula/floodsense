"""Hydrological conditioning of a DEM: depression filling, D8 flow directions, flow accumulation.

Algorithms: priority-flood depression filling with epsilon gradient (Barnes, Lehman & Mulla 2014) and D8 steepest-descent
routing (O'Callaghan & Mark 1984). Implemented here in plain NumPy/Python so it installs on any laptop (no compiled GIS deps).

CAVEAT: run on a surface model (buildings/trees included). Buildings act as dams and create spurious pits, so outputs are
SUSCEPTIBILITY PROXIES for where water may collect or concentrate, not a model of real drainage (which includes culverts,
underpasses and storm drains that are not in any elevation data).
"""
from __future__ import annotations

import heapq
import math

import numpy as np

_OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def fill_depressions(dem: np.ndarray, epsilon: float = 1e-4) -> np.ndarray:
    """Return the DEM with every closed depression raised to its spill level (+epsilon slope so flats drain).

    Water may leave through the array border or through nodata (NaN) cells, which act as outlets.
    """
    if dem.ndim != 2:
        raise ValueError("dem must be 2-D")
    h, w = dem.shape
    W = w + 2
    pad = np.full((h + 2, W), np.nan)
    pad[1:-1, 1:-1] = dem
    valid2d = np.isfinite(pad)
    touches_outside = np.zeros_like(valid2d)
    for dr, dc in _OFFS:
        touches_outside |= ~np.roll(np.roll(valid2d, dr, 0), dc, 1)
    seeds = np.flatnonzero((valid2d & touches_outside).ravel()).tolist()

    z = pad.ravel().tolist()
    filled = z[:]
    isvalid = valid2d.ravel().tolist()
    visited = bytearray(len(z))
    heap = []
    for i in seeds:
        visited[i] = 1
        heap.append((z[i], i))
    heapq.heapify(heap)
    offs = [dr * W + dc for dr, dc in _OFFS]
    pop, push = heapq.heappop, heapq.heappush
    while heap:
        zc, c = pop(heap)
        lo = zc + epsilon
        for o in offs:
            n = c + o
            if visited[n] or not isvalid[n]:
                continue
            visited[n] = 1
            zn = z[n]
            if zn < lo:
                zn = lo
            filled[n] = zn
            push(heap, (zn, n))
    return np.asarray(filled, dtype="float64").reshape(h + 2, W)[1:-1, 1:-1]


def flow_directions(filled: np.ndarray, dx_m: float, dy_m: float) -> np.ndarray:
    """D8: flat index of the steepest-descent neighbour for each cell, or -1 for outlets/nodata. Shape (h*w,)."""
    if dx_m <= 0 or dy_m <= 0:
        raise ValueError("pixel size must be positive")
    h, w = filled.shape
    pad = np.full((h + 2, w + 2), np.nan)
    pad[1:-1, 1:-1] = filled
    centre = pad[1:-1, 1:-1]
    best = np.zeros((h, w))
    which = np.full((h, w), -1, dtype=np.int8)
    for k, (dr, dc) in enumerate(_OFFS):
        nb = pad[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
        with np.errstate(invalid="ignore"):
            slope = (centre - nb) / math.hypot(dr * dy_m, dc * dx_m)
        better = np.isfinite(slope) & (slope > best)
        best = np.where(better, slope, best)
        which = np.where(better, k, which)
    rr, cc = np.mgrid[0:h, 0:w]
    dr_arr = np.array([o[0] for o in _OFFS])
    dc_arr = np.array([o[1] for o in _OFFS])
    safe = np.where(which >= 0, which, 0)
    down = np.where(which >= 0, (rr + dr_arr[safe]) * w + (cc + dc_arr[safe]), -1)
    return down.ravel().astype("int64")


def flow_accumulation(filled: np.ndarray, down: np.ndarray) -> np.ndarray:
    """Number of cells (itself included) draining through each cell. NaN where the DEM is nodata."""
    flat = filled.ravel()
    valid = np.isfinite(flat)
    order = np.argsort(-np.where(valid, flat, -np.inf), kind="stable")  # highest first, nodata last
    acc = np.where(valid, 1, 0).tolist()
    dl = down.tolist()
    vl = valid.tolist()
    for i in order.tolist():
        if not vl[i]:
            break
        d = dl[i]
        if d >= 0:
            acc[d] += acc[i]
    out = np.asarray(acc, dtype="float64")
    out[~valid] = np.nan
    return out.reshape(filled.shape)


def hydro_features(dem: np.ndarray, dx_m: float, dy_m: float) -> dict[str, np.ndarray]:
    """depression_depth_m (>=0) and flow_acc_log10_m2 (log10 of upslope area in m2), both NaN on nodata."""
    filled = fill_depressions(dem.astype("float64"))
    depth = np.where(np.isfinite(dem), filled - dem, np.nan)
    depth = np.where(depth < 1e-3, 0.0, depth)  # ignore epsilon-sized artefacts
    acc = flow_accumulation(filled, flow_directions(filled, dx_m, dy_m))
    with np.errstate(invalid="ignore"):
        log_area = np.log10(acc * dx_m * dy_m)
    return {"depression_depth_m": depth.astype("float32"), "flow_acc_log10_m2": log_area.astype("float32")}
