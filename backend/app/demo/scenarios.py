"""SYNTHETIC rainfall scenarios for demonstrations. Deterministic, replayable, clearly labelled.

Nothing here reads or writes the weather table. These are invented storms, not reconstructions of real events.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.geo.grid import GridPoint

DISCLAIMER = ("SYNTHETIC DEMO DATA — an invented storm for demonstration. It is not an observation, "
              "forecast, or reconstruction of any real event.")


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    duration_minutes: int
    step_minutes: int
    peak_mm_per_hour: float
    radius_deg: float  # spatial spread (std-dev) of the storm cell


SCENARIOS: dict[str, Scenario] = {s.id: s for s in [
    Scenario("cloudburst", "Cloudburst crossing the city (synthetic)",
             "An intense cell moves west to east across the study area over 3 hours.", 180, 15, 70.0, 0.06),
    Scenario("steady_monsoon", "Steady monsoon rain (synthetic)",
             "Broad, moderate rain with little spatial variation.", 180, 15, 12.0, 0.5),
    Scenario("dry", "No rain (synthetic control)", "Control scenario with zero rainfall.", 180, 15, 0.0, 0.1),
]}


def frame_count(s: Scenario) -> int:
    return s.duration_minutes // s.step_minutes + 1


def make_frame(s: Scenario, minute: int, points: list[GridPoint], bbox: tuple[float, float, float, float]) -> list[dict]:
    """Rain intensity (mm/h) per point at `minute`. Pure function of inputs."""
    if minute < 0 or minute > s.duration_minutes or minute % s.step_minutes:
        raise ValueError(f"minute must be a multiple of {s.step_minutes} in [0, {s.duration_minutes}]")
    min_lon, min_lat, max_lon, max_lat = bbox
    frac = minute / s.duration_minutes
    envelope = math.sin(math.pi * frac) ** 2  # ramps up, peaks mid-scenario, fades
    cx = min_lon + frac * (max_lon - min_lon) if s.id == "cloudburst" else (min_lon + max_lon) / 2
    cy = (min_lat + max_lat) / 2
    out = []
    for p in points:
        d2 = (p.lon - cx) ** 2 + (p.lat - cy) ** 2
        mm = s.peak_mm_per_hour * envelope * math.exp(-d2 / (2 * s.radius_deg ** 2))
        out.append({"point_id": p.point_id, "lat": p.lat, "lon": p.lon, "precipitation_mm": round(mm, 2)})
    return out
