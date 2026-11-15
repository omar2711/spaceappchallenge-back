"""Single-band descriptive variability, without period or event claims."""

import numpy as np

from .models import CurveSummary, LightCurve


def summarize_curve(curve: LightCurve) -> CurveSummary:
    """Sort by epoch and test a constant mean with independent Gaussian errors."""
    order = np.argsort(curve.mjd, kind="stable")
    values = np.asarray(curve.values)[order]
    errors = np.asarray(curve.uncertainty)[order]
    weights = (errors.min() / errors) ** 2
    mean = float(np.average(values, weights=weights))
    sorted_curve = curve.model_copy(update={
        "mjd": np.asarray(curve.mjd)[order].tolist(),
        "values": values.tolist(), "uncertainty": errors.tolist(),
    })
    return CurveSummary(
        curve=sorted_curve, weighted_mean=mean,
        mean_uncertainty=float(errors.min() / np.sqrt(weights.sum())),
        peak_to_peak=float(np.ptp(values)),
        chi_square_constant=float(np.sum(((values - mean) / errors) ** 2)),
        degrees_of_freedom=len(values) - 1,
    )
