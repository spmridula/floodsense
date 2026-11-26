from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.risk import methodology as M
from app.risk.engine import CellTableError, explain
from app.services import risk_service as rs

router = APIRouter(prefix="/api/risk", tags=["risk"])
Horizon = Query(0, ge=0, le=24, description="Hours ahead of the latest rainfall hour (0 = current estimate; >0 experimental)")


def _run(session, settings, horizon):
    try:
        return rs.run(session, settings, horizon)
    except CellTableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _f(x, nd=3):
    return None if x is None or x != x else round(float(x), nd)


@router.get("/methodology", summary="Every weight, threshold and reference used, with what was and was not verified")
def methodology() -> dict:
    return {"model_version": M.VERSION, "score_semantics": M.SCORE_SEMANTICS,
            "formula": "R = S x H;  S = weighted mean of percentile ranks of terrain proxies;  H = max(H_intensity, H_accumulation)",
            "susceptibility": M.SUSCEPTIBILITY, "intensity_anchors_mm_per_h": M.INTENSITY_ANCHORS,
            "accumulation_anchors_mm": M.ACCUMULATION_ANCHORS, "accumulation_window_hours": M.ACCUMULATION_WINDOW_HOURS,
            "category_bounds": [{"upper_exclusive": None if b == float("inf") else b, "category": c} for b, c in M.CATEGORY_BOUNDS],
            "limitations": M.LIMITATIONS, "references": M.REFERENCES}


@router.get("/summary")
def summary(horizon: int = Horizon, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    r = _run(session, settings, horizon)
    counts = {c: 0 for c in M.CATEGORIES}
    if r.result is not None:
        for c, n in r.result["category"].value_counts().items():
            counts[c] = int(n)
    n_water = int(r.table.is_water.sum())
    return {**r.meta, "cells_total": r.table.n, "cells_scored": sum(counts.values()), "cells_water": n_water,
            "water_masked": r.table.water_masked,
            "cells_without_terrain_data": int(r.table.susceptibility.isna().sum()) - n_water, "category_counts": counts}


@router.get("/cells", summary="Compact per-cell results (geometry comes with the map in Phase 4)")
def cells(horizon: int = Horizon, min_category: str | None = Query(None, pattern="^(low|moderate|high|critical)$"),
          session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    r = _run(session, settings, horizon)
    rows = []
    if r.result is not None:
        df = r.result
        if min_category:
            df = df[df["category"].map({c: i for i, c in enumerate(M.CATEGORIES)}).fillna(-1) >= M.CATEGORIES.index(min_category)]
        rows = [{"cell_id": t.cell_id, "lat": round(t.lat, 5), "lon": round(t.lon, 5), "susceptibility": _f(t.susceptibility, 4),
                 "score": _f(t.score, 4), "category": t.category} for t in df.itertuples()]
        water = r.table.is_water
    else:  # no rainfall: still expose static terrain susceptibility, with no score
        t = r.table
        rows = [{"cell_id": cid, "lat": round(float(t.df.at[cid, 'lat']), 5), "lon": round(float(t.df.at[cid, 'lon']), 5),
                 "susceptibility": _f(t.susceptibility[cid], 4), "score": None, "category": None} for cid in t.df.index]
    return {**{k: r.meta[k] for k in ("status", "reliable", "model_version", "score_semantics", "horizon_hours", "horizon_status",
                                      "data_freshness", "observation_time", "target_time", "prediction_time", "warnings")}, "cells": rows}


@router.get("/cells/{cell_id}", summary="Full explanation for one cell")
def cell_detail(cell_id: str, horizon: int = Horizon, session: Session = Depends(get_session),
                settings: Settings = Depends(get_settings)) -> dict:
    r = _run(session, settings, horizon)
    if cell_id not in r.table.df.index:
        raise HTTPException(404, f"unknown cell {cell_id!r}")
    base = {k: r.meta[k] for k in ("status", "reliable", "model_version", "score_semantics", "horizon_hours", "horizon_status", "horizon_note",
                                   "data_freshness", "weather_fetched_at", "observation_time", "target_time", "prediction_time",
                                   "warnings", "uncertainty", "limitations", "attribution")}
    cell = r.table.df.loc[cell_id]
    base.update(cell_id=cell_id, lat=float(cell["lat"]), lon=float(cell["lon"]), susceptibility=_f(r.table.susceptibility[cell_id], 4))
    if bool(r.table.is_water[cell_id]):
        base.update(status="water_body", score=None, category=None, hazard=None,
                    explanation={"summary": "Water body (lake, reservoir or river): not scored. Risk for people near its edge is not represented here.",
                                 "terrain_factors": [], "rainfall": None})
        return base
    if r.result is None:
        base.update(score=None, category=None, explanation={"summary": "No rainfall data available; only static terrain susceptibility is known.",
                                                              "terrain_factors": [], "rainfall": None})
        return base
    row = r.result.loc[cell_id]
    base.update(score=_f(row["score"], 4), category=row["category"], hazard=_f(row["hazard"], 4),
                explanation=explain(r.table, row, r.acc_hours))
    return base
