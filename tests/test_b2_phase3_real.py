"""Opt-in tests against actual acquired products; never fabricated observations."""

import hashlib
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import httpx
import pytest
from astropy.coordinates import SkyCoord

from app.b2.archive import CutoutCache
from app.b2.catalog_snapshot import SplicesSnapshot, scs_splices_snapshot
from app.b2.models import CatalogQuery
from app.b2.observation_models import DownloadLimits, Target
from app.b2.phase3 import TargetResult, _measure


def bundle():
    path, root = os.getenv("B2_PHASE3_BUNDLE"), os.getenv("B2_DATA_ROOT")
    if not path or not root:
        pytest.skip("Set B2_PHASE3_BUNDLE and B2_DATA_ROOT to actual phase3 artifacts")
    targets = [TargetResult.model_validate_json(p.read_text(encoding="utf-8"))
               for p in sorted(Path(path).glob("target-*/target-result.json"))]
    return targets, Path(root)


def test_actual_phase3_fits_and_measurements():
    targets, root = bundle()
    assert len(targets) == 5
    accepted = 0
    for target in targets:
        assert target.astrometry is not None and target.run is not None
        for cutout in target.run.cutouts:
            assert cutout.asset.provenance.kind == "observation"
            assert urlsplit(cutout.observation.access_url).hostname == "irsa.ipac.caltech.edu"
            assert hashlib.sha256((root/cutout.asset.path).read_bytes()).hexdigest() == cutout.sha256
        for previous in target.run.measurements:
            c = next(c for c in target.run.cutouts if c.asset.path == previous.input_path)
            result = _measure(c, root, target.astrometry, previous.aperture)
            assert result.flux_jy == pytest.approx(previous.flux_jy, rel=1e-10)
            assert result.uncertainty_jy == pytest.approx(previous.uncertainty_jy, rel=1e-10)
            accepted += 1
    assert accepted >= 1, "Real bundle must contain a reproducible accepted flux estimate, not necessarily a detection"


def test_actual_cutout_cache_replay_no_network():
    targets, root = bundle()
    c = next(c for t in targets if t.run for c in t.run.cutouts)
    params = parse_qs(urlsplit(c.cutout_url).query)
    ra, dec = params["center"][0].removesuffix("d").split(",")
    target = Target(target_id="cache replay center", ra_deg=float(ra), dec_deg=float(dec),
                    coordinate_source="Actual acquisition URL")
    def forbidden(request):
        raise AssertionError("Cache replay must not contact any service")
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        result = CutoutCache(root, client, DownloadLimits(max_files=1, max_file_bytes=5_000_000,
            cutout_size_deg=float(params["size"][0]))).fetch(c.observation, target)
    assert result.cache_hit and result.sha256 == c.sha256


def test_actual_splices_source_and_units():
    path = os.getenv("B2_REAL_SPLICES_JSON")
    if not path:
        pytest.skip("Set B2_REAL_SPLICES_JSON to an actual SCS or TAP snapshot")
    snapshot = SplicesSnapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))
    assert snapshot.rows and snapshot.columns["ra"]["unit"] == "deg"
    center = SkyCoord(snapshot.query.ra_deg, snapshot.query.dec_deg, unit="deg")
    for row in snapshot.rows:
        assert isinstance(row["source_id"], str)
        point = SkyCoord(float(row["ra"]), float(row["dec"]), unit="deg")
        assert center.separation(point).deg <= snapshot.query.radius_deg


def test_live_splices_scs():
    if os.getenv("B2_LIVE_SPLICES") != "1":
        pytest.skip("Explicitly set B2_LIVE_SPLICES=1 to contact IRSA SCS")
    with httpx.Client(timeout=30) as client:
        snapshot = scs_splices_snapshot(CatalogQuery(ra_deg=76.95652603458,
            dec_deg=30.40143817389, radius_deg=.01, limit=5), client)
    assert len(snapshot.rows) <= 5 and snapshot.columns
