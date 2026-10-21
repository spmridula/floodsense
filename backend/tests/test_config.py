import pytest
from pydantic import ValidationError

from app.config import Settings


def test_defaults_valid():
    s = Settings(_env_file=None)
    assert s.env == "local" and s.refresh_interval_seconds >= 300


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="production", cors_origins=["*"])


def test_bad_bbox_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, study_area_bbox=(78.6, 17.2, 78.2, 17.6))


def test_refresh_interval_floor():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, refresh_interval_seconds=10)


def test_stale_must_exceed_refresh():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, refresh_interval_seconds=3600, stale_after_seconds=3000)
