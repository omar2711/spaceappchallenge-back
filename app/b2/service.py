"""B3's offline read interface: reuse scientific contracts, never invoke network adapters."""

from pathlib import Path
import math
from typing import Literal

from .catalog_snapshot import SplicesSnapshot
from .difference_export import DifferenceArtifacts
from .models import Contract
from .observation_models import Measurement, Observation, Target
from .offline_bundle import (BundleFile, BundleManifest, IntegrityReport, digest, read_index,
    read_json, resource_path, validate_bundle)
from .phase3 import TargetResult, export_target, reprocess_target
from .spectral_products import SpectralProduct


class ScienceServiceError(ValueError):
    """B3 maps code to HTTP itself; errors contain no configured absolute root."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class FeatureState(Contract):
    availability: Literal["available", "preliminary", "incomplete", "unavailable", "blocked"]
    reason: str


class TargetStatus(Contract):
    target_id: str
    processing_status: str
    observation_metadata: FeatureState
    photometry: FeatureState
    spectra: FeatureState
    light_curve: FeatureState
    differences: FeatureState
    warnings: list[str]


class ReproductionReport(Contract):
    success: bool
    targets_reprocessed: int
    measurements_compared: int
    mismatched_targets: list[str]


class DemoSummary(Contract):
    success: bool
    integrity: IntegrityReport
    targets: list[TargetStatus]
    catalog_rows: int
    catalog: FeatureState
    observations: dict[str, list[Observation]]
    photometry: dict[str, list[Measurement]]
    spectra: dict[str, list[SpectralProduct]]
    splices: SplicesSnapshot | None
    differences: dict[str, list[DifferenceArtifacts]]
    products: list[BundleFile]
    warnings: list[str]
    reproduction: ReproductionReport | None = None


class ScienceService:
    """Read-only, manifest-allowlisted facade. Construct from server configuration.

    The constructor performs full integrity verification by default. Return values
    are newly parsed Pydantic objects; callers cannot mutate the internal inventory.
    A checksum proves integrity, not a source detection or calibrated light curve.
    """

    def __init__(self, package_root: Path, *, data_root: Path | None = None,
                 allow_synthetic: bool = False):
        self.root = package_root.resolve()
        self.data_root = data_root
        self.integrity = validate_bundle(self.root, data_root=data_root, allow_synthetic=allow_synthetic)
        if not self.integrity.valid:
            raise ScienceServiceError("invalid_package", "Offline package failed integrity verification")
        self.manifest = BundleManifest.model_validate(read_json(self.root, "manifest.json"))
        self.entries = {e.target_id: e for e in read_index(self.root, self.manifest.index_path)}

    def resolve_product(self, path: str) -> Path:
        """Resolve only an inventory entry; recheck integrity before handing it to B3."""
        file = next((f for f in self.manifest.files if f.path == path), None)
        if file is None:
            raise ScienceServiceError("unknown_product", "Product is not in the package inventory")
        try:
            result = resource_path(self.root, self.manifest, file, self.data_root)
            if result.stat().st_size != file.size_bytes or digest(result) != file.sha256:
                raise ScienceServiceError("checksum_mismatch", "Product changed after package validation")
            return result
        except OSError:
            raise ScienceServiceError("missing_product", "Product is missing") from None
        except ScienceServiceError:
            raise
        except ValueError:
            raise ScienceServiceError("unsafe_product", "Product no longer resolves within its configured root") from None

    def get_result(self, target_id: str) -> TargetResult:
        """Return the existing TargetResult, including provenance, exclusions and warnings."""
        if target_id not in self.entries:
            raise ScienceServiceError("unknown_target", "Unknown target identifier")
        path = self.entries[target_id].target_result_path
        self.resolve_product(path)
        return TargetResult.model_validate(read_json(self.root, path))

    def list_targets(self) -> list[Target]:
        results = [self.get_result(name) for name in self.entries]
        targets = []
        for result in results:
            if result.run:
                targets.append(result.run.target)
            elif result.astrometry:
                targets.append(result.astrometry.reference)
        return targets

    def get_observations(self, target_id: str) -> list[Observation]:
        r = self.get_result(target_id)
        return r.run.search.observations if r.run and r.run.search else []

    def get_photometry(self, target_id: str) -> list[Measurement]:
        r = self.get_result(target_id)
        return r.run.measurements if r.run else []

    def get_spectra(self, target_id: str) -> list[SpectralProduct]:
        """May contain sparse preliminary samples; availability must be read alongside."""
        return self.get_result(target_id).spectra

    def get_splices(self) -> SplicesSnapshot | None:
        path = self.manifest.splices_path
        if path is None:
            return None
        self.resolve_product(path)
        return SplicesSnapshot.model_validate(read_json(self.root, path))

    def get_differences(self, target_id: str) -> list[DifferenceArtifacts]:
        self.get_result(target_id)  # validate the identifier even for an empty list
        results = []
        for path in self.manifest.difference_paths:
            self.resolve_product(path)
            d = DifferenceArtifacts.model_validate(read_json(self.root, path))
            if d.result.science.target and d.result.science.target.target_id == target_id:
                results.append(d)
        return results

    def list_products(self, target_id: str | None = None) -> list[BundleFile]:
        if target_id is None:
            return [p.model_copy(deep=True) for p in self.manifest.files]
        result = self.get_result(target_id)
        entry = self.entries[target_id]
        prefix = Path(entry.target_result_path).parent.as_posix() + "/"
        inputs = {f"data/{c.asset.path}" for c in result.run.cutouts} if result.run else set()
        return [p.model_copy(deep=True) for p in self.manifest.files if p.path.startswith(prefix) or p.path in inputs]

    def get_status(self, target_id: str) -> TargetStatus:
        r = self.get_result(target_id)
        points = sum(p.accepted for s in r.spectra for p in s.points)
        official = any(s.method == "official_forced_photometry" for s in r.spectra)
        differences = self.get_differences(target_id)
        notes = list(r.limitations) + (list(r.run.warnings) if r.run else [])
        if r.run:
            notes.extend(i.message for i in r.run.issues)
            notes.extend(f"{target_id}: preliminary aperture S/N={m.flux_jy/m.uncertainty_jy:.2f}; no detection asserted"
                         for m in r.run.measurements)
        for s in r.spectra:
            notes.extend(s.warnings)
        notes.append("Scientific availability does not establish a source or molecular detection")
        return TargetStatus(target_id=target_id, processing_status=r.run.status if r.run else "failed",
            observation_metadata=FeatureState(availability="available" if self.get_observations(target_id) else "unavailable",
                                              reason="Cached observation metadata; limited query, not complete coverage"),
            photometry=FeatureState(availability="preliminary" if self.get_photometry(target_id) else "unavailable",
                                    reason="Finite-aperture estimates remain unvalidated" if self.get_photometry(target_id)
                                    else "No accepted photometry under the recorded quality/background recipe"),
            spectra=FeatureState(availability="available" if official and points >= 2 else "incomplete" if points else "unavailable",
                reason="Read method, flags, calibration and epoch metadata; sparse aperture samples are not a complete spectrum"),
            light_curve=FeatureState(availability="unavailable", reason="No validated temporal curve registered; response/aperture calibration pending"),
            differences=FeatureState(availability="available" if differences else "blocked",
                reason="Inspect temporal_comparison_verified and B1 evidence" if differences else "B1 has not supplied a registered compatible real pair"),
            warnings=list(dict.fromkeys(notes)))

    def summary(self) -> DemoSummary:
        catalog = self.get_splices()
        return DemoSummary(success=True, integrity=self.integrity.model_copy(deep=True),
            targets=[self.get_status(name) for name in self.entries],
            catalog_rows=len(catalog.rows) if catalog else 0,
            catalog=FeatureState(availability="available" if catalog is not None else "unavailable",
                                 reason="Recorded SPLICES candidates, never confirmed molecular detections"),
            observations={name: self.get_observations(name) for name in self.entries},
            photometry={name: self.get_photometry(name) for name in self.entries},
            spectra={name: self.get_spectra(name) for name in self.entries}, splices=catalog,
            differences={name: self.get_differences(name) for name in self.entries},
            products=self.list_products(),
            warnings=["Successful offline integration is not completion of the pending scientific analyses",
                      "Photometry is preliminary; inspect per-sample S/N and warnings; no detections are asserted",
                      "No fabricated curves or temporal differences"])

    def reproduce(self, output: Path) -> ReproductionReport:
        """Recompute cached targets into a NEW directory and compare scientific values."""
        output.mkdir(parents=True, exist_ok=False)
        data_root = self.data_root if self.manifest.fits_mode == "external" else self.root / "data"
        if data_root is None:
            raise ScienceServiceError("missing_data_root", "Reproduction requires the FITS root")
        compared = 0
        processed = 0
        mismatches = []
        for index, name in enumerate(self.entries):
            original = self.get_result(name)
            if original.run is None or original.astrometry is None:
                continue
            new = reprocess_target(original.run, original.astrometry, data_root, original.processing_aperture)
            export_target(original.astrometry, new, data_root, output / f"target-{index}", original.processing_aperture)
            processed += 1
            before = {(m.input_path, m.mjd, m.detector): m for m in original.run.measurements}
            after = {(m.input_path, m.mjd, m.detector): m for m in new.measurements}
            matched = before.keys() == after.keys()
            for key in before.keys() & after.keys():
                a, b = before[key], after[key]
                matched &= all(math.isclose(getattr(a, field), getattr(b, field), rel_tol=1e-10, abs_tol=1e-15)
                               for field in ("flux_jy", "uncertainty_jy", "wavelength_um", "bandwidth_um"))
                compared += 1
            if not matched:
                mismatches.append(name)
        return ReproductionReport(success=not mismatches, targets_reprocessed=processed,
                                  measurements_compared=compared, mismatched_targets=mismatches)
