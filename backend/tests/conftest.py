import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated settings + empty temp SQLite DB for each test."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("FLOODSENSE_DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()
    db._engines.clear()


@pytest.fixture
def migrated(env):
    from sqlalchemy.orm import sessionmaker
    db.run_migrations(env)
    with sessionmaker(bind=db.get_engine(env))() as s:
        db.seed_data_sources(s)
    return env


@pytest.fixture
def client(migrated):
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)
