import json

from sqlalchemy.orm import sessionmaker

from app import db
from app.geo.provenance import mark_source_verified, record_artifact, sha256_file


def test_manifest_hash_relative_path_and_update(tmp_path):
    f = tmp_path / "raw" / "a.bin"; f.parent.mkdir(); f.write_bytes(b"hello")
    m = tmp_path / "manifest.json"
    e = record_artifact(m, "a", f, "https://src", "MIT", {"k": 1}, base_dir=tmp_path)
    assert e["sha256"] == sha256_file(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert e["path"] == "raw/a.bin"                                 # portable, no absolute path
    f.write_bytes(b"changed"); record_artifact(m, "a", f, "https://src", "MIT", base_dir=tmp_path)
    data = json.loads(m.read_text())
    assert list(data["artifacts"]) == ["a"] and data["artifacts"]["a"]["sha256"] != e["sha256"]


def test_mark_source_verified_sets_status_and_time(migrated):
    with sessionmaker(bind=db.get_engine(migrated))() as s:
        assert mark_source_verified(s, "open_meteo") is True
        row = s.query(db.DataSourceRow).filter_by(key="open_meteo").one()
        assert row.verification == "verified" and row.last_checked is not None
        assert mark_source_verified(s, "does_not_exist") is False
