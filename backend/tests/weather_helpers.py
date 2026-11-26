"""Fake Open-Meteo payloads and transports. No network is ever used in tests."""
from datetime import datetime, timedelta, timezone

import httpx

from app.geo.grid import GridPoint
from app.ingest.weather import OpenMeteoClient

PTS = [GridPoint("17.20_78.25", 17.2, 78.25), GridPoint("17.30_78.35", 17.3, 78.35)]


def hours(now: datetime, past: int = 4, future: int = 2) -> list[str]:
    base = now.replace(minute=0, second=0, microsecond=0)
    return [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(-past + 1, future + 1)]


def location(times: list[str], values: list, unit: str = "mm") -> dict:
    return {"latitude": 17.2, "longitude": 78.2, "hourly_units": {"precipitation": unit},
            "hourly": {"time": times, "precipitation": values}}


def good_payload(now: datetime, n_points: int = 2):
    t = hours(now)
    items = [location(t, [round(0.5 * (i + 1) * k, 2) for k in range(len(t))]) for i in range(n_points)]
    return items if n_points > 1 else items[0]


def client(handler, retries: int = 2) -> OpenMeteoClient:
    sleeps: list[float] = []
    c = OpenMeteoClient("https://example.test/v1", 1.0, retries, 6, 3,
                        transport=httpx.MockTransport(handler), sleep=sleeps.append)
    c.sleeps = sleeps  # type: ignore[attr-defined]
    return c


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=timezone.utc)
