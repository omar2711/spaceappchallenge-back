"""B3 endpoint tests (offline: local ephemerides and static JSON)."""
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_moon_sites_cited():
    body = client.get("/moon/sites").json()
    ids = {s["id"] for s in body["sites"]}
    assert {"apollo11", "apollo17", "haworth", "malapert_massif"} <= ids and "apollo13" not in ids
    assert all(s.get("source") for s in body["sites"])
    assert "DE421" in body["frame"]


def test_moon_visibility_fast_and_consistent():
    t0 = time.time()
    r = client.get("/moon/visibility", params={"site": "haworth", "start": "2026-12-01", "days": 30, "step_min": 10})
    assert r.status_code == 200 and time.time() - t0 < 2
    s = r.json()["summary"]
    assert 0 <= s["sunlit_fraction"] <= 1 and 0 <= s["earth_visible_fraction"] <= 1
    assert s["sun_and_earth_hours"] <= min(s["sunlit_hours"], s["earth_visible_hours"]) + 0.01


def test_moon_apollo11_matches_horizons():
    # JPL Horizons, Sun from Apollo 11 LM site (0.67416 N, 23.47314 E) at 2026-11-15 00:00 UTC: EL -0.977, AZ 91.546
    r = client.get("/moon/visibility", params={"site": "apollo11", "start": "2026-11-15T00:00", "days": 1, "step_min": 60})
    ser = r.json()["series"]
    assert abs(ser["sun_elevation_deg"][0] - (-0.977)) < 0.01 and abs(ser["sun_azimuth_deg"][0] - 91.546) < 0.01
    assert abs(ser["earth_elevation_deg"][0] - 63.683) < 0.01


def test_moon_errors():
    assert client.get("/moon/visibility", params={"site": "nope", "start": "2026-12-01"}).status_code == 404
    assert client.get("/moon/visibility", params={"site": "apollo11", "start": "2026-12-01", "days": 31}).status_code == 422
    assert client.get("/moon/visibility", params={"site": "apollo11", "start": "ayer"}).status_code == 422
