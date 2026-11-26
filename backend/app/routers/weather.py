from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.ingest.weather import OpenMeteoClient
from app.services import weather_service as svc

router = APIRouter(prefix="/api/weather", tags=["weather"])


def get_client(settings: Settings = Depends(get_settings)) -> OpenMeteoClient:
    return OpenMeteoClient(settings.open_meteo_base_url, settings.http_timeout_seconds, settings.http_max_retries,
                           settings.weather_past_hours, settings.weather_forecast_hours)


@router.get("/latest", summary="Latest stored weather with freshness (never fabricated)")
def latest(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    return svc.snapshot(session, settings)


@router.post("/refresh", summary="Fetch new data now (rate-limited)")
def refresh(request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
            client: OpenMeteoClient = Depends(get_client)) -> dict:
    out = svc.refresh_weather(session, client, settings)
    if out.status == "skipped_cooldown":
        raise HTTPException(status_code=429, detail=out.message, headers={"Retry-After": str(out.retry_after_seconds)})
    if out.status == "failed":
        # Upstream problem: 502, and the previously stored data remains available from /latest.
        raise HTTPException(status_code=502, detail=f"{out.message} Previously stored data (if any) is unchanged.")
    return {"status": out.status, "message": out.message, "rows_written": out.rows_written,
            "snapshot": svc.snapshot(session, settings)}
