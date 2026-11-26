import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.demo.risk import scenario_risk
from app.demo.scenarios import DISCLAIMER, SCENARIOS, frame_count, make_frame
from app.risk import methodology as M
from app.risk.engine import CellTableError, load_cell_table
from app.geo.grid import weather_grid

router = APIRouter(prefix="/api/demo", tags=["demo (synthetic)"])


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {"label": "synthetic_demo", "disclaimer": DISCLAIMER, "scenarios": [
        {"id": s.id, "name": s.name, "description": s.description, "duration_minutes": s.duration_minutes,
         "step_minutes": s.step_minutes, "frames": frame_count(s)} for s in SCENARIOS.values()]}


@router.get("/scenarios/{scenario_id}/frames/{minute}")
def frame(scenario_id: str, minute: int, settings: Settings = Depends(get_settings)) -> dict:
    s = SCENARIOS.get(scenario_id)
    if s is None:
        raise HTTPException(404, f"unknown scenario {scenario_id!r}")
    points = weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg)
    try:
        pts = make_frame(s, minute, points, settings.study_area_bbox)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    vals = [p["precipitation_mm"] for p in pts]
    return {"label": "synthetic_demo", "disclaimer": DISCLAIMER, "scenario": s.id, "minute": minute,
            "summary": {"mean_mm_per_hour": round(sum(vals) / len(vals), 3), "max_mm_per_hour": max(vals)}, "points": pts}


def _demo_run(scenario: str, minute: int, settings: Settings):
    s = SCENARIOS.get(scenario)
    if s is None:
        raise HTTPException(404, f"unknown scenario {scenario!r}")
    try:
        table = load_cell_table(settings.cells_path)
    except CellTableError as exc:
        raise HTTPException(503, str(exc)) from exc
    points = weather_grid(settings.study_area_bbox, settings.weather_grid_step_deg)
    try:
        res, rain = scenario_risk(table, s, minute, points, settings.study_area_bbox)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return s, table, res, rain


@router.get("/risk", summary="Synthetic storm run through the real risk engine (counts per category)")
def demo_risk(scenario: str, minute: int, settings: Settings = Depends(get_settings)) -> dict:
    s, table, res, rain = _demo_run(scenario, minute, settings)
    counts = {c: 0 for c in M.CATEGORIES}
    for c, n in res["category"].value_counts().items():
        counts[c] = int(n)
    return {"label": "synthetic_demo", "disclaimer": DISCLAIMER + " Terrain and the risk formula are real; the rainfall is invented.",
            "scenario": s.id, "minute": minute, "model_version": M.VERSION, "score_semantics": M.SCORE_SEMANTICS,
            "max_mm_per_hour": round(float(np.nanmax(rain.intensity_mm)), 2), "max_accumulation_mm": round(float(np.nanmax(rain.accumulation_mm)), 1),
            "cells_total": int(table.n), "cells_water": int(table.is_water.sum()), "cells_scored": sum(counts.values()), "category_counts": counts}


@router.get("/risk/cells", summary="Per-cell results of a synthetic storm (for the map)")
def demo_risk_cells(scenario: str, minute: int, settings: Settings = Depends(get_settings)) -> dict:
    s, table, res, rain = _demo_run(scenario, minute, settings)
    rows = [{"cell_id": t.cell_id, "susceptibility": None if t.susceptibility != t.susceptibility else round(float(t.susceptibility), 4),
             "score": None if t.score != t.score else round(float(t.score), 4), "category": t.category} for t in res.itertuples()]
    return {"label": "synthetic_demo", "disclaimer": DISCLAIMER + " Terrain and the risk formula are real; the rainfall is invented.",
            "scenario": s.id, "minute": minute, "cells": rows}
