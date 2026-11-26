from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

pytest.importorskip("geopandas")
from shapely.geometry import box

from app import db
from app.config import get_settings
from app.geo.cells import build_cells
from app.geo.grid import weather_grid
from app.main import create_app
from app.routers.weather import get_client
from tests.test_terrain import write_dem
from tests.weather_helpers import client as make_client, hours, location

BBOX = (78.25, 17.2, 78.65, 17.6)


def synthetic_dem():
    yy, xx = np.mgrid[0:200, 0:200].astype(float)
    dem = 540 - 0.05 * yy + 3 * np.sin(xx / 15) + 2 * np.cos(yy / 11)
    dem[90:100, 90:100] -= 8                                         # a pit
    return dem


@pytest.fixture
def env2(migrated, tmp_path, monkeypatch):
    monkeypatch.setenv("FLOODSENSE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    return tmp_path


@pytest.fixture
def with_cells(env2):
    write_dem(env2 / "dem.tif", synthetic_dem())
    build_cells(env2 / "dem.tif", box(78.40, 17.39, 78.46, 17.45), weather_grid(BBOX, 0.1), 9, env2 / "processed" / "cells_res9.gpkg")
    return env2


def payload(value_fn):
    n = len(weather_grid(BBOX, 0.1))
    t = hours(datetime.now(timezone.utc), past=24, future=3)
    return [location(t, [value_fn(i) for i in range(len(t))]) for _ in range(n)]


def app_with_weather(value_fn):
    app = create_app()
    app.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(200, json=payload(value_fn)))
    c = TestClient(app)
    assert c.post("/api/weather/refresh").status_code == 200
    return c


def test_503_when_cell_table_missing(env2):
    r = TestClient(create_app()).get("/api/risk/summary")
    assert r.status_code == 503 and "build-cells" in r.json()["message"]


def test_503_when_cell_table_is_outdated(env2):
    import geopandas as gpd
    (env2 / "processed").mkdir()
    gpd.GeoDataFrame({"cell_id": ["a"], "lat": [17.4], "lon": [78.4], "low_coverage": [False], "elevation_m_mean": [500.0]},
                     geometry=[box(78.4, 17.4, 78.41, 17.41)], crs="EPSG:4326").to_file(env2 / "processed" / "cells_res9.gpkg", driver="GPKG")
    r = TestClient(create_app()).get("/api/risk/cells")
    assert r.status_code == 503 and "Re-run" in r.json()["message"]


def test_no_weather_gives_unavailable_but_still_shows_static_susceptibility(with_cells):
    c = TestClient(create_app())
    s = c.get("/api/risk/summary").json()
    assert s["status"] == "unavailable" and s["reliable"] is False and s["cells_scored"] == 0
    cells = c.get("/api/risk/cells").json()
    assert cells["status"] == "unavailable" and len(cells["cells"]) == s["cells_total"]
    assert all(x["score"] is None and x["category"] is None for x in cells["cells"])
    assert any(x["susceptibility"] is not None for x in cells["cells"])         # terrain layer still available, clearly without a score


def test_dry_weather_is_all_low_and_metadata_is_complete(with_cells):
    c = app_with_weather(lambda i: 0.0)
    s = c.get("/api/risk/summary").json()
    assert s["status"] == "ok" and s["reliable"] is True and s["category_counts"]["low"] == s["cells_scored"] > 0
    assert s["category_counts"]["high"] == s["category_counts"]["critical"] == 0
    assert s["model_version"] and "NOT a probability" in s["score_semantics"] and s["uncertainty"]["available"] is False
    assert s["horizon_status"] == "current_estimate" and s["data_freshness"] == "fresh"
    assert datetime.fromisoformat(s["observation_time"]) <= datetime.fromisoformat(s["prediction_time"])
    assert "Open-Meteo" in s["attribution"] and s["limitations"]


def age_last_run(minutes: int):
    """Move the last successful fetch into the past so the 5-minute upstream cooldown does not block a re-fetch."""
    with sessionmaker(bind=db.get_engine())() as s:
        run = s.scalars(select(db.IngestionRun).order_by(db.IngestionRun.id.desc())).first()
        run.finished_at = run.finished_at - timedelta(minutes=minutes)
        s.commit()


def test_heavy_rain_raises_categories_and_more_rain_never_reduces_them(with_cells):
    heavy = app_with_weather(lambda i: 6.0)
    light = heavy.get("/api/risk/summary").json()["category_counts"]
    age_last_run(10)
    heavy.app.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(200, json=payload(lambda i: 60.0)))
    assert heavy.post("/api/weather/refresh").status_code == 200
    hs = heavy.get("/api/risk/summary").json()["category_counts"]
    assert hs["high"] + hs["critical"] > light["high"] + light["critical"] and hs["critical"] > 0
    assert sum(hs.values()) == sum(light.values())


def test_cells_filter_and_cell_detail_explanation(with_cells):
    c = app_with_weather(lambda i: 60.0)
    hi = c.get("/api/risk/cells?min_category=high").json()["cells"]
    assert hi and all(x["category"] in ("high", "critical") for x in hi)
    assert c.get("/api/risk/cells?min_category=bogus").status_code == 422
    top = max(hi, key=lambda x: x["score"])
    d = c.get(f"/api/risk/cells/{top['cell_id']}").json()
    assert d["category"] == top["category"] and d["explanation"]["terrain_factors"] and d["explanation"]["rainfall"]["kind"]
    assert d["explanation"]["summary"].startswith("Risk index")
    assert d["uncertainty"]["available"] is False and d["target_time"]
    assert c.get("/api/risk/cells/8928308280fffff").status_code == 404


def test_horizon_is_experimental_and_validated(with_cells):
    c = app_with_weather(lambda i: 5.0)
    s = c.get("/api/risk/summary?horizon=2").json()
    assert s["horizon_status"] == "experimental_forecast" and any("EXPERIMENTAL" in w for w in s["warnings"])
    assert datetime.fromisoformat(s["target_time"]) > datetime.fromisoformat(s["observation_time"])
    assert c.get("/api/risk/summary?horizon=4").status_code == 422        # beyond the stored forecast hours
    assert c.get("/api/risk/summary?horizon=-1").status_code == 422


def test_stale_data_is_flagged_unreliable(with_cells):
    c = app_with_weather(lambda i: 30.0)
    with sessionmaker(bind=db.get_engine())() as s:
        run = s.scalars(select(db.IngestionRun)).first()
        run.finished_at = run.finished_at - timedelta(hours=6)
        s.commit()
    r = c.get("/api/risk/summary").json()
    assert r["data_freshness"] == "stale" and r["reliable"] is False and any("stale" in w.lower() for w in r["warnings"])


def test_short_history_warns_that_accumulation_is_underestimated(with_cells):
    app = create_app()
    n = len(weather_grid(BBOX, 0.1))
    short = [location(hours(datetime.now(timezone.utc), past=4, future=2), [1.0] * 6) for _ in range(n)]
    app.dependency_overrides[get_client] = lambda: make_client(lambda r: httpx.Response(200, json=short))
    c = TestClient(app)
    assert c.post("/api/weather/refresh").status_code == 200
    s = c.get("/api/risk/summary").json()
    assert s["accumulation_hours_available"] < 24 and any("underestimated" in w for w in s["warnings"])


def test_methodology_endpoint_is_honest_about_verification(env2):
    m = TestClient(create_app()).get("/api/risk/methodology").json()
    assert abs(sum(v["weight"] for v in m["susceptibility"].values()) - 1) < 1e-9
    assert any("NOT verified" in r["checked"] for r in m["references"]) and any("NOT read" in r["checked"] for r in m["references"])
    assert m["category_bounds"][-1]["upper_exclusive"] is None


def test_cli_risk_commands_end_to_end(with_cells, capsys, tmp_path):
    from app.cli import main
    c = app_with_weather(lambda i: 40.0)           # stores weather in the temp DB
    assert main(["risk-now"]) == 0
    out = capsys.readouterr().out
    assert "baseline-0.1.0" in out and "Category counts" in out and "NOT a probability" in out
    assert main(["risk-sensitivity", "--trials", "10"]) == 0 and "spearman_mean" in capsys.readouterr().out
    import geopandas as gpd
    cells = gpd.read_file(with_cells / "processed" / "cells_res9.gpkg")
    top = cells.nlargest(5, "flow_acc_log10_m2_max")
    csv = tmp_path / "h.csv"; top[["lat", "lon"]].to_csv(csv, index=False)
    assert main(["risk-backtest", "--hotspots", str(csv)]) == 0 and "auc_vs_all_other_cells" in capsys.readouterr().out
    assert main(["risk-backtest", "--hotspots", str(tmp_path / "nope.csv")]) == 1
    assert main(["risk-now", "--horizon", "9"]) == 1 and "horizon" in capsys.readouterr().out
