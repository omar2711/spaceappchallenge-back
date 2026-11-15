"""Phase-4 offline unit tests. All numeric FITS/catalog fixtures are SYNTHETIC."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from astropy.io import fits
from pydantic import ValidationError

from app.b2.b1_adapter import B1Frame, process_b1_pair, validate_b1_frame
from app.b2.catalog_snapshot import SplicesSnapshot
from app.b2.models import CatalogQuery, FitsAsset, Provenance
from app.b2.observation_models import CachedCutout, Observation, ObservationQuery, ObservationSearch, ScienceRun, Target
from app.b2.offline_bundle import BundleManifest, digest, export_bundle, read_json, validate_bundle
from app.b2.offline_demo import main
from app.b2.phase3 import APERTURE, export_target
from app.b2.photometry import aperture_measurement
from app.b2.safe_paths import inside, relative_path
from app.b2.service import ScienceService, ScienceServiceError
from app.b2.targets import Astrometry, TARGET_NAMES
from app.b2.spatial_wcs import same_celestial_grid
from test_b2_observations import frame_fixture, make_fits

SYNTHETIC = Provenance(kind="synthetic", source="synthetic unit test only")


@pytest.fixture
def source_bundle(tmp_path):
    source, cache = tmp_path / "source", tmp_path / "cache"
    source.mkdir()
    cache.mkdir()
    path = cache / "SYNTHETIC.fits"
    path.write_bytes(make_fits())
    catalog = tmp_path / "splices.json"
    snapshot = SplicesSnapshot(query=CatalogQuery(ra_deg=10, dec_deg=20, radius_deg=.01, limit=5),
        adql=None, protocol="SCS", endpoint="https://irsa.ipac.caltech.edu/SCS", retrieved_at_utc="2026-11-15T00:00:00Z",
        columns={"ra": {"unit": "deg"}, "dec": {"unit": "deg"}},
        rows=[{"source_id": "SYNTHETIC", "ra": 10., "dec": 20.}],
        possibly_truncated=False, warnings=["SYNTHETIC fixture, no actual NASA source"])
    catalog.write_text(snapshot.model_dump_json(), encoding="utf-8")
    index = []
    for i, name in enumerate(TARGET_NAMES):
        target = Target(target_id=name, ra_deg=10, dec_deg=20, coordinate_source="synthetic")
        a = Astrometry(reference=target, resolved_name="synthetic", pm_ra_cosdec_mas_yr=0,
            pm_dec_mas_yr=0, parallax_mas=10, radial_velocity_km_s=0,
            retrieved_at_utc="2026-11-15T00:00:00Z", query="synthetic")
        run = ScienceRun(target=target, search=ObservationSearch(
            query=ObservationQuery(ra_deg=10, dec_deg=20, radius_deg=.001),
            observations=[], status="empty", queried_at_utc="2026-11-15T00:00:00Z", possibly_truncated=False), status="empty")
        if name == "WISE 0855":
            url = "https://synthetic.invalid/SYNTHETIC.fits"
            cutout = CachedCutout(observation=Observation(observation_id="synthetic", collection="synthetic", access_url=url),
                asset=FitsAsset(path=path.name, hdu="IMAGE", provenance=SYNTHETIC.model_copy(update={"source": url})),
                cutout_url=url, sha256=digest(path), size_bytes=path.stat().st_size,
                retrieved_at_utc="2026-11-15T00:00:00Z", cache_hit=True)
            run.cutouts = [cutout]
            run.measurements = [aperture_measurement(cutout, cache, target, APERTURE)]
            run.status = "insufficient_compatible_epochs"
        result = export_target(a, run, cache, source / f"target-{i}")
        index.append(dict(target_id=name, status=run.status,
            spectral_points=sum(len(s.points) for s in result.spectra),
            target_result_path=f"target-{i}/target-result.json", photometry_path=f"target-{i}/photometry/run.json",
            spectral_products=[f"target-{i}/spectral-{j}/spectrum.json" for j in range(len(result.spectra))],
            limitations=result.limitations))
    (source / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return source, cache, catalog


@pytest.fixture
def package(source_bundle, tmp_path):
    source, cache, catalog = source_bundle
    output = tmp_path / "package"
    export_bundle(source, cache, catalog, output, allow_synthetic=True)
    return output, cache


@pytest.mark.parametrize("value", ["../x", "/etc/passwd", "C:/data/x", "C:\\data\\x", "\\\\server\\x",
    "a/../b", "a//b", "a/./b", "a.json:stream", "x/", "CON.txt", "a/NUl", "a/foo. ", "a\x00b"])
def test_unsafe_paths(value):
    with pytest.raises(ValueError):
        relative_path(value)


def test_relative_paths_and_urls(tmp_path):
    assert relative_path("target-2/spectrum.json") == "target-2/spectrum.json"
    (tmp_path / "url.json").write_text('{"source":"https://irsa.ipac.caltech.edu/file"}', encoding="utf-8")
    assert read_json(tmp_path, "url.json")["source"].startswith("https")


def test_package_integrity_and_no_fits_copy(package):
    root, cache = package
    report = validate_bundle(root, allow_synthetic=True)
    assert report.valid and report.target_count == 5 and report.fits_verified == 1
    assert (root / "data/SYNTHETIC.fits").samefile(cache / "SYNTHETIC.fits")
    assert not validate_bundle(root).valid  # never mislabel synthetic fixtures as observations


def test_external_package_explicit_root(source_bundle, tmp_path):
    source, cache, catalog = source_bundle
    root = tmp_path / "external"
    export_bundle(source, cache, catalog, root, fits_mode="external", allow_synthetic=True)
    assert not (root / "data").exists()
    assert not validate_bundle(root, allow_synthetic=True).valid
    assert validate_bundle(root, data_root=cache, allow_synthetic=True).valid


def test_default_export_rejects_synthetic_source(source_bundle, tmp_path):
    with pytest.raises(ValueError, match="Synthetic"):
        export_bundle(*source_bundle, tmp_path / "wrong")
    assert not (tmp_path / "wrong").exists()


def test_export_does_not_overwrite(package, source_bundle):
    with pytest.raises(FileExistsError):
        export_bundle(*source_bundle, package[0], allow_synthetic=True)


def test_missing_file_and_bad_json(package):
    root, _ = package
    # Rename within temporary synthetic fixture, never touch repository data.
    path = root / "target-0/astrometry.json"
    path.rename(path.with_suffix(".missing"))
    assert not validate_bundle(root, allow_synthetic=True).valid
    path.with_suffix(".missing").rename(path)
    path.write_text("{bad json", encoding="utf-8")
    assert not validate_bundle(root, allow_synthetic=True).valid


def test_tampered_product_checksum(package):
    root, _ = package
    path = root / "target-2/photometry/measurements.csv"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("tampered")
    report = validate_bundle(root, allow_synthetic=True)
    assert not report.valid and any(i.code == "checksum_mismatch" for i in report.issues)


def test_missing_provenance_rejected_before_export(source_bundle, tmp_path):
    source, cache, catalog = source_bundle
    path = source / "target-2/target-result.json"
    data = json.loads(path.read_text())
    data["run"]["cutouts"][0]["asset"]["provenance"]["source"] = ""
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        export_bundle(source, cache, catalog, tmp_path / "bad", allow_synthetic=True)


def test_absolute_reference_rejected(source_bundle, tmp_path):
    source, cache, catalog = source_bundle
    index = json.loads((source / "index.json").read_text())
    index[0]["target_result_path"] = "C:/outside/private.json"
    (source / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError):
        export_bundle(source, cache, catalog, tmp_path / "bad", allow_synthetic=True)


def test_inconsistent_embedded_json(source_bundle, tmp_path):
    source, cache, catalog = source_bundle
    path = source / "target-2/photometry/run.json"
    data = json.loads(path.read_text())
    data["measurements"][0]["flux_jy"] *= 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        export_bundle(source, cache, catalog, tmp_path / "bad", allow_synthetic=True)


def test_service_contract_and_preliminary_states(package):
    root, _ = package
    service = ScienceService(root, allow_synthetic=True)
    assert len(service.list_targets()) == 5
    assert service.get_status("WISE 0855").photometry.availability == "preliminary"
    assert service.get_status("WISE 0855").spectra.availability == "incomplete"
    assert service.get_status("WISE 0855").light_curve.availability == "unavailable"
    assert service.get_status("RW Aurigae").differences.availability == "blocked"
    assert service.get_differences("RW Aurigae") == []
    assert service.get_splices().rows[0]["source_id"] == "SYNTHETIC"
    assert service.get_spectra("WISE 0855")[0].points[0].detection_claim == "none"
    products = service.list_products("WISE 0855")
    assert products and all(p.path.startswith(("target-2/", "data/")) for p in products)
    summary = service.summary()
    assert summary.model_dump(mode="json")
    assert summary.photometry["WISE 0855"][0].status == "preliminary_aperture"
    assert summary.spectra["WISE 0855"][0].points[0].detection_claim == "none"
    with pytest.raises(ScienceServiceError) as e:
        service.get_result("missing")
    assert e.value.code == "unknown_target"
    with pytest.raises(ScienceServiceError):
        service.resolve_product("../../private.json")


def test_offline_reproduction_network_forbidden(package, tmp_path):
    root, _ = package
    with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
            patch.object(httpx.Client, "send", side_effect=AssertionError("Network forbidden")):
        service = ScienceService(root, allow_synthetic=True)
        replay = service.reproduce(tmp_path / "replayed")
    assert replay.success and replay.targets_reprocessed == 5 and replay.measurements_compared == 1


def test_cli_rejects_invalid_bundle_and_summary_not_written(tmp_path):
    with patch("sys.argv", ["offline_demo", "demo", "--bundle", str(tmp_path), "--summary", str(tmp_path/"summary.json")]):
        assert main() == 1
    assert not (tmp_path / "summary.json").exists()


def b1_frame(root, name, mjd, *, sigma=False):
    base = frame_fixture(root, name, 10 if mjd == 60001 else 3)
    with fits.open(root / name, mode="update") as hdus:
        hdus["SCI"].header["MJD-OBS"] = mjd
        hdus["SCI"].header["TIMESYS"] = "UTC"
        if sigma:
            hdus["VAR"].header["BUNIT"] = "Jy"
    data = base.model_dump()
    if sigma:
        data["uncertainty"], data["variance"] = data["variance"], None
    return B1Frame(**(data | dict(target=Target(target_id="synthetic", ra_deg=0, dec_deg=0, coordinate_source="synthetic"),
        mjd=mjd, time_scale="utc", pass_id=f"synthetic-pass-{mjd}", band_id="synthetic-channel",
        registration_evidence="synthetic identity grid", psf_evidence="synthetic identical PSF",
        metadata_provenance=SYNTHETIC)))


def test_b1_pair_variance_and_sigma_are_reusable(tmp_path):
    a, b = b1_frame(tmp_path, "a.fits", 60001, sigma=True), b1_frame(tmp_path, "b.fits", 60000)
    before = digest(tmp_path / "a.fits"), digest(tmp_path / "b.fits")
    artifact = process_b1_pair(a, b, tmp_path, tmp_path / "difference")
    assert artifact.result.uncertainty is not None
    assert artifact.result.science.pass_id == a.pass_id
    persisted = json.loads((tmp_path / "difference/difference.json").read_text())
    assert persisted["result"]["science"]["pass_id"] == a.pass_id
    assert before == (digest(tmp_path / "a.fits"), digest(tmp_path / "b.fits"))
    assert not artifact.temporal_comparison_verified


@pytest.mark.parametrize("changes", [{"band_id": "different"}, {"pass_id": "synthetic-pass-60001"},
    {"response_id": "different"}, {"calibration_id": "different"}, {"psf_match_id": "different"}])
def test_b1_incompatible_pair_rejected(tmp_path, changes):
    a, b = b1_frame(tmp_path, "a.fits", 60001), b1_frame(tmp_path, "b.fits", 60000)
    with pytest.raises(ValueError):
        process_b1_pair(a, b.model_copy(update=changes), tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("changes", [{"mjd": 123}, {"time_scale": "tt"},
    {"declared_unit": "mJy"}, {"declared_wcs": {"CTYPE1": "LINEAR"}},
    {"registration_evidence": " "}])
def test_b1_metadata_matches_fits(tmp_path, changes):
    frame = b1_frame(tmp_path, "a.fits", 60001)
    with pytest.raises(ValueError):
        validate_b1_frame(frame.model_copy(update=changes), tmp_path)


def test_b1_external_input_validation(tmp_path):
    frame = b1_frame(tmp_path, "a.fits", 60001)
    data = frame.model_dump()
    data["mjd"] = float("nan")
    with pytest.raises(ValidationError):
        B1Frame.model_validate(data)
    data = frame.model_dump()
    data["uncertainty"] = data["variance"]
    with pytest.raises(ValidationError):
        B1Frame.model_validate(data)
    asset = frame.image.model_copy(update={"path": "../outside.fits"})
    with pytest.raises(ValueError):
        validate_b1_frame(frame.model_copy(update={"image": asset}), tmp_path)


def test_spatial_grid_keeps_sip_but_ignores_exposure_date():
    from astropy.wcs import WCS
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    h = w.to_header()
    h["A_ORDER"], h["B_ORDER"] = 2, 2
    h["A_2_0"], h["B_0_2"] = .001, .001
    h["MJD-OBS"] = 60000
    later = h.copy()
    later["MJD-OBS"] = 60001
    assert same_celestial_grid(h, later)
    later["A_2_0"] = .002
    assert not same_celestial_grid(h, later)
