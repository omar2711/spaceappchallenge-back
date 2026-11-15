"""Allowlisted offline packages: typed references, checksums and no network I/O."""

import hashlib
import math
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from pydantic import Field, TypeAdapter, model_validator

from .catalog_snapshot import SplicesSnapshot
from .difference_export import DifferenceArtifacts
from .models import Contract
from .phase3 import TargetResult
from .safe_paths import RelativePath, inside, relative_path
from .spectral_products import SpectralProduct
from .observation_models import ScienceRun


class IndexEntry(Contract):
    """Typed representation of the existing phase-3 index, not a new science DTO."""

    target_id: str = Field(min_length=1)
    status: str
    spectral_points: int = Field(ge=0)
    target_result_path: RelativePath
    photometry_path: RelativePath | None
    spectral_products: list[RelativePath]
    limitations: list[str]


class BundleFile(Contract):
    path: RelativePath
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0, le=20_000_000)
    role: Literal["product", "fits", "derived_fits"]
    media_type: str

    @model_validator(mode="after")
    def consistent_type(self) -> "BundleFile":
        suffix = Path(self.path).suffix.lower()
        expected = {".json": "application/json", ".csv": "text/csv", ".png": "image/png", ".fits": "application/fits"}
        if expected.get(suffix) != self.media_type or (suffix == ".fits") != (self.role in ("fits", "derived_fits")):
            raise ValueError("File extension, role and media type disagree")
        return self


class BundleManifest(Contract):
    schema_version: Literal["b2.offline.v1"] = "b2.offline.v1"
    data_kind: Literal["observation", "synthetic"] = "observation"
    fits_mode: Literal["link", "external"]
    index_path: RelativePath = "index.json"
    splices_path: RelativePath | None = None
    difference_paths: list[RelativePath] = Field(default_factory=list)
    files: list[BundleFile] = Field(max_length=512)

    @model_validator(mode="after")
    def unique_files(self) -> "BundleManifest":
        paths = [f.path.casefold() for f in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate/case-colliding bundle paths")
        if sum(f.size_bytes for f in self.files) > 100_000_000:
            raise ValueError("Offline bundle exceeds 100 MB budget")
        if any(f.role == "fits" and not f.path.startswith("data/") for f in self.files):
            raise ValueError("FITS resources must use the data/ namespace")
        return self


class IntegrityIssue(Contract):
    code: str
    path: str | None = None
    message: str


class IntegrityReport(Contract):
    valid: bool
    files_verified: int = 0
    fits_verified: int = 0
    target_count: int = 0
    issues: list[IntegrityIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(root: Path, path: str) -> Any:
    file = inside(root, path)
    if file.stat().st_size > 10_000_000:
        raise ValueError("JSON exceeds 10 MB budget")
    def reject_constant(value: str) -> None:
        raise ValueError("Nonfinite JSON numbers are not accepted")
    result = json.loads(file.read_text(encoding="utf-8"), parse_constant=reject_constant)
    def portable(value: Any) -> None:
        if isinstance(value, str) and re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|^\\\\", value):
            raise ValueError("Absolute Windows path found in metadata")
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"path", "input_path", "target_result_path", "photometry_path",
                           "index_path", "splices_path"} and isinstance(item, str):
                    relative_path(item)
                if key in {"result_paths", "spectral_products", "difference_paths"} and isinstance(item, list):
                    for name in item:
                        if isinstance(name, str):
                            relative_path(name)
                portable(item)
        if isinstance(value, list):
            for item in value:
                portable(item)
    portable(result)
    return result


def read_index(root: Path, path: str = "index.json") -> list[IndexEntry]:
    entries = TypeAdapter(list[IndexEntry]).validate_python(read_json(root, path))
    if not entries or len({e.target_id for e in entries}) != len(entries):
        raise ValueError("Index must contain unique targets")
    if len({e.target_result_path.casefold() for e in entries}) != len(entries):
        raise ValueError("Targets must not share a result file")
    return entries


def referenced_files(root: Path, entries: list[IndexEntry], *, allow_synthetic: bool = False
                      ) -> tuple[set[str], dict[str, tuple[str, int]]]:
    """Validate cross-file consistency and collect only explicitly referenced products."""
    products = {"index.json"}
    sources: dict[str, tuple[str, int]] = {}
    for entry in entries:
        r = TargetResult.model_validate(read_json(root, entry.target_result_path))
        if r.target_id != entry.target_id:
            raise ValueError("Target identity disagrees with index")
        base = Path(entry.target_result_path).parent.as_posix()
        def child(name: str) -> str:
            relative_path(name)
            return name if base == "." else f"{base}/{name}"
        products.add(entry.target_result_path)
        if r.run is None:
            if entry.photometry_path or entry.spectral_products or r.spectra:
                raise ValueError("Unavailable target references scientific products")
            continue
        if r.run.target.target_id != r.target_id or entry.status != r.run.status:
            raise ValueError("Processing identity/status disagrees with index")
        if not entry.photometry_path:
            raise ValueError("Run has no photometry metadata reference")
        persisted = ScienceRun.model_validate(read_json(root, entry.photometry_path))
        if persisted != r.run:
            raise ValueError("Photometry JSON disagrees with embedded result")
        products.add(entry.photometry_path)
        photo_base = Path(entry.photometry_path).parent.as_posix()
        for name in r.run.result_paths:
            relative_path(name)
            products.add(f"{photo_base}/{name}")
        if len(entry.spectral_products) != len(r.spectra):
            raise ValueError("Spectral references disagree with embedded products")
        if entry.spectral_points != sum(len(p.points) for p in r.spectra):
            raise ValueError("Spectral sample count disagrees with index")
        for path, spectral in zip(entry.spectral_products, r.spectra):
            if SpectralProduct.model_validate(read_json(root, path)) != spectral:
                raise ValueError("Spectral JSON disagrees with embedded product")
            if spectral.target.target_id != r.target_id or not spectral.warnings:
                raise ValueError("Spectral identity or warnings missing")
            products.add(path)
            parent = Path(path).parent.as_posix()
            for name in spectral.result_paths:
                products.add(f"{parent}/{relative_path(name)}")
        for name in ("astrometry.json", "compatibility.json", "aperture-validation.json"):
            path = child(name)
            read_json(root, path)
            products.add(path)
        cuts = {c.asset.path: c for c in r.run.cutouts}
        for c in r.run.cutouts:
            relative_path(c.asset.path)
            if not allow_synthetic and c.asset.provenance.kind != "observation":
                raise ValueError("Synthetic data cannot enter the observational package")
            if c.asset.provenance.source != c.cutout_url:
                raise ValueError("Cutout source provenance mismatch")
            if not c.observation.collection or not c.observation.observation_id or not c.retrieved_at_utc:
                raise ValueError("Incomplete observation provenance")
            if not allow_synthetic and any(urlsplit(url).scheme != "https" or
                    urlsplit(url).hostname != "irsa.ipac.caltech.edu"
                    for url in (c.cutout_url, c.observation.access_url)):
                raise ValueError("Observation must reference official IRSA source URLs")
            expected = (c.sha256, c.size_bytes)
            if c.asset.path in sources and sources[c.asset.path] != expected:
                raise ValueError("Conflicting FITS provenance")
            sources[c.asset.path] = expected
        for m in r.run.measurements:
            relative_path(m.input_path)
            if m.input_path not in cuts or m.target.target_id != r.target_id or not m.warnings:
                raise ValueError("Photometry lacks input provenance or scientific warnings")
        for spectral in r.spectra:
            for point in spectral.points:
                relative_path(point.input_path)
                if point.input_path not in cuts:
                    raise ValueError("Spectral input is absent from the acquired data")
                if point.input_sha256 != cuts[point.input_path].sha256:
                    raise ValueError("Spectral checksum provenance mismatch")
                if point.source_url != cuts[point.input_path].observation.access_url:
                    raise ValueError("Spectral URL provenance mismatch")
                if point.accepted and spectral.method == "preliminary_aperture":
                    measurement = next((m for m in r.run.measurements if m.input_path == point.input_path), None)
                    if measurement is None or any(getattr(point, key) != getattr(measurement, key) for key in
                                        ("wavelength_um", "bandwidth_um", "flux_jy", "uncertainty_jy", "mjd", "detector")):
                        raise ValueError("Preliminary spectrum disagrees with photometry")
                    if point.signal_to_noise is None or not math.isclose(point.signal_to_noise, measurement.flux_jy/measurement.uncertainty_jy, rel_tol=1e-10):
                        raise ValueError("Spectral S/N disagrees with recorded flux/error")
    for path in products:
        if Path(path).suffix.lower() not in (".json", ".csv", ".png"):
            raise ValueError("Unapproved product type")
        inside(root, path)
    return products, sources


def resource_path(root: Path, manifest: BundleManifest, file: BundleFile,
                  data_root: Path | None = None) -> Path:
    if file.role == "fits" and manifest.fits_mode == "external":
        if data_root is None:
            raise ValueError("External FITS root is required")
        return inside(data_root, file.path.removeprefix("data/"))
    return inside(root, file.path)


def validate_bundle(root: Path, *, data_root: Path | None = None,
                     allow_synthetic: bool = False) -> IntegrityReport:
    """Validate a package without contacts to NASA, CDS or any other service."""
    report = IntegrityReport(valid=False)
    try:
        manifest = BundleManifest.model_validate(read_json(root, "manifest.json"))
        if manifest.data_kind == "synthetic" and not allow_synthetic:
            raise ValueError("Synthetic package is disabled in observational mode")
        entries = read_index(root, manifest.index_path)
        products, sources = referenced_files(root, entries, allow_synthetic=allow_synthetic)
        report.target_count = len(entries)
        files = {f.path: f for f in manifest.files}
        required = products | {f"data/{path}" for path in sources}
        if manifest.splices_path:
            s = SplicesSnapshot.model_validate(read_json(root, manifest.splices_path))
            if not s.warnings or not s.endpoint.startswith("https://irsa.ipac.caltech.edu/"):
                raise ValueError("SPLICES source or warnings missing")
            center = SkyCoord(s.query.ra_deg, s.query.dec_deg, unit="deg")
            for row in s.rows:
                if row["ra"] is None or row["dec"] is None:
                    raise ValueError("Missing SPLICES coordinates")
                ra = float(row["ra"]) * u.Unit(s.columns["ra"]["unit"]).to(u.deg)
                dec = float(row["dec"]) * u.Unit(s.columns["dec"]["unit"]).to(u.deg)
                if not math.isfinite(ra) or not math.isfinite(dec) or not 0 <= ra < 360 or not -90 <= dec <= 90:
                    raise ValueError("Invalid SPLICES coordinates")
                if not isinstance(row["source_id"], str) or not row["source_id"]:
                    raise ValueError("SPLICES source ID must be preserved as a string")
                if center.separation(SkyCoord(ra, dec, unit="deg")).deg > s.query.radius_deg + 1e-6:
                    raise ValueError("SPLICES source lies outside recorded search cone")
            required.add(manifest.splices_path)
        for name in manifest.difference_paths:
            difference = DifferenceArtifacts.model_validate(read_json(root, name))
            if not allow_synthetic and (difference.input_kind != "observational_inputs" or
                    any(f.image.provenance.kind != "observation" for f in
                        (difference.result.science, difference.result.reference))):
                raise ValueError("Synthetic difference cannot enter an observational package")
            required.add(name)
            base = Path(name).parent.as_posix()
            for artifact in difference.result.result_paths:
                required.add(f"{base}/{relative_path(artifact)}")
        if set(files) != required:
            raise ValueError("Manifest does not match the allowlisted file references")
        for file in manifest.files:
            try:
                path = resource_path(root, manifest, file, data_root)
                if path.stat().st_size != file.size_bytes or digest(path) != file.sha256:
                    report.issues.append(IntegrityIssue(code="checksum_mismatch", path=file.path,
                                                        message="Size or SHA-256 mismatch"))
                    continue
                if file.path in {f"data/{name}" for name in sources}:
                    if file.role != "fits" or (file.sha256, file.size_bytes) != sources[file.path[5:]]:
                        raise ValueError("FITS manifest disagrees with acquisition provenance")
                elif file.role not in ("product", "derived_fits"):
                    raise ValueError("Invalid file role")
                if file.role == "fits":
                    with fits.open(path, memmap=False) as hdus:
                        hdus.verify("exception")
                        image = hdus["IMAGE"]
                        if image.data is None or image.data.ndim != 2 or not WCS(image.header).has_celestial:
                            raise ValueError("Invalid science image or celestial WCS")
                        u.Unit(image.header["BUNIT"]).to(u.MJy / u.sr)
                    report.fits_verified += 1
                elif file.role == "derived_fits":
                    with fits.open(path, memmap=False) as hdus:
                        hdus.verify("exception")
                        if hdus[0].data is None or hdus[0].data.ndim != 2 or "VALID" not in hdus:
                            raise ValueError("Invalid derived difference image")
                elif path.suffix == ".json":
                    read_json(root, file.path)
                report.files_verified += 1
            except (OSError, ValueError, KeyError):
                report.issues.append(IntegrityIssue(code="invalid_or_missing_file", path=file.path,
                                                    message="File missing, unsafe, or incompatible with its declared role"))
        report.valid = not report.issues
        report.warnings = ["Integrity verification does not validate a detection, calibration or light curve",
                           "Hardlinked FITS share storage with the local cache; use read-only serving"]
    except FileNotFoundError as exc:
        name = None
        if exc.filename:
            try:
                name = Path(exc.filename).relative_to(root.resolve()).as_posix()
            except ValueError:
                pass
        report.issues.append(IntegrityIssue(code="missing_file", path=name, message="Required package file is missing"))
    except (OSError, ValueError, KeyError, TypeError):
        report.issues.append(IntegrityIssue(code="invalid_package", message="Invalid JSON, references, paths, provenance or manifest"))
    return report


def export_bundle(source: Path, cache_root: Path, splices: Path, output: Path, *,
                   fits_mode: Literal["link", "external"] = "link",
                   allow_synthetic: bool = False,
                   differences: list[Path] | None = None) -> BundleManifest:
    """Collect only referenced files. Hardlink, never silently copy the FITS cache.

    On filesystems without hardlinks choose external mode and supply data_root
    explicitly during validation/service setup. The original artifacts are not edited.
    """
    entries = read_index(source)
    if fits_mode not in ("link", "external"):
        raise ValueError("Unsupported FITS packaging mode")
    products, sources = referenced_files(source, entries, allow_synthetic=allow_synthetic)
    SplicesSnapshot.model_validate(read_json(splices.parent, splices.name))
    prepared_differences = []
    for directory in differences or []:
        d = DifferenceArtifacts.model_validate(read_json(directory, "difference.json"))
        if not allow_synthetic and (d.input_kind != "observational_inputs" or
                any(frame.image.provenance.kind != "observation" for frame in (d.result.science, d.result.reference))):
            raise ValueError("Synthetic difference is not an observational result")
        for name in d.result.result_paths:
            if Path(name).suffix.lower() not in (".json", ".png", ".fits"):
                raise ValueError("Unapproved difference artifact")
            inside(directory, name)
        prepared_differences.append((directory, d))
    if output.exists():
        raise FileExistsError("Choose a fresh output directory")
    # Verify every source before writing a concrete package.
    for name, (sha, size) in sources.items():
        path = inside(cache_root, name)
        if path.stat().st_size != size or digest(path) != sha:
            raise ValueError("Source FITS checksum mismatch")
    output.mkdir(parents=True)
    files = []
    media = {".json": "application/json", ".csv": "text/csv", ".png": "image/png"}
    for name in sorted(products):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inside(source, name), destination)
        files.append(BundleFile(path=name, sha256=digest(destination), size_bytes=destination.stat().st_size,
                                role="product", media_type=media[destination.suffix]))
    catalog = output / "catalog/splices.json"
    catalog.parent.mkdir()
    shutil.copyfile(inside(splices.parent, splices.name), catalog)
    files.append(BundleFile(path="catalog/splices.json", sha256=digest(catalog), size_bytes=catalog.stat().st_size,
                            role="product", media_type="application/json"))
    for name, (sha, size) in sorted(sources.items()):
        path = inside(cache_root, name)
        if fits_mode == "link":
            destination = output / "data" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, destination)
        files.append(BundleFile(path=f"data/{name}", sha256=sha, size_bytes=size,
                                role="fits", media_type="application/fits"))
    difference_paths = []
    for index, (directory, difference) in enumerate(prepared_differences):
        base = f"differences/{index}"
        difference_paths.append(f"{base}/difference.json")
        for name in set(difference.result.result_paths) | {"difference.json"}:
            destination = output / base / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inside(directory, name), destination)
            files.append(BundleFile(path=f"{base}/{name}", sha256=digest(destination),
                size_bytes=destination.stat().st_size, role="derived_fits" if destination.suffix == ".fits" else "product",
                media_type="application/fits" if destination.suffix == ".fits" else media[destination.suffix]))
    manifest = BundleManifest(fits_mode=fits_mode, files=files, splices_path="catalog/splices.json",
        difference_paths=difference_paths, data_kind="synthetic" if allow_synthetic else "observation")
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        handle.write(manifest.model_dump_json(indent=2))
    validation = validate_bundle(output, data_root=cache_root, allow_synthetic=allow_synthetic)
    if not validation.valid:
        raise ValueError("Exported package failed validation; no source file was modified")
    return manifest
