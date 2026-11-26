import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import db
from app.main import create_app
from tests.test_risk_api import env2, with_cells  # noqa: F401  (shared fixtures)


def get(c, scenario="cloudburst", minute=90):
    return c.get(f"/api/demo/risk?scenario={scenario}&minute={minute}")


def test_storm_makes_the_real_engine_react(with_cells):
    c = TestClient(create_app())
    start, peak = get(c, minute=0).json(), get(c, minute=90).json()
    assert start["category_counts"]["low"] == start["cells_scored"] > 0 and start["max_mm_per_hour"] == 0
    assert peak["max_mm_per_hour"] > 20
    assert peak["category_counts"]["high"] + peak["category_counts"]["critical"] > 0
    assert sum(peak["category_counts"].values()) == peak["cells_scored"] == peak["cells_total"]


def test_everything_is_labelled_synthetic_and_nothing_is_stored(with_cells):
    c = TestClient(create_app())
    d = get(c).json()
    assert d["label"] == "synthetic_demo" and "SYNTHETIC" in d["disclaimer"] and "invented" in d["disclaimer"]
    assert "NOT a probability" in d["score_semantics"]
    with sessionmaker(bind=db.get_engine())() as s:
        assert s.scalar(select(func.count()).select_from(db.WeatherObservation)) == 0
        assert s.scalar(select(func.count()).select_from(db.IngestionRun)) == 0
    assert c.get("/api/weather/latest").json()["points"] == []


def test_dry_control_stays_low_at_every_minute_and_accumulation_persists_after_the_storm(with_cells):
    c = TestClient(create_app())
    assert all(get(c, "dry", m).json()["category_counts"]["low"] == get(c, "dry", m).json()["cells_scored"] for m in (0, 90, 180))
    after = get(c, minute=180).json()
    assert after["max_mm_per_hour"] < 1 and after["max_accumulation_mm"] > 10     # storm over, rain already fallen still counts


def test_errors(with_cells, env2):
    c = TestClient(create_app())
    assert get(c, "nope").status_code == 404
    assert all(get(c, minute=m).status_code == 422 for m in (7, -15, 195, 181))
    import shutil; shutil.rmtree(env2 / "processed")
    r = get(c)
    assert r.status_code == 503 and "build-cells" in r.json()["message"]
