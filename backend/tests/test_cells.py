import numpy as np
import pytest

for m in ("rasterio", "geopandas", "h3", "scipy", "shapely", "pyogrio"):
    pytest.importorskip(m)
import geopandas as gpd
from shapely.geometry import MultiPolygon, box

from app.geo.cells import build_cells, cells_for_geometry
from app.geo.grid import weather_grid
from tests.test_terrain import write_dem


def test_cells_for_polygon_and_multipolygon_and_hole():
    sq = box(78.40, 17.40, 78.45, 17.45)
    n = len(cells_for_geometry(sq, 9))
    assert 200 < n < 350  # ~30 km2 / 0.108 km2
    both = MultiPolygon([sq, box(78.50, 17.40, 78.55, 17.45)])
    assert len(cells_for_geometry(both, 9)) > 1.8 * n
    holed = box(78.40, 17.40, 78.45, 17.45).difference(box(78.41, 17.41, 78.44, 17.44))
    assert 0.5 * n < len(cells_for_geometry(holed, 9)) < 0.75 * n  # hole removes 9/25 = 36% of the area


def test_cells_for_geometry_rejects_non_polygon():
    from shapely.geometry import Point
    with pytest.raises(ValueError):
        cells_for_geometry(Point(78, 17), 9)


def test_build_cells_end_to_end_on_synthetic_dem(tmp_path):
    arr = np.linspace(600, 500, 200)[:, None] * np.ones((1, 200))
    write_dem(tmp_path / "dem.tif", arr)
    # study area deliberately extends beyond the DEM -> uncovered cells must be flagged, not filled
    geom = box(78.40, 17.35, 78.46, 17.45)
    pts = weather_grid((78.25, 17.2, 78.65, 17.6), 0.1)
    out = tmp_path / "out" / "cells.gpkg"
    info = build_cells(tmp_path / "dem.tif", geom, pts, 9, out)
    gdf = gpd.read_file(out)
    assert info["cells"] == len(gdf) and gdf["cell_id"].is_unique
    assert {"elevation_m_mean", "slope_deg_mean", "rel_elev_m_mean", "weather_point_id", "weather_point_dist_km", "low_coverage"} <= set(gdf.columns)
    cov, unc = gdf[~gdf.low_coverage], gdf[gdf.low_coverage]
    assert len(cov) > 0 and len(unc) > 0 and info["low_coverage_cells"] == len(unc)
    feats = ["elevation_m_mean", "elevation_m_min", "slope_deg_mean", "rel_elev_m_mean"]
    assert unc[feats].isna().all().all()                            # thin/no data -> NaN, never invented
    assert cov[feats].notna().all().all() and (cov["n_samples"] >= 5).all()
    assert cov["elevation_m_mean"].between(500, 600).all()
    assert gdf["weather_point_id"].isin([p.point_id for p in pts]).all()
    assert gdf.crs.to_epsg() == 4326 and gdf.geometry.is_valid.all()
    assert out.with_suffix(".features.json").exists()


def test_build_cells_missing_dem_coverage_entirely(tmp_path):
    write_dem(tmp_path / "dem.tif", np.full((50, 50), 520.0))
    far = box(79.50, 18.00, 79.52, 18.02)
    info = build_cells(tmp_path / "dem.tif", far, weather_grid((78.25, 17.2, 78.65, 17.6), 0.1), 9, tmp_path / "c.gpkg")
    assert info["low_coverage_cells"] == info["cells"]            # everything flagged


def test_summarize_cells_and_cli(tmp_path, monkeypatch, capsys):
    # DEM with one deliberate 20 m-deep pit: it must show up as the lowest relative-elevation cell
    arr = np.full((200, 200), 520.0); arr[95:105, 95:105] = 500.0
    write_dem(tmp_path / "dem.tif", arr)
    geom = box(78.40, 17.39, 78.46, 17.45)
    out = tmp_path / "cells.gpkg"
    build_cells(tmp_path / "dem.tif", geom, weather_grid((78.25, 17.2, 78.65, 17.6), 0.1), 9, out)
    from app.geo.cells import summarize_cells
    info = summarize_cells(gpd.read_file(out), n_lowest=3)
    assert info["cells"] > 100 and info["low_coverage"] == 0
    f = info["features"]["rel_elev_m_mean"]
    assert f["min"] < -3 and f["min"] <= f["p1"] <= f["median"] <= f["p99"] <= f["max"]
    pit = info["lowest_relative_elevation"][0]
    assert 17.41 < pit["lat"] < 17.43 and 78.42 < pit["lon"] < 78.44        # the pit centre is ~(17.42, 78.43)
    assert len(info["lowest_relative_elevation"]) == 3
    # CLI end to end on the same file
    from app.cli import main
    monkeypatch.setenv("FLOODSENSE_DATA_DIR", str(tmp_path))
    from app.config import get_settings; get_settings.cache_clear()
    (tmp_path / "processed").mkdir(); out.replace(tmp_path / "processed" / "cells_res9.gpkg")
    assert main(["cells-summary"]) == 0
    text = capsys.readouterr().out
    assert "rel_elev_m_mean" in text and "google.com/maps?q=" in text
    get_settings.cache_clear()
