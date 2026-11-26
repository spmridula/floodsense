from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import db
from app.demo.scenarios import SCENARIOS, make_frame
from app.geo.grid import weather_grid
from app.main import create_app

BBOX = (78.25, 17.20, 78.65, 17.60)
PTS = weather_grid(BBOX, 0.1)


def test_frames_are_deterministic():
    s = SCENARIOS["cloudburst"]
    assert make_frame(s, 90, PTS, BBOX) == make_frame(s, 90, PTS, BBOX)


def test_cloudburst_moves_west_to_east_and_peaks_midway():
    s = SCENARIOS["cloudburst"]
    def peak_lon(m):
        f = make_frame(s, m, PTS, BBOX)
        return max(f, key=lambda p: p["precipitation_mm"])["lon"]
    assert peak_lon(30) < peak_lon(150)
    mx = {m: max(p["precipitation_mm"] for p in make_frame(s, m, PTS, BBOX)) for m in (0, 90, 180)}
    assert mx[0] == 0 and mx[180] < 1e-6 and mx[90] > 20


def test_dry_control_is_zero():
    assert all(p["precipitation_mm"] == 0 for p in make_frame(SCENARIOS["dry"], 90, PTS, BBOX))


def test_invalid_minute_rejected():
    import pytest
    with pytest.raises(ValueError):
        make_frame(SCENARIOS["cloudburst"], 7, PTS, BBOX)


def test_api_labels_everything_synthetic_and_never_touches_weather_table(migrated):
    c = TestClient(create_app())
    lst = c.get("/api/demo/scenarios").json()
    assert lst["label"] == "synthetic_demo" and "SYNTHETIC" in lst["disclaimer"]
    f = c.get("/api/demo/scenarios/cloudburst/frames/90").json()
    assert f["label"] == "synthetic_demo" and "not an observation" in f["disclaimer"] and f["summary"]["max_mm_per_hour"] > 0
    assert c.get("/api/demo/scenarios/nope/frames/0").status_code == 404
    assert c.get("/api/demo/scenarios/cloudburst/frames/7").status_code == 422
    with sessionmaker(bind=db.get_engine(migrated))() as s:
        assert s.scalar(select(func.count()).select_from(db.WeatherObservation)) == 0
    assert c.get("/api/weather/latest").json()["points"] == []  # demo rain never leaks into real data
