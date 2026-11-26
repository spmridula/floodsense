import numpy as np
import pandas as pd
import pytest

from app.risk.evaluation import auc_presence, backtest, enrichment, load_hotspots_csv, mean_percentile, sensitivity
from tests.risk_helpers import synthetic_table


def test_auc_perfect_reversed_and_chance():
    s = np.arange(100.0)
    pos_top = s >= 90
    assert auc_presence(s, pos_top) == 1.0 and auc_presence(-s, pos_top) == 0.0
    rng = np.random.default_rng(0)
    assert abs(auc_presence(rng.random(5000), rng.random(5000) < 0.05) - 0.5) < 0.08
    assert auc_presence(s, np.zeros(100, bool)) is None and auc_presence(s, np.ones(100, bool)) is None


def test_auc_ignores_nan_scores_and_handles_ties():
    s = np.array([1.0, 1.0, 1.0, np.nan, 2.0])
    # NaN row dropped -> hotspot score 1 vs non-hotspots [1, 1, 2]: ties give half credit each, losing to 2 gives none
    assert auc_presence(s, np.array([True, False, False, True, False])) == pytest.approx((0.5 + 0.5 + 0.0) / 3)


def test_enrichment_and_mean_percentile():
    s = np.arange(100.0); pos = s >= 95
    e = enrichment(s, pos, 0.10)
    assert e["hotspots_captured"] == 5 and e["expected_by_chance"] == 0.5 and e["ratio_vs_chance"] == 10.0
    assert mean_percentile(s, pos) == pytest.approx(0.975)
    assert mean_percentile(s, np.zeros(100, bool)) is None


def test_sensitivity_zero_perturbation_is_identical_and_grows_with_perturbation():
    t = synthetic_table(1)
    z = sensitivity(t, n=10, perturb=0.0)
    assert z["spearman_min"] == pytest.approx(1.0) and z["top_decile_overlap_min"] == 1.0
    mild, wild = sensitivity(t, n=60, perturb=0.3, seed=1), sensitivity(t, n=60, perturb=0.9, seed=1)
    assert 0.5 < wild["spearman_mean"] < mild["spearman_mean"] < 1.0
    assert wild["top_decile_overlap_mean"] < mild["top_decile_overlap_mean"]
    assert sensitivity(t, n=20, perturb=0.5, seed=5) == sensitivity(t, n=20, perturb=0.5, seed=5)     # reproducible


def test_load_hotspots_csv_validation(tmp_path):
    f = tmp_path / "h.csv"
    f.write_text("Name,LAT,Lon\nA,17.4,78.4\nB,17.41,78.41\n"); df = load_hotspots_csv(f)
    assert list(df.columns) == ["name", "lat", "lon"] and len(df) == 2                       # case-insensitive headers
    f.write_text("x,y\n1,2\n")
    with pytest.raises(ValueError, match="'lat' and 'lon'"): load_hotspots_csv(f)
    f.write_text("lat,lon\n17.4,78.4\n95,78.4\n")
    with pytest.raises(ValueError, match="CSV row 3"): load_hotspots_csv(f)
    f.write_text("lat,lon\n17.4,abc\n")
    with pytest.raises(ValueError, match="missing or out-of-range"): load_hotspots_csv(f)
    f.write_text("lat,lon\n")
    with pytest.raises(ValueError, match="no rows"): load_hotspots_csv(f)


def test_backtest_detects_skill_chance_and_counts_unmatched():
    t = synthetic_table(2)
    top = t.susceptibility.nlargest(40).index
    good = pd.DataFrame({"lat": t.df.loc[top, "lat"].to_numpy(), "lon": t.df.loc[top, "lon"].to_numpy()})
    r = backtest(t, good)
    assert r["auc_vs_all_other_cells"] > 0.95 and r["enrichment_top10pct"]["ratio_vs_chance"] > 5
    assert not any("far too few" in c for c in r["caveats"])
    rng = np.random.default_rng(3)
    pick = rng.choice(t.df.index.to_numpy(), 80, replace=False)
    rand = pd.DataFrame({"lat": t.df.loc[pick, "lat"].to_numpy(), "lon": t.df.loc[pick, "lon"].to_numpy()})
    assert 0.35 < backtest(t, rand)["auc_vs_all_other_cells"] < 0.65
    far = pd.DataFrame({"lat": [28.6, 28.61], "lon": [77.2, 77.21]})                           # Delhi: outside the study area
    rf = backtest(t, far)
    assert rf["cells_scored"] == 0 and rf["outside_study_area_or_no_data"] == 2 and rf["auc_vs_all_other_cells"] is None
    assert any("far too few" in c for c in rf["caveats"]) and any("Presence-only" in c for c in rf["caveats"])
