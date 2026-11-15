"""Preparation only: no invented ephemerides, composition, or comet detections."""

from .models import CometPlan, FitsAsset


def prepare_comet(assets: list[FitsAsset]) -> CometPlan:
    """Declare remaining prerequisites before moving-target analysis is possible."""
    return CometPlan(
        assets=assets,
        status="awaiting_geometry_and_calibration" if assets else "awaiting_data",
        required=["Calibrated science, uncertainty and quality FITS HDUs",
                  "Observation start/end, time scale and exposure duration",
                  "Observer-specific ephemerides and moving-target registration",
                  "Wavelength calibration, response, PSF and background treatment",
                  "Aperture definition and calibration/geometry provenance"],
    )
