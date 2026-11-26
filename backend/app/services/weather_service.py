"""Orchestrates weather refresh and serves the latest snapshot with honest freshness."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import IngestionRun, WeatherObservation, utcnow
from app.geo.grid import weather_grid
from app.ingest.weather import SOURCE, OpenMeteoClient, WeatherError

log = logging.getLogger(__name__)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class Freshness(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass
class RefreshOutcome:
    status: str  # "updated" | "skipped_cooldown" | "failed"
    message: str
    retry_after_seconds: int = 0
    rows_written: int = 0


def last_success(session: Session) -> IngestionRun | None:
    return session.scalars(
        select(IngestionRun).where(IngestionRun.source_key == SOURCE, IngestionRun.status == "success")
        .order_by(IngestionRun.finished_at.desc()).limit(1)
    ).first()


def last_run(session: Session) -> IngestionRun | None:
    return session.scalars(
        select(IngestionRun).where(IngestionRun.source_key == SOURCE).order_by(IngestionRun.id.desc()).limit(1)
    ).first()


def classify(age_seconds: float | None, settings: Settings) -> Freshness:
    if age_seconds is None:
        return Freshness.UNAVAILABLE
    if age_seconds <= 2 * settings.refresh_interval_seconds:
        return Freshness.FRESH
    if age_seconds <= settings.stale_after_seconds:
        return Freshness.AGING
    return Freshness.STALE


def refresh_weather(session: Session, client: OpenMeteoClient, settings: Settings,
                    now: datetime | None = None) -> RefreshOutcome:
    """Fetch and store. On ANY failure existing rows are left untouched and the failure is recorded."""
    injected = now is not None
    now = now or utcnow()

    def done() -> datetime:  # one consistent clock: real time in production, the injected time in tests
        return now if injected else utcnow()

    points = weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg)
    ids = {p.point_id for p in points}
    prev = last_success(session)
    covers = prev is not None and session.scalar(
        select(func.count()).select_from(WeatherObservation).where(
            WeatherObservation.run_id == prev.id, WeatherObservation.point_id.in_(ids))) > 0
    if prev and prev.finished_at and covers:  # a changed study area/grid must never be blocked by the cooldown
        age = (now - as_utc(prev.finished_at)).total_seconds()
        if age < settings.weather_min_refresh_seconds:
            wait = int(settings.weather_min_refresh_seconds - age) + 1
            return RefreshOutcome("skipped_cooldown", f"Data is only {int(age)}s old; upstream is not re-queried within "
                                  f"{settings.weather_min_refresh_seconds}s.", retry_after_seconds=wait)

    run = IngestionRun(source_key=SOURCE, started_at=now, status="failed")
    session.add(run)
    session.flush()
    try:
        result = client.fetch(points)
    except WeatherError as exc:
        run.status, run.error, run.finished_at = "failed", str(exc)[:500], done()
        session.commit()
        log.error("weather refresh failed: %s", exc)
        return RefreshOutcome("failed", str(exc))
    except Exception as exc:  # noqa: BLE001 - never let an unexpected bug look like fresh data
        run.status, run.error, run.finished_at = "failed", f"{type(exc).__name__}: {exc}"[:500], done()
        session.commit()
        log.exception("unexpected weather refresh error")
        return RefreshOutcome("failed", "Unexpected error while refreshing weather data.")

    existing = {
        (o.point_id, as_utc(o.valid_time)): o
        for o in session.scalars(select(WeatherObservation).where(
            WeatherObservation.source == SOURCE,
            WeatherObservation.valid_time >= min(r.valid_time for r in result.readings) - timedelta(minutes=1)))
    }
    written = 0
    for r in result.readings:
        row = existing.get((r.point_id, r.valid_time))
        is_fc = int(r.valid_time > now)
        if row is None:
            session.add(WeatherObservation(source=SOURCE, point_id=r.point_id, lat=r.lat, lon=r.lon,
                                           valid_time=r.valid_time, fetched_at=now, precipitation_mm=r.precipitation_mm,
                                           is_forecast=is_fc, run_id=run.id))
        else:  # newer fetch supersedes: same point+hour never duplicated
            row.precipitation_mm, row.fetched_at, row.is_forecast, row.run_id = r.precipitation_mm, now, is_fc, run.id
        written += 1
    run.status, run.record_count, run.finished_at = "success", written, done()
    if result.rejected:
        run.error = f"{result.rejected} readings rejected by validation"
    session.commit()
    return RefreshOutcome("updated", f"Stored {written} readings for {result.points_ok}/{result.points_requested} points.",
                          rows_written=written)


def snapshot(session: Session, settings: Settings, now: datetime | None = None) -> dict:
    """Latest known data. Never fabricates: no data -> freshness 'unavailable' and empty points."""
    now = now or utcnow()
    ok, failed = last_success(session), last_run(session)
    fetched_at = as_utc(ok.finished_at) if ok else None
    age = (now - fetched_at).total_seconds() if fetched_at else None
    freshness = classify(age, settings)

    ids = {p.point_id for p in weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg)}
    points: list[dict] = []
    note = None
    if ok:
        newest = (select(WeatherObservation.point_id, func.max(WeatherObservation.valid_time).label("vt"))
                  .where(WeatherObservation.source == SOURCE, WeatherObservation.valid_time <= now,
                         WeatherObservation.point_id.in_(ids))
                  .group_by(WeatherObservation.point_id).subquery())
        rows = session.scalars(select(WeatherObservation).join(
            newest, (WeatherObservation.point_id == newest.c.point_id) & (WeatherObservation.valid_time == newest.c.vt))
            .where(WeatherObservation.source == SOURCE, WeatherObservation.point_id.in_(ids))
            .order_by(WeatherObservation.point_id)).all()
        for o in rows:
            points.append({"point_id": o.point_id, "lat": o.lat, "lon": o.lon, "valid_time": as_utc(o.valid_time),
                           "precipitation_mm": o.precipitation_mm, "was_forecast_when_fetched": bool(o.is_forecast)})
    if ok and not points:  # stored data belongs to a different study area / grid: do not present it as current
        freshness, note = Freshness.UNAVAILABLE, ("Stored weather data is for a different study area or grid spacing. "
                                                   "Refresh to fetch data for the current configuration.")
    vals = [p["precipitation_mm"] for p in points if p["precipitation_mm"] is not None]
    return {
        "note": note,
        "label": "live_forecast",
        "label_explanation": "Modelled precipitation from Open-Meteo (grid estimate), not a rain-gauge observation.",
        "attribution": "Weather data by Open-Meteo.com",
        "freshness": freshness.value,
        "fetched_at": fetched_at,
        "age_seconds": int(age) if age is not None else None,
        "generated_at": now,
        "latest_valid_time": max((p["valid_time"] for p in points), default=None),
        "last_run_status": failed.status if failed else None,
        "last_error": failed.error if failed and failed.status == "failed" else None,
        "summary": {"points": len(points), "points_with_value": len(vals),
                    "mean_mm_per_hour": round(sum(vals) / len(vals), 3) if vals else None,
                    "max_mm_per_hour": max(vals) if vals else None},
        "points": points,
    }
