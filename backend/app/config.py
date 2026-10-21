"""Application settings. All values come from environment variables (prefix FLOODSENSE_) or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLOODSENSE_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    env: Literal["local", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'floodsense.db').as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Study area. NOTE: this bounding box is an APPROXIMATE rectangle around Greater Hyderabad,
    # used only until the official GHMC boundary is ingested in Phase 2.
    study_area_name: str = "Hyderabad (Greater Hyderabad, approximate bounds)"
    study_area_bbox: tuple[float, float, float, float] = Field(
        default=(78.25, 17.20, 78.65, 17.60), description="min_lon, min_lat, max_lon, max_lat"
    )

    # Weather provider (used from Phase 2). Free tier is non-commercial; see Open-Meteo terms.
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    http_max_retries: int = Field(default=3, ge=0, le=6)
    refresh_interval_seconds: int = Field(default=900, ge=300, description="Never poll faster than 5 min")
    stale_after_seconds: int = Field(default=3 * 3600, ge=600)

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        min_lon, min_lat, max_lon, max_lat = self.study_area_bbox
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError("study_area_bbox must be (min_lon, min_lat, max_lon, max_lat) with min < max")
        if self.env == "production" and any(o.strip() == "*" for o in self.cors_origins):
            raise ValueError("Wildcard CORS origin is not allowed when FLOODSENSE_ENV=production")
        if self.stale_after_seconds <= self.refresh_interval_seconds:
            raise ValueError("stale_after_seconds must exceed refresh_interval_seconds")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
