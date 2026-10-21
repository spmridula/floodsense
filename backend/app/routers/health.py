from datetime import datetime, timezone

from fastapi import APIRouter, Response

from app import __version__
from app.db import check_database
from app.schemas import HealthResponse, ReadyCheck, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness: process is up")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, time=datetime.now(timezone.utc))


@router.get("/ready", response_model=ReadyResponse, summary="Readiness: dependencies usable")
def ready(response: Response) -> ReadyResponse:
    ok, detail = check_database()
    checks = [ReadyCheck(name="database", ok=ok, detail=detail)]
    all_ok = all(c.ok for c in checks)
    if not all_ok:
        response.status_code = 503
    return ReadyResponse(status="ready" if all_ok else "not_ready", checks=checks)
