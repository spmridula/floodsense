import math
import time

import numpy as np
import pytest

from app.geo.hydro import fill_depressions, flow_accumulation, flow_directions, hydro_features


def test_fill_raises_a_pit_to_its_spill_level_only():
    dem = np.full((9, 9), 100.0); dem[4, 4] = 90.0
    f = fill_depressions(dem)
    assert f[4, 4] == pytest.approx(100.0, abs=0.01)           # pit filled to the rim
    assert np.all(f >= dem) and np.abs(f - dem).sum() < 10.1    # nothing else meaningfully changed


def test_fill_leaves_a_draining_slope_untouched():
    dem = 100.0 - np.tile(np.arange(10.0), (10, 1))
    assert np.allclose(fill_depressions(dem), dem)


def test_pit_with_an_outlet_channel_is_not_a_depression():
    dem = np.full((9, 9), 100.0); dem[4, 4] = 90.0; dem[4, 5] = 95.0; dem[4, 6] = 92.0; dem[4, 7] = 85.0; dem[4, 8] = 80.0
    f = fill_depressions(dem)
    assert f[4, 4] == pytest.approx(95.0, abs=0.01)             # spills over the 95 m saddle, not the 100 m rim


def test_fill_is_idempotent_and_handles_nodata_as_outlet():
    rng = np.random.default_rng(1)
    dem = 500 + np.cumsum(rng.normal(0, 0.5, (30, 30)), axis=0) + rng.normal(0, 0.3, (30, 30))
    f = fill_depressions(dem)
    assert np.allclose(fill_depressions(f), f, atol=1e-3)
    dem2 = np.full((9, 9), 100.0); dem2[4, 4] = 90.0; dem2[4, 5] = np.nan   # pit next to nodata can drain into it
    f2 = fill_depressions(dem2)
    assert f2[4, 4] < 90.01 and np.isnan(f2[4, 5])


def test_flow_accumulation_on_eastward_plane_counts_upstream_cells():
    dem = 100.0 - np.tile(np.arange(10.0), (7, 1))
    f = fill_depressions(dem)
    acc = flow_accumulation(f, flow_directions(f, 30, 30))
    assert np.array_equal(acc, np.tile(np.arange(1.0, 11.0), (7, 1)))      # column c collects c+1 cells


def test_flow_converges_in_a_v_valley():
    xx, yy = np.meshgrid(np.arange(21.0), np.arange(21.0))
    dem = 100 + 2.0 * np.abs(xx - 10) - 0.5 * yy        # valley along x=10, descending southwards (increasing y)
    f = fill_depressions(dem)
    acc = flow_accumulation(f, flow_directions(f, 30, 30))
    assert acc[19, 10] > 5 * acc[19, 3]           # the valley floor collects far more than a hillside cell
    assert acc[20, 10] == 21 * 21                 # every cell in the basin drains out through the valley's last cell


def test_mass_is_conserved_every_cell_drains_to_exactly_one_outlet():
    rng = np.random.default_rng(7)
    dem = 500 + 10 * np.sin(np.linspace(0, 6, 40))[:, None] + 8 * np.cos(np.linspace(0, 5, 40))[None, :] + rng.normal(0, 0.4, (40, 40))
    dem[10:13, 10:13] = np.nan
    f = fill_depressions(dem)
    down = flow_directions(f, 30, 30)
    acc = flow_accumulation(f, down).ravel()
    outlets = (down == -1) & np.isfinite(acc)
    assert acc[outlets].sum() == np.isfinite(dem).sum()


def test_hydro_features_nodata_and_units():
    dem = np.full((9, 9), 100.0); dem[4, 4] = 90.0; dem[0, 0] = np.nan
    h = hydro_features(dem, 30.0, 30.0)
    assert h["depression_depth_m"][4, 4] == pytest.approx(10.0, abs=0.01)
    assert np.isnan(h["depression_depth_m"][0, 0]) and np.isnan(h["flow_acc_log10_m2"][0, 0])
    assert h["flow_acc_log10_m2"][8, 8] >= math.log10(900) - 1e-6          # at least its own 30x30 m


def test_runtime_is_acceptable_at_realistic_size():
    rng = np.random.default_rng(3)
    dem = 500 + np.cumsum(rng.normal(0, 0.2, (400, 400)), axis=0) + rng.normal(0, 0.2, (400, 400))
    t = time.time(); hydro_features(dem, 30.0, 30.0); dt = time.time() - t
    assert dt < 30          # 160k px; the real tile is ~1.5M px, so expect roughly 10x this on your laptop
    print(f"hydro 160k px: {dt:.1f}s")
