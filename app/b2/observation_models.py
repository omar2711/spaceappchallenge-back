"""Additive phase-2 contracts; legacy B2 payloads remain unchanged."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .models import CatalogQuery, Contract, FitsAsset, Number, Positive, Provenance


def _collections() -> list[Literal["spherex_dr1", "spherex_qr3"]]:
    return ["spherex_dr1", "spherex_qr3"]


class Target(Contract):
    target_id: str = Field(min_length=1)
    ra_deg: Annotated[Number, Field(ge=0, lt=360)]
    dec_deg: Annotated[Number, Field(ge=-90, le=90)]
    coordinate_source: str = Field(min_length=1)


class ObservationQuery(CatalogQuery):
    radius_deg: Annotated[Positive, Field(le=0.1)]
    limit: int = Field(default=12, ge=1, le=100)
    collections: list[Literal["spherex_dr1", "spherex_qr3"]] = Field(
        default_factory=_collections, min_length=1, max_length=2)


class Observation(Contract):
    observation_id: str
    collection: str
    access_url: str
    band: str | None = None
    detector: str | None = None
    mjd_start: Number | None = None
    mjd_end: Number | None = None
    time_scale: Literal["utc", "tdb", "tt"] | None = None
    wavelength_min_m: Positive | None = None
    wavelength_max_m: Positive | None = None


class ObservationSearch(Contract):
    query: ObservationQuery
    observations: list[Observation]
    status: Literal["ok", "empty"]
    queried_at_utc: str
    possibly_truncated: bool
    warnings: list[str] = Field(default_factory=list)


class DownloadLimits(Contract):
    max_files: int = Field(default=4, ge=1, le=12)
    max_file_bytes: int = Field(default=4_000_000, ge=2880, le=20_000_000)
    max_total_bytes: int = Field(default=16_000_000, ge=2880, le=100_000_000)
    cutout_size_deg: Annotated[Positive, Field(le=0.05)] = 0.03
    max_seconds: Annotated[Positive, Field(le=300)] = 90


class CachedCutout(Contract):
    observation: Observation
    asset: FitsAsset
    cutout_url: str
    sha256: str
    size_bytes: int
    retrieved_at_utc: str
    cache_hit: bool


class ApertureConfig(Contract):
    """Radii in equivalent local pixels, applied on sky; not total-source flux."""

    radius_px: Positive = 2.5
    annulus_inner_px: Positive = 5
    annulus_outer_px: Positive = 8
    # Require explicit flag policy; SOURCE bit is not a bad-pixel flag.
    rejected_flag_bits: int = Field(ge=0, le=2**32 - 1)
    flag_policy_source: str = Field(min_length=1)
    background_rejected_flag_bits: int = Field(default=0, ge=0, le=2**32 - 1,
        description="Additional bits excluded only in background, e.g. SOURCE")

    @model_validator(mode="after")
    def radii(self) -> "ApertureConfig":
        if not self.radius_px < self.annulus_inner_px < self.annulus_outer_px:
            raise ValueError("Require aperture < inner annulus < outer annulus")
        return self


class Measurement(Contract):
    target: Target
    observation: Observation
    dataset_version: str
    input_path: str
    mjd: Number | None
    time_scale: Literal["utc", "tdb", "tt"] | None
    detector: str
    wavelength_um: Positive
    bandwidth_um: Positive
    flux_jy: Number
    uncertainty_jy: Positive
    background_mjy_sr: Number
    aperture: ApertureConfig
    response_id: str | None = Field(default=None, description="Externally verified response identity")
    status: Literal["preliminary_aperture"] = "preliminary_aperture"
    warnings: list[str]


class ProcessingIssue(Contract):
    observation_id: str | None
    stage: Literal["query", "download", "photometry"]
    message: str


class ScienceRun(Contract):
    target: Target
    search: ObservationSearch | None
    cutouts: list[CachedCutout] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    issues: list[ProcessingIssue] = Field(default_factory=list)
    status: Literal["empty", "failed", "partial", "insufficient_compatible_epochs"]
    warnings: list[str] = Field(default_factory=list)
    result_paths: list[str] = Field(default_factory=list)


class FrameSpec(Contract):
    """B2 adapter input, NOT the definitive B1 manifest. All HDUs explicit."""

    image: FitsAsset
    variance: FitsAsset | None = None
    uncertainty: FitsAsset | None = Field(default=None, description="Optional standard deviation, in image units")
    flags: FitsAsset
    detector: str = Field(min_length=1)
    response_id: str = Field(min_length=1)
    calibration_id: str = Field(min_length=1)
    psf_match_id: str = Field(min_length=1)
    background_mask: FitsAsset = Field(description="Nonzero = blank-sky pixel, independent of science")
    rejected_flag_bits: int = Field(ge=0, le=2**32 - 1)
    target: Target | None = None
    observation: Observation | None = None
    dataset_version: str | None = None
    # Optional review metadata, retained when a stricter B1Frame is serialized
    # through this base contract in difference artifacts.
    mjd: Number | None = None
    time_scale: Literal["utc", "tt", "tdb"] | None = None
    pass_id: str | None = None
    band_id: str | None = None
    declared_unit: str | None = None
    declared_wcs: dict[str, str | float | int] | None = None
    registration_evidence: str | None = None
    psf_evidence: str | None = None
    metadata_provenance: Provenance | None = None

    @model_validator(mode="after")
    def unique_noise_source(self) -> "FrameSpec":
        if self.variance is not None and self.uncertainty is not None:
            raise ValueError("Provide variance or standard deviation, not both")
        return self


class ValidatedDifference(Contract):
    science: FrameSpec
    reference: FrameSpec
    pixels: list[list[Number | None]]
    uncertainty: list[list[Number | None]] | None
    unit: str
    background_offset: Number
    background_offset_uncertainty: Number | None
    warnings: list[str]
    status: Literal["difference_only"] = "difference_only"
    result_paths: list[str] = Field(default_factory=list)


class CompatibleSamples(Contract):
    """Sorted samples sharing attested response; still preliminary aperture data."""

    groups: list[list[Measurement]]
    excluded: list[Measurement]
    warnings: list[str]
