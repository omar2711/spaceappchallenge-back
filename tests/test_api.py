"""API tests. They use cached data only (no IRSA access): run from the repo root after the pipeline and
`python -m analysis.field_spectrum --prepare-all` have produced data/ and public-data/."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PRESETS = json.loads(Path("public-data/custom/presets.json").read_text(encoding="utf-8"))["presets"]


def test_root_and_health_unchanged():
    assert client.get("/").json()["status"] == "ok"
    assert client.get("/health").json() == {"status": "ok"}


def test_static_public_data():
    r = client.get("/data/targets/index.json")
    assert r.status_code == 200
    assert {t["target_id"] for t in r.json()["targets"]} >= {"barnard", "eps_ind_b"}
    assert client.get("/data/targets/barnard/S1_D1.webp").headers["content-type"] == "image/webp"
    assert client.get("/data/catalogs/splices.json").status_code == 200


def test_custom_cached_preset_is_ready():
    p = PRESETS[0]
    r = client.post("/custom", json={"ra": p["ra"], "dec": p["dec"], "fov_arcmin": p["fov_arcmin"],
                                     "max_exposures_per_group": p["max_exposures_per_group"]})
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "ready" and body["job_id"] == p["job_id"]
    assert client.get(body["manifest_url"]).status_code == 200
    assert client.get(f"/custom/{p['job_id']}").json()["state"] == "ready"


@pytest.mark.parametrize("payload", [{"ra": 400, "dec": 0}, {"ra": 10, "dec": 95}, {"ra": 10, "dec": 0, "fov_arcmin": 7}])
def test_custom_invalid_input(payload):
    assert client.post("/custom", json=payload).status_code == 422


def test_custom_unknown_job():
    assert client.get("/custom/cdeadbeef0000").status_code == 404


def test_spectrum_in_prepared_field():
    r = client.get("/spectrum", params={"field": "eps_ind_b", "ra": 331.12786, "dec": -56.77502, "label": "field star"})
    assert r.status_code == 200
    body = r.json()
    combined = body["spectra"][-1]
    assert combined["epoch"] == "combined" and len(combined["points"]) > 20
    assert body["elapsed_s"] < 10


def test_spectrum_errors():
    assert client.get("/spectrum", params={"field": "nope", "ra": 1, "dec": 1}).status_code == 404
    assert client.get("/spectrum", params={"field": "eps_ind_b", "ra": 10, "dec": 10}).status_code == 422


def test_offline_mode_rejects_uncached_custom(monkeypatch):
    import app.spherex as sx
    monkeypatch.setattr(sx, "OFFLINE", True)
    assert client.post("/custom", json={"ra": 10.123, "dec": 20.456}).status_code == 503
    p = PRESETS[0]  # cached presets still work offline
    r = client.post("/custom", json={"ra": p["ra"], "dec": p["dec"], "fov_arcmin": p["fov_arcmin"]})
    assert r.status_code == 202 and r.json()["state"] == "ready"


def test_demo_network_blocker_really_blocks():
    import socket
    from app import demo
    saved = socket.socket.connect, socket.create_connection
    try:
        demo.block_network()
        with pytest.raises(OSError, match="demo offline"):
            socket.create_connection(("irsa.ipac.caltech.edu", 443), timeout=2)
        s = socket.socket()
        with pytest.raises(OSError, match="demo offline"):
            s.connect(("8.8.8.8", 53))
        s.close()
    finally:
        socket.socket.connect, socket.create_connection = saved
