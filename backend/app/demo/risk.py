"""Run a SYNTHETIC storm through the REAL risk engine, so the engine's behaviour can be seen without waiting for real rain.

Nothing here touches the database or real weather. Rainfall is invented (see scenarios.py); the terrain and the
risk formula are the real ones, so the output shows how the engine responds, not what will happen in Hyderabad.
"""
from __future__ import annotations

import numpy as np

from app.demo.scenarios import Scenario, make_frame
from app.geo.grid import GridPoint
from app.risk.engine import CellTable, compute
from app.risk.rain import RainField, apply_idw, idw_matrix


def scenario_rain_field(table: CellTable, s: Scenario, minute: int, points: list[GridPoint], bbox) -> RainField:
    if minute < 0 or minute > s.duration_minutes or minute % s.step_minutes:
        raise ValueError(f"minute must be a multiple of {s.step_minutes} in [0, {s.duration_minutes}]")
    frames = [make_frame(s, m, points, bbox) for m in range(0, minute + 1, s.step_minutes)]
    per_frame = [np.array([p["precipitation_mm"] for p in f]) for f in frames]
    intensity = per_frame[-1]                                         # mm/h at this minute
    accumulation = sum(f * s.step_minutes / 60.0 for f in per_frame)  # mm fallen since the scenario began
    W = idw_matrix(table.df["lat"].to_numpy(), table.df["lon"].to_numpy(), [p.lat for p in points], [p.lon for p in points])
    return RainField(apply_idw(W, intensity), apply_idw(W, accumulation), None, len(frames), len(points))  # type: ignore[arg-type]


def scenario_risk(table: CellTable, s: Scenario, minute: int, points: list[GridPoint], bbox):
    rain = scenario_rain_field(table, s, minute, points, bbox)
    return compute(table, rain), rain
