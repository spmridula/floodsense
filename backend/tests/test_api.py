from fastapi.testclient import TestClient

from app.main import create_app


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "X-Request-ID" in r.headers


def test_ready_ok_when_migrated(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["checks"][0]["ok"] is True


def test_ready_503_when_not_migrated(env):
    r = TestClient(create_app()).get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


def test_sources_seeded_and_honestly_labelled(client):
    data = client.get("/api/sources").json()
    by_key = {s["key"]: s for s in data}
    assert {"open_meteo", "copernicus_dem", "osm_roads", "ghmc_hotspots"} <= by_key.keys()
    # Nothing is claimed verified in Phase 1, and missing data is flagged unavailable.
    assert all(s["verification"] != "verified" for s in data)
    assert by_key["ghmc_hotspots"]["label"] == "unavailable"


def test_seed_is_idempotent(migrated):
    from sqlalchemy.orm import sessionmaker
    from app import db
    with sessionmaker(bind=db.get_engine(migrated))() as s:
        assert db.seed_data_sources(s) == 0


def test_study_area_marked_approximate(client):
    d = client.get("/api/study-area").json()
    assert d["bbox_is_approximate"] is True and d["bbox_min_lon"] < d["bbox_max_lon"]


def test_consistent_error_schema_404(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert set(r.json()) == {"error", "message", "request_id"}


def test_validation_error_schema(client):
    # POST to a GET-only route -> 405 in the same schema
    r = client.post("/health")
    assert r.status_code == 405 and r.json()["error"] == "http_error"


def test_cli_init_db(env, capsys):
    from app.cli import main
    assert main(["init-db"]) == 0
    assert "Seeded 6" in capsys.readouterr().out
