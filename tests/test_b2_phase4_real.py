"""Opt-in real package/B1 integration. No downloads or fabricated B1 contracts."""

import json
import os
import socket
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.b2.b1_adapter import B1Frame, process_b1_pair
from app.b2.offline_bundle import validate_bundle
from app.b2.offline_demo import main
from app.b2.service import DemoSummary, ScienceService


def package_root():
    value = os.getenv("B2_OFFLINE_BUNDLE")
    if not value:
        pytest.skip("Set B2_OFFLINE_BUNDLE to the actual validated phase-4 package")
    return Path(value)


def test_actual_phase4_package_integrity_and_service():
    root = package_root()
    report = validate_bundle(root)
    assert report.valid and report.target_count == 5 and report.fits_verified == 12
    service = ScienceService(root)
    assert len(service.list_targets()) == 5
    m = service.get_photometry("WISE 0855")[0]
    assert m.flux_jy/m.uncertainty_jy == pytest.approx(1.15699684, rel=1e-7)
    assert service.get_status("WISE 0855").spectra.availability == "incomplete"
    assert not service.get_photometry("RW Aurigae")
    assert not service.get_photometry("R Draconis")
    assert service.get_status("R Draconis").light_curve.availability == "unavailable"
    assert len(service.get_splices().rows) == 1
    assert not service.get_differences("RW Aurigae")


def test_actual_phase4_cli_offline_no_network(tmp_path):
    root = package_root()
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")), \
            patch.object(httpx.Client, "send", side_effect=AssertionError("Network forbidden")), \
            patch("sys.argv", ["offline_demo", "demo", "--bundle", str(root),
                "--summary", str(tmp_path/"summary.json"), "--recompute", str(tmp_path/"replayed")]):
        assert main() == 0
    summary = json.loads((tmp_path/"summary.json").read_text())
    typed = DemoSummary.model_validate(summary)
    assert typed.reproduction is not None and typed.reproduction.success
    assert summary["success"] and summary["reproduction"]["success"]
    assert summary["reproduction"]["targets_reprocessed"] == 5
    assert summary["reproduction"]["measurements_compared"] == 1
    assert len(summary["observations"]["WISE 0855"]) == 48
    assert summary["spectra"]["WISE 0855"][0]["points"][0]["signal_to_noise"] == pytest.approx(1.15699684, rel=1e-7)
    assert summary["differences"]["RW Aurigae"] == []


def test_real_b1_adapter_pair(tmp_path):
    value, root = os.getenv("B2_B1_PAIR_JSON"), os.getenv("B2_B1_DATA_ROOT")
    if not value or not root:
        pytest.skip("Need real B1Pair adapter JSON + B2_B1_DATA_ROOT: target, epochs, passes, effective band, PSF/registration evidence, masks/noise")
    payload = json.loads(Path(value).read_text(encoding="utf-8"))
    science, reference = (B1Frame.model_validate(payload[key]) for key in ("science", "reference"))
    assert science.metadata_provenance.kind == reference.metadata_provenance.kind == "observation"
    result = process_b1_pair(science, reference, Path(root), tmp_path/"difference")
    assert result.input_kind == "observational_inputs"
