"""Glue: stored weather + static cell table -> risk results with honest metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import WeatherObservation, utcnow
from app.geo.grid import weather_grid
from app.ingest.weather import SOURCE
from app.risk import methodology as M
from app.risk.engine import CellTable, compute, load_cell_table
from app.risk.rain import PointSeries, build_rain_field
from app.services import weather_service as ws


@dataclass
class RiskRun:
    table: CellTable
    meta: dict
    result: pd.DataFrame | None = None
    acc_hours: int = 0
    warnings: list[str] = field(default_factory=list)


def _series(session: Session, settings: Settings, base: datetime) -> list[PointSeries]:
    ids = {p.point_id for p in weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg)}
    start = base - timedelta(hours=M.ACCUMULATION_WINDOW_HOURS + 2)
    rows = session.scalars(select(WeatherObservation).where(
        WeatherObservation.source == SOURCE, WeatherObservation.point_id.in_(ids), WeatherObservation.valid_time >= start)).all()
    by: dict[str, PointSeries] = {}
    for o in rows:
        ps = by.setdefault(o.point_id, PointSeries(o.point_id, o.lat, o.lon, {}))
        ps.hourly[ws.as_utc(o.valid_time)] = o.precipitation_mm
    return list(by.values())


def run(session: Session, settings: Settings, horizon: int, now: datetime | None = None) -> RiskRun:
    """Compute risk for every cell. Raises CellTableError if static data is missing; ValueError for a bad horizon."""
    now = now or utcnow()
    if not 0 <= horizon <= settings.weather_forecast_hours:
        raise ValueError(f"horizon must be between 0 and {settings.weather_forecast_hours} hours")
    table = load_cell_table(settings.cells_path)
    snap = ws.snapshot(session, settings, now)
    meta = {
        "model_version": M.VERSION, "score_semantics": M.SCORE_SEMANTICS, "prediction_time": now,
        "horizon_hours": horizon,
        "horizon_status": "current_estimate" if horizon == 0 else "experimental_forecast",
        "horizon_note": M.HORIZON_NOTE[0] if horizon == 0 else M.HORIZON_NOTE["forecast"],
        "data_freshness": snap["freshness"], "weather_fetched_at": snap["fetched_at"], "observation_time": snap["latest_valid_time"],
        "weather_label": snap["label"], "attribution": snap["attribution"],
        "uncertainty": {"available": False, "reason": "The index is not calibrated against observed floods, so no meaningful "
                                                      "confidence or uncertainty interval can be given."},
        "limitations": M.LIMITATIONS,
    }
    out = RiskRun(table, meta)
    base = snap["latest_valid_time"]
    if snap["freshness"] == "unavailable" or base is None:
        meta.update(status="unavailable", reliable=False, target_time=None, warnings=[snap.get("note") or "No weather data available."])
        return out
    series = _series(session, settings, base)
    rain = build_rain_field(table.df["lat"].to_numpy(), table.df["lon"].to_numpy(), series, base, horizon)
    out.result, out.acc_hours = compute(table, rain), rain.accumulation_hours_available
    warns = []
    if snap["freshness"] == "stale":
        warns.append("Weather data is stale; results should not be relied on.")
    elif snap["freshness"] == "aging":
        warns.append("Weather data is aging; refresh recommended.")
    if (now - base) > timedelta(hours=2):
        warns.append("Latest rainfall hour is more than 2 hours old.")
    if rain.accumulation_hours_available < M.ACCUMULATION_WINDOW_HOURS:
        warns.append(f"Only {rain.accumulation_hours_available} of {M.ACCUMULATION_WINDOW_HOURS} hours of rainfall history are stored, "
                     "so the accumulation component may be underestimated.")
    if horizon > 0:
        warns.append(M.HORIZON_NOTE["forecast"])
    n_ok = int(out.result["score"].notna().sum())
    if n_ok == 0:
        warns.append("Rainfall could not be estimated for any cell.")
    meta.update(status="ok" if n_ok else "unavailable", target_time=rain.target_time,
                reliable=snap["freshness"] in ("fresh", "aging") and (now - base) <= timedelta(hours=2) and n_ok > 0,
                warnings=warns, accumulation_hours_available=rain.accumulation_hours_available)
    return out
