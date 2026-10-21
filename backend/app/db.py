"""Database layer: SQLAlchemy 2.x (sync) with Alembic migrations. SQLite locally; PostgreSQL later via DATABASE_URL."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Integer, String, Text, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import BACKEND_DIR, Settings, get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DataSourceRow(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    coverage: Mapped[str] = mapped_column(String(200), nullable=False)
    license: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(300), nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    verification: Mapped[str] = mapped_column(String(32), nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestionRun(Base):
    """One row per fetch attempt: gives provenance and a failure history (used from Phase 2)."""
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | failed
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


_engines: dict[str, Engine] = {}


def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url not in _engines:
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
        if url.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def _fk(dbapi_conn, _):  # enforce foreign keys on SQLite
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        _engines[url] = engine
    return _engines[url]


def get_session():
    """FastAPI dependency."""
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def run_migrations(url: str | None = None) -> None:
    command.upgrade(_alembic_config(url or get_settings().database_url), "head")


def check_database(url: str | None = None) -> tuple[bool, str]:
    """Return (ok, detail). OK only if reachable AND migrated to head."""
    url = url or get_settings().database_url
    try:
        engine = get_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            current = MigrationContext.configure(conn).get_current_revision()
        head = ScriptDirectory.from_config(_alembic_config(url)).get_current_head()
        if current != head:
            return False, f"database at revision {current!r}, expected {head!r}; run init-db"
        return True, f"revision {current}"
    except Exception as exc:  # noqa: BLE001 - surface any DB failure in readiness
        return False, f"{type(exc).__name__}: {exc}"


def seed_data_sources(session: Session) -> int:
    """Insert missing registry rows; never overwrites rows (so verification status set later is preserved)."""
    from app.data_sources import SOURCES

    existing = {k for (k,) in session.query(DataSourceRow.key).all()}
    added = 0
    for src in SOURCES:
        if src["key"] in existing:
            continue
        session.add(DataSourceRow(**{**src, "label": src["label"].value, "verification": src["verification"].value}))
        added += 1
    session.commit()
    return added
