"""Offline phase-3 unit tests: all numerical tables/FITS here are SYNTHETIC."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.table import MaskedColumn, Table
from astropy.time import Time
from pydantic import ValidationError

from app.b2.catalog_snapshot import scs_splices_snapshot, tap_table
from app.b2.difference_export import export_difference
from app.b2.models import CatalogQuery, FitsAsset, Provenance
from app.b2.observation_models import Target
from app.b2.phase3 import APERTURE, TargetResult, _process, main
from app.b2.spectral_products import (SpectralPoint, SpectralProduct, export_spectral_product,
                                    read_official_spectrum)
from app.b2.targets import Astrometry, target_at_epoch
from test_b2_observations import CONFIG, cached, frame_fixture, make_fits
from app.b2.photometry import aperture_measurement

TARGET = Target(target_id="synthetic", ra_deg=10, dec_deg=20, coordinate_source="synthetic")
PROVENANCE = Provenance(kind="synthetic", source="unit test only, NOT observations")


def official_shaped_table():
    """Schema matches official columns; values are analytic synthetic fixtures."""
    return Table({"wavelength": [1., 2.], "lambda_width": [.01, .02],
                  "flux": [1e6, -2e6], "flux_err": [1e5, 2e5], "mjd": [60000., 60001.],
                  "det_id": [1, 2], "data_collection": ["dr1", "dr1"],
                  "lvf_id": ["synthetic-1", "synthetic-2"], "flags": [0, 0]},
                 units={"wavelength": "um", "lambda_width": "um", "flux": "uJy",
                        "flux_err": "uJy", "mjd": "d"})


def import_fixture(tmp_path, table, *, format="votable", **kwargs):
    name = "synthetic.fits" if format == "fits" else "synthetic.xml"
    table.write(tmp_path / name, format=format)
    return read_official_spectrum(FitsAsset(path=name, hdu=1, provenance=PROVENANCE), tmp_path,
        TARGET, dataset_version="synthetic-v1", calibration_id="synthetic-calibration",
        rejected_bits=2**32 | 2**33 | 128, flag_policy_source="synthetic mask",
        table_format=format, **kwargs)


@pytest.mark.parametrize("format", ["fits", "votable"])
def test_spectral_import_units_and_signed_flux(tmp_path, format):
    product = import_fixture(tmp_path, official_shaped_table(), format=format)
    assert product.status == "usable_samples"
    assert [p.flux_jy for p in product.points] == pytest.approx([1, -2])
    assert [p.uncertainty_jy for p in product.points] == pytest.approx([.1, .2])
    assert product.points[0].time_scale is None


@pytest.mark.parametrize("column,value", [("wavelength", np.nan), ("flux", np.nan),
    ("flux_err", 0), ("flux_err", -1), ("lambda_width", -1), ("flags", 2**32)])
def test_spectral_invalid_rows_preserved(tmp_path, column, value):
    table = official_shaped_table()
    table[column] = table[column].astype(float)
    table[column][0] = value
    p = import_fixture(tmp_path, table)
    assert p.status == "partial" and len(p.points) == 2
    assert not p.points[0].accepted and p.points[0].reasons
    assert p.points[1].accepted
    assert "NaN" not in p.model_dump_json()


def test_spectral_masked_error(tmp_path):
    table = official_shaped_table()
    table["flux_err"] = MaskedColumn([1e5, 2e5], mask=[True, False], unit="uJy")
    p = import_fixture(tmp_path, table)
    assert p.points[0].uncertainty_jy is None and not p.points[0].accepted


@pytest.mark.parametrize("unit", [None, "s"])
def test_spectral_units_rejected(tmp_path, unit):
    table = official_shaped_table()
    table["flux"].unit = unit
    with pytest.raises(ValueError):
        import_fixture(tmp_path, table)


def test_spectral_calibration_required(tmp_path):
    p = import_fixture(tmp_path, official_shaped_table())
    payload = p.model_dump()
    payload["calibration_id"] = None
    with pytest.raises(ValidationError):
        SpectralProduct.model_validate(payload)
    payload = p.points[0].model_dump()
    payload["flux_jy"] = None
    with pytest.raises(ValidationError):
        SpectralPoint.model_validate(payload)


def test_spectral_empty_and_export(tmp_path):
    p = import_fixture(tmp_path, official_shaped_table()[:0])
    assert p.status == "empty"
    exported = export_spectral_product(p, tmp_path / "empty")
    assert exported.result_paths == ["spectrum.json", "spectrum.csv"]
    with pytest.raises(FileExistsError):
        export_spectral_product(p, tmp_path / "empty")


def test_spectral_export_reference_bands(tmp_path):
    p = import_fixture(tmp_path, official_shaped_table())
    exported = export_spectral_product(p, tmp_path / "spectrum")
    assert (tmp_path / "spectrum/spectrum.png").read_bytes().startswith(b"\x89PNG")
    assert set(exported.reference_bands_um.values()) == {3.05, 4.27, 4.67}
    assert all("not a detection" in key for key in exported.reference_bands_um)


def test_proper_motion_epoch_and_missing():
    astrometry = Astrometry(reference=TARGET, resolved_name="synthetic", pm_ra_cosdec_mas_yr=1000,
        pm_dec_mas_yr=0, retrieved_at_utc="synthetic", query="synthetic")
    later = target_at_epoch(astrometry, Time(2001., format="jyear", scale="tt"))
    assert (later.ra_deg - TARGET.ra_deg) * 3600 == pytest.approx(1/np.cos(np.deg2rad(20)), rel=1e-5)
    with pytest.raises(ValueError, match="proper motion"):
        target_at_epoch(astrometry.model_copy(update={"pm_dec_mas_yr": None}), Time(2001., format="jyear"))


def test_difference_fits_png_metadata(tmp_path):
    a, b = frame_fixture(tmp_path, "a.fits", 10), frame_fixture(tmp_path, "b.fits", 3)
    result = export_difference(a, b, tmp_path, tmp_path / "difference")
    assert not result.temporal_comparison_verified and result.input_kind == "synthetic_present"
    with fits.open(tmp_path / "difference/difference.fits", checksum=True) as hdus:
        assert hdus[0].header["SYNTHET"]
        assert np.all(hdus[0].data == 0)
        assert hdus["UNCERTAINTY"].header["BUNIT"] == "Jy"
        assert np.all(hdus["VALID"].data == 1)
    assert (tmp_path / "difference/difference.png").exists()
    assert len(result.input_sha256) == 2


def test_difference_export_rejects_before_creating(tmp_path):
    a, b = frame_fixture(tmp_path, "a.fits", 10), frame_fixture(tmp_path, "b.fits", 3)
    with pytest.raises(ValueError, match="response_id"):
        export_difference(a, b.model_copy(update={"response_id": "other"}), tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def votable_bytes(table):
    out = BytesIO()
    table.write(out, format="votable")
    return out.getvalue()


def test_scs_snapshot_units_identity(tmp_path):
    table = Table({"source_id": [854236268010143747], "ra": [10.], "dec": [20.], "j": [12.]},
                  units={"ra": "deg", "dec": "deg", "j": "mag"})
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=votable_bytes(table)))) as c:
        result = scs_splices_snapshot(CatalogQuery(ra_deg=10, dec_deg=20, radius_deg=.01, limit=5), c)
    assert result.rows[0]["source_id"] == "854236268010143747"
    assert result.columns["j"]["unit"] == "mag"
    assert result.protocol == "SCS" and not result.possibly_truncated


def test_scs_empty():
    table = Table(names=["source_id", "ra", "dec"], dtype=[int, float, float])
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=votable_bytes(table)))) as c:
        assert scs_splices_snapshot(CatalogQuery(ra_deg=0, dec_deg=0, radius_deg=.001, limit=5), c).rows == []


def test_tap_service_error_in_http_200():
    error = b'''<?xml version="1.0"?><VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE><INFO name="QUERY_STATUS" value="ERROR">synthetic failure</INFO></RESOURCE></VOTABLE>'''
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=error))) as c:
        with pytest.raises(ValueError, match="synthetic failure"):
            tap_table("SELECT TOP 1 ra FROM splices", c, maxrec=1)


def test_catalog_network_not_empty():
    def offline(request):
        raise httpx.ConnectError("synthetic failure")
    with httpx.Client(transport=httpx.MockTransport(offline)) as c:
        with pytest.raises(httpx.ConnectError):
            scs_splices_snapshot(CatalogQuery(ra_deg=0, dec_deg=0, radius_deg=.001, limit=5), c)


def test_phase3_schemas():
    for cls in (SpectralPoint, SpectralProduct, TargetResult, Astrometry):
        assert cls.model_json_schema()


def test_source_mask_changes_background_acceptance(tmp_path):
    stream = BytesIO()
    with fits.open(BytesIO(make_fits()), memmap=False) as hdus:
        hdus["FLAGS"].data[:] = 1 << 21
        hdus.writeto(stream)
    cutout = cached(tmp_path, stream.getvalue())
    assert aperture_measurement(cutout, tmp_path, TARGET, CONFIG).flux_jy > 0
    strict = CONFIG.model_copy(update={"background_rejected_flag_bits": 1 << 21})
    with pytest.raises(ValueError, match="background pixels"):
        aperture_measurement(cutout, tmp_path, TARGET, strict)


def test_spectral_fastapi_roundtrip(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    product = import_fixture(tmp_path, official_shaped_table())
    api = FastAPI()
    @api.post("/spectrum", response_model=SpectralProduct)
    def echo(payload: SpectralProduct) -> SpectralProduct:
        return payload
    with TestClient(api) as client:
        response = client.post("/spectrum", json=product.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["points"][0]["flux_jy"] == 1
    assert "SpectralProduct" in api.openapi()["components"]["schemas"]


def test_offline_mode_never_queries(tmp_path):
    directory = tmp_path / "prior/target-0"
    directory.mkdir(parents=True)
    result = TargetResult(target_id="synthetic", limitations=["synthetic resolution failure"])
    (directory / "target-result.json").write_text(result.model_dump_json(), encoding="utf-8")
    with patch("sys.argv", ["phase3", "--output", str(tmp_path/"output"), "--offline", str(tmp_path/"prior")]), \
            patch("app.b2.phase3.search_observations", side_effect=AssertionError("Network forbidden")), \
            patch("app.b2.phase3.resolve_target", side_effect=AssertionError("Network forbidden")):
        main()
    assert (tmp_path/"output/index.json").exists()
