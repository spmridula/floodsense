from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import Settings, get_settings
from app.geo.export import cells_geojson_bytes
from app.risk.engine import CellTableError, load_cell_table

router = APIRouter(prefix="/api/cells", tags=["cells"])
_cache: dict[str, tuple[float, bytes]] = {}


@router.get("/geojson", summary="Cell polygons with static terrain features (cached; ETag supported)")
def geojson(request: Request, settings: Settings = Depends(get_settings)) -> Response:
    try:
        table = load_cell_table(settings.cells_path)
    except CellTableError as exc:
        raise HTTPException(503, str(exc)) from exc
    mtime = settings.cells_path.stat().st_mtime
    hit = _cache.get(str(settings.cells_path))
    if not hit or hit[0] != mtime:
        hit = (mtime, cells_geojson_bytes(table))
        _cache[str(settings.cells_path)] = hit
    etag = f'"{mtime}-{len(hit[1])}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(content=hit[1], media_type="application/geo+json", headers={"ETag": etag, "Cache-Control": "no-cache"})
