"""Spectral products with per-sample provenance; no implicit time/band merging."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Literal

import numpy as np
from astropy import units as u
from astropy.table import Table
from pydantic import Field, model_validator

from .models import Contract, FitsAsset, Number, Positive
from .observation_models import CachedCutout, Measurement, Target

REFERENCE_BANDS = {"H2O reference (not a detection)": 3.05,
                   "CO2 reference (not a detection)": 4.27,
                   "CO reference (not a detection)": 4.67}


class SpectralPoint(Contract):
    row: int = Field(ge=0)
    wavelength_um: Positive | None
    bandwidth_um: Positive | None
    flux_jy: Number | None
    uncertainty_jy: Positive | None
    mjd: Number | None
    time_scale: Literal["utc", "tt", "tdb"] | None = None
    detector: str | None
    collection: str | None
    observation_id: str | None
    flags: int | None = Field(default=None, ge=0)
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    input_path: str
    source_url: str
    measurement_target: Target | None = None
    signal_to_noise: Number | None = None
    detection_claim: Literal["none"] = "none"
    input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cutout_url: str | None = None
    retrieved_at_utc: str | None = None

    @model_validator(mode="after")
    def usable(self) -> "SpectralPoint":
        if self.accepted and any(v is None for v in (
                self.wavelength_um, self.flux_jy, self.uncertainty_jy,
                self.detector, self.collection, self.observation_id)):
            raise ValueError("Accepted point lacks required science metadata")
        if self.accepted and self.reasons:
            raise ValueError("Accepted point cannot contain rejection reasons")
        return self


class SpectralProduct(Contract):
    target: Target
    method: Literal["official_forced_photometry", "preliminary_aperture"]
    dataset_version: str = Field(min_length=1)
    calibration_id: str | None = None
    points: list[SpectralPoint]
    status: Literal["empty", "partial", "usable_samples"]
    warnings: list[str]
    reference_bands_um: dict[str, Positive] = Field(default_factory=lambda: dict(REFERENCE_BANDS))
    result_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def calibration(self) -> "SpectralProduct":
        if self.method == "official_forced_photometry" and not self.calibration_id:
            raise ValueError("Official spectrum requires explicit calibration provenance")
        accepted = sum(p.accepted for p in self.points)
        expected = "empty" if not accepted else "partial" if accepted < len(self.points) else "usable_samples"
        if self.status != expected:
            raise ValueError("Product status does not match accepted sample count")
        return self


def from_measurements(target: Target, measurements: list[Measurement],
                       cutouts: list[CachedCutout] | None = None) -> list[SpectralProduct]:
    """Separate collections and processing versions; do not coadd any epochs."""
    groups: dict[tuple[str, str], list[Measurement]] = {}
    for m in measurements:
        if m.target.target_id != target.target_id:
            raise ValueError("Measurements belong to a different target")
        groups.setdefault((m.observation.collection, m.dataset_version), []).append(m)
    products = []
    provenance = {c.asset.path: c for c in cutouts or []}
    for (_, version), samples in groups.items():
        points = [SpectralPoint(row=i, wavelength_um=m.wavelength_um, bandwidth_um=m.bandwidth_um,
            flux_jy=m.flux_jy, uncertainty_jy=m.uncertainty_jy, mjd=m.mjd,
            time_scale=m.time_scale, detector=m.detector, collection=m.observation.collection,
            observation_id=m.observation.observation_id, accepted=True, input_path=m.input_path,
            source_url=m.observation.access_url, measurement_target=m.target,
            signal_to_noise=m.flux_jy/m.uncertainty_jy,
            input_sha256=provenance[m.input_path].sha256 if m.input_path in provenance else None,
            cutout_url=provenance[m.input_path].cutout_url if m.input_path in provenance else None,
            retrieved_at_utc=provenance[m.input_path].retrieved_at_utc if m.input_path in provenance else None)
            for i, m in enumerate(samples)]
        products.append(SpectralProduct(target=target, method="preliminary_aperture",
            dataset_version=version, points=points, status="usable_samples",
            warnings=["Sparse finite-aperture spectrophotometry, NOT a complete calibrated source spectrum",
                      "No aperture/PSF/colour correction; statistical errors exclude calibration systematics",
                      "Non-simultaneous samples are not combined; variability may change spectral appearance",
                      "Negative fluxes are retained; no molecular detection inferred"]
            + (["At least one sample has |S/N| < 3; these flux estimates are not detections"]
               if any(abs(m.flux_jy/m.uncertainty_jy) < 3 for m in samples) else [])))
    return products


def read_official_spectrum(asset: FitsAsset, root: Path, target: Target, *,
                           dataset_version: str, calibration_id: str,
                           rejected_bits: int, flag_policy_source: str,
                           time_scale: Literal["utc", "tt", "tdb"] | None = None,
                           table_format: Literal["fits", "votable"] = "votable") -> SpectralProduct:
    """Read explicit IRSA Spectrophotometry Tool columns (documented in sp.html).

    Requires units from the table, explicit calibration/policy provenance, and
    per-row flags, observation identity, detector and collection. No guessed
    column aliases, units, errors, wavelengths, or fills for missing samples.
    FITS table HDU is explicit. Import does not claim independent calibration QA.
    """
    if not calibration_id.strip() or not flag_policy_source.strip() or rejected_bits < 0:
        raise ValueError("Calibration and flag policy must be explicit")
    root = root.resolve(strict=True)
    path = (root / asset.path).resolve(strict=True)
    if Path(asset.path).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Spectral table must be inside data root")
    if path.stat().st_size > 10_000_000:
        raise ValueError("Spectral table exceeds 10 MB import budget")
    kwargs = {"hdu": asset.hdu} if table_format == "fits" else {}
    table = Table.read(path, format=table_format, **kwargs)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(table) > 10000:
        raise ValueError("Spectral table exceeds 10000-row budget")
    required = ["wavelength", "flux", "flux_err", "lambda_width", "mjd", "det_id",
                "data_collection", "lvf_id", "flags"]
    if any(name not in table.colnames for name in required):
        raise ValueError("Missing documented official spectrum columns")
    factors = {}
    for name, unit in [("wavelength", u.um), ("lambda_width", u.um),
                       ("flux", u.Jy), ("flux_err", u.Jy), ("mjd", u.day)]:
        if table[name].unit is None:
            raise ValueError(f"Missing unit for {name}")
        factors[name] = u.Unit(table[name].unit).to(unit)
    points = []
    for i, row in enumerate(table):
        reasons = []
        def value(name: str, positive: bool = False) -> float | None:
            raw = row[name]
            if np.ma.is_masked(raw) or not np.isfinite(raw):
                reasons.append(f"Missing/nonfinite {name}")
                return None
            number = float(raw) * factors[name]
            if positive and number <= 0:
                reasons.append(f"Nonpositive {name}")
                return None
            return number
        wavelength = value("wavelength", True)
        width = value("lambda_width", True)
        flux, error, mjd = value("flux"), value("flux_err", True), value("mjd")
        labels: dict[str, str | None] = {}
        for name in ("det_id", "data_collection", "lvf_id"):
            labels[name] = None if np.ma.is_masked(row[name]) else str(row[name])
            if not labels[name]:
                reasons.append(f"Missing {name}")
        flags = None
        raw_flags = row["flags"]
        if np.ma.is_masked(raw_flags) or not np.isfinite(raw_flags) or raw_flags < 0 or raw_flags != int(raw_flags):
            reasons.append("Invalid flags")
        else:
            flags = int(raw_flags)
            if flags & rejected_bits:
                reasons.append("Rejected quality flags")
        if labels["data_collection"] not in ("dr1", "qr3", "spherex_dr1", "spherex_qr3"):
            reasons.append("Unsupported release")
        points.append(SpectralPoint(row=i, wavelength_um=wavelength, bandwidth_um=width,
            flux_jy=flux, uncertainty_jy=error, mjd=mjd, time_scale=time_scale,
            detector=labels["det_id"], collection=labels["data_collection"],
            observation_id=labels["lvf_id"], flags=flags, accepted=not reasons, reasons=reasons,
            input_path=asset.path, source_url=asset.provenance.source,
            signal_to_noise=flux/error if flux is not None and error is not None else None,
            input_sha256=digest))
    count = sum(p.accepted for p in points)
    return SpectralProduct(target=target, method="official_forced_photometry",
        dataset_version=dataset_version, calibration_id=calibration_id, points=points,
        status="empty" if not count else "partial" if count < len(points) else "usable_samples",
        warnings=[f"Flag policy: {flag_policy_source}; rejected mask {rejected_bits}",
                  "Imported official photometry; independent calibration validation still required",
                  "Samples retain individual epochs; no coaddition or molecular detections inferred"])


def export_spectral_product(product: SpectralProduct, output: Path) -> SpectralProduct:
    """Scatter only, per-epoch annotations; reference bands explicitly not detections."""
    output.mkdir(parents=True, exist_ok=False)
    result = product.model_copy(deep=True)
    result.result_paths = ["spectrum.json", "spectrum.csv"]
    fields = list(SpectralPoint.model_fields)
    with (output / "spectrum.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for p in product.points:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                             for key, value in p.model_dump().items()})
    accepted = [p for p in product.points if p.accepted]
    if accepted:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        fig = Figure(figsize=(10, 5))
        FigureCanvasAgg(fig)
        ax = fig.add_subplot()
        for p in accepted:
            assert p.wavelength_um is not None and p.flux_jy is not None and p.uncertainty_jy is not None
            ax.errorbar(p.wavelength_um, p.flux_jy, yerr=p.uncertainty_jy,
                        xerr=p.bandwidth_um / 2 if p.bandwidth_um else None, fmt="o", capsize=2,
                        label=f"D{p.detector}, MJD {p.mjd:.5f}" if p.mjd is not None else f"D{p.detector}, epoch unknown")
        for index, (label, wavelength) in enumerate(REFERENCE_BANDS.items()):
            ax.axvline(wavelength, color="gray", linestyle=":", alpha=.7)
            ax.text(wavelength, .98 - index * .065, label, rotation=0,
                    transform=ax.get_xaxis_transform(), ha="right", va="top", fontsize=8)
        ax.set(xlim=(.7, 5.05), xlabel="Vacuum wavelength [um]", ylabel="Flux density [Jy]",
               title=f"{product.target.target_id}: {len(accepted)} spectral samples / {product.method}")
        if len(accepted) <= 12:
            ax.legend(fontsize=7, loc="best")
        fig.text(.5, .01, "Different epochs are not combined. Reference bands are NOT molecular detections.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .04, 1, 1))
        fig.savefig(output / "spectrum.png", dpi=140)
        result.result_paths.append("spectrum.png")
    with (output / "spectrum.json").open("x", encoding="utf-8") as handle:
        handle.write(result.model_dump_json(indent=2))
    return result
