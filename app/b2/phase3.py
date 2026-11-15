"""Bounded five-target acquisition and strictly offline replay for a science demo."""

import argparse
import json
from pathlib import Path

import httpx
from astropy.io import fits
from astropy.time import Time
from pydantic import Field

from .archive import CutoutCache, search_observations
from .compatibility import group_compatible_samples
from .models import Contract
from .observation_models import (ApertureConfig, CachedCutout, DownloadLimits,
    ObservationQuery, ProcessingIssue, ScienceRun)
from .photometry import aperture_measurement
from .pipeline import export_run
from .spectral_products import SpectralProduct, export_spectral_product, from_measurements
from .targets import Astrometry, TARGET_NAMES, resolve_target, target_at_epoch

FLAG_POLICY = "https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/ ; reject all bits except SOURCE(21), FULLSAMPLE(12); mask SOURCE in background"
APERTURE = ApertureConfig(rejected_flag_bits=4292866047, flag_policy_source=FLAG_POLICY,
    background_rejected_flag_bits=1 << 21, annulus_outer_px=7)


class TargetResult(Contract):
    target_id: str
    astrometry: Astrometry | None = None
    run: ScienceRun | None = None
    spectra: list[SpectralProduct] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    processing_aperture: ApertureConfig = Field(default_factory=lambda: APERTURE.model_copy(deep=True))


def _measure(cutout: CachedCutout, root: Path, astrometry: Astrometry,
             aperture: ApertureConfig):
    # read_image in aperture_measurement enforces root containment; check here
    # before reading the observation-time header too.
    path = (root / cutout.asset.path).resolve(strict=True)
    if Path(cutout.asset.path).is_absolute() or not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Cutout path escapes data root")
    header = fits.getheader(path, "IMAGE")
    scale = str(header["TIMESYS"]).lower()
    if scale not in ("utc", "tt", "tdb"):
        raise ValueError("Unsupported or missing FITS time scale")
    epoch = Time(float(header["MJD-OBS"]), format="mjd", scale=scale)
    return aperture_measurement(cutout, root, target_at_epoch(astrometry, epoch), aperture)


def _process(run: ScienceRun, astrometry: Astrometry, cache_root: Path,
             aperture: ApertureConfig = APERTURE) -> ScienceRun:
    result = run.model_copy(deep=True)
    result.measurements = []
    result.issues = [issue for issue in result.issues if issue.stage != "photometry"]
    result.result_paths = []
    for cutout in result.cutouts:
        try:
            result.measurements.append(_measure(cutout, cache_root, astrometry, aperture))
        except Exception as exc:
            result.issues.append(ProcessingIssue(observation_id=cutout.observation.observation_id,
                stage="photometry", message=f"{type(exc).__name__}: {exc}"))
    result.status = ("partial" if result.issues else "insufficient_compatible_epochs") if result.measurements else "failed"
    if result.search and result.search.status == "empty" and not result.cutouts and not result.issues:
        result.status = "empty"
    result.warnings = list(astrometry.warnings) + [
        "Proper motion propagated to FITS epoch; observer parallax is not modeled",
        "Preliminary finite aperture; no validated total-flux calibration or temporal light curve",
        "Budget-limited acquisition does not establish archive completeness"]
    return result


def reprocess_target(run: ScienceRun, astrometry: Astrometry, cache_root: Path,
                     aperture: ApertureConfig = APERTURE) -> ScienceRun:
    """Public offline entry point reusing the phase-3 calculation without network."""
    return _process(run, astrometry, cache_root, aperture)


def acquire_target(astrometry: Astrometry, cache: CutoutCache,
                   existing: list[CachedCutout] | None = None) -> ScienceRun:
    """Query up to 48 metadata rows; at most two new cutouts for this target.

    Existing products are reused even when a newly limited SIA page omits them.
    Acquisition positions use approximate ObsCore epoch; measurement positions
    always use the actual FITS epoch/time scale. No source recentering is fitted.
    """
    target = target_at_epoch(astrometry, Time(2025.5, format="jyear", scale="tt"))
    run = ScienceRun(target=target, search=None, status="failed", cutouts=list(existing or []))
    query = ObservationQuery(ra_deg=target.ra_deg, dec_deg=target.dec_deg, radius_deg=1/3600, limit=48)
    try:
        run.search = search_observations(query, attempts=1)
    except Exception as exc:
        run.issues.append(ProcessingIssue(observation_id=None, stage="query", message=f"{type(exc).__name__}: {exc}"))
        return _process(run, astrometry, cache.root)
    seen = {c.observation.access_url for c in run.cutouts}
    detectors = {c.observation.band for c in run.cutouts}
    choices = sorted(run.search.observations,
                     key=lambda o: (o.band in detectors, o.mjd_start if o.mjd_start is not None else float("inf")))
    selected = []
    for observation in choices:
        if observation.access_url in seen:
            continue
        if observation.band in detectors:
            continue
        selected.append(observation)
        detectors.add(observation.band)
        if len(selected) == 2:
            break
    if len(selected) < 2:
        used = seen | {o.access_url for o in selected}
        selected.extend(o for o in choices if o.access_url not in used)
        selected = selected[:2]
    for observation in selected:
        try:
            if observation.mjd_start is None:
                raise ValueError("No observation epoch available for acquisition")
            # ObsCore time scale absent: this approximation is for centering only.
            center = target_at_epoch(astrometry, Time(observation.mjd_start, format="mjd", scale="tt"))
            run.cutouts.append(cache.fetch(observation, center))
        except Exception as exc:
            run.issues.append(ProcessingIssue(observation_id=observation.observation_id,
                stage="download", message=f"{type(exc).__name__}: {exc}"))
    result = _process(run, astrometry, cache.root)
    if not run.search.observations and not run.cutouts:
        result.status = "empty"
    return result


def export_target(astrometry: Astrometry, run: ScienceRun, cache_root: Path, output: Path,
                   aperture: ApertureConfig = APERTURE) -> TargetResult:
    """Exports raw epochs separately and growth checks; no claim of validated spectra."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "astrometry.json").write_text(astrometry.model_dump_json(indent=2), encoding="utf-8")
    saved_run = export_run(run, output / "photometry")
    products = from_measurements(run.target, run.measurements, run.cutouts)
    saved_products = [export_spectral_product(p, output / f"spectral-{i}") for i, p in enumerate(products)]
    compatible = group_compatible_samples(run.measurements)
    (output / "compatibility.json").write_text(compatible.model_dump_json(indent=2), encoding="utf-8")
    growth = []
    for m in run.measurements:
        cutout = next(c for c in run.cutouts if c.asset.path == m.input_path)
        for radius in (2., 2.5, 3.):
            row: dict = {"input_path": m.input_path, "radius_px": radius}
            try:
                config = m.aperture.model_copy(update={"radius_px": radius})
                sample = _measure(cutout, cache_root, astrometry, config)
                row.update(flux_jy=sample.flux_jy, uncertainty_jy=sample.uncertainty_jy,
                           status="preliminary", warning="Correlated apertures; not an independent calibration test")
            except Exception as exc:
                row.update(status="rejected", error=f"{type(exc).__name__}: {exc}")
            growth.append(row)
    (output / "aperture-validation.json").write_text(json.dumps(growth, indent=2), encoding="utf-8")
    result = TargetResult(target_id=run.target.target_id, astrometry=astrometry,
        run=saved_run, spectra=saved_products, processing_aperture=aperture, limitations=[
            "Sparse spectral samples only; no complete official forced-photometry spectrum acquired",
            "Aperture growth is diagnostic, not an aperture/PSF correction",
            "No response_id/calibrated total flux per epoch; no validated light curve",
            "Observer parallax/orbital motion and blending require further validation"])
    (output / "target-result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh directory")
    parser.add_argument("--cache", type=Path, default=Path(".b2-cache"))
    parser.add_argument("--astrometry", type=Path, help="Directory of verified Astrometry JSON files")
    parser.add_argument("--offline", type=Path, help="Prior phase3 output; absolutely no network")
    parser.add_argument("--reuse", type=Path, action="append", default=[], help="Prior ScienceRun JSON")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results: list[TargetResult] = []
    if args.offline:
        for target_dir in sorted(args.offline.glob("target-*")):
            old = TargetResult.model_validate_json((target_dir / "target-result.json").read_text(encoding="utf-8"))
            if old.astrometry is None or old.run is None:
                results.append(old)
                directory = args.output / target_dir.name
                directory.mkdir()
                (directory / "target-result.json").write_text(old.model_dump_json(indent=2), encoding="utf-8")
                continue
            run = _process(old.run, old.astrometry, args.cache, old.processing_aperture)
            results.append(export_target(old.astrometry, run, args.cache, args.output / target_dir.name,
                                          old.processing_aperture))
        if not results:
            raise ValueError("Offline bundle contains no target results")
    else:
        saved_astrometry = {}
        if args.astrometry:
            for path in args.astrometry.glob("*.json"):
                a = Astrometry.model_validate_json(path.read_text(encoding="utf-8"))
                saved_astrometry[a.reference.target_id] = a
        reused: dict[str, list[CachedCutout]] = {}
        for path in args.reuse:
            previous = ScienceRun.model_validate_json(path.read_text(encoding="utf-8"))
            reused.setdefault(previous.target.target_id, []).extend(previous.cutouts)
        # Global new-download budget across all five targets, not five independent budgets.
        with httpx.Client(timeout=30) as client:
            cache = CutoutCache(args.cache, client, DownloadLimits(max_files=10,
                max_file_bytes=5_000_000, max_total_bytes=45_000_000, max_seconds=300))
            for index, name in enumerate(TARGET_NAMES):
                print(name, flush=True)
                try:
                    a = saved_astrometry.get(name) or resolve_target(name, client)
                    run = acquire_target(a, cache, reused.get(name))
                    results.append(export_target(a, run, args.cache, args.output / f"target-{index}"))
                except Exception as exc:
                    result = TargetResult(target_id=name, limitations=[f"{type(exc).__name__}: {exc}"])
                    results.append(result)
                    directory = args.output / f"target-{index}"
                    directory.mkdir(exist_ok=True)
                    with (directory / "target-result.json").open("x", encoding="utf-8") as handle:
                        handle.write(result.model_dump_json(indent=2))
    index_rows = []
    for path in sorted(args.output.glob("target-*/target-result.json")):
        r = TargetResult.model_validate_json(path.read_text(encoding="utf-8"))
        directory = path.parent.name
        index_rows.append({"target_id": r.target_id, "status": r.run.status if r.run else "failed",
            "spectral_points": sum(len(p.points) for p in r.spectra),
            "target_result_path": f"{directory}/target-result.json",
            "photometry_path": f"{directory}/photometry/run.json" if r.run else None,
            "spectral_products": [f"{directory}/spectral-{i}/spectrum.json" for i in range(len(r.spectra))],
            "limitations": r.limitations})
    (args.output / "index.json").write_text(json.dumps(index_rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
