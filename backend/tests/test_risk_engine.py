from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.risk import methodology as M
from app.risk.engine import CellTableError, categorize, compute, explain, hazard, make_table, percentile_ranks, susceptibility
from app.risk.rain import PointSeries, RainField, apply_idw, build_rain_field, idw_matrix
from tests.risk_helpers import FEATS, synthetic_df, synthetic_table

T = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def field(table, mm, acc=None, hours=24):
    n = table.n
    return RainField(np.full(n, float(mm)), np.full(n, float(mm if acc is None else acc)), T, hours, 20)


def test_methodology_weights_sum_to_one_and_bounds_ordered():
    assert sum(s["weight"] for s in M.SUSCEPTIBILITY.values()) == pytest.approx(1.0)
    bounds = [b for b, _ in M.CATEGORY_BOUNDS]
    assert bounds == sorted(bounds) and M.CATEGORIES == ["low", "moderate", "high", "critical"]
    assert "NOT a probability" in M.SCORE_SEMANTICS


def test_hazard_anchors_and_monotonicity():
    h = hazard(np.array([0, 12, 20, 50, 80, 500.0]), np.array([0, 15.6, 64.5, 115.6, 204.5, 999.0]))
    assert list(np.round(h["h_intensity"], 3)) == [0, 0.4, 0.6, 0.9, 1.0, 1.0]
    assert list(np.round(h["h_accumulation"], 3)) == [0, 0.25, 0.5, 0.75, 1.0, 1.0]
    x = np.linspace(0, 150, 600)
    assert np.all(np.diff(hazard(x, x)["hazard"]) >= -1e-12)


def test_hazard_takes_max_and_ignores_missing_accumulation():
    h = hazard(np.array([5.0, 5.0, np.nan]), np.array([100.0, np.nan, 100.0]))["hazard"]
    expected_acc = 0.5 + 0.25 * (100 - 64.5) / (115.6 - 64.5)       # linear between the "heavy" and "very heavy" anchors
    assert h[0] == pytest.approx(expected_acc) and expected_acc > 5 / 12 * 0.4   # accumulation beats intensity here
    assert h[1] == pytest.approx(5 / 12 * 0.4)         # intensity alone when accumulation unknown
    assert np.isnan(h[2])                              # intensity unknown -> hazard unknown, never defaulted


def test_categories_at_boundaries():
    got = categorize(np.array([0, .1999, .20, .3999, .40, .6499, .65, 1.0, np.nan]))
    assert list(got[:-1]) == ["low", "low", "moderate", "moderate", "high", "high", "critical", "critical"] and got[-1] is None


def test_susceptibility_direction_and_range():
    df = pd.DataFrame({"cell_id": list("abcde"), "lat": 17.4, "lon": 78.4, "low_coverage": False,
                       "rel_elev_m_mean": [-9, -3, 0, 3, 9], "elevation_m_mean": [480, 500, 520, 540, 560],
                       "depression_depth_m_max": [4, 3, 2, 1, 0], "flow_acc_log10_m2_max": [6, 5, 4, 3, 2], "slope_deg_mean": [0.5, 1, 2, 4, 8]})
    t = make_table(df)
    s = t.susceptibility
    assert s["a"] == pytest.approx(1.0) and s["a"] > s["b"] > s["c"] > s["d"] > s["e"] and s["e"] == pytest.approx(0.2)
    assert s.between(0, 1).all()


def test_missing_any_feature_gives_nan_not_partial_score():
    t = synthetic_table(nan_cells=3)
    assert t.susceptibility.iloc[:3].isna().all() and t.susceptibility.iloc[3:].notna().all()


def test_make_table_rejects_outdated_columns():
    with pytest.raises(CellTableError, match="build-cells"):
        make_table(synthetic_df().drop(columns=["flow_acc_log10_m2_max"]))


def test_dry_weather_is_low_everywhere_and_score_is_exact_product():
    t = synthetic_table()
    dry = compute(t, field(t, 0.0))
    assert (dry["score"] == 0).all() and (dry["category"] == "low").all()
    r = compute(t, field(t, 20.0, acc=10.0))
    i = r["susceptibility"].idxmax()
    assert r.at[i, "score"] == pytest.approx(r.at[i, "susceptibility"] * 0.6)      # 20 mm/h -> H = 0.6


def test_more_rain_never_lowers_any_cell_score():
    t = synthetic_table()
    prev = compute(t, field(t, 0.0))["score"].to_numpy()
    for mm in [1, 5, 12, 20, 35, 50, 80, 120]:
        cur = compute(t, field(t, mm, acc=mm * 2))["score"].to_numpy()
        assert np.all(cur >= prev - 1e-12)
        prev = cur


def test_extreme_rain_reaches_critical_only_on_susceptible_cells():
    t = synthetic_table()
    r = compute(t, field(t, 80.0, acc=250))
    crit = r[r.category == "critical"]
    assert 0 < len(crit) < len(r) and crit["susceptibility"].min() >= 0.65 - 1e-9
    assert (r.loc[r.susceptibility < 0.2, "category"] == "low").all() or (r["susceptibility"].min() >= 0.2)


def test_unknown_rain_gives_none_category():
    t = synthetic_table()
    r = compute(t, RainField(np.full(t.n, np.nan), np.full(t.n, np.nan), T, 0, 0))
    assert r["score"].isna().all() and r["category"].isna().all()


# ---- interpolation ----
def test_idw_exact_hit_midpoint_missing_and_far_points():
    pl, po = np.array([17.40, 17.40, 17.40, 17.40, 17.40]), np.array([78.40, 78.50, 78.60, 78.70, 78.80])
    W = idw_matrix([17.40], [78.40], pl, po)
    assert W.sum() == pytest.approx(1) and W[0, 0] == 1.0                       # sits on point 0 -> exactly that point
    v = np.array([1.0, 2.0, 3.0, 4.0, 1000.0])
    assert apply_idw(W, v)[0] == 1.0
    mid = idw_matrix([17.40], [78.45], pl, po)
    assert apply_idw(mid, v)[0] == pytest.approx(1.5, abs=0.4) and apply_idw(mid, v)[0] < 4          # far outlier (1000) ignored (k=4 nearest)
    assert (idw_matrix([17.4], [78.45], pl, po) > 0).sum() == 4
    assert apply_idw(mid, np.array([np.nan, 2.0, 3.0, 4.0, 1000.0]))[0] > 1.5  # missing point dropped, others renormalised
    assert np.isnan(apply_idw(mid, np.full(5, np.nan))[0])


def test_idw_rejects_no_points():
    with pytest.raises(ValueError):
        idw_matrix([17.4], [78.4], [], [])


def series(values_by_hour, lat=17.4, lon=78.4, pid="p"):
    return PointSeries(pid, lat, lon, dict(values_by_hour))


def test_rain_field_window_sum_and_hours_available():
    hist = {T - timedelta(hours=i): 1.0 for i in range(24)}
    f = build_rain_field([17.4], [78.4], [series(hist)], T, 0)
    assert f.intensity_mm[0] == 1.0 and f.accumulation_mm[0] == 24.0 and f.accumulation_hours_available == 24
    partial = {T - timedelta(hours=i): 2.0 for i in range(6)}
    g = build_rain_field([17.4], [78.4], [series(partial)], T, 0)
    assert g.accumulation_mm[0] == 12.0 and g.accumulation_hours_available == 6       # flagged upstream as underestimated


def test_rain_field_missing_target_hour_is_unknown_and_horizon_shifts_target():
    hist = {T - timedelta(hours=i): 1.0 for i in range(1, 24)}                         # target hour itself missing
    f = build_rain_field([17.4], [78.4], [series(hist)], T, 0)
    assert np.isnan(f.intensity_mm[0]) and np.isnan(f.accumulation_mm[0])
    data = {T + timedelta(hours=h): float(h) for h in range(0, 4)}
    g = build_rain_field([17.4], [78.4], [series(data)], T, 2)
    assert g.intensity_mm[0] == 2.0 and g.target_time == T + timedelta(hours=2)
    with pytest.raises(ValueError):
        build_rain_field([17.4], [78.4], [series(data)], T, -1)


# ---- explanation ----
def test_explanation_is_traceable():
    t = synthetic_table()
    r = compute(t, field(t, 30.0, acc=80))
    cid = r["susceptibility"].idxmax()
    ex = explain(t, r.loc[cid], 24)
    contribs = [f["contribution"] for f in ex["terrain_factors"]]
    assert contribs == sorted(contribs, reverse=True)
    assert sum(contribs) == pytest.approx(r.at[cid, "susceptibility"], abs=1e-3)       # factors add up to S exactly
    assert {f["kind"] for f in ex["terrain_factors"]} <= {"proxy", "derived_from_dem"}
    assert "not a gauge reading" in ex["rainfall"]["text"] and ex["rainfall"]["kind"] == "modelled_forecast_interpolated"
    assert r.at[cid, "category"] in ex["summary"] and "probab" not in ex["summary"].lower()
    nan = r.loc[cid].copy(); nan["score"] = np.nan
    assert "unavailable" in explain(t, nan, 0)["summary"]
