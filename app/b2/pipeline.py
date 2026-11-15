"""Reproducible bounded science runs and exports, independent of HTTP endpoints."""

import csv
from pathlib import Path
from typing import Any

import httpx

from .archive import CutoutCache, search_observations
from .observation_models import (ApertureConfig, DownloadLimits, ObservationQuery,
                                 ProcessingIssue, ScienceRun, Target)
from .photometry import aperture_measurement


def run_target(target: Target, query: ObservationQuery, cache_root: Path,
               client: httpx.Client, aperture: ApertureConfig, limits: DownloadLimits,
               *, irsa: Any = None) -> ScienceRun:
    """Discover -> bounded cutouts -> measurements. Every failure remains visible."""
    if query.ra_deg != target.ra_deg or query.dec_deg != target.dec_deg:
        raise ValueError("Query and photometry target coordinates must match")
    run = ScienceRun(target=target, search=None, status="failed")
    try:
        run.search = search_observations(query, irsa=irsa)
    except Exception as exc:
        run.issues.append(ProcessingIssue(observation_id=None, stage="query",
                                           message=f"{type(exc).__name__}: {exc}"))
        return run
    if not run.search.observations:
        run.status = "empty"
        return run
    cache = CutoutCache(cache_root, client, limits)
    for observation in run.search.observations[:limits.max_files]:
        try:
            cutout = cache.fetch(observation, target)
            run.cutouts.append(cutout)
        except Exception as exc:
            run.issues.append(ProcessingIssue(observation_id=observation.observation_id,
                stage="download", message=f"{type(exc).__name__}: {exc}"))
            continue
        try:
            run.measurements.append(aperture_measurement(cutout, cache_root, target, aperture))
        except Exception as exc:
            run.issues.append(ProcessingIssue(observation_id=observation.observation_id,
                stage="photometry", message=f"{type(exc).__name__}: {exc}"))
    run.status = ("partial" if run.issues else "insufficient_compatible_epochs") if run.measurements else "failed"
    run.warnings = ["Budget-limited selection; not a complete light curve",
                    "No response-matched, aperture-corrected light curve has been established",
                    "Fluxes are preliminary aperture measurements; no magnitudes generated"]
    return run


def export_run(run: ScienceRun, output: Path) -> ScienceRun:
    """Create a fresh output directory; never overwrite existing artifacts.

    PNG shows isolated points per detector with wavelength labels, no connected
    light curve. Zero fabricated points are emitted for failed or empty runs.
    """
    output.mkdir(parents=True, exist_ok=False)
    run = run.model_copy(deep=True)
    run.result_paths = ["run.json", "measurements.csv"]
    fields = ["target_id", "ra_deg", "dec_deg", "collection", "dataset_version",
              "observation_id", "source_url", "mjd", "time_scale", "detector",
              "wavelength_um", "bandwidth_um", "flux_jy", "uncertainty_jy", "status", "input_path"]
    with (output / "measurements.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for m in run.measurements:
            writer.writerow(dict(target_id=run.target.target_id, ra_deg=run.target.ra_deg,
                dec_deg=run.target.dec_deg, collection=m.observation.collection,
                dataset_version=m.dataset_version, observation_id=m.observation.observation_id,
                source_url=m.observation.access_url, mjd=m.mjd, time_scale=m.time_scale,
                detector=m.detector, wavelength_um=m.wavelength_um, bandwidth_um=m.bandwidth_um,
                flux_jy=m.flux_jy, uncertainty_jy=m.uncertainty_jy, status=m.status, input_path=m.input_path))
    timed = [m for m in run.measurements if m.mjd is not None and m.time_scale is not None]
    if timed:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib.ticker import MaxNLocator
        # Separate panels by detector AND time scale. No cross-band aggregation.
        groups = sorted({(m.detector, m.time_scale) for m in timed})
        figure = Figure(figsize=(9, max(3, 3 * len(groups))))
        FigureCanvasAgg(figure)
        for index, (detector, scale) in enumerate(groups, 1):
            ax = figure.add_subplot(len(groups), 1, index)
            epochs = [m.mjd for m in timed if (m.detector, m.time_scale) == (detector, scale) and m.mjd is not None]
            padding = max((max(epochs) - min(epochs)) * .1, .001)
            ax.set_xlim(min(epochs) - padding, max(epochs) + padding)
            ax.ticklabel_format(axis="x", style="plain", useOffset=False)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            for m in timed:
                if (m.detector, m.time_scale) != (detector, scale):
                    continue
                assert m.mjd is not None
                ax.errorbar(m.mjd, m.flux_jy, yerr=m.uncertainty_jy, fmt="o")
                ax.annotate(f"{m.wavelength_um:.4f} um", (m.mjd, m.flux_jy), fontsize=8)
            ax.set(xlabel=f"MJD ({scale})", ylabel="Finite-aperture flux [Jy]",
                   title=f"{run.target.target_id} / detector {detector}: preliminary samples, different wavelengths")
        figure.tight_layout()
        figure.savefig(output / "samples.png", dpi=140)
        run.result_paths.append("samples.png")
    with (output / "run.json").open("x", encoding="utf-8") as handle:
        handle.write(run.model_dump_json(indent=2))
    return run


def reprocess_run(run: ScienceRun, cache_root: Path, aperture: ApertureConfig) -> ScienceRun:
    """Recompute existing cutouts without network, preserving discovery provenance."""
    result = run.model_copy(deep=True)
    result.measurements = []
    result.issues = [issue for issue in result.issues if issue.stage != "photometry"]
    result.result_paths = []
    for cutout in run.cutouts:
        try:
            result.measurements.append(aperture_measurement(cutout, cache_root, run.target, aperture))
        except Exception as exc:
            result.issues.append(ProcessingIssue(observation_id=cutout.observation.observation_id,
                stage="photometry", message=f"{type(exc).__name__}: {exc}"))
    result.status = ("partial" if result.issues else "insufficient_compatible_epochs") if result.measurements else "failed"
    return result
