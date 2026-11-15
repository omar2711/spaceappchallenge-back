from fastapi.testclient import TestClient

from app import main as api


client = TestClient(api.app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_targets_contains_all_official_targets() -> None:
    response = client.get("/api/v1/targets")

    assert response.status_code == 200
    targets = response.json()["targets"]
    assert {target["target_id"] for target in targets} == {
        "barnard",
        "eps_ind_b",
        "wise0855",
        "rw_aur",
        "r_dra",
    }


def test_target_manifest_and_analysis_are_available() -> None:
    manifest = client.get("/api/v1/targets/barnard")
    analysis = client.get("/api/v1/targets/barnard/analysis")

    assert manifest.status_code == 200
    assert manifest.json()["target_id"] == "barnard"
    assert analysis.status_code == 200
    assert {"difference_images", "deep_images", "light_curves", "spectra"} <= analysis.json().keys()


def test_unknown_target_returns_not_found() -> None:
    response = client.get("/api/v1/targets/not-a-target")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown target: not-a-target"


def test_published_webp_is_served() -> None:
    response = client.get("/data/targets/barnard/S1_D1.webp")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"


def test_published_data_does_not_allow_path_traversal() -> None:
    response = client.get("/data/../pyproject.toml")

    assert response.status_code == 404


def test_create_custom_field_enqueues_valid_request(monkeypatch) -> None:
    expected = {
        "job_id": "c123456789abc",
        "state": "pending",
        "manifest": None,
    }
    calls = []

    def fake_submit(ra, dec, fov_arcmin, max_exposures_per_group):
        calls.append((ra, dec, fov_arcmin, max_exposures_per_group))
        return expected

    monkeypatch.setattr(api, "submit_custom", fake_submit)
    response = client.post(
        "/api/v1/custom",
        json={"ra": 67.9105, "dec": 18.2327},
    )

    assert response.status_code == 202
    assert response.json() == expected
    assert calls == [(67.9105, 18.2327, 3, 2)]


def test_create_custom_field_rejects_invalid_coordinates() -> None:
    response = client.post(
        "/api/v1/custom",
        json={"ra": 360, "dec": 18.2327},
    )

    assert response.status_code == 422


def test_get_custom_field_status(monkeypatch) -> None:
    expected = {"job_id": "c123456789abc", "state": "ready", "progress": 100}
    monkeypatch.setattr(api, "get_status", lambda job_id: expected)

    response = client.get("/api/v1/custom/c123456789abc")

    assert response.status_code == 200
    assert response.json() == expected


def test_get_custom_field_status_handles_unknown_job(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_status", lambda job_id: None)

    response = client.get("/api/v1/custom/c123456789abc")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown custom job: c123456789abc"


def test_get_custom_field_status_rejects_invalid_job_id() -> None:
    response = client.get("/api/v1/custom/not-a-job")

    assert response.status_code == 422


def test_cochabamba_visibility_returns_observation_details() -> None:
    response = client.get(
        "/api/v1/visibility/cochabamba/barnard",
        params={"at": "2026-11-15T04:00:00Z"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_id"] == "barnard"
    assert body["location"]["name"] == "Cochabamba"
    assert "altitude_deg" in body["target"]
    assert body["reason"] in {"daylight", "target_below_20_degrees", "visible"}


def test_cochabamba_visibility_rejects_unknown_target() -> None:
    response = client.get("/api/v1/visibility/cochabamba/not-a-target")

    assert response.status_code == 404


def test_list_moon_sites_contains_south_pole_and_apollo() -> None:
    response = client.get("/api/v1/moon/sites")

    assert response.status_code == 200
    categories = {site["category"] for site in response.json()["sites"]}
    assert {"south_pole", "apollo"} <= categories


def test_moon_site_conditions_return_sun_and_earth_visibility() -> None:
    response = client.get(
        "/api/v1/moon/sites/shackleton/conditions",
        params={"at": "2026-11-15T04:00:00Z"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["site"]["id"] == "shackleton"
    assert "sun_altitude_deg" in body["conditions"]
    assert "earth_visible" in body["conditions"]
    assert body["conditions"]["model"] == "approximate IAU lunar fixed frame"


def test_moon_site_conditions_reject_unknown_site() -> None:
    response = client.get("/api/v1/moon/sites/not-a-site/conditions")

    assert response.status_code == 404


def test_mars_route_contains_water_waypoints() -> None:
    response = client.get("/api/v1/mars/route")

    assert response.status_code == 200
    body = response.json()
    assert body["body"] == "Mars"
    assert len(body["waypoints"]) >= 3
    assert "hazards" in body["waypoints"][0]


def test_ice_catalog_contains_source_and_entries() -> None:
    response = client.get("/api/v1/ice")

    assert response.status_code == 200
    body = response.json()
    assert body["catalog"] == "SPLICES"
    assert body["entries"]
    assert body["source_url"].startswith("https://")


def test_3i_atlas_declares_ephemeris_status() -> None:
    response = client.get("/api/v1/comets/3i-atlas")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "3i-atlas"
    assert body["ephemeris"]["available"] is False
