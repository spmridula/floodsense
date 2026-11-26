import numpy as np
import pandas as pd
import pytest

for m in ("shapely", "h3", "geopandas", "rasterio", "pyogrio", "scipy"):
    pytest.importorskip(m)
import h3
from shapely.geometry import Polygon, box

from app.geo.cells import build_cells
from app.geo.grid import weather_grid
from app.geo.water import water_fraction
from app.risk import methodology as M
from app.risk.engine import compute, make_table, percentile_ranks
from app.risk.rain import RainField
from tests.risk_helpers import FEATS, synthetic_df
from tests.test_terrain import write_dem


def cell_poly(cell):
    return Polygon([(lo, la) for la, lo in h3.cell_to_boundary(cell)])


def test_water_fraction_full_half_none_and_empty():
    cell = h3.latlng_to_cell(17.43, 78.39, 9)
    poly = cell_poly(cell)
    lat, lon = h3.cell_to_latlng(cell)
    minx, miny, maxx, maxy = poly.bounds
    assert water_fraction([poly], box(minx - 1, miny - 1, maxx + 1, maxy + 1))[0] == pytest.approx(1.0)
    half = water_fraction([poly], box(minx - 1, miny - 1, lon, maxy + 1))[0]
    assert 0.45 < half < 0.55                                          # cut through the centre -> about half
    assert water_fraction([poly], box(79, 18, 79.1, 18.1))[0] == 0.0
    assert len(water_fraction([], box(0, 0, 1, 1))) == 0
    both = water_fraction([poly, cell_poly(h3.latlng_to_cell(17.5, 78.5, 9))], box(minx - 0.001, miny - 0.001, maxx + 0.001, maxy + 0.001))
    assert list(np.round(both, 3)) == [1.0, 0.0]


def test_build_cells_adds_water_fraction_only_when_a_water_layer_is_given(tmp_path):
    yy, xx = np.mgrid[0:200, 0:200].astype(float)
    write_dem(tmp_path / "dem.tif", 540 - 0.05 * yy + np.sin(xx / 15))
    geom, pts = box(78.40, 17.39, 78.46, 17.45), weather_grid((78.25, 17.2, 78.65, 17.6), 0.1)
    plain = build_cells(tmp_path / "dem.tif", geom, pts, 9, tmp_path / "a.gpkg")
    assert plain["water_masked"] is False and plain["water_cells"] is None
    import geopandas as gpd
    assert "water_fraction" not in gpd.read_file(tmp_path / "a.gpkg").columns
    lake = box(78.41, 17.40, 78.43, 17.42)
    wet = build_cells(tmp_path / "dem.tif", geom, pts, 9, tmp_path / "b.gpkg", water_geom=lake)
    g = gpd.read_file(tmp_path / "b.gpkg")
    assert wet["water_masked"] is True and wet["water_cells"] > 5 and g["water_fraction"].between(0, 1).all()
    assert (g["water_fraction"] >= 0.5).sum() == wet["water_cells"] and (g["water_fraction"] == 0).sum() > 50


def test_water_cells_are_excluded_from_ranks_and_never_scored():
    df = synthetic_df(0)
    df["water_fraction"] = 0.0
    wet = df.index[:25]
    df.loc[wet, "water_fraction"] = 0.9
    df.loc[wet, "rel_elev_m_mean"] = -50.0                              # extreme "low-lying" lake surface
    df.loc[wet, "depression_depth_m_max"] = 40.0
    t = make_table(df)
    assert t.water_masked and t.is_water.sum() == 25 and t.susceptibility.iloc[:25].isna().all()
    indexed = df.set_index("cell_id", drop=False)
    expected = percentile_ranks(indexed[~t.is_water])
    assert np.allclose(t.ranks.loc[expected.index].to_numpy(), expected.to_numpy())      # lakes did not shift land percentiles
    r = compute(t, RainField(np.full(t.n, 90.0), np.full(t.n, 250.0), None, 24, 20))
    assert r.loc[t.is_water, "category"].isna().all() and r.loc[~t.is_water, "category"].notna().all()
    assert (r.loc[~t.is_water, "category"] == "critical").any()


def test_partial_water_below_threshold_is_still_scored_and_missing_layer_is_flagged():
    df = synthetic_df(1)
    df["water_fraction"] = 0.0; df.loc[df.index[:5], "water_fraction"] = M.WATER_THRESHOLD - 0.01
    t = make_table(df)
    assert t.is_water.sum() == 0 and t.susceptibility.notna().all() and t.water_masked
    assert make_table(synthetic_df(1)).water_masked is False          # no layer -> not masked, and the API says so
