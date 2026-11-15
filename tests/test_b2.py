"""All fixtures are SYNTHETIC mathematical examples, never NASA observations."""

from io import BytesIO

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.b2.catalog import build_adql, query_splices
from app.b2.comet import prepare_comet
from app.b2.fits_io import read_image
from app.b2.images import difference_images
from app.b2.lightcurves import summarize_curve
from app.b2.models import (CatalogQuery, ContinuumRequest, CurveSummary,
                           DifferenceRequest, FitsAsset, LightCurve, Provenance,
                           Spectrum)
from app.b2.spectra import process_spectrum
from app.main import app

SYNTHETIC = Provenance(kind="synthetic", source="unit-test analytical fixture")


@pytest.mark.parametrize("target", ["RW Aurigae", "R Draconis"])
def test_curve(target):
    curve = LightCurve(target=target, band="synthetic", time_scale="utc",
                       mjd=[2, 1], values=[12, 10], uncertainty=[1, 1],
                       unit="mag", provenance=SYNTHETIC)
    result = summarize_curve(curve)
    assert result.curve.mjd == [1, 2]
    assert result.weighted_mean == 11
    assert result.mean_uncertainty == pytest.approx(1 / np.sqrt(2))
    assert result.chi_square_constant == 2
    assert result.peak_to_peak == 2
    assert result.degrees_of_freedom == 1
    assert curve.mjd == [2, 1]


def spectrum(**changes):
    return Spectrum(**dict(dict(wavelength_um=[1, 2], flux=[2, 1],
                               uncertainty=[.2, .1], flux_unit="Jy",
                               provenance=SYNTHETIC), **changes))


def test_optical_depth():
    result = process_spectrum(ContinuumRequest(spectrum=spectrum(), continuum=[2, 2]))
    assert result.normalized_flux == [1, .5]
    assert result.optical_depth == pytest.approx([0, np.log(2)])
    assert result.optical_depth_uncertainty == pytest.approx([.1, .1])
    assert "No molecular detection" in result.interpretation


@pytest.mark.parametrize("changes", [{"wavelength_um": [2, 1]},
                                      {"flux": [1]}, {"flux": [1, float("nan")]},
                                      {"uncertainty": [0, 1]}])
def test_bad_spectrum(changes):
    with pytest.raises(ValidationError):
        spectrum(**changes)


@pytest.mark.parametrize("flux,continuum", [([0, 1], [1, 1]), ([1, 1], [1]),
                                            ([1, 1], [-1, 1])])
def test_bad_continuum(flux, continuum):
    with pytest.raises(ValidationError):
        ContinuumRequest(spectrum=spectrum(flux=flux), continuum=continuum)


@pytest.mark.parametrize("changes", [{"mjd": [1]}, {"values": [1]},
                                     {"uncertainty": [-1, 1]}, {"mjd": [1, float("inf")]}])
def test_bad_curve(changes):
    data = dict(target="RW Aurigae", band="synthetic", time_scale="utc",
                mjd=[1, 2], values=[1, 2], uncertainty=[1, 1], unit="Jy",
                provenance=SYNTHETIC)
    data.update(changes)
    with pytest.raises(ValidationError):
        LightCurve(**data)


def asset(path):
    return FitsAsset(path=path, hdu=0, provenance=SYNTHETIC)


def write_image(path, data, shift=0, unit="Jy", celestial=True):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1 + shift, 1]
    wcs.wcs.cdelt = [-.001, .001]
    wcs.wcs.crval = [10, 20]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = wcs.to_header() if celestial else fits.Header()
    if unit:
        header["BUNIT"] = unit
    fits.writeto(path, np.asarray(data, dtype=float), header)


def test_difference_and_null(tmp_path):
    write_image(tmp_path / "s.fits", [[3, np.nan], [5, 7]])
    write_image(tmp_path / "r.fits", [[1000, 1000], [1000, 1000]], unit="mJy")
    result = difference_images(DifferenceRequest(science=asset("s.fits"),
                               reference=asset("r.fits"), reference_scale=2), tmp_path)
    assert result.pixels == [[1, None], [3, 5]]
    assert result.valid_pixels == 3
    assert "null" in result.model_dump_json()


@pytest.mark.parametrize("kwargs", [{"shift": 1}, {"unit": "s"},
                                    {"unit": ""}, {"celestial": False}])
def test_bad_images(tmp_path, kwargs):
    write_image(tmp_path / "s.fits", [[1, 2]])
    write_image(tmp_path / "r.fits", [[1, 2]], **kwargs)
    with pytest.raises(ValueError):
        difference_images(DifferenceRequest(science=asset("s.fits"),
                          reference=asset("r.fits")), tmp_path)


def test_shape_and_hdu(tmp_path):
    write_image(tmp_path / "s.fits", [[1, 2]])
    write_image(tmp_path / "r.fits", [[1]])
    with pytest.raises(ValueError, match="shapes"):
        difference_images(DifferenceRequest(science=asset("s.fits"),
                          reference=asset("r.fits")), tmp_path)
    fits.writeto(tmp_path / "vector.fits", np.ones(3))
    with pytest.raises(ValueError, match="2-D"):
        read_image(asset("vector.fits"), tmp_path)


def test_traversal(tmp_path):
    child = tmp_path / "root"
    child.mkdir()
    write_image(tmp_path / "outside.fits", [[1]])
    with pytest.raises(ValueError, match="escapes"):
        read_image(asset("../outside.fits"), child)
    with pytest.raises(ValueError, match="relative"):
        read_image(asset(str(tmp_path / "outside.fits")), child)


def test_catalog_mock_only():
    buffer = BytesIO()
    Table({"source_id": [123], "ra": [10.], "dec": [20.]}).write(buffer, format="votable")
    query = CatalogQuery(ra_deg=10, dec_deg=20, radius_deg=.01, limit=1)
    def handler(request):
        assert request.url.host == "irsa.ipac.caltech.edu"
        assert request.url.params["QUERY"] == build_adql(query)
        return httpx.Response(200, content=buffer.getvalue())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = query_splices(query, client)
    assert result.sources[0].source_id == "123"
    assert result.possibly_truncated


def test_catalog_error():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            query_splices(CatalogQuery(ra_deg=0, dec_deg=0, radius_deg=.1), client)


def test_comet_preparation():
    assert prepare_comet([]).status == "awaiting_data"
    assert prepare_comet([asset("comet.fits")]).status == "awaiting_geometry_and_calibration"


def test_fastapi_contract_and_existing_backend():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    sandbox = FastAPI()
    sandbox.post("/science", response_model=CurveSummary)(summarize_curve)
    assert "LightCurve" in sandbox.openapi()["components"]["schemas"]
    with TestClient(sandbox) as client:
        response = client.post("/science", json={"target": "RW Aurigae", "band": "synthetic",
            "time_scale": "utc", "mjd": [1, 2], "values": [1, 3],
            "uncertainty": [1, 1], "unit": "Jy", "provenance": SYNTHETIC.model_dump()})
        assert response.status_code == 200
        assert response.json()["weighted_mean"] == 2
