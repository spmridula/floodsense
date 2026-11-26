"""User-marked known waterlogging spots, stored in data/hotspots.csv (read by `risk-backtest`).

Local single-user store: atomic writes, size limit, validation, CSV-injection guard. These are the USER'S OWN reports,
not an official dataset.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["id", "lat", "lon", "name", "added_at"]
MAX_POINTS = 500
_lock = threading.Lock()


class HotspotError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def clean_name(name: str | None) -> str:
    n = re.sub(r"[\x00-\x1f\x7f]", " ", (name or "")).strip()[:80]
    return "'" + n if n[:1] in ("=", "+", "-", "@") else n      # neutralise spreadsheet formula injection


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [{"id": r["id"], "lat": float(r["lat"]), "lon": float(r["lon"]), "name": r["name"], "added_at": r["added_at"]}
                for r in csv.DictReader(f)]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def add(path: Path, lat: float, lon: float, name: str | None, bbox: tuple[float, float, float, float], resolution: int = 9) -> dict:
    import h3

    min_lon, min_lat, max_lon, max_lat = bbox
    if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
        raise HotspotError("Point is outside the study area.")
    with _lock:
        rows = load(path)
        if len(rows) >= MAX_POINTS:
            raise HotspotError(f"Limit of {MAX_POINTS} marked spots reached.", 409)
        cell = h3.latlng_to_cell(lat, lon, resolution)
        if any(h3.latlng_to_cell(r["lat"], r["lon"], resolution) == cell for r in rows):
            raise HotspotError("A spot is already marked in this cell.", 409)
        row = {"id": uuid.uuid4().hex[:8], "lat": round(lat, 6), "lon": round(lon, 6), "name": clean_name(name),
               "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        rows.append(row)
        _write(path, rows)
        return row


def remove(path: Path, hotspot_id: str) -> bool:
    with _lock:
        rows = load(path)
        kept = [r for r in rows if r["id"] != hotspot_id]
        if len(kept) == len(rows):
            return False
        _write(path, kept)
        return True
