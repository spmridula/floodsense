import csv

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.test_risk_api import env2, with_cells  # noqa: F401


@pytest.fixture
def hs(env_tmp):
    return TestClient(create_app()), env_tmp


@pytest.fixture
def env_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOODSENSE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def post(c, lat=17.43, lon=78.39, name="Underpass"):
    return c.post("/api/hotspots", json={"lat": lat, "lon": lon, "name": name})


def test_crud_roundtrip_and_persistence(hs):
    c, d = hs
    assert c.get("/api/hotspots").json()["hotspots"] == []
    r = post(c); assert r.status_code == 201
    row = r.json()
    assert row["lat"] == 17.43 and len(row["id"]) == 8 and row["added_at"].endswith("+00:00")
    listed = c.get("/api/hotspots").json()
    assert listed["source"] == "user_marked" and "not an official" in listed["note"] and len(listed["hotspots"]) == 1
    with open(d / "hotspots.csv", newline="") as f:                    # really on disk, restart-safe
        assert list(csv.DictReader(f))[0]["name"] == "Underpass"
    assert TestClient(create_app()).get("/api/hotspots").json()["hotspots"][0]["id"] == row["id"]
    assert c.delete(f"/api/hotspots/{row['id']}").status_code == 200 and c.get("/api/hotspots").json()["hotspots"] == []
    assert c.delete("/api/hotspots/zzzz").status_code == 404
    assert not list(d.glob("*.part"))


@pytest.mark.parametrize("lat,lon", [(28.6, 77.2), (17.0, 78.4), (17.4, 79.5)])
def test_outside_study_area_rejected(hs, lat, lon):
    c, _ = hs
    r = post(c, lat, lon)
    assert r.status_code == 422 and "outside the study area" in r.json()["message"]


@pytest.mark.parametrize("body", [{"lat": 200, "lon": 78.4}, {"lat": "x", "lon": 78.4}, {"lon": 78.4}, {"lat": 17.4, "lon": 78.4, "name": "a" * 300}])
def test_invalid_bodies_rejected(hs, body):
    assert hs[0].post("/api/hotspots", json=body).status_code == 422


def test_duplicate_cell_conflict_but_nearby_other_cell_ok(hs):
    c, _ = hs
    assert post(c).status_code == 201
    assert post(c, 17.43001, 78.39001, "again").status_code == 409                # same ~330 m cell
    assert post(c, 17.45, 78.45, "elsewhere").status_code == 201


def test_names_are_sanitised_against_formula_injection_and_control_chars(hs):
    c, d = hs
    for i, (n, want) in enumerate([("=HYPERLINK(\"x\")", "'=HYPERLINK(\"x\")"), ("+cmd", "'+cmd"), ("@x", "'@x"), ("-1+1", "'-1+1"),
                                   ("a\nb\tc", "a b c"), ("  spaced  ", "spaced"), (None, "")]):
        r = post(c, 17.30 + i * 0.01, 78.30 + i * 0.01, n)
        assert r.status_code == 201 and r.json()["name"] == want


def test_limit(hs, monkeypatch):
    from app import hotspots
    monkeypatch.setattr(hotspots, "MAX_POINTS", 2)
    c, _ = hs
    assert post(c, 17.30, 78.30).status_code == 201 and post(c, 17.35, 78.35).status_code == 201
    r = post(c, 17.40, 78.40)
    assert r.status_code == 409 and "Limit" in r.json()["message"]


def test_backtest_uses_marked_spots_by_default(with_cells, env2, capsys):                  # noqa: F811
    from app.cli import main
    import geopandas as gpd
    cells = gpd.read_file(env2 / "processed" / "cells_res9.gpkg").nlargest(6, "flow_acc_log10_m2_max")
    c = TestClient(create_app())
    for t in cells.itertuples():
        assert post(c, t.lat, t.lon, f"spot {t.cell_id}").status_code == 201
    assert main(["risk-backtest"]) == 0
    out = capsys.readouterr().out
    assert '"hotspots_in_file": 6' in out and "auc_vs_all_other_cells" in out and "far too few" in out
