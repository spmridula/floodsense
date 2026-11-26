import json

import httpx
import pytest

from app.geo.fetch import FetchError, dem_tile_names, dem_tile_url, download_file, graph_quality

HYD = (78.25, 17.20, 78.65, 17.60)


def test_hyderabad_needs_exactly_one_tile_with_documented_name():
    assert dem_tile_names(HYD) == ["Copernicus_DSM_COG_10_N17_00_E078_00_DEM"]
    assert dem_tile_url("Copernicus_DSM_COG_10_N17_00_E078_00_DEM") == (
        "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N17_00_E078_00_DEM/Copernicus_DSM_COG_10_N17_00_E078_00_DEM.tif")


def test_bbox_crossing_integer_degrees_needs_multiple_tiles():
    names = dem_tile_names((77.8, 16.9, 78.2, 17.1))
    assert len(names) == 4 and any("N16_00_E077" in n for n in names) and any("N17_00_E078" in n for n in names)


def test_bbox_exactly_on_tile_edge_does_not_pull_extra_tile():
    assert dem_tile_names((78.0, 17.0, 79.0, 18.0)) == ["Copernicus_DSM_COG_10_N17_00_E078_00_DEM"]


def test_southern_western_hemisphere_naming():
    # lower-left corner convention: lat -33.5 lies in the tile whose corner is -34; lon -70.5 in the tile with corner -71
    assert dem_tile_names((-70.5, -33.5, -70.2, -33.2)) == ["Copernicus_DSM_COG_10_S34_00_W071_00_DEM"]
    four = dem_tile_names((-70.5, -33.5, -69.5, -32.5))
    assert sorted(four) == sorted(f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM" for ns in ("S34", "S33") for ew in ("W071", "W070"))


def test_90m_uses_other_bucket_and_invalid_inputs():
    assert "copernicus-dem-90m" in dem_tile_url("x", 90)
    with pytest.raises(ValueError): dem_tile_names(HYD, 10)
    with pytest.raises(ValueError): dem_tile_names((78.6, 17.2, 78.2, 17.6))


def test_download_success_is_atomic_no_part_files(tmp_path):
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 5000))
    p = download_file("https://e.test/a.tif", tmp_path / "d" / "a.tif", t)
    assert p.read_bytes() == b"x" * 5000 and not list((tmp_path / "d").glob("*.part"))


@pytest.mark.parametrize("status", [403, 404])
def test_download_missing_tile_has_actionable_message(tmp_path, status):
    t = httpx.MockTransport(lambda r: httpx.Response(status))
    with pytest.raises(FetchError, match="not be publicly released"):
        download_file("https://e.test/a.tif", tmp_path / "a.tif", t)
    assert not (tmp_path / "a.tif").exists()


def test_download_empty_and_network_error(tmp_path):
    with pytest.raises(FetchError, match="empty"):
        download_file("https://e.test/a.tif", tmp_path / "a.tif", httpx.MockTransport(lambda r: httpx.Response(200, content=b"")))
    def boom(r): raise httpx.ConnectError("no route")
    with pytest.raises(FetchError, match="internet"):
        download_file("https://e.test/a.tif", tmp_path / "b.tif", httpx.MockTransport(boom))


def test_graph_quality():
    ok = graph_quality(1000, 2500, 980)
    assert ok["warnings"] == [] and ok["largest_component_fraction"] == 0.98
    assert graph_quality(1000, 2500, 500)["warnings"]
    with pytest.raises(FetchError): graph_quality(0, 0, 0)


def test_check_boundary_area_and_warnings():
    gpd = pytest.importorskip("geopandas"); from shapely.geometry import box, Point
    from app.geo.fetch import check_boundary
    ok = check_boundary(gpd.GeoDataFrame(geometry=[box(78.3, 17.3, 78.55, 17.55)], crs="EPSG:4326"))
    assert 700 < ok["area_km2"] < 800 and ok["warnings"] == []          # 0.25 deg square near 17.4N ~ 745 km2
    tiny = check_boundary(gpd.GeoDataFrame(geometry=[box(78.3, 17.3, 78.31, 17.31)], crs="EPSG:4326"))
    assert tiny["warnings"]
    with pytest.raises(FetchError): check_boundary(gpd.GeoDataFrame(geometry=[Point(78, 17)], crs="EPSG:4326"))
    with pytest.raises(FetchError): check_boundary(gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))
