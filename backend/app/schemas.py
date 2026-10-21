"""Shared API schemas. DataLabel is the app-wide vocabulary for what a piece of data IS."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DataLabel(str, Enum):
    LIVE_OBSERVATION = "live_observation"      # measured, recent
    LIVE_FORECAST = "live_forecast"            # modelled by a provider
    HISTORICAL = "historical"                  # archived real data
    MODEL_PREDICTION = "model_prediction"      # produced by FloodSense's engine
    SYNTHETIC_DEMO = "synthetic_demo"          # fabricated for demonstration; never shown as real
    UNAVAILABLE = "unavailable"                # no data exists / not yet ingested


class VerificationStatus(str, Enum):
    NOT_VERIFIED = "not_verified"              # named in research, endpoint/data not yet downloaded
    VERIFIED = "verified"                      # downloaded/queried and checked by this project
    UNAVAILABLE = "unavailable"                # looked for, not found


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime


class ReadyCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: str
    checks: list[ReadyCheck]


class StudyAreaResponse(BaseModel):
    name: str
    bbox_min_lon: float
    bbox_min_lat: float
    bbox_max_lon: float
    bbox_max_lat: float
    bbox_is_approximate: bool
    note: str


class DataSourceOut(BaseModel):
    key: str
    name: str
    url: str
    coverage: str
    license: str
    role: str
    limitations: str
    label: DataLabel
    verification: VerificationStatus
    last_checked: datetime | None


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
