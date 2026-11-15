"""B2-side adapter for B1 images; does not define or modify B1's own manifest."""

from pathlib import Path
from typing import Literal

from astropy import units as u
from astropy.time import Time
from astropy.wcs import WCS
from pydantic import Field

from .difference_export import DifferenceArtifacts, export_difference
from .fits_io import read_image
from .models import Number, Provenance
from .observation_models import FrameSpec, Target
from .safe_paths import inside
from .spatial_wcs import same_celestial_grid


class B1Frame(FrameSpec):
    """Extend FrameSpec with explicit pass/epoch/band and review attestations.

    WCS and units are read from the selected image HDU. Optional declared WCS and
    units must match; no header inheritance or hidden unit conversion is guessed.
    """

    target: Target
    mjd: Number
    time_scale: Literal["utc", "tt", "tdb"]
    pass_id: str = Field(min_length=1)
    band_id: str = Field(min_length=1, description="Effective band/channel, not detector alone")
    declared_unit: str | None = None
    declared_wcs: dict[str, str | float | int] | None = None
    registration_evidence: str = Field(min_length=1)
    psf_evidence: str = Field(min_length=1)
    metadata_provenance: Provenance


def validate_b1_frame(frame: B1Frame, data_root: Path) -> None:
    """Check server-root paths and metadata against FITS, without writing inputs."""
    frame = B1Frame.model_validate(frame.model_dump())
    for asset in (frame.image, frame.flags, frame.background_mask, frame.variance, frame.uncertainty):
        if asset is not None:
            inside(data_root, asset.path)
            if asset.provenance.kind != frame.metadata_provenance.kind:
                raise ValueError("Mixed synthetic/observational provenance in B1 inputs")
    _, header = read_image(frame.image, data_root)
    if str(header.get("DETECTOR", "")) != frame.detector:
        raise ValueError("Declared detector disagrees with FITS")
    if str(header.get("TIMESYS", "")).lower() != frame.time_scale or "MJD-OBS" not in header:
        raise ValueError("Explicit MJD-OBS and matching TIMESYS required in selected HDU")
    if abs(float(header["MJD-OBS"]) - frame.mjd) > 1e-6:
        raise ValueError("Declared epoch disagrees with FITS (tolerance 0.0864 seconds)")
    wcs = WCS(header)
    if not wcs.has_celestial:
        raise ValueError("Celestial WCS required")
    if frame.declared_wcs is not None:
        if not same_celestial_grid(header, frame.declared_wcs):
            raise ValueError("Declared WCS disagrees with FITS")
    unit = u.Unit(header["BUNIT"])
    if frame.declared_unit and u.Unit(frame.declared_unit) != unit:
        raise ValueError("Declared photometric unit disagrees with FITS")
    if frame.observation:
        if frame.observation.mjd_start is not None and abs(frame.observation.mjd_start-frame.mjd) > 1e-6:
            raise ValueError("Observation metadata epoch disagrees with frame")
    if not frame.response_id.strip() or not frame.calibration_id.strip() or not frame.psf_match_id.strip():
        raise ValueError("Response, calibration and PSF identity must be explicit")
    if not frame.pass_id.strip() or not frame.band_id.strip() or not frame.registration_evidence.strip() or not frame.psf_evidence.strip():
        raise ValueError("Pass, band, registration and PSF evidence must be nonblank")


def process_b1_pair(science: B1Frame, reference: B1Frame, data_root: Path,
                    output: Path) -> DifferenceArtifacts:
    """Validate two distinct passes, then reuse the existing strict difference engine.

    Registration and PSF evidence remain caller attestations. A computed difference
    does not by itself confirm a temporal change or a source detection.
    """
    if science.target.target_id != reference.target.target_id:
        raise ValueError("Different target identifiers")
    if science.pass_id == reference.pass_id:
        raise ValueError("Distinct pass identifiers are required")
    if science.band_id != reference.band_id:
        raise ValueError("Incompatible effective band")
    if Time(science.mjd, format="mjd", scale=science.time_scale) == Time(reference.mjd, format="mjd", scale=reference.time_scale):
        raise ValueError("Distinct observation epochs are required")
    validate_b1_frame(science, data_root)
    validate_b1_frame(reference, data_root)
    return export_difference(science, reference, data_root, output)
