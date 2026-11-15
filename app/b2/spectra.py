"""Continuum normalization for supplied calibrated SPHEREx spectral samples."""

import numpy as np

from .models import ContinuumRequest, ProcessedSpectrum


def process_spectrum(request: ContinuumRequest) -> ProcessedSpectrum:
    """tau=-ln(F/C); sigma_tau=sigma_F/F assuming an exact continuum.

    This approximation excludes continuum uncertainty and spectral covariance.
    Negative tau is preserved; no clipping or molecular identification occurs.
    """
    flux = np.asarray(request.spectrum.flux)
    normalized = flux / np.asarray(request.continuum)
    return ProcessedSpectrum(
        spectrum=request.spectrum, normalized_flux=normalized.tolist(),
        optical_depth=(-np.log(normalized)).tolist(),
        optical_depth_uncertainty=(np.asarray(request.spectrum.uncertainty) / flux).tolist(),
    )
