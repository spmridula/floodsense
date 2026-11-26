import pytest

from app.geo.grid import GridPoint, make_point_id, nearest_point, validate_bbox, weather_grid

BBOX = (78.25, 17.20, 78.65, 17.60)


def test_weather_grid_covers_bbox_inclusive():
    g = weather_grid(BBOX, 0.1)
    assert len(g) == 25
    assert min(p.lat for p in g) == 17.2 and max(p.lat for p in g) == 17.6
    assert min(p.lon for p in g) == 78.25 and max(p.lon for p in g) == 78.65
    assert len({p.point_id for p in g}) == 25  # ids unique


def test_grid_step_larger_than_bbox_gives_single_row():
    assert len(weather_grid((78.0, 17.0, 78.1, 17.1), 0.5)) == 1


@pytest.mark.parametrize("bad", [(78.6, 17.2, 78.2, 17.6), (78, 17, 78, 18), (-200, 0, 10, 10), (0, -95, 10, 10)])
def test_invalid_bbox_rejected(bad):
    with pytest.raises(ValueError):
        validate_bbox(bad)


def test_nonpositive_step_rejected():
    with pytest.raises(ValueError):
        weather_grid(BBOX, 0)


def test_nearest_point_and_empty():
    pts = [GridPoint("a", 17.2, 78.25), GridPoint("b", 17.6, 78.65)]
    assert nearest_point(17.55, 78.6, pts).point_id == "b"
    with pytest.raises(ValueError):
        nearest_point(17, 78, [])


def test_point_id_format():
    assert make_point_id(17.2, 78.25) == "17.20_78.25"


def test_grid_covers_non_divisible_bbox_without_leaving_it():
    # the real Hyderabad boundary box returned by fetch-boundary (not a multiple of the step)
    b = (78.2387, 17.2916, 78.6224, 17.5608)
    g = weather_grid(b, 0.1)
    assert len(g) == 4 * 5 and len({p.point_id for p in g}) == len(g)
    assert min(p.lat for p in g) == b[1] and max(p.lat for p in g) == b[3]    # both edges covered...
    assert min(p.lon for p in g) == b[0] and max(p.lon for p in g) == b[2]
    assert all(b[0] <= p.lon <= b[2] and b[1] <= p.lat <= b[3] for p in g)    # ...and nothing outside the box
    lats = sorted({p.lat for p in g}); lons = sorted({p.lon for p in g})
    assert max(b - a for a, b in zip(lats, lats[1:])) <= 0.1 + 1e-9           # spacing never wider than requested
    assert max(b - a for a, b in zip(lons, lons[1:])) <= 0.1 + 1e-9


def test_tiny_bbox_gets_single_centre_point():
    g = weather_grid((78.0, 17.0, 78.1, 17.1), 0.5)
    assert len(g) == 1 and (g[0].lat, g[0].lon) == (17.05, 78.05)
