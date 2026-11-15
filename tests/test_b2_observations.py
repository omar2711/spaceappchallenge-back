"""Synthetic offline fixtures only; live/B1 tests are in a separate opt-in file."""

import json
from io import BytesIO
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from app.b2.archive import CutoutCache, cutout_url, search_observations
from app.b2.models import FitsAsset, Provenance
from app.b2.observation_models import (ApertureConfig, DownloadLimits, FrameSpec,
    Observation, ObservationQuery, ScienceRun, Target)
from app.b2.photometry import aperture_measurement
from app.b2.pipeline import export_run, run_target
from app.b2.validated_images import validated_difference
from app.b2.compatibility import group_compatible_samples

TARGET = Target(target_id="synthetic-test", ra_deg=10, dec_deg=20, coordinate_source="synthetic")
QUERY = ObservationQuery(ra_deg=10, dec_deg=20, radius_deg=.001, limit=2)
OBS = Observation(observation_id="synthetic", collection="spherex_dr1",
    access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/synthetic.fits")
CONFIG = ApertureConfig(rejected_flag_bits=2, flag_policy_source="synthetic: reject bit 1 only")
PROVENANCE = Provenance(kind="synthetic", source="unit test only")


def fake_irsa(table=None, error=None):
    def query_sia(**kwargs):
        assert kwargs["maxrec"] == 2
        assert kwargs["collection"] == ["spherex_dr1", "spherex_qr3"]
        if error:
            raise error
        return table if table is not None else Table()
    return SimpleNamespace(query_sia=query_sia)


def make_fits(*, image_unit="MJy/sr", mask_center=False, with_variance=True,
              variance_value=4., epoch=True):
    w = WCS(naxis=2)
    w.wcs.crpix = [13, 13]
    w.wcs.crval = [10, 20]
    w.wcs.cdelt = [-.001, .001]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = w.to_header()
    header["BUNIT"] = image_unit
    header["DETECTOR"] = "1"
    if epoch:
        header["MJD-OBS"] = 60000
        header["TIMESYS"] = "UTC"
    # Analytic alternate WCS for tests only; not the actual WAVE-TAB product.
    for axis, ctype in [(1, "WAVE"), (2, "LINEAR")]:
        header[f"CTYPE{axis}W"] = ctype
        header[f"CUNIT{axis}W"] = "um"
        header[f"CRVAL{axis}W"] = 1. if axis == 1 else .02
        header[f"CRPIX{axis}W"] = 13
        header[f"CDELT{axis}W"] = 1e-6
    image = np.full((25, 25), 10.)
    image[12, 12] = 100
    flags = np.zeros(image.shape, dtype=np.int32)
    flags[12, 12] = 2 if mask_center else 2**21  # SOURCE must remain usable
    primary = fits.PrimaryHDU()
    primary.header["VERSION"] = "synthetic-v1"
    hdus = [primary, fits.ImageHDU(image, header, name="IMAGE"),
            fits.ImageHDU(flags, name="FLAGS")]
    if with_variance:
        vh = fits.Header({"BUNIT": "MJy2 sr-2"})
        hdus.append(fits.ImageHDU(np.full(image.shape, variance_value), vh, name="VARIANCE"))
    buffer = BytesIO()
    fits.HDUList(hdus).writeto(buffer)
    return buffer.getvalue()


def cached(tmp_path, content):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content))) as client:
        return CutoutCache(tmp_path, client, DownloadLimits()).fetch(OBS, TARGET)


def test_sia_empty_and_retries():
    assert search_observations(QUERY, irsa=fake_irsa()).status == "empty"
    with pytest.raises(TimeoutError):
        search_observations(QUERY, irsa=fake_irsa(error=TimeoutError("synthetic network failure")), attempts=1)


def test_sia_metadata():
    t = Table({"obs_id": ["a", "b"], "obs_collection": ["spherex_dr1"] * 2,
               "access_url": [OBS.access_url] * 2, "t_min": [60000., 60001.],
               "t_max": [60000.1, 60001.1], "energy_bandpassname": ["SPHEREx-D1"] * 2})
    r = search_observations(QUERY, irsa=fake_irsa(t))
    assert r.possibly_truncated and r.observations[0].mjd_start == 60000
    assert r.observations[0].time_scale is None


def test_sia_missing_required():
    with pytest.raises(ValueError, match="access_url"):
        search_observations(QUERY, irsa=fake_irsa(Table({"obs_id": ["a"], "obs_collection": ["spherex_dr1"]})))


def test_cache_success_and_reuse(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        assert "center=" in str(request.url) and "size=" in str(request.url)
        return httpx.Response(200, content=make_fits())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cache = CutoutCache(tmp_path, client, DownloadLimits(max_files=2))
        a, b = cache.fetch(OBS, TARGET), cache.fetch(OBS, TARGET)
    assert not a.cache_hit and b.cache_hit and a.sha256 == b.sha256
    assert len(calls) == 1
    assert not a.asset.path.startswith("/")


@pytest.mark.parametrize("url", ["http://irsa.ipac.caltech.edu/a.fits", "https://evil.test/x.fits",
                                  "https://irsa.ipac.caltech.edu/not-ibe/file.fits"])
def test_reject_origin(url):
    with pytest.raises(ValueError):
        cutout_url(OBS.model_copy(update={"access_url": url}), TARGET, .03)


@pytest.mark.parametrize("body", [b"corrupt", b"<html>service error</html>"])
def test_corrupt_fits(tmp_path, body):
    with pytest.raises((OSError, ValueError)):
        cached(tmp_path, body)
    assert not list(tmp_path.glob("*.fits"))


def test_download_network_retries(tmp_path):
    calls = []
    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("synthetic offline")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            CutoutCache(tmp_path, client, DownloadLimits()).fetch(OBS, TARGET)
    assert len(calls) == 2


def test_download_budget(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=make_fits()))) as client:
        cache = CutoutCache(tmp_path, client, DownloadLimits(max_file_bytes=2880))
        with pytest.raises(ValueError, match="byte budget"):
            cache.fetch(OBS, TARGET)
    assert not list(tmp_path.glob("*.fits"))


def test_real_fits_io_synthetic_photometry(tmp_path):
    result = aperture_measurement(cached(tmp_path, make_fits()), tmp_path, TARGET, CONFIG)
    factor = (np.deg2rad(.001)) ** 2 * 1e6
    assert result.flux_jy == pytest.approx(90 * factor, rel=1e-6)
    assert result.background_mjy_sr == 10
    assert result.uncertainty_jy > 0
    assert result.wavelength_um == pytest.approx(1.)
    assert result.bandwidth_um == pytest.approx(.02)
    assert result.mjd == 60000 and result.time_scale == "utc"
    assert result.dataset_version == "synthetic-v1"


def test_uncertainty_scales_with_variance(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    a = aperture_measurement(cached(first, make_fits(variance_value=1)), first, TARGET, CONFIG)
    b = aperture_measurement(cached(second, make_fits(variance_value=4)), second, TARGET, CONFIG)
    assert b.uncertainty_jy == pytest.approx(a.uncertainty_jy * 2)


def test_compatible_grouping_requires_response_and_deduplication(tmp_path):
    m = aperture_measurement(cached(tmp_path, make_fits()), tmp_path, TARGET, CONFIG)
    assert group_compatible_samples([m]).excluded == [m]
    a = m.model_copy(update={"response_id": "synthetic-attested-response"})
    b = a.model_copy(update={"input_path": "other.fits", "mjd": 60001.})
    result = group_compatible_samples([b, a, a])
    assert [x.mjd for x in result.groups[0]] == [60000, 60001]
    assert len(result.excluded) == 1
    c = b.model_copy(update={"response_id": "different"})
    assert len(group_compatible_samples([a, c]).groups) == 2


def test_tampered_cached_fits_rejected(tmp_path):
    c = cached(tmp_path, make_fits())
    path = tmp_path / c.asset.path
    with path.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        aperture_measurement(c, tmp_path, TARGET, CONFIG)


@pytest.mark.parametrize("kwargs,exception", [({"mask_center": True}, ValueError),
    ({"with_variance": False}, KeyError), ({"image_unit": "s"}, ValueError),
    ({"variance_value": -1}, ValueError)])
def test_invalid_photometry(tmp_path, kwargs, exception):
    cutout = cached(tmp_path, make_fits(**kwargs))
    with pytest.raises(exception):
        aperture_measurement(cutout, tmp_path, TARGET, CONFIG)


def test_missing_date_and_export(tmp_path):
    root = tmp_path / "cache"
    m = aperture_measurement(cached(root, make_fits(epoch=False)), root, TARGET, CONFIG)
    assert m.mjd is None and m.time_scale is None
    run = ScienceRun(target=TARGET, search=None, measurements=[m], status="insufficient_compatible_epochs")
    output = tmp_path / "out"
    result = export_run(run, output)
    assert result.result_paths == ["run.json", "measurements.csv"]
    assert json.loads((output / "run.json").read_text())["measurements"][0]["mjd"] is None
    with pytest.raises(FileExistsError):
        export_run(run, output)


def test_png_export(tmp_path):
    root = tmp_path / "cache"
    m = aperture_measurement(cached(root, make_fits()), root, TARGET, CONFIG)
    run = ScienceRun(target=TARGET, search=None, measurements=[m], status="insufficient_compatible_epochs")
    result = export_run(run, tmp_path / "export")
    assert "samples.png" in result.result_paths
    assert (tmp_path / "export" / "samples.png").read_bytes().startswith(b"\x89PNG")


def test_pipeline_empty_failure(tmp_path):
    with httpx.Client() as client:
        r = run_target(TARGET, QUERY, tmp_path, client, CONFIG, DownloadLimits(), irsa=fake_irsa())
        assert r.status == "empty" and not r.cutouts
        r = run_target(TARGET, QUERY, tmp_path, client, CONFIG, DownloadLimits(),
                       irsa=fake_irsa(error=TimeoutError("synthetic")))
        assert r.status == "failed" and r.issues[0].stage == "query"


def frame_fixture(root, name, offset, variance=True):
    # Independent synthetic registered frames for analytic propagation.
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.cdelt = [-.001, .001]
    h = w.to_header()
    h["DETECTOR"], h["BUNIT"] = "1", "Jy"
    vh = fits.Header({"BUNIT": "Jy2"})
    hdus = fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.full((6, 6), offset), h, name="SCI"),
        fits.ImageHDU(np.zeros((6, 6), dtype=int), name="FLAGS"),
        fits.ImageHDU(np.ones((6, 6)), name="SKY"),
        fits.ImageHDU(np.ones((6, 6)), vh, name="VAR")])
    hdus.writeto(root / name)
    def a(hdu):
        return FitsAsset(path=name, hdu=hdu, provenance=PROVENANCE)
    return FrameSpec(image=a("SCI"), flags=a("FLAGS"), background_mask=a("SKY"),
        variance=a("VAR") if variance else None, detector="1", response_id="synthetic-response",
        calibration_id="synthetic-cal", psf_match_id="synthetic-psf", rejected_flag_bits=2)


def test_validated_difference(tmp_path):
    a, b = frame_fixture(tmp_path, "a.fits", 10), frame_fixture(tmp_path, "b.fits", 3)
    result = validated_difference(a, b, tmp_path)
    assert result.background_offset == 7
    assert np.asarray(result.pixels).sum() == 0
    # All pixels are in the offset estimate: Var(A-B-mean) = 2*(1-1/N).
    assert result.uncertainty[0][0] == pytest.approx(np.sqrt(2 * (1 - 1/36)))


@pytest.mark.parametrize("field", ["detector", "response_id", "calibration_id", "psf_match_id"])
def test_difference_rejects_incompatible(tmp_path, field):
    a, b = frame_fixture(tmp_path, "a.fits", 10), frame_fixture(tmp_path, "b.fits", 3)
    with pytest.raises(ValueError, match=field):
        validated_difference(a, b.model_copy(update={field: "different"}), tmp_path)


def test_difference_missing_uncertainty(tmp_path):
    a, b = frame_fixture(tmp_path, "a.fits", 10), frame_fixture(tmp_path, "b.fits", 3, variance=False)
    assert validated_difference(a, b, tmp_path).uncertainty is None


def test_new_contract_schemas():
    from app.b2 import observation_models
    from app.b2.models import Contract
    for value in vars(observation_models).values():
        if isinstance(value, type) and issubclass(value, Contract):
            assert value.model_json_schema()
