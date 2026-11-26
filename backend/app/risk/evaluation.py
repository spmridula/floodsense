"""Evaluation WITHOUT flood-event labels: weight sensitivity, and a presence-only back-test against user-supplied hotspots.

No fitting happens anywhere (weights are fixed in methodology.py), so there is no train/test leakage to guard against; the
back-test measures how well a fixed ranking agrees with independently listed trouble spots.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from app.risk import methodology as M
from app.risk.engine import CellTable, susceptibility


def auc_presence(scores: np.ndarray, positive: np.ndarray) -> float | None:
    """P(random hotspot cell outranks random other cell) (Mann-Whitney). None if undefined. 0.5 = no skill."""
    ok = np.isfinite(scores)
    s, p = scores[ok], positive[ok].astype(bool)
    n_pos, n_neg = int(p.sum()), int((~p).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    r = rankdata(s)
    return float((r[p].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def enrichment(scores: np.ndarray, positive: np.ndarray, top_fraction: float) -> dict:
    ok = np.isfinite(scores)
    s, p = scores[ok], positive[ok].astype(bool)
    k = max(1, int(round(top_fraction * len(s))))
    top = np.argsort(-s, kind="stable")[:k]
    captured = int(p[top].sum())
    expected = p.sum() * k / len(s)
    return {"top_fraction": top_fraction, "hotspots_captured": captured, "hotspots_total": int(p.sum()),
            "expected_by_chance": round(float(expected), 2), "ratio_vs_chance": round(captured / expected, 2) if expected else None}


def mean_percentile(scores: np.ndarray, positive: np.ndarray) -> float | None:
    ok = np.isfinite(scores)
    s, p = scores[ok], positive[ok].astype(bool)
    if p.sum() == 0:
        return None
    pct = (rankdata(s) - 0.5) / len(s)
    return float(pct[p].mean())


def sensitivity(table: CellTable, n: int = 200, perturb: float = 0.5, seed: int = 0, top_fraction: float = 0.1) -> dict:
    """How much does the cell ranking change if every weight is randomly scaled by U(1-perturb, 1+perturb)?"""
    rng = np.random.default_rng(seed)
    base = table.susceptibility
    ok = base.notna().to_numpy()
    base_v = base.to_numpy()[ok]
    k = max(1, int(top_fraction * ok.sum()))
    base_top = set(np.argsort(-base_v)[:k])
    rhos, overlaps = [], []
    for _ in range(n):
        w = {f: s["weight"] * rng.uniform(1 - perturb, 1 + perturb) for f, s in M.SUSCEPTIBILITY.items()}
        v = susceptibility(table.ranks, w).to_numpy()[ok]
        rhos.append(float(np.corrcoef(rankdata(base_v), rankdata(v))[0, 1]))
        overlaps.append(len(base_top & set(np.argsort(-v)[:k])) / k)
    return {"n_trials": n, "weight_perturbation": perturb, "spearman_mean": round(float(np.mean(rhos)), 4), "spearman_min": round(float(np.min(rhos)), 4),
            "top_decile_overlap_mean": round(float(np.mean(overlaps)), 4), "top_decile_overlap_min": round(float(np.min(overlaps)), 4)}


def load_hotspots_csv(path: Path) -> pd.DataFrame:
    """CSV with columns lat, lon (and optional name). Raises ValueError with a clear message on bad input."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"lat", "lon"} <= set(df.columns):
        raise ValueError("CSV must have 'lat' and 'lon' columns")
    df["lat"], df["lon"] = pd.to_numeric(df["lat"], errors="coerce"), pd.to_numeric(df["lon"], errors="coerce")
    bad = df[df["lat"].isna() | df["lon"].isna() | ~df["lat"].between(-90, 90) | ~df["lon"].between(-180, 180)]
    if len(bad):
        raise ValueError(f"{len(bad)} row(s) have missing or out-of-range coordinates (first at CSV row {bad.index[0] + 2})")
    if df.empty:
        raise ValueError("CSV has no rows")
    return df


def backtest(table: CellTable, hotspots: pd.DataFrame, resolution: int = 9) -> dict:
    import h3

    cells = [h3.latlng_to_cell(float(r.lat), float(r.lon), resolution) for r in hotspots.itertuples()]
    unique = set(cells)
    in_table = {c for c in unique if c in table.df.index and np.isfinite(table.susceptibility.get(c, np.nan))}
    scores = table.susceptibility.to_numpy()
    positive = table.susceptibility.index.isin(in_table)
    auc = auc_presence(scores, positive)
    out = {"hotspots_in_file": int(len(hotspots)), "distinct_cells": len(unique), "cells_scored": len(in_table),
           "outside_study_area_or_no_data": len(unique) - len(in_table), "auc_vs_all_other_cells": None if auc is None else round(auc, 4),
           "mean_percentile_of_hotspot_cells": None if (m := mean_percentile(scores, positive)) is None else round(m, 4),
           "enrichment_top10pct": enrichment(scores, positive, 0.10), "enrichment_top20pct": enrichment(scores, positive, 0.20), "caveats": [
               "Presence-only test: non-hotspot cells are treated as negatives although they were never verified as dry, so AUC is "
               "biased downward and should be read as agreement with the list, not as flood-prediction accuracy.",
               "It evaluates terrain susceptibility only (a chronic-hotspot list says nothing about rainfall timing).",
               "Hotspot lists reflect where water was REPORTED, which depends on traffic and reporting, not only on physics."]}
    if len(in_table) < 30:
        out["caveats"].insert(0, f"Only {len(in_table)} scored hotspot cells: far too few for a stable estimate; treat as anecdotal.")
    return out
