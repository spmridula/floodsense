from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import DataSourceRow, get_session
from app.schemas import DataSourceOut, StudyAreaResponse

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/study-area", response_model=StudyAreaResponse)
def study_area(settings: Settings = Depends(get_settings)) -> StudyAreaResponse:
    min_lon, min_lat, max_lon, max_lat = settings.study_area_bbox
    return StudyAreaResponse(
        name=settings.study_area_name, bbox_min_lon=min_lon, bbox_min_lat=min_lat,
        bbox_max_lon=max_lon, bbox_max_lat=max_lat, bbox_is_approximate=True,
        note="Approximate rectangle; the official GHMC boundary is ingested in Phase 2.",
    )


@router.get("/sources", response_model=list[DataSourceOut], summary="Data-source register with verification status")
def sources(session: Session = Depends(get_session)) -> list[DataSourceOut]:
    rows = session.query(DataSourceRow).order_by(DataSourceRow.key).all()
    return [DataSourceOut.model_validate(r, from_attributes=True) for r in rows]
