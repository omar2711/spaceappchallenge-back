from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


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
