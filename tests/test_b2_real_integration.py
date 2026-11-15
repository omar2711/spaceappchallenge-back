"""Opt-in real integrations. No fabricated B1 manifest and no network by default."""

import json
import os
from pathlib import Path

import pytest

from app.b2.archive import search_observations
from app.b2.fits_io import read_image
from app.b2.models import FitsAsset
from app.b2.observation_models import FrameSpec, ObservationQuery, ScienceRun
from app.b2.photometry import aperture_measurement
from app.b2.validated_images import validated_difference


def test_live_irsa_small_query():
    if os.getenv("B2_LIVE_IRSA") != "1":
        pytest.skip("Set B2_LIVE_IRSA=1; queries only two metadata rows")
    # Position from the official IRSA introductory notebook, not a target claim.
    result = search_observations(ObservationQuery(ra_deg=304.693508808,
        dec_deg=42.4436872991, radius_deg=1/3600, limit=2), attempts=1)
    assert len(result.observations) <= 2


def test_b1_real_fits():
    config = os.getenv("B2_REAL_ASSET_JSON")
    root = os.getenv("B2_DATA_ROOT")
    if not config or not root:
        pytest.skip("Provide B2_DATA_ROOT and B2_REAL_ASSET_JSON (B2 FitsAsset adapter output)")
    asset = FitsAsset.model_validate_json(Path(config).read_text(encoding="utf-8"))
    assert asset.provenance.kind == "observation"
    data, header = read_image(asset, Path(root))
    assert data.ndim == 2 and "BUNIT" in header


def test_b1_real_difference():
    config, root = os.getenv("B2_REAL_PAIR_JSON"), os.getenv("B2_DATA_ROOT")
    if not config or not root:
        pytest.skip("Provide B2_DATA_ROOT and B2_REAL_PAIR_JSON with science/reference FrameSpec adapters")
    pair = json.loads(Path(config).read_text(encoding="utf-8"))
    science, reference = (FrameSpec.model_validate(pair[key]) for key in ("science", "reference"))
    assert science.image.provenance.kind == reference.image.provenance.kind == "observation"
    result = validated_difference(science, reference, Path(root))
    assert result.pixels


def test_real_cached_photometry():
    config, root = os.getenv("B2_REAL_RUN_JSON"), os.getenv("B2_DATA_ROOT")
    if not config or not root:
        pytest.skip("Provide B2_REAL_RUN_JSON and B2_DATA_ROOT for offline real-photometry replay")
    run = ScienceRun.model_validate_json(Path(config).read_text(encoding="utf-8"))
    assert run.measurements, "Select a real run with at least one accepted measurement"
    for previous in run.measurements:
        cutout = next(c for c in run.cutouts if c.asset.path == previous.input_path)
        assert cutout.asset.provenance.kind == "observation"
        result = aperture_measurement(cutout, Path(root), run.target, previous.aperture)
        assert result.flux_jy == pytest.approx(previous.flux_jy, rel=1e-9)
