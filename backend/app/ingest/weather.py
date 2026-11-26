"""Open-Meteo client: fetch, validate, return typed points. No database access here.

Semantics verified against Open-Meteo docs (2026-10-21): hourly `precipitation` is the SUM of the PRECEDING hour, in mm;
multi-location requests return a JSON list; `past_hours` / `forecast_hours` control the window.
Values are MODELLED grid estimates, never gauge observations.
"""
from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

from app.geo.grid import GridPoint

log = logging.getLogger(__name__)
SOURCE = "open_meteo"
MAX_PLAUSIBLE_MM_PER_HOUR = 500.0  # above any recorded hourly rainfall; anything higher is a data error


class WeatherError(Exception):
    """Any failure to obtain valid weather data. Message is safe to show to users."""


@dataclass(frozen=True)
class WeatherReading:
    point_id: str
    lat: float
    lon: float
    valid_time: datetime  # UTC, end of the hour covered
    precipitation_mm: float | None  # None = provider returned no value


@dataclass
class FetchResult:
    readings: list[WeatherReading]
    rejected: int  # readings dropped by validation
    points_requested: int
    points_ok: int


def _parse_time(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"unparseable timestamp {value!r}") from exc
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def parse_response(payload: object, points: list[GridPoint]) -> FetchResult:
    """Validate a provider payload. Raises WeatherError if nothing usable; drops individual bad readings."""
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(points):
        raise WeatherError(f"provider returned {len(items)} locations for {len(points)} requested")
    readings: list[WeatherReading] = []
    rejected = 0
    points_ok = 0
    for point, item in zip(points, items):  # match by ORDER: provider snaps lat/lon to its own grid
        if not isinstance(item, dict) or item.get("error"):
            raise WeatherError(f"provider error: {item.get('reason') if isinstance(item, dict) else 'bad item'}")
        hourly, units = item.get("hourly"), item.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise WeatherError("response missing hourly data")
        if units.get("precipitation") != "mm":
            raise WeatherError(f"unexpected precipitation unit {units.get('precipitation')!r} (expected 'mm')")
        times, values = hourly.get("time"), hourly.get("precipitation")
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values) or not times:
            raise WeatherError("hourly time/precipitation arrays missing or different lengths")
        ok_here = 0
        seen: set[datetime] = set()
        for t, v in zip(times, values):
            vt = _parse_time(t)
            if vt in seen:  # duplicate timestamp within one point
                rejected += 1
                continue
            seen.add(vt)
            if v is None:
                readings.append(WeatherReading(point.point_id, point.lat, point.lon, vt, None))
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) \
                    or v < 0 or v > MAX_PLAUSIBLE_MM_PER_HOUR:
                rejected += 1
                continue
            readings.append(WeatherReading(point.point_id, point.lat, point.lon, vt, float(v)))
            ok_here += 1
        points_ok += ok_here > 0
    if points_ok == 0:
        raise WeatherError("no valid precipitation values in response")
    return FetchResult(readings, rejected, len(points), points_ok)


class OpenMeteoClient:
    def __init__(self, base_url: str, timeout: float, max_retries: int, past_hours: int, forecast_hours: int,
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.base_url = base_url.rstrip("/")
        self.timeout, self.max_retries = timeout, max_retries
        self.past_hours, self.forecast_hours = past_hours, forecast_hours
        self._transport, self._sleep = transport, sleep

    def fetch(self, points: list[GridPoint]) -> FetchResult:
        if not points:
            raise WeatherError("no grid points configured")
        params = {
            "latitude": ",".join(f"{p.lat:.4f}" for p in points),
            "longitude": ",".join(f"{p.lon:.4f}" for p in points),
            "hourly": "precipitation",
            "past_hours": self.past_hours,
            "forecast_hours": self.forecast_hours,
            "timezone": "GMT",
            "timeformat": "iso8601",
        }
        last_error = "unknown error"
        with httpx.Client(timeout=self.timeout, transport=self._transport,
                          headers={"User-Agent": "FloodSense-student-project/0.2"}) as http:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = http.get(f"{self.base_url}/forecast", params=params)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"network error: {type(exc).__name__}"
                else:
                    if resp.status_code == 200:
                        try:
                            return parse_response(resp.json(), points)
                        except ValueError as exc:  # invalid JSON
                            raise WeatherError("provider returned invalid JSON") from exc
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last_error = f"provider HTTP {resp.status_code}"
                    else:  # 4xx other than 429: our request is wrong; retrying will not help
                        raise WeatherError(f"provider rejected request (HTTP {resp.status_code})")
                if attempt < self.max_retries:
                    delay = min(30.0, 0.5 * 2 ** attempt) * (0.5 + random.random() / 2)
                    log.warning("weather fetch failed (%s); retry %d/%d in %.1fs", last_error, attempt + 1, self.max_retries, delay)
                    self._sleep(delay)
        raise WeatherError(f"weather fetch failed after {self.max_retries + 1} attempts: {last_error}")
