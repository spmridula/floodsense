from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import db
from app.config import Settings
from app.db import IngestionRun, WeatherObservation
from app.geo.grid import weather_grid
from app.services import weather_service as svc
from tests.weather_helpers import client, hours, location, utc

T0 = utc(2026, 10, 21, 12, 30)


@pytest.fixture
def settings(migrated):
    return Settings(_env_file=None, database_url=migrated)


@pytest.fixture
def session(migrated):
    with sessionmaker(bind=db.get_engine(migrated))() as s:
        yield s


def payload_for(settings, now, value=1.0):
    n = len(weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg))
    t = hours(now, past=4, future=2)
    return [location(t, [value] * len(t)) for _ in range(n)]


def ok_client(settings, now, value=1.0):
    return client(lambda r: httpx.Response(200, json=payload_for(settings, now, value)))


def test_unavailable_before_any_fetch(session, settings):
    s = svc.snapshot(session, settings, now=T0)
    assert s["freshness"] == "unavailable" and s["points"] == [] and s["fetched_at"] is None


def test_refresh_stores_and_snapshot_separates_times(session, settings):
    out = svc.refresh_weather(session, ok_client(settings, T0), settings, now=T0)
    assert out.status == "updated" and out.rows_written == 25 * 6
    s = svc.snapshot(session, settings, now=T0 + timedelta(minutes=2))
    assert s["freshness"] == "fresh" and s["label"] == "live_forecast"
    assert s["summary"]["points"] == 25
    assert s["latest_valid_time"] <= T0 + timedelta(minutes=2)  # "current" never uses a future hour
    assert s["fetched_at"] is not None and s["latest_valid_time"] != s["fetched_at"]
    assert all(p["was_forecast_when_fetched"] is False for p in s["points"])


def test_rows_marked_forecast_when_in_future(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0), settings, now=T0)
    n_fc = session.scalar(select(func.count()).select_from(WeatherObservation).where(WeatherObservation.is_forecast == 1))
    assert n_fc == 25 * 2  # the two future hours per point


def test_no_duplicates_on_later_refresh_and_values_updated(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0, 1.0), settings, now=T0)
    later = T0 + timedelta(minutes=20)
    svc.refresh_weather(session, ok_client(settings, later, 7.0), settings, now=later)
    total = session.scalar(select(func.count()).select_from(WeatherObservation))
    assert total == 25 * 6  # same hours overwritten, not duplicated
    s = svc.snapshot(session, settings, now=later)
    assert s["summary"]["max_mm_per_hour"] == 7.0


def test_cooldown_protects_upstream(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0), settings, now=T0)
    def boom(r): raise AssertionError("upstream must not be called during cooldown")
    out = svc.refresh_weather(session, client(boom), settings, now=T0 + timedelta(seconds=30))
    assert out.status == "skipped_cooldown" and out.retry_after_seconds > 0


def test_failed_refresh_keeps_old_data_and_records_error(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0, 3.0), settings, now=T0)
    later = T0 + timedelta(minutes=30)
    out = svc.refresh_weather(session, client(lambda r: httpx.Response(500), retries=1), settings, now=later)
    assert out.status == "failed"
    s = svc.snapshot(session, settings, now=later)
    assert s["summary"]["max_mm_per_hour"] == 3.0          # old data still served, not replaced or zeroed
    assert s["last_run_status"] == "failed" and "HTTP 500" in s["last_error"]
    assert s["fetched_at"] == T0                          # still the LAST SUCCESS, not the failed attempt
    assert session.scalar(select(func.count()).select_from(IngestionRun).where(IngestionRun.status == "failed")) == 1


def test_failure_on_empty_db_stays_unavailable_not_fake(session, settings):
    out = svc.refresh_weather(session, client(lambda r: httpx.Response(503), retries=0), settings, now=T0)
    s = svc.snapshot(session, settings, now=T0)
    assert out.status == "failed" and s["freshness"] == "unavailable" and s["points"] == []


@pytest.mark.parametrize("age_s,expected", [(60, "fresh"), (1800, "fresh"), (3600, "aging"),
                                            (3 * 3600, "aging"), (3 * 3600 + 1, "stale"), (None, "unavailable")])
def test_freshness_thresholds(settings, age_s, expected):
    assert svc.classify(age_s, settings).value == expected


def test_data_becomes_stale_as_time_passes(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0), settings, now=T0)
    s = svc.snapshot(session, settings, now=T0 + timedelta(hours=5))
    assert s["freshness"] == "stale" and s["age_seconds"] >= 5 * 3600 - 60


def test_changing_study_area_excludes_old_points_and_bypasses_cooldown(session, settings):
    svc.refresh_weather(session, ok_client(settings, T0, 9.0), settings, now=T0)
    assert svc.snapshot(session, settings, now=T0)["summary"]["points"] == 25
    new = Settings(_env_file=None, database_url=settings.database_url, study_area_bbox=(78.2387, 17.2916, 78.6224, 17.5608))
    snap = svc.snapshot(session, new, now=T0)
    assert snap["points"] == [] and snap["freshness"] == "unavailable" and "different study area" in snap["note"]
    # 30 s later the cooldown would normally block, but the stored data does not cover the new grid, so it must fetch
    soon = T0 + timedelta(seconds=30)
    out = svc.refresh_weather(session, ok_client(new, soon, 1.5), new, now=soon)
    assert out.status == "updated"
    s2 = svc.snapshot(session, new, now=soon)
    assert s2["summary"]["points"] == 20 and s2["summary"]["max_mm_per_hour"] == 1.5   # old 9.0 mm/h points not mixed in
    assert s2["note"] is None and s2["freshness"] == "fresh"
    # and now that the new grid is covered, the cooldown applies again
    again = svc.refresh_weather(session, client(lambda r: (_ for _ in ()).throw(AssertionError("no call"))), new, now=soon + timedelta(seconds=10))
    assert again.status == "skipped_cooldown"
