from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import hotspots as store
from app.config import Settings, get_settings

router = APIRouter(prefix="/api/hotspots", tags=["hotspots (user-marked)"])


class NewHotspot(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=200)


def _path(settings: Settings):
    return settings.data_dir / "hotspots.csv"


@router.get("")
def list_hotspots(settings: Settings = Depends(get_settings)) -> dict:
    return {"source": "user_marked", "note": "Your own reports of waterlogging spots, not an official dataset.",
            "file": str(_path(settings)), "hotspots": store.load(_path(settings))}


@router.post("", status_code=201)
def add_hotspot(body: NewHotspot, settings: Settings = Depends(get_settings)) -> dict:
    try:
        return store.add(_path(settings), body.lat, body.lon, body.name, settings.study_area_bbox, settings.cells_resolution)
    except store.HotspotError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.delete("/{hotspot_id}")
def delete_hotspot(hotspot_id: str, settings: Settings = Depends(get_settings)) -> dict:
    if not store.remove(_path(settings), hotspot_id):
        raise HTTPException(404, f"unknown hotspot {hotspot_id!r}")
    return {"deleted": hotspot_id}
