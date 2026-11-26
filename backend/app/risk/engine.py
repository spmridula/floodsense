"""Baseline risk engine: transparent, deterministic, testable. See methodology.py for every constant."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.risk import methodology as M
from app.risk.rain import RainField

REQUIRED_COLUMNS = ["cell_id", "lat", "lon", "low_coverage", *M.SUSCEPTIBILITY.keys()]


class CellTableError(Exception):
    """Cell table missing, unreadable or outdated; message tells the user what to run."""


@dataclass
class CellTable:
    df: pd.DataFrame            # indexed by cell_id
    ranks: pd.DataFrame         # percentile rank per feature, oriented so 1 = most susceptible
    susceptibility: pd.Series   # S per cell (NaN if any feature missing, or if the cell is a water body)
    is_water: pd.Series         # True for water-body cells (never scored)
    water_masked: bool          # False when no water layer was supplied (lakes are then NOT excluded)

    @property
    def n(self) -> int:
        return len(self.df)


def percentile_ranks(df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    out = {}
    for feat, spec in M.SUSCEPTIBILITY.items():
        x = df[feat]
        r = x.rank(pct=True) if spec["direction"] == "high" else (-x).rank(pct=True)
        out[feat] = r
    return pd.DataFrame(out, index=df.index)


def susceptibility(ranks: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    """Weighted mean of ranks. A cell missing ANY feature gets NaN (never a partial score)."""
    w = weights or {f: s["weight"] for f, s in M.SUSCEPTIBILITY.items()}
    total = sum(w.values())
    s = sum(ranks[f] * (w[f] / total) for f in M.SUSCEPTIBILITY)
    return s.where(ranks.notna().all(axis=1))


def make_table(df: pd.DataFrame) -> CellTable:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CellTableError(f"cell table lacks columns {missing}. Re-run: python -m app.cli build-cells")
    d = df.set_index("cell_id", drop=False)
    water_masked = "water_fraction" in d.columns and bool(d["water_fraction"].notna().any())
    is_water = (d["water_fraction"].fillna(0) >= M.WATER_THRESHOLD) if water_masked else pd.Series(False, index=d.index)
    ranks = percentile_ranks(d[~is_water]).reindex(d.index)     # lakes must not distort the percentile scale
    return CellTable(d, ranks, susceptibility(ranks), is_water, water_masked)


_cache: dict[str, tuple[float, CellTable]] = {}


def load_cell_table(path: Path) -> CellTable:
    """Read the GeoPackage attributes (no geometry) once and cache until the file changes."""
    if not path.exists():
        raise CellTableError(f"{path.name} not found. Run: python -m app.cli build-cells")
    mtime = path.stat().st_mtime
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        import pyogrio
        df = pyogrio.read_dataframe(path, read_geometry=False)
    except ImportError as exc:
        raise CellTableError("geospatial packages missing. Run: pip install -r requirements-geo.txt") from exc
    table = make_table(pd.DataFrame(df))
    _cache[str(path)] = (mtime, table)
    return table


def hazard(intensity_mm: np.ndarray, accumulation_mm: np.ndarray) -> dict[str, np.ndarray]:
    """Severity 0..1 from modelled rainfall. Intensity is required; accumulation is used when available."""
    hi_x, hi_y = zip(*M.INTENSITY_ANCHORS)
    ha_x, ha_y = zip(*M.ACCUMULATION_ANCHORS)
    h_int = np.interp(intensity_mm, hi_x, hi_y)        # NaN in -> NaN out
    h_acc = np.interp(accumulation_mm, ha_x, ha_y)
    both = np.fmax(h_int, h_acc)
    h = np.where(np.isfinite(h_int), np.where(np.isfinite(h_acc), both, h_int), np.nan)   # no intensity -> no hazard
    return {"h_intensity": h_int, "h_accumulation": h_acc, "hazard": h}


def categorize(score: np.ndarray) -> np.ndarray:
    bounds = [b for b, _ in M.CATEGORY_BOUNDS[:-1]]
    idx = np.digitize(score, bounds, right=False)       # score == bound -> next category up
    out = np.array(M.CATEGORIES, dtype=object)[idx]
    out[~np.isfinite(score)] = None
    return out


def compute(table: CellTable, rain: RainField) -> pd.DataFrame:
    """Per-cell result frame. Rows with unknown terrain or rainfall have score NaN and category None -- never a default."""
    h = hazard(rain.intensity_mm, rain.accumulation_mm)
    S = table.susceptibility.to_numpy()
    score = S * h["hazard"]
    res = pd.DataFrame({"cell_id": table.df.index, "lat": table.df["lat"].to_numpy(), "lon": table.df["lon"].to_numpy(),
                        "susceptibility": S, "hazard": h["hazard"], "h_intensity": h["h_intensity"],
                        "h_accumulation": h["h_accumulation"], "rain_mm_per_h": rain.intensity_mm,
                        "rain_acc_mm": rain.accumulation_mm, "score": score, "category": categorize(score)},
                       index=table.df.index)
    return res


def explain(table: CellTable, row: pd.Series, rain_acc_hours: int) -> dict:
    """Plain-language, fully traceable explanation for one cell. Every sentence maps to a computed number."""
    cell = table.df.loc[row.name]
    factors = []
    for feat, spec in M.SUSCEPTIBILITY.items():
        rank = float(table.ranks.loc[row.name, feat])
        contrib = spec["weight"] * rank
        val = float(cell[feat])
        pct = round(rank * 100)
        side = "lower" if spec["direction"] == "low" else "higher"
        factors.append({
            "feature": feat, "label": spec["label"], "value": round(val, 2), "unit": spec["unit"],
            "kind": spec["kind"], "weight": spec["weight"], "rank_percentile": pct, "contribution": round(contrib, 4),
            "text": f"{spec['label']}: {val:.1f} {spec['unit']} - {side} than {pct}% of Hyderabad cells ({spec['kind'].replace('_', ' ')}).",
        })
    factors.sort(key=lambda f: f["contribution"], reverse=True)
    rain = {
        "intensity_mm_per_hour": None if not np.isfinite(row["rain_mm_per_h"]) else round(float(row["rain_mm_per_h"]), 2),
        "accumulation_mm": None if not np.isfinite(row["rain_acc_mm"]) else round(float(row["rain_acc_mm"]), 1),
        "accumulation_window_hours": M.ACCUMULATION_WINDOW_HOURS, "accumulation_hours_with_data": rain_acc_hours,
        "severity_from_intensity": None if not np.isfinite(row["h_intensity"]) else round(float(row["h_intensity"]), 3),
        "severity_from_accumulation": None if not np.isfinite(row["h_accumulation"]) else round(float(row["h_accumulation"]), 3),
        "kind": "modelled_forecast_interpolated", "text": "Modelled rainfall (Open-Meteo), interpolated between ~10 km sample points; not a gauge reading.",
    }
    if np.isfinite(row["score"]):
        top = "; ".join(f["text"] for f in factors[:3])
        summary = (f"Risk index {row['score']:.2f} ({row['category']}) = terrain susceptibility {row['susceptibility']:.2f} x rainfall severity "
                   f"{row['hazard']:.2f}. Strongest terrain factors: {top}")
    else:
        summary = "No risk index: terrain features or rainfall are unavailable for this cell."
    return {"summary": summary, "terrain_factors": factors, "rainfall": rain}
