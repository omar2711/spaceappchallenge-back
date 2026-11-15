"""Difference already registered, calibrated images; does not align or match PSFs."""

from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.wcs import WCS

from .fits_io import read_image
from .models import DifferenceRequest, DifferenceResult
from .spatial_wcs import same_celestial_grid


def difference_images(request: DifferenceRequest, data_root: Path) -> DifferenceResult:
    """Require identical celestial WCS definitions and equivalent brightness units.

    Strict WCS equality deliberately rejects some equivalent grids. B1 must align,
    PSF-match, mask flagged pixels as NaN, and photometrically calibrate beforehand.
    """
    science, sh = read_image(request.science, data_root)
    reference, rh = read_image(request.reference, data_root)
    if science.shape != reference.shape:
        raise ValueError("Image shapes differ")
    sw, rw = WCS(sh), WCS(rh)
    if not sw.has_celestial or not rw.has_celestial:
        raise ValueError("Both images require celestial WCS")
    if not same_celestial_grid(sh, rh):
        raise ValueError("Images must have identical WCS; alignment is required")
    if "BUNIT" not in sh or "BUNIT" not in rh:
        raise ValueError("Both images require BUNIT")
    conversion = u.Unit(rh["BUNIT"]).to(u.Unit(sh["BUNIT"]))
    result = science - request.reference_scale * conversion * reference
    valid = np.isfinite(science) & np.isfinite(reference) & np.isfinite(result)
    pixels = [[float(v) if ok else None for v, ok in zip(row, mask)]
              for row, mask in zip(result, valid)]
    return DifferenceResult(pixels=pixels, valid_pixels=int(valid.sum()),
                            unit=sh["BUNIT"], science=request.science,
                            reference=request.reference,
                            reference_scale=request.reference_scale)
