import httpx
import pytest

from app.ingest.weather import WeatherError, parse_response
from tests.weather_helpers import PTS, client, good_payload, hours, location, utc

NOW = utc(2026, 10, 21, 12, 30)


def ok_handler(request):
    assert request.url.params["hourly"] == "precipitation" and request.url.params["timezone"] == "GMT"
    assert request.url.params["latitude"].count(",") == 1
    return httpx.Response(200, json=good_payload(NOW))


def test_success_parses_all_points_with_utc_times():
    r = client(ok_handler).fetch(PTS)
    assert r.points_ok == 2 and r.rejected == 0 and len(r.readings) == 2 * 6
    assert all(x.valid_time.tzinfo is not None for x in r.readings)
    assert {x.point_id for x in r.readings} == {p.point_id for p in PTS}


def test_single_location_object_response_is_accepted():
    r = parse_response(good_payload(NOW, n_points=1), PTS[:1])
    assert r.points_ok == 1


def test_location_count_mismatch_rejected():
    with pytest.raises(WeatherError, match="2 locations for 1 requested|1 locations for 2"):
        parse_response(good_payload(NOW, 1), PTS)


def test_timeout_retries_then_fails_cleanly():
    calls = []
    def h(req):
        calls.append(1); raise httpx.ReadTimeout("slow")
    c = client(h, retries=2)
    with pytest.raises(WeatherError, match="after 3 attempts"):
        c.fetch(PTS)
    assert len(calls) == 3 and len(c.sleeps) == 2  # backoff between attempts, not after the last


def test_429_then_success_recovers():
    seq = iter([httpx.Response(429), httpx.Response(200, json=good_payload(NOW))])
    r = client(lambda req: next(seq)).fetch(PTS)
    assert r.points_ok == 2


def test_5xx_retried_but_400_not():
    calls = []
    def h(req):
        calls.append(1); return httpx.Response(400, json={"error": True, "reason": "bad"})
    with pytest.raises(WeatherError, match="rejected request"):
        client(h, retries=3).fetch(PTS)
    assert len(calls) == 1


def test_invalid_json_body():
    with pytest.raises(WeatherError, match="invalid JSON"):
        client(lambda r: httpx.Response(200, content=b"<html>oops</html>")).fetch(PTS)


@pytest.mark.parametrize("payload,msg", [
    ([{"hourly": None}, {"hourly": None}], "missing hourly"),
    ([location(hours(NOW), [1] * 6, unit="inch")] * 2, "unit"),
    ([location(hours(NOW), [1, 2])] * 2, "different lengths"),
    ([{"error": True, "reason": "limit"}] * 2, "provider error"),
])
def test_malformed_payloads(payload, msg):
    with pytest.raises(WeatherError, match=msg):
        parse_response(payload, PTS)


def test_bad_values_dropped_not_stored():
    t = hours(NOW, 4, 2)  # 6 timestamps
    vals = [1.0, -2.0, None, 9999, float("nan"), True]
    r = parse_response([location(t, vals), location(t, [0.1] * 6)], PTS)
    p0 = [x for x in r.readings if x.point_id == PTS[0].point_id]
    assert r.rejected == 4  # negative, absurd, NaN, bool
    assert [x.precipitation_mm for x in p0] == [1.0, None]  # None kept as explicit "missing"


def test_duplicate_timestamp_dropped():
    t = hours(NOW)[:2] + hours(NOW)[:1]
    r = parse_response([location(t, [1, 2, 3])] * 2, PTS)
    assert r.rejected == 2 and len(r.readings) == 4


def test_all_missing_is_failure_not_empty_success():
    with pytest.raises(WeatherError, match="no valid precipitation"):
        parse_response([location(hours(NOW), [None] * 6)] * 2, PTS)
