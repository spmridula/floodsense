import math

import numpy as np
import pytest

pytest.importorskip("rasterio"); pytest.importorskip("scipy"); pytest.importorskip("h3"); pytest.importorskip("pandas")
import rasterio
from rasterio.transform import from_origin

from app.geo.terrain import cell_stats, describe_dem, pixel_size_m, read_dem, relative_elevation, slope_degrees


def test_slope_of_known_plane():
    dem = np.tile(np.arange(20, dtype="float32"), (20, 1))  # +1 m per pixel eastwards
    s = slope_degrees(dem, dx_m=30.0, dy_m=30.0)
    assert np.allclose(s, math.degrees(math.atan(1 / 30)), atol=1e-4)  # 1.909 deg everywhere, incl. edges


def test_flat_is_zero_and_diagonal_adds_components():
    assert np.allclose(slope_degrees(np.full((5, 5), 500.0), 30, 30), 0)
    yy, xx = np.mgrid[0:10, 0:10].astype("float32")
    s = slope_degrees(xx + yy, 30, 30)
    assert np.allclose(s, math.degrees(math.atan(math.sqrt(2) / 30)), atol=1e-4)


def test_slope_nodata_gives_nan_not_invented_values():
    dem = np.full((6, 6), 100.0, dtype="float32"); dem[2, 2] = np.nan
    s = slope_degrees(dem, 30, 30)
    assert np.isnan(s[2, 2])                       # the nodata pixel itself
    assert np.isnan(s[2, 3]) and np.isnan(s[1, 2])  # neighbours whose gradient used it
    assert np.isfinite(s[0, 0]) and np.isfinite(s[4, 4])


def test_slope_input_validation():
    with pytest.raises(ValueError): slope_degrees(np.zeros(5), 30, 30)
    with pytest.raises(ValueError): slope_degrees(np.zeros((1, 5)), 30, 30)
    with pytest.raises(ValueError): slope_degrees(np.zeros((5, 5)), 0, 30)


def test_relative_elevation_pit_is_negative_and_matches_hand_calc():
    dem = np.zeros((11, 11), dtype="float32"); dem[5, 5] = -5
    rel = relative_elevation(dem, window_px=5)
    assert rel[5, 5] == pytest.approx(-4.8, abs=1e-4)  # -5 - (-5/25)
    assert rel[0, 0] == pytest.approx(0, abs=1e-6)


def test_relative_elevation_ignores_nodata_in_mean():
    dem = np.full((9, 9), 10.0, dtype="float32"); dem[4, 4] = np.nan
    rel = relative_elevation(dem, 5)
    assert np.isnan(rel[4, 4]) and rel[4, 5] == pytest.approx(0, abs=1e-5)


def test_pixel_size_shrinks_east_west_with_latitude():
    from affine import Affine
    t = Affine(0.0003, 0, 78.0, 0, -0.0003, 18.0)
    dx0, dy0 = pixel_size_m(t, 0.0); dx17, dy17 = pixel_size_m(t, 17.4)
    assert dx17 < dx0 and dy17 == dy0 and 30 < dy17 < 36


def test_describe_dem_warnings():
    ok = describe_dem(np.full((10, 10), 520.0, dtype="float32"))
    assert ok["warnings"] == []
    bad = np.full((10, 10), 5000.0, dtype="float32"); bad[:3] = np.nan
    w = describe_dem(bad)["warnings"]
    assert len(w) == 2
    with pytest.raises(ValueError):
        describe_dem(np.full((3, 3), np.nan))


def write_dem(path, arr, nodata=-9999.0, crs="EPSG:4326"):
    t = from_origin(78.40, 17.45, 0.0003, 0.0003)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="float32", crs=crs, transform=t, nodata=nodata) as dst:
        dst.write(arr.astype("float32"), 1)
    return t


def test_read_dem_converts_nodata_and_rejects_projected(tmp_path):
    arr = np.full((10, 10), 520.0); arr[0, 0] = -9999.0
    write_dem(tmp_path / "a.tif", arr)
    dem, _ = read_dem(tmp_path / "a.tif")
    assert np.isnan(dem[0, 0]) and dem[1, 1] == 520
    write_dem(tmp_path / "b.tif", arr, crs="EPSG:32644")
    with pytest.raises(ValueError, match="EPSG:4326"):
        read_dem(tmp_path / "b.tif")


def test_cell_stats_recovers_known_gradient(tmp_path):
    # elevation rises 100 m from south to north across 200 rows
    arr = np.linspace(600, 500, 200)[:, None] * np.ones((1, 200))
    t = write_dem(tmp_path / "g.tif", arr)
    dem, t = read_dem(tmp_path / "g.tif")
    g = cell_stats(dem, slope_degrees(dem, 30, 30), relative_elevation(dem), t, resolution=9)
    assert len(g) > 50 and g["n_samples"].min() >= 1
    assert 500 <= g["elevation_m_mean"].min() and g["elevation_m_mean"].max() <= 600
    assert g["elevation_m_min"].le(g["elevation_m_mean"]).all()
    assert g["slope_deg_mean"].mean() > 0
