"""Opt-in stricter difference adapter; original difference API stays compatible."""

from pathlib import Path

import numpy as np
from astropy import units as u

from .fits_io import read_image
from .observation_models import FrameSpec, ValidatedDifference
from .spatial_wcs import same_celestial_grid


def _frame(spec: FrameSpec, root: Path):
    image, header = read_image(spec.image, root)
    flags, fh = read_image(spec.flags, root)
    sky, sh = read_image(spec.background_mask, root)
    for asset, ancillary_header in [(spec.flags, fh), (spec.background_mask, sh)]:
        if asset.path != spec.image.path:
            if not same_celestial_grid(header, ancillary_header):
                raise ValueError("Ancillary file requires the identical celestial WCS")
    if flags.shape != image.shape or sky.shape != image.shape:
        raise ValueError("Ancillary image dimensions do not match")
    if not np.all(np.isfinite(flags)) or np.any(flags < 0) or np.any(flags != np.floor(flags)):
        raise ValueError("Flags must be finite nonnegative integers")
    if np.any(flags > 2**32 - 1):
        raise ValueError("Flag values exceed 32 bits")
    valid = np.isfinite(image) & ((flags.astype(np.uint64) & spec.rejected_flag_bits) == 0)
    variance = None
    noise_asset = spec.variance or spec.uncertainty
    if noise_asset:
        variance, vh = read_image(noise_asset, root)
        if noise_asset.path != spec.image.path:
            if not same_celestial_grid(header, vh):
                raise ValueError("Variance file requires the identical celestial WCS")
        if variance.shape != image.shape:
            raise ValueError("Variance dimensions do not match")
        valid &= np.isfinite(variance) & (variance >= 0)
        if spec.uncertainty:
            variance = (variance * u.Unit(vh["BUNIT"]).to(u.Unit(header["BUNIT"]))) ** 2
        else:
            variance *= u.Unit(vh["BUNIT"]).to(u.Unit(header["BUNIT"]) ** 2)
    if str(header.get("DETECTOR", "")) != spec.detector:
        raise ValueError("FITS detector disagrees with adapter metadata")
    return image, header, valid, variance, np.isfinite(sky) & (sky != 0)


def validated_difference(science: FrameSpec, reference: FrameSpec, root: Path) -> ValidatedDifference:
    """Same response/calibration/PSF IDs required, with independent blank-sky mask.

    IDs are B1 attestations, not inferred from detector names. No resampling.
    Background offset is an unweighted mean on common blank sky; its variance
    includes spatial scatter. Covariance of background pixels with offset is
    accounted for on those pixels when input variances are supplied.
    """
    for name in ("detector", "response_id", "calibration_id", "psf_match_id"):
        if getattr(science, name) != getattr(reference, name):
            raise ValueError(f"Incompatible {name}")
    a, ah, av, va, asky = _frame(science, root)
    b, bh, bv, vb, bsky = _frame(reference, root)
    if a.shape != b.shape:
        raise ValueError("Image shapes differ")
    if not same_celestial_grid(ah, bh):
        raise ValueError("Identical celestial WCS and pixel scale required")
    factor = u.Unit(bh["BUNIT"]).to(u.Unit(ah["BUNIT"]))
    difference = a - b * factor
    valid = av & bv & np.isfinite(difference)
    sky = valid & asky & bsky
    n = int(sky.sum())
    if n < 20:
        raise ValueError("At least 20 common blank-sky pixels required")
    offset = float(np.mean(difference[sky]))
    difference -= offset
    sigma = None
    offset_sigma = None
    notes = ["Registration/PSF/response compatibility attested by caller; inspect residuals",
             "No calibration systematics or resampling covariance included"]
    if va is not None and vb is not None:
        variance = va + factor ** 2 * vb
        offset_variance = max(float(variance[sky].sum() / n ** 2),
                              float(np.var(difference[sky], ddof=1) / n))
        total = variance + offset_variance
        total[sky] -= 2 * variance[sky] / n
        sigma = np.sqrt(np.maximum(total, 0))
        offset_sigma = np.sqrt(offset_variance)
    else:
        notes.append("Missing variance on at least one frame; no uncertainty reported")
    def json_pixels(array):
        return [[float(v) if ok else None for v, ok in zip(row, mask)]
                for row, mask in zip(array, valid)]
    return ValidatedDifference(science=science, reference=reference,
        pixels=json_pixels(difference), uncertainty=json_pixels(sigma) if sigma is not None else None,
        unit=ah["BUNIT"], background_offset=offset,
        background_offset_uncertainty=offset_sigma, warnings=notes)
