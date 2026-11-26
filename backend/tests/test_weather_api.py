import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import db
from app.config import get_settings
from app.main import create_app
from app.routers.weather import get_client
from app.geo.grid import weather_grid
from tests.weather_helpers import client as make_client, hours, location, utc


@pytest.fixture
def app_(migrated, monkeypatch):
    monkeypatch.setenv("FLOODSENSE_WEATHER_MIN_REFRESH_SECONDS", "300")
    get_settings.cache_clear()
    return create_app()


def payload():
    s = get_settings()
    n = len(weather_grid(s.study_area_bbox, s.weather_grid_step_deg))
    from datetime import datetime, timezone
    t = hours(datetime.now(timezone.utc), 4, 2)
    return [location(t, [2.5] * len(t)) for _ in range(n)]


def test_latest_unavailable_initially(app_):
    d = TestClient(app_).get("/api/weather/latest").json()
    assert d["freshness"] == "unavailable" and d["points"] == [] and d["label"] == "live_forecast"
    assert "not a rain-gauge" in d["label_explanation"] and d["attribution"]


def test_refresh_then_latest_then_cooldown_429(app_):
    app_.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(200, json=payload()))
    c = TestClient(app_)
    r = c.post("/api/weather/refresh")
    assert r.status_code == 200 and r.json()["snapshot"]["summary"]["points"] == 25
    d = c.get("/api/weather/latest").json()
    assert d["freshness"] == "fresh" and d["summary"]["max_mm_per_hour"] == 2.5
    r2 = c.post("/api/weather/refresh")
    assert r2.status_code == 429 and int(r2.headers["Retry-After"]) > 0
    assert r2.json()["error"] == "http_error"


def test_upstream_failure_is_502_and_data_unchanged(app_):
    app_.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(200, json=payload()))
    c = TestClient(app_)
    assert c.post("/api/weather/refresh").status_code == 200
    # age the success beyond cooldown, then break upstream
    with sessionmaker(bind=db.get_engine())() as s:
        from datetime import timedelta
        run = s.scalars(select(db.IngestionRun)).first()
        run.finished_at = run.finished_at - timedelta(hours=1)
        s.commit()
    app_.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(503), retries=0)
    r = c.post("/api/weather/refresh")
    assert r.status_code == 502 and "unchanged" in r.json()["message"]
    d = c.get("/api/weather/latest").json()
    assert d["summary"]["max_mm_per_hour"] == 2.5 and d["last_run_status"] == "failed" and d["freshness"] == "aging"
