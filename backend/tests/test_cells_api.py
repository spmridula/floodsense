import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("geopandas")
from shapely.geometry import box

from app.geo.cells import build_cells
from app.geo.grid import weather_grid
from app.main import create_app
from tests.test_risk_api import app_with_weather, env2, synthetic_dem, BBOX  # noqa: F401
from tests.test_terrain import write_dem


@pytest.fixture
def with_water_cells(env2):
    write_dem(env2 / "dem.tif", synthetic_dem())
    build_cells(env2 / "dem.tif", box(78.40, 17.39, 78.46, 17.45), weather_grid(BBOX, 0.1), 9, env2 / "processed" / "cells_res9.gpkg",
                water_geom=box(78.41, 17.40, 78.43, 17.42))
    return env2


def test_geojson_503_without_table(env2):
    r = TestClient(create_app()).get("/api/cells/geojson")
    assert r.status_code == 503 and "build-cells" in r.json()["message"]


def test_geojson_structure_cache_and_etag(with_water_cells):
    c = TestClient(create_app())
    r = c.get("/api/cells/geojson")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    d = r.json()
    assert d["type"] == "FeatureCollection" and d["water_masked"] is True and len(d["features"]) > 100
    f = d["features"][0]
    ring = f["geometry"]["coordinates"][0]
    assert f["geometry"]["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) in (6, 7)     # closed hexagon (or pentagon)
    lon, lat = ring[0]
    assert 78.3 < lon < 78.5 and 17.3 < lat < 17.5                                                    # GeoJSON is [lon, lat]
    assert {"cell_id", "susceptibility", "is_water", "water_fraction", "low_coverage", "rel_elev_m_mean", "depression_depth_m_max",
            "flow_acc_log10_m2_max", "elevation_m_mean", "slope_deg_mean"} <= set(f["properties"])
    assert f["id"] == f["properties"]["cell_id"]
    water = [x for x in d["features"] if x["properties"]["is_water"]]
    assert water and all(x["properties"]["susceptibility"] is None for x in water)                   # never scored
    assert len({x["id"] for x in d["features"]}) == len(d["features"])
    etag = r.headers["etag"]
    assert c.get("/api/cells/geojson", headers={"If-None-Match": etag}).status_code == 304
    assert c.get("/api/cells/geojson", headers={"If-None-Match": '"stale"'}).status_code == 200
    assert "NaN" not in r.text                                                                        # strict JSON


def test_risk_summary_and_detail_handle_water(with_water_cells):
    c = app_with_weather(lambda i: 60.0)
    s = c.get("/api/risk/summary").json()
    assert s["water_masked"] is True and s["cells_water"] > 5
    assert s["cells_scored"] + s["cells_water"] + s["cells_without_terrain_data"] == s["cells_total"]
    geo = c.get("/api/cells/geojson").json()["features"]
    wid = next(x["id"] for x in geo if x["properties"]["is_water"])
    d = c.get(f"/api/risk/cells/{wid}").json()
    assert d["status"] == "water_body" and d["score"] is None and d["category"] is None and "not scored" in d["explanation"]["summary"]
    land = next(x["id"] for x in geo if not x["properties"]["is_water"] and x["properties"]["susceptibility"] is not None)
    assert c.get(f"/api/risk/cells/{land}").json()["category"] is not None


def test_demo_cells_endpoint(with_water_cells):
    c = TestClient(create_app())
    a = c.get("/api/demo/risk/cells?scenario=cloudburst&minute=0").json()
    b = c.get("/api/demo/risk/cells?scenario=cloudburst&minute=90").json()
    assert a["label"] == b["label"] == "synthetic_demo" and "SYNTHETIC" in b["disclaimer"]
    n = len(c.get("/api/cells/geojson").json()["features"])
    assert len(a["cells"]) == len(b["cells"]) == n
    cats = lambda d: {x["category"] for x in d["cells"]}
    assert cats(a) <= {"low", None} and cats(b) & {"high", "critical"}
    assert c.get("/api/demo/risk/cells?scenario=cloudburst&minute=7").status_code == 422
    assert c.get("/api/demo/risk/cells?scenario=nope&minute=0").status_code == 404
    s = c.get("/api/demo/risk?scenario=cloudburst&minute=90").json()
    assert s["cells_water"] > 5 and s["cells_scored"] + s["cells_water"] == s["cells_total"]
